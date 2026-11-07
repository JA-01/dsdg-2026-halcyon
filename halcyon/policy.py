"""Ordering policy. Owner: see docs/adr/0001-architecture.md.

Contract: plan(data, cutoff, weeks, forecasts) ->
DataFrame[week, material, order_units, share_KES..share_AUR], one row per
(week, material). `forecasts` has columns week, material, disruption_prob,
price_forecast for the same weeks. Shares sum to 1 and are 0 for countries
that do not sell the material. `data` is `halcyon.data.as_of(..., cutoff)`.

Per material, an LP over the window mirrors the simulator's economics with
estimates known at the cutoff: each supplier's capacity and lead time (its
current state if it looks hit now, otherwise normal) and its recent landed
cost. A safety stock of 1.75 weeks' demand (optionally more as the forecast
disruption probability rises), capped at the demand the window still needs so
it is used up rather than salvaged, hedges against capacity cuts and delays.
A convex sourcing cost spreads orders across suppliers whose costs are close. Rows with no order get even shares,
which lifts diversification at no cost. A final score-aware rebalance (_rebalance) shifts share
toward cheap-enough peers and merges small rows into earlier weeks when the diversification
points beat the F points lost, at the score's own exchange rate.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from halcyon.data import COUNTRIES, MATERIALS

HOLDING, SHORTAGE, SALVAGE, OPENING_WEEKS = 0.02, 5.0, 0.7, 5
HIT_CAPACITY = 0.37  # mean capacity ratio of a hit supplier, weeks 1-208


@dataclass(frozen=True)
class Params:
    cap_margin: float = 0.90      # plan on this fraction of estimated capacity
    buffer_weeks: float = 0.0     # extra safety stock (weeks of demand) at disruption_prob = 1
    base_buffer: float = 1.75     # safety stock (weeks of demand) always held
    buffer_penalty: float = 1.0   # cost per unit below the safety stock, x reference cost
    recent: int = 4               # weeks of history for landed cost and current state
    taper: float = 1.0            # cap safety stock at this fraction of remaining window demand (0: off)
    diversity: float = 0.04       # convex sourcing cost slope, x reference cost (see _solve)
    tariffs: bool = True          # apply tariff changes announced by the cutoff to landed costs
    # Scenario knob: {country: (from_week, multiplier)} scales that country's planned
    # capacity from `from_week` on (e.g. {"KES": (224, 0.37)}). Empty: no change.
    country_capacity: dict = field(default_factory=dict)
    # Risk-aware sourcing: risk_fn(data, cutoff, weeks) -> [week, material, country, risk].
    # risk_capacity cuts planned capacity by risk x (1 - 0.37); risk_cost adds risk x ref.
    risk_fn: object = None        # default: halcyon.disruption_news.supplier_risk
    risk_capacity: float = 0.0
    risk_cost: float = 0.0         # 0.5 tested: see PR; off by default
    # Export-ban signature (#114): a supplier whose futures basis (futures_4w / spot - 1)
    # is > 5%, or > 3.5% two weeks running, at the cutoff is planned at
    # basis_capacity x normal for basis_weeks from basis_lead weeks after its first flag.
    basis_haircut: bool = True
    basis_lead: int = 2           # earliest observed lag (1 of 6 onsets came 2 weeks after
                                  # the first flag; median 3): banning a week early costs ~0.15
    basis_weeks: int = 8
    basis_capacity: float = 0.05
    # Score-aware rebalance (_rebalance): trade cost for diversification at the
    # score's own exchange rate, then merge rows into earlier weeks when it pays.
    rebalance: bool = True
    merge_back: int = 3


def _estimates(data, cutoff, material, params):
    """Per-supplier capacity, lead time and landed cost as seen at the cutoff."""
    sellers = data["suppliers"].loc[data["suppliers"].material == material].set_index("country")
    hist = data["supply_history"]
    hist = hist.loc[(hist.material == material) & (hist.week > cutoff - params.recent)]
    last = hist.sort_values("week").groupby("country").last().reindex(sellers.index)
    normal = sellers.normal_capacity_units.to_numpy(float)
    base_lead = sellers.base_lead_weeks.to_numpy(float)
    cap_now, lead_now = last.capacity_units.to_numpy(float), last.lead_time_weeks.to_numpy(float)
    # A supplier's current state persists into the window only if it looks hit now.
    hit = (cap_now < 0.9 * normal) | (lead_now > base_lead)
    cap = np.where(hit, cap_now, 0.98 * normal) * params.cap_margin
    lead = np.where(hit, lead_now, base_lead).astype(int)
    landed = hist.groupby("country").landed_cost.mean().reindex(sellers.index).to_numpy(float)
    return list(sellers.index), cap, lead, landed


def _announced(data, cutoff, material, countries, weeks, landed):
    """T x C landed costs with tariff changes announced by the cutoff applied from
    their effective week (landed cost = spot x (1 + tariff) + shipping). All five
    announcements in weeks 1-208 took effect as announced."""
    out = np.tile(landed, (len(weeks), 1))
    now = data["tariffs"].merge(data["prices"], on=["week", "material", "country"])
    now = now.loc[(now.week == cutoff) & (now.material == material) & now.announced_rate.notna()]
    for row in now.itertuples():
        if row.country in countries:
            start = np.searchsorted(weeks, row.announced_effective_week)
            out[start:, countries.index(row.country)] += row.spot_price * (row.announced_rate - row.tariff_rate)
    return out


def _basis_bans(data, cutoff, params):
    """{material: {country: expected onset week}} for suppliers flagged by a futures
    basis spike at the cutoff and not already hit (prices and supply up to cutoff)."""
    prices = data["prices"].loc[data["prices"].week <= cutoff].copy()
    prices["basis"] = prices.futures_4w / prices.spot_price - 1
    basis = prices.pivot_table(index="week", columns=["material", "country"], values="basis")
    from halcyon.disruption_news import BASIS_HIGH, BASIS_TWO_WEEK  # shared thresholds
    high, mid = basis > BASIS_HIGH, basis > BASIS_TWO_WEEK
    flag = high | (mid & mid.shift(fill_value=False))
    state = data["supply_history"].loc[data["supply_history"].week == cutoff].merge(
        data["suppliers"][["material", "country", "normal_capacity_units", "base_lead_weeks"]])
    hit = {(r.material, r.country) for r in state.itertuples()
           if r.capacity_units < 0.9 * r.normal_capacity_units or r.lead_time_weeks > r.base_lead_weeks}
    out = {}
    if cutoff not in flag.index:
        return out
    for key in flag.columns[flag.loc[cutoff].to_numpy()]:
        if key in hit:
            continue
        run = flag[key].loc[:cutoff][::-1]
        first = cutoff - (int(run.cumprod().sum()) - 1)  # start of the current flagged run
        out.setdefault(key[0], {})[key[1]] = max(first + params.basis_lead, cutoff + 1)
    return out


def _solve(demand, opening, cap, lead, landed, ref, buffer, penalty, diversity=0.0, tiers=12):
    """LP over requests r[t, c] (planned fills); returns the T x C matrix.

    With `diversity` > 0, each supplier's weekly request is split into chunks of
    mean demand / `tiers`; each further chunk costs `diversity / 4` x the
    reference cost more. That convex sourcing cost favors a second supplier
    whenever its landed cost is close to the cheapest one's.
    """
    T, C = len(demand), cap.shape[-1]
    cap = np.broadcast_to(cap, (T, C))
    chunk = max(demand.mean() / tiers, 1e-9) if diversity else np.inf
    owner, size, extra = [], [], []  # one LP column per (t, c, tier)
    for t in range(T):
        for c in range(C):
            left, k = cap[t, c], 0
            while left > 1e-9:
                owner.append((t, c)); size.append(min(chunk, left)); extra.append(diversity * ref * k / 4)
                left -= chunk; k += 1
    nr = len(owner)  # then served s[t], stock I[t], safety shortfall u[t]
    n = nr + 3 * T
    landed = np.broadcast_to(landed, (T, C))
    cost = np.concatenate([[landed[t, c] for t, c in owner] + np.array(extra), np.full(T, -SHORTAGE * ref),
                           np.full(T, HOLDING * ref), np.full(T, penalty * ref)])
    A_eq, b_eq = np.zeros((T, n)), np.zeros(T)
    for j, (t, c) in enumerate(owner):
        if t + lead[c] < T:
            A_eq[t + lead[c], j] = -1
        else:
            cost[j] -= SALVAGE * ref  # arrives after the window: salvaged
    for t in range(T):
        A_eq[t, nr + t] = A_eq[t, nr + T + t] = 1
        if t:
            A_eq[t, nr + T + t - 1] = -1
    b_eq[0] = opening
    cost[nr + 2 * T - 1] -= SALVAGE * ref
    A_ub = np.zeros((T, n))  # -I[t] - u[t] <= -buffer[t]
    A_ub[np.arange(T), nr + T + np.arange(T)] = -1
    A_ub[np.arange(T), nr + 2 * T + np.arange(T)] = -1
    bounds = [(0, u) for u in size] + [(0, d) for d in demand] + [(0, None)] * (2 * T)
    res = linprog(cost, A_ub=A_ub, b_ub=-buffer, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(res.message)
    r = np.zeros((T, C))
    np.add.at(r, tuple(np.array(owner).T), res.x[:nr])
    return r


def plan(data, cutoff, weeks, forecasts, params=Params()):
    weeks = list(weeks)
    demand_all = data["demand"].set_index(["week", "material"]).demand_units
    probs = forecasts.set_index(["week", "material"]).disruption_prob
    risk = None
    if params.risk_capacity or params.risk_cost:
        if params.risk_fn is None:
            from halcyon.disruption_news import supplier_risk as risk_fn
        else:
            risk_fn = params.risk_fn
        frame = risk_fn(data, cutoff, weeks)
        risk = dict(zip(zip(frame.week, frame.material, frame.country), frame.risk.astype(float)))
    bans = _basis_bans(data, cutoff, params) if params.basis_haircut else {}
    cost_weight = 40 / _f_denominator(data, cutoff) if params.rebalance else 0.0
    rows = []
    for m in MATERIALS:
        countries, cap, lead, landed = _estimates(data, cutoff, m, params)
        demand = np.array([demand_all[(w, m)] for w in weeks], float)
        p = np.array([probs[(w, m)] for w in weeks], float)
        buffer = (params.base_buffer + params.buffer_weeks * p) * np.append(demand[1:], 0.0)
        if params.taper:  # never hold more safety stock than the window still needs
            remaining = np.append(np.cumsum(demand[::-1])[::-1][1:], 0.0)
            buffer = np.minimum(buffer, params.taper * remaining)
        # Opening stock is 5x week-1 demand (Phase 2 calibration vs official scores).
        opening = OPENING_WEEKS * demand[0]
        if params.tariffs:  # announced tariff changes raise or lower future landed costs
            landed_t = _announced(data, cutoff, m, countries, weeks, landed)
        else:
            landed_t = landed
        cap = np.tile(cap, (len(weeks), 1))
        for country, onset in bans.get(m, {}).items():
            span = (np.asarray(weeks) >= onset) & (np.asarray(weeks) < onset + params.basis_weeks)
            cap[span, countries.index(country)] *= params.basis_capacity / 0.98
        for country, (from_week, multiplier) in params.country_capacity.items():
            if country in countries:
                cap[np.asarray(weeks) >= from_week, countries.index(country)] *= multiplier
        if risk is not None:
            rk = np.array([[risk.get((w, m, c), 0.0) for c in countries] for w in weeks])
            cap = cap * (1 - params.risk_capacity * rk * (1 - HIT_CAPACITY))
            landed_t = np.broadcast_to(landed_t, rk.shape) + params.risk_cost * rk * landed.mean()
        r = _solve(demand, opening, cap, lead, landed_t, landed.mean(),
                   buffer, params.buffer_penalty, params.diversity)
        if params.rebalance:
            r = _rebalance(r, cap, lead, np.broadcast_to(landed_t, cap.shape), landed.mean(),
                           cost_weight, params.merge_back)
        for t, w in enumerate(weeks):
            units = float(r[t].sum())
            ordered = units > 1e-6
            split = r[t] / units if ordered else np.full(len(countries), 1 / len(countries))
            shares = {f"share_{c}": 0.0 for c in COUNTRIES}
            shares.update({f"share_{c}": float(s) for c, s in zip(countries, split)})
            rows.append({"week": w, "material": m, "order_units": units if ordered else 0.0, **shares})
    return pd.DataFrame(rows)


# Score points per unit of one row's diversification: 0.30 (R) x 0.30 (div share)
# x 100, averaged over the 130 rows of a window.
DIVERSIFICATION_POINTS = 9 / 130


def _f_denominator(data, cutoff):
    """Smallest naive-minus-hindsight cost over past 13-week windows ending at
    cutoff, cutoff-13, ... (windows starting at week 7 or later). F points per
    unit of cost are 40 / this; the minimum keeps the cost weight conservative."""
    from halcyon import score

    gaps = []
    for end in range(cutoff, 18, -13):
        start, weeks = end - 12, list(range(end - 12, end + 1))
        naive_cost = score.simulate(score.naive(data, start - 1, weeks), data, start, end).cost.sum()
        gaps.append(naive_cost - score.hindsight(data, start, end)[0])
    return float(min(gaps))


def _diversification(units):
    total = units.sum()
    if total <= 1e-6:
        return 1.0
    n = len(units)
    return (1 - ((units / total) ** 2).sum()) / (1 - 1 / n)


def _waterfill(b, a, lo, hi):
    """argmin a*sum(s^2) + b.s  s.t.  sum(s) = 1, lo <= s <= hi (bisection on the multiplier)."""
    left, right = b.min() - 4 * a - 1, b.max() + 4 * a + 1
    for _ in range(100):
        nu = (left + right) / 2
        if np.clip((nu - b) / (2 * a), lo, hi).sum() > 1:
            right = nu
        else:
            left = nu
    return np.clip((left - b) / (2 * a), lo, hi)


def _rebalance(r, cap, lead, landed, ref, cost_weight, merge_back):
    """Post-process LP units r[t, c] (exploration, AV, Nov 7; 11 origins +0.49, 11/11).

    1. Water-fill: on each ordering row, move share from the main supplier to the
       others to maximize DIVERSIFICATION_POINTS * div - cost_weight * cost,
       keeping row units, planned capacity, and never adding share to a slower
       supplier or to one whose planned capacity is cut below half in the window.
    2. Merge: from the last week back, move a whole row into one of the previous
       merge_back weeks when capacity there allows and the diversification gain
       (the emptied row gets even shares) beats extra holding and price change.
    """
    r = r.copy()
    T, n = r.shape
    a = DIVERSIFICATION_POINTS * n / (n - 1)
    cut = cap.min(axis=0) < 0.5 * cap.max(axis=0)
    for t in range(T):
        units = r[t].sum()
        if units <= 1e-6:
            continue
        s0 = r[t] / units
        main = int(np.argmax(s0))
        hi = np.maximum(np.minimum(cap[t] / units, 1), s0)
        hi[main] = s0[main]
        hi = np.where((lead > lead[main]) | cut, s0, hi)
        lo = s0.copy()
        lo[main] = 0.0
        s = _waterfill(cost_weight * units * landed[t], a, lo, hi)
        if s[main] < s0[main] - 1e-9:
            r[t] = units * s
    for t in range(T - 1, 0, -1):
        if r[t].sum() <= 1e-6:
            continue
        best = None
        for k in range(1, min(merge_back, t) + 1):
            p = t - k
            merged = r[p] + r[t]
            if np.any(merged > np.maximum(cap[p], r[p]) + 1e-6):
                continue
            gain = DIVERSIFICATION_POINTS * (
                (1 - _diversification(r[t])) + _diversification(merged) - _diversification(r[p]))
            cost = cost_weight * (HOLDING * ref * r[t].sum() * k + r[t] @ (landed[p] - landed[t]))
            if gain > cost and (best is None or gain - cost > best[0]):
                best = (gain - cost, p)
        if best:
            r[best[1]] += r[t]
            r[t] = 0.0
    return r
