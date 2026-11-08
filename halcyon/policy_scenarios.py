"""Scenario-coupled open-loop ordering policy (challenger, issue #129 experiment 1).

Same contract as policy.plan. The incumbent plans one nominal supply path plus
a fixed safety stock. Here, history up to the cutoff supplies a library of
physical shock events (supplier episodes with capacity < 0.9x normal or lead
time > base, grouped by start week). Each event is replayed at several onset
weeks inside the window and weighted by the cutoff-only event rate. A two-stage
LP then chooses one executable set of requests that minimizes expected cost
over the nominal path and all scenarios:

- every scenario fills exactly min(request, capacity), as the simulator does:
  equality wherever its capacity covers the planned request bound, and an exact
  min (one binary per capped cell, MILP) elsewhere, so the optimizer can never
  refuse units it requested; the excess above capacity is cancelled unpaid;
- arrivals use the scenario's lead times;
- holding, shortage (5x) and salvage (70%, in stock and in transit) are costed
  per scenario.

The nominal path, convex sourcing tiers, announced tariffs, basis bans, the
taper and the score-aware rebalance are the incumbent's (halcyon.policy).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

from halcyon import policy as incumbent
from halcyon.data import COUNTRIES, MATERIALS

HOLDING, SHORTAGE, SALVAGE, OPENING_WEEKS = (incumbent.HOLDING, incumbent.SHORTAGE,
                                             incumbent.SALVAGE, incumbent.OPENING_WEEKS)


@dataclass(frozen=True)
class Params:
    base: incumbent.Params = field(default_factory=incumbent.Params)
    onsets: tuple = (0, 3, 6, 9)      # onset weeks (relative to window start) per replayed event
    generalize_single: bool = True    # a single-supplier event may recur at any material of that country
    weight_scale: float = 1.0         # multiplies the cutoff-only event rate
    buffer: float = None              # safety stock weeks (None: incumbent's base_buffer)
    rebalance: bool = True            # incumbent's post-hoc water-fill / row merge
    exact_min: bool = True            # enforce fill = min(request, capacity) in capped scenarios (MILP)


def events(data, cutoff):
    """Completed physical shock events with start <= cutoff, from supply_history only.

    Returns (events, weeks_observed). Each event is a dict with `start` and
    `hits` = {(material, country): (ratios, extras)}, the week-by-week capacity
    ratio and extra lead time of every supplier episode starting that week.
    Episodes still running at the cutoff are left to the nominal (persistence) path.
    """
    sh = data["supply_history"].loc[data["supply_history"].week <= cutoff].merge(
        data["suppliers"][["material", "country", "normal_capacity_units", "base_lead_weeks"]])
    sh = sh.sort_values(["material", "country", "week"])
    ratio = (sh.capacity_units / sh.normal_capacity_units).to_numpy()
    extra = (sh.lead_time_weeks - sh.base_lead_weeks).to_numpy()
    hit = (ratio < 0.9) | (extra > 0)
    by_start = {}
    keys = list(zip(sh.material, sh.country))
    weeks = sh.week.to_numpy()
    i, n = 0, len(sh)
    while i < n:
        if not hit[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and hit[j + 1] and keys[j + 1] == keys[i] and weeks[j + 1] == weeks[j] + 1:
            j += 1
        complete = weeks[j] < cutoff  # the episode ended at or before the cutoff
        if complete and weeks[i] > 1:
            ev = by_start.setdefault(int(weeks[i]), {})
            ev[keys[i]] = (ratio[i:j + 1].copy(), extra[i:j + 1].astype(int).copy())
        i = j + 1
    library = [dict(start=s, hits=h) for s, h in sorted(by_start.items())]
    return library, int(cutoff)


def scenario_hits(library, material, countries, sellers, params):
    """Window-level scenario keys that touch `material`: [(key, share, hits)].

    key = (event index, material the event recurs at, or None for an exact replay);
    share is the fraction of the event's probability this key carries. A
    single-supplier event may recur at any of its country's n materials (1/n
    each, including the original one); multi-supplier events replay exactly.
    """
    out = []
    for i, ev in enumerate(library):
        if params.generalize_single and len(ev["hits"]) == 1:
            (_, c0), traj = next(iter(ev["hits"].items()))
            if c0 in countries:
                out.append(((i, material), 1.0 / len(sellers[c0]), {(material, c0): traj}))
            continue
        hits = {k: v for k, v in ev["hits"].items() if k[0] == material}
        if hits:
            out.append(((i, None), 1.0, hits))
    return out


def _scenarios(library, observed, material, countries, normal, base_lead, cap0, lead0, weeks, params, sellers):
    """[(key, weight, cap[T,C], lead[T,C])] for one material; the nominal path first (key None).

    Each (event, onset) carries T / (weeks observed x onsets) of probability, so the
    event scenarios together carry the cutoff-only expected number of events per window."""
    T = len(weeks)
    nominal_actual = cap0 / params.base.cap_margin  # what the supplier ships when nothing new happens
    per_event = params.weight_scale * T / max(observed, 1) / len(params.onsets)
    out = []
    for key, share, hits in scenario_hits(library, material, countries, sellers, params):
        for onset in params.onsets:
            cap = nominal_actual.copy()
            lead = np.tile(lead0, (T, 1)).astype(int)
            for (_, country), (ratios, extras) in hits.items():
                c = countries.index(country)
                for k in range(len(ratios)):
                    t = onset + k
                    if t >= T:
                        break
                    cap[t, c] = min(cap[t, c], normal[c] * ratios[k])
                    lead[t, c] = max(lead[t, c], base_lead[c] + extras[k])
            out.append(((key, onset), per_event * share, cap, lead))
    total = sum(w for _, w, _, _ in out)
    if total > 0.95:  # keep at least 5% on the nominal path
        out = [(k, w * 0.95 / total, c, l) for k, w, c, l in out]
        total = 0.95
    nominal = (None, 1.0 - total, nominal_actual.copy(), np.tile(lead0, (T, 1)).astype(int))
    return [nominal] + out


def _solve(demand, opening, cap0, scenarios, landed, ref, buffer, penalty, diversity, tiers=12,
           tier_scale=1.0, credits=None, exact=True, return_objective=False):
    """Two-stage LP; returns requests r[t, c] (T x C).

    `scenarios` is [(weight, cap[T,C], lead[T,C])]; the weight multiplies every
    cost of that scenario. `credits[s]` (optional, length T) is subtracted per
    unit served in week t of scenario s (a score credit for shock-week fill)."""
    T, C = cap0.shape
    chunk = max(demand.mean() / tiers, 1e-9) if diversity else np.inf
    owner, size, extra = [], [], []
    for t in range(T):
        for c in range(C):
            left, k = cap0[t, c], 0
            while left > 1e-9:
                owner.append((t, c)); size.append(min(chunk, left)); extra.append(diversity * ref * k / 4)
                left -= chunk; k += 1
    nq = len(owner)
    S = len(scenarios)
    block = T * C + 3 * T  # f[t,c], served[t], stock[t], buffer shortfall[t]
    n = nq + S * block
    cost = np.zeros(n)
    cost[:nq] = np.asarray(extra) * tier_scale
    lo, hi = np.zeros(n), np.full(n, np.inf)
    hi[:nq] = size
    eq_r, eq_c, eq_v, eq_b = [], [], [], []
    ub_r, ub_c, ub_v, ub_b = [], [], [], []
    row_eq = row_ub = 0
    capped = []  # (fill column, request columns, scenario capacity, request bound M)
    q_of = {}
    for j, (t, c) in enumerate(owner):
        q_of.setdefault((t, c), []).append(j)
    landed = np.broadcast_to(landed, (T, C))
    for s, (w, cap, lead) in enumerate(scenarios):
        o = nq + s * block
        f = lambda t, c: o + t * C + c
        sv, st, sh = o + T * C, o + T * C + T, o + T * C + 2 * T
        for t in range(T):
            for c in range(C):
                cost[f(t, c)] = w * landed[t, c]
                arrive = t + int(lead[t, c])
                if arrive >= T:
                    cost[f(t, c)] -= w * SALVAGE * ref  # still in transit at the end: salvaged
                # link fills to requests: equality when the scenario covers the request bound
                cols = q_of.get((t, c), [])
                equal = cap[t, c] >= cap0[t, c] - 1e-9
                target = (eq_r, eq_c, eq_v, eq_b) if equal else (ub_r, ub_c, ub_v, ub_b)
                r_idx = row_eq if equal else row_ub
                target[0].append(r_idx); target[1].append(f(t, c)); target[2].append(1.0)
                for j in cols:
                    target[0].append(r_idx); target[1].append(j); target[2].append(-1.0)
                target[3].append(0.0)
                if equal:
                    row_eq += 1
                else:
                    row_ub += 1
                    hi[f(t, c)] = max(cap[t, c], 0.0)
                    if cap[t, c] > 1e-9:  # fill must equal min(request, capacity): no refusals
                        capped.append((f(t, c), cols, float(cap[t, c]), float(cap0[t, c])))
            cost[sv + t] = -w * SHORTAGE * ref - (credits[s][t] if credits is not None else 0.0)
            cost[st + t] = w * HOLDING * ref
            cost[sh + t] = w * penalty * ref
            hi[sv + t] = demand[t]
        cost[st + T - 1] -= w * SALVAGE * ref
        # stock balance: I[t] - I[t-1] + served[t] - arrivals[t] = (opening if t == 0)
        for t in range(T):
            eq_r += [row_eq, row_eq]; eq_c += [st + t, sv + t]; eq_v += [1.0, 1.0]
            if t:
                eq_r.append(row_eq); eq_c.append(st + t - 1); eq_v.append(-1.0)
            eq_b.append(opening if t == 0 else 0.0)
            row_eq += 1
        for t in range(T):
            for c in range(C):
                arrive = t + int(lead[t, c])
                if arrive < T:
                    eq_r.append(row_eq - T + arrive); eq_c.append(f(t, c)); eq_v.append(-1.0)
        # soft safety stock: -I[t] - u[t] <= -buffer[t]
        for t in range(T):
            ub_r += [row_ub, row_ub]; ub_c += [st + t, sh + t]; ub_v += [-1.0, -1.0]
            ub_b.append(-buffer[t])
            row_ub += 1
    if exact and capped:
        # f = min(q, cap) exactly, with one binary z per capped cell (z = 1: capacity binds), M = request bound:
        #   f >= q - M z,  f >= cap - M (1 - z),  q <= cap + M z,  q >= cap - M (1 - z)
        nz = len(capped)
        cost = np.concatenate([cost, np.zeros(nz)])
        lo, hi = np.concatenate([lo, np.zeros(nz)]), np.concatenate([hi, np.ones(nz)])
        for k, (fc, qcols, cp, M) in enumerate(capped):
            z = n + k
            rows = [([fc, *qcols, z], [-1.0, *[1.0] * len(qcols), -M], 0.0),       # -f + q - M z <= 0
                    ([fc, z], [-1.0, M], M - cp),                                   # -f + M z <= M - cap
                    ([*qcols, z], [*[1.0] * len(qcols), -M], cp),                   # q - M z <= cap
                    ([*qcols, z], [*[-1.0] * len(qcols), M], M - cp)]               # -q + M z <= M - cap
            for cols_, vals, rhs in rows:
                ub_r += [row_ub] * len(cols_); ub_c += cols_; ub_v += vals; ub_b.append(rhs)
                row_ub += 1
        n += nz
    A_eq = sparse.csr_matrix((eq_v, (eq_r, eq_c)), shape=(row_eq, n))
    A_ub = sparse.csr_matrix((ub_v, (ub_r, ub_c)), shape=(row_ub, n))
    if exact and capped:
        integrality = np.zeros(n); integrality[n - len(capped):] = 1
        constraints = [LinearConstraint(A_ub, -np.inf, np.array(ub_b)),
                       LinearConstraint(A_eq, np.array(eq_b), np.array(eq_b))]
        for limit in (900, 3600):  # wall-clock limits; typical solves take < 5 s
            res = milp(cost, integrality=integrality, bounds=Bounds(lo, hi), constraints=constraints,
                       options={"mip_rel_gap": 1e-4, "time_limit": limit})
            if res.x is not None:
                break
        if res.x is None:
            raise RuntimeError(res.message)
    else:
        res = linprog(cost, A_ub=A_ub, b_ub=np.array(ub_b), A_eq=A_eq, b_eq=np.array(eq_b),
                      bounds=np.column_stack([lo, hi]), method="highs")
        if not res.success:
            raise RuntimeError(res.message)
    r = np.zeros((T, C))
    for j, (t, c) in enumerate(owner):
        r[t, c] += res.x[j]
    return (r, float(res.fun)) if return_objective else r


def nominal(data, cutoff, weeks, material, bp, bans, probs, demand_all, base_buffer):
    """The incumbent's nominal planning inputs for one material (halcyon.policy.plan)."""
    T = len(weeks)
    countries, cap, lead, landed = incumbent._estimates(data, cutoff, material, bp)
    sup = data["suppliers"].loc[data["suppliers"].material == material].set_index("country").reindex(countries)
    demand = np.array([demand_all[(w, material)] for w in weeks], float)
    p = np.array([probs[(w, material)] for w in weeks], float)
    buffer = (base_buffer + bp.buffer_weeks * p) * np.append(demand[1:], 0.0)
    if bp.taper:
        remaining = np.append(np.cumsum(demand[::-1])[::-1][1:], 0.0)
        buffer = np.minimum(buffer, bp.taper * remaining)
    landed_t = incumbent._announced(data, cutoff, material, countries, weeks, landed) if bp.tariffs else landed
    cap0 = np.tile(cap, (T, 1))
    for country, onset in bans.get(material, {}).items():
        span = (np.asarray(weeks) >= onset) & (np.asarray(weeks) < onset + bp.basis_weeks)
        cap0[span, countries.index(country)] *= bp.basis_capacity / 0.98
    # Scenario overlay, same convention as halcyon.policy.plan: scale the planned capacity
    # of `country` from absolute week `from_week` on. The scenario paths start from this
    # nominal capacity (cap0 / cap_margin), so replayed events stack on top of it.
    for country, (from_week, multiplier) in bp.country_capacity.items():
        if country in countries:
            cap0[np.asarray(weeks) >= from_week, countries.index(country)] *= multiplier
    return dict(countries=countries, cap0=cap0, lead=lead, landed=landed, landed_t=np.broadcast_to(landed_t, cap0.shape),
                demand=demand, opening=OPENING_WEEKS * demand[0], buffer=buffer,
                normal=sup.normal_capacity_units.to_numpy(float), base_lead=sup.base_lead_weeks.to_numpy(int))


