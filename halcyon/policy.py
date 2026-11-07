"""Ordering policy. Owner: see docs/adr/0001-architecture.md.

Contract: plan(data, cutoff, weeks, forecasts) ->
DataFrame[week, material, order_units, share_KES..share_AUR], one row per
(week, material). `forecasts` has columns week, material, disruption_prob,
price_forecast for the same weeks. Shares sum to 1 and are 0 for countries
that do not sell the material. `data` is `halcyon.data.as_of(..., cutoff)`.

Per material, an LP over the window mirrors the simulator's economics with
estimates known at the cutoff: each supplier's capacity and lead time (its
current state if it looks hit now, otherwise normal) and its recent landed
cost. A safety stock of 1.75 weeks' demand (plus more as the forecast
disruption probability rises), capped at the demand the window still needs so
it is used up rather than salvaged, hedges against capacity cuts and delays.
A convex sourcing cost spreads orders across suppliers whose costs are close. Rows with no order get even shares,
which lifts diversification at no cost.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from halcyon.data import COUNTRIES, MATERIALS

HOLDING, SHORTAGE, SALVAGE, OPENING_WEEKS = 0.02, 5.0, 0.7, 5


@dataclass(frozen=True)
class Params:
    cap_margin: float = 0.90      # plan on this fraction of estimated capacity
    buffer_weeks: float = 1.0     # extra safety stock (weeks of demand) at disruption_prob = 1
    base_buffer: float = 1.75     # safety stock (weeks of demand) always held
    buffer_penalty: float = 1.0   # cost per unit below the safety stock, x reference cost
    recent: int = 4               # weeks of history for landed cost and current state
    taper: float = 1.0            # cap safety stock at this fraction of remaining window demand (0: off)
    diversity: float = 0.04       # convex sourcing cost slope, x reference cost (see _solve)


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


def _solve(demand, opening, cap, lead, landed, ref, buffer, penalty, diversity=0.0, tiers=12):
    """LP over requests r[t, c] (planned fills); returns the T x C matrix.

    With `diversity` > 0, each supplier's weekly request is split into chunks of
    mean demand / `tiers`; each further chunk costs `diversity / 4` x the
    reference cost more. That convex sourcing cost favors a second supplier
    whenever its landed cost is close to the cheapest one's.
    """
    T, C = len(demand), len(cap)
    chunk = max(demand.mean() / tiers, 1e-9) if diversity else np.inf
    owner, size, extra = [], [], []  # one LP column per (t, c, tier)
    for t in range(T):
        for c in range(C):
            left, k = cap[c], 0
            while left > 1e-9:
                owner.append((t, c)); size.append(min(chunk, left)); extra.append(diversity * ref * k / 4)
                left -= chunk; k += 1
    nr = len(owner)  # then served s[t], stock I[t], safety shortfall u[t]
    n = nr + 3 * T
    cost = np.concatenate([[landed[c] for _, c in owner] + np.array(extra), np.full(T, -SHORTAGE * ref),
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
    rows = []
    for m in MATERIALS:
        countries, cap, lead, landed = _estimates(data, cutoff, m, params)
        demand = np.array([demand_all[(w, m)] for w in weeks], float)
        p = np.array([probs[(w, m)] for w in weeks], float)
        buffer = (params.base_buffer + params.buffer_weeks * p) * np.append(demand[1:], 0.0)
        if params.taper:  # never hold more safety stock than the window still needs
            remaining = np.append(np.cumsum(demand[::-1])[::-1][1:], 0.0)
            buffer = np.minimum(buffer, params.taper * remaining)
        r = _solve(demand, OPENING_WEEKS * demand[0], cap, lead, landed, landed.mean(),
                   buffer, params.buffer_penalty, params.diversity)
        for t, w in enumerate(weeks):
            units = float(r[t].sum())
            ordered = units > 1e-6
            split = r[t] / units if ordered else np.full(len(countries), 1 / len(countries))
            shares = {f"share_{c}": 0.0 for c in COUNTRIES}
            shares.update({f"share_{c}": float(s) for c, s in zip(countries, split)})
            rows.append({"week": w, "material": m, "order_units": units if ordered else 0.0, **shares})
    return pd.DataFrame(rows)
