"""Score-maximizing orders for a window whose supply is already released (#119 D).

Starting from the hindsight-optimal fills, a per-material hill climb trades cost
for diversification at the score's exchange rate: 9/130 points per unit of one
row's diversification against 40/D points per unit of cost, D being the window's
naive-minus-hindsight cost. Moves merge a row into an earlier week or shift
volume between suppliers; no move may add a shortage, so fill stays at its
hindsight level. Requests above a supplier's realized capacity are cancelled
free, so a capacity-bound supplier's share is raised to balance the row at no
cost ("free inflation"). Only for released windows: it reads realized supply.
"""

import numpy as np
import pandas as pd

from halcyon.data import COUNTRIES, MATERIALS

DIV_POINTS = 9 / 130
HOLDING, SHORTAGE, SALVAGE = 0.02, 5.0, 0.7


def _sim(f, demand, opening, lead, landed, ref):
    """(cost, total shortage) of fills f[t, c] for one material."""
    T = len(demand)
    arrivals = np.zeros(T + 64)
    for t in range(T):
        np.add.at(arrivals, t + lead[t], f[t])
    stock, cost, short = opening, float((f * landed).sum()), 0.0
    for t in range(T):
        stock += arrivals[t]
        served = min(stock, demand[t])
        short += demand[t] - served
        stock -= served
        cost += HOLDING * ref * stock + SHORTAGE * ref * (demand[t] - served)
    return cost - SALVAGE * ref * (stock + arrivals[T:].sum()), short


def _requests(f, cap):
    """Requests q >= f with q = f where capacity doesn't bind; binding suppliers are
    raised (free: the excess is cancelled) to the level that maximizes diversification."""
    total = f.sum()
    if total <= 1e-9:
        return np.ones_like(f)
    bound = f >= cap - 1e-9
    if not bound.any():
        return f
    best, best_q = -1.0, f
    for level in np.unique(np.r_[f, f.max() * np.linspace(0.2, 1.0, 9)]):
        q = np.where(bound, np.maximum(f, level), f)
        d = _div(q)
        if d > best + 1e-12:
            best, best_q = d, q
    return best_q


def _div(q):
    s = q / q.sum()
    return (1 - (s ** 2).sum()) / (1 - 1 / len(q))


def _objective(f, cap, demand, opening, lead, landed, ref, weight):
    cost, short = _sim(f, demand, opening, lead, landed, ref)
    div = sum(_div(_requests(f[t], cap[t])) if f[t].sum() > 1e-9 else 1.0 for t in range(len(f)))
    return DIV_POINTS * div - weight * cost, short


def _climb(f, cap, demand, opening, lead, landed, ref, weight, merge_back=3, rounds=6):
    best, short0 = _objective(f, cap, demand, opening, lead, landed, ref, weight)
    T, C = f.shape
    for _ in range(rounds):
        improved = False
        for t in range(T):
            candidates = []
            if f[t].sum() > 1e-9:  # merge the whole row into an earlier week
                for k in range(1, merge_back + 1):
                    if t - k >= 0 and np.all(f[t - k] + f[t] <= cap[t - k] + 1e-9):
                        g = f.copy(); g[t - k] += f[t]; g[t] = 0
                        candidates.append(g)
            for a in range(C):  # shift part of a's volume to b, same week
                for b in range(C):
                    if a == b or f[t, a] <= 1e-9:
                        continue
                    room = cap[t, b] - f[t, b]
                    for frac in (0.1, 0.25, 0.5, 1.0):
                        d = min(f[t, a] * frac, room)
                        if d > 1e-9:
                            g = f.copy(); g[t, a] -= d; g[t, b] += d
                            candidates.append(g)
            for g in candidates:
                value, short = _objective(g, cap, demand, opening, lead, landed, ref, weight)
                if short <= short0 + 1e-6 and value > best + 1e-9:
                    best, f, improved = value, g, True
        if not improved:
            break
    return f


def orders(tables, start, end, hindsight_plan, naive_cost, hindsight_cost, slack=0.0):
    """Optimized [week, material, order_units, share_*] for a released window.

    `slack` > 0 assumes Kaggle's hindsight is that fraction of the gap cheaper
    than ours is not (spend F above 1); default 0 is conservative."""
    weight = 40 / ((naive_cost - hindsight_cost) * (1 + slack))
    sh = tables["supply_history"]
    demand_all = tables["demand"].set_index(["week", "material"]).demand_units
    plan = hindsight_plan.set_index(["week", "material"])
    weeks = list(range(start, end + 1))
    rows = []
    for m in MATERIALS:
        rows_m = sh.loc[(sh.material == m) & sh.week.between(start, end)]
        piv = rows_m.pivot(index="week", columns="country", values=["capacity_units", "lead_time_weeks", "landed_cost"])
        countries = list(piv["capacity_units"].columns)
        cap = piv["capacity_units"].to_numpy(float)
        lead = piv["lead_time_weeks"].to_numpy(int)
        landed = piv["landed_cost"].to_numpy(float)
        demand = np.array([demand_all[(w, m)] for w in weeks], float)
        units = plan.loc[[(w, m) for w in weeks], "order_units"].to_numpy(float)
        shares = plan.loc[[(w, m) for w in weeks], [f"share_{c}" for c in countries]].to_numpy(float)
        f = np.minimum(units[:, None] * shares, cap)
        f = _climb(f, cap, demand, 5 * demand[0], lead, landed, landed.mean(), weight)
        for t, w in enumerate(weeks):
            q = _requests(f[t], cap[t])
            total = q.sum() if f[t].sum() > 1e-9 else 0.0
            split = q / q.sum() if total else np.full(len(countries), 1 / len(countries))
            row = {f"share_{c}": 0.0 for c in COUNTRIES}
            row.update({f"share_{c}": float(s) for c, s in zip(countries, split)})
            rows.append(dict(week=w, material=m, order_units=float(total), **row))
    return pd.DataFrame(rows)