def rows_from(r, countries, weeks, material):
    r = np.clip(r, 0.0, None)  # LP round-off can leave -1e-16 units, i.e. shares just below 0
    rows = []
    for t, w in enumerate(weeks):
        units = float(r[t].sum())
        ordered = units > 1e-6
        split = r[t] / units if ordered else np.full(len(countries), 1 / len(countries))
        shares = {f"share_{c}": 0.0 for c in COUNTRIES}
        shares.update({f"share_{c}": float(s) for c, s in zip(countries, split)})
        rows.append({"week": w, "material": material, "order_units": units if ordered else 0.0, **shares})
    return rows


def plan(data, cutoff, weeks, forecasts, params=Params()):
    weeks = list(weeks)
    bp = params.base
    demand_all = data["demand"].set_index(["week", "material"]).demand_units
    probs = forecasts.set_index(["week", "material"]).disruption_prob
    library, observed = events(data, cutoff)
    sellers = data["suppliers"].groupby("country").material.apply(list)
    bans = incumbent._basis_bans(data, cutoff, bp) if bp.basis_haircut else {}
    cost_weight = 40 / incumbent._f_denominator(data, cutoff) if params.rebalance else 0.0
    base_buffer = bp.base_buffer if params.buffer is None else params.buffer
    rows = []
    for m in MATERIALS:
        x = nominal(data, cutoff, weeks, m, bp, bans, probs, demand_all, base_buffer)
        scen = _scenarios(library, observed, m, x["countries"], x["normal"], x["base_lead"], x["cap0"], x["lead"],
                          weeks, params, sellers)
        r = _solve(x["demand"], x["opening"], x["cap0"], [(w, c, l) for _, w, c, l in scen], x["landed_t"],
                   x["landed"].mean(), x["buffer"], bp.buffer_penalty, bp.diversity, exact=params.exact_min)
        if params.rebalance:
            r = incumbent._rebalance(r, x["cap0"], x["lead"], x["landed_t"], x["landed"].mean(),
                                     cost_weight, bp.merge_back)
        rows += rows_from(r, x["countries"], weeks, m)
    return pd.DataFrame(rows)


def plan_kes_overlay(data, cutoff, weeks, forecasts):
    """Combined hedge (#129 follow-up): the scenario policy plus the existing authorized
    week-224 Kestria hypothesis (halcyon.events: KES capacity x 0.37 from week 224).
    Pair it with events.predict_shock for the KES probability floor. Identical to
    plan() for any window ending before week 224."""
    from halcyon import events
    overlay = incumbent.Params(country_capacity={"KES": (events._BAN_WEEK, events._BAN_CAPACITY)})
    return plan(data, cutoff, weeks, forecasts, Params(base=overlay))


def compose(public_from, private_from, start=222):
    """A submission with the public rows of `public_from` and the private rows (week >= start)
    of `private_from`, both in submission (id) form with the same row order."""
    if list(public_from.id) != list(private_from.id):
        raise ValueError("frames must share the submission row order")
    private = public_from.id.str[1:4].astype(int) >= start
    out = public_from.copy()
    out.loc[private] = private_from.loc[private].to_numpy()
    return out
