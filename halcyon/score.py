"""Local estimate of the competition score. Not the official Kaggle score.

    python -m halcyon.score --cutoffs 65,78,91,104,117,130,143,156,169,182,195
    python -m halcyon.score --file submission.csv --start 209 --end 221

Score = 100 * (0.30 P + 0.40 F + 0.30 R), each part clipped to [0, 1]:
P = 0.6 Brier skill + 0.4 MAPE skill against the historical rate / last price,
F = (naive cost - cost) / (naive cost - hindsight cost),
R = 0.7 shock-fill skill + 0.3 diversification.

Simulator assumptions the rules leave open (see `Sim`): the cost reference is
the window's mean realized landed cost, the opening stock is 5x the first week's
demand, holding applies to stock left after demand, and orders may be fractional.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from halcyon.data import COUNTRIES, MATERIALS, SHARE_COLUMNS, read_all

KEY = ["week", "material"]
DEFAULT_CUTOFFS = tuple(range(65, 196, 13))


@dataclass(frozen=True)
class Sim:
    holding: float = 0.02
    shortage: float = 5.0
    salvage: float = 0.7
    opening_weeks: int = 5
    opening: str = "first_week"  # or "sum": the next 5 weeks of demand


def _window(frame, start, end):
    return frame.loc[frame.week.between(start, end)]


def _supply(tables, material, start, end):
    """Realized (weeks, countries, capacity, lead, landed) arrays for one material."""
    rows = _window(tables["supply_history"], start, end)
    rows = rows.loc[rows.material == material].pivot(
        index="week", columns="country", values=["capacity_units", "lead_time_weeks", "landed_cost"])
    weeks = list(range(start, end + 1))
    if list(rows.index) != weeks:
        raise ValueError(f"supply_history lacks weeks {start}-{end} for {material}")
    countries = list(rows["capacity_units"].columns)
    return (countries, rows["capacity_units"].to_numpy(float),
            rows["lead_time_weeks"].to_numpy(int), rows["landed_cost"].to_numpy(float))


def _demand(tables, material, start, end):
    d = tables["demand"]
    d = d.loc[d.material == material].set_index("week").demand_units
    return d.reindex(range(start, end + 1)).to_numpy(float), d


def _opening(sim, demand_series, start):
    if sim.opening == "sum":
        return float(demand_series.reindex(range(start, start + sim.opening_weeks)).sum())
    return sim.opening_weeks * float(demand_series[start])


def simulate(decisions, tables, start, end, sim=Sim()):
    """Per-(week, material) outcome of `decisions` against realized supply."""
    decisions = decisions.set_index(KEY)
    labels = tables["outcomes"].set_index(KEY).disrupted
    records = []
    for m in MATERIALS:
        countries, cap, lead, landed = _supply(tables, m, start, end)
        demand, series = _demand(tables, m, start, end)
        ref = landed.mean()
        stock, transit = _opening(sim, series, start), {}
        sellers = len(countries)
        for t, week in enumerate(range(start, end + 1)):
            row = decisions.loc[(week, m)]
            request = row.order_units * row[[f"share_{c}" for c in countries]].to_numpy(float)
            filled = np.minimum(request, cap[t])
            for c in range(sellers):
                transit[t + lead[t, c]] = transit.get(t + lead[t, c], 0.0) + filled[c]
            stock += transit.pop(t, 0.0)
            served = min(stock, demand[t])
            stock -= served
            cost = filled @ landed[t] + sim.holding * ref * stock + sim.shortage * ref * (demand[t] - served)
            if week == end:
                cost -= sim.salvage * ref * (stock + sum(transit.values()))
            hhi = float((row[list(SHARE_COLUMNS)].to_numpy(float) ** 2).sum())
            shock = any(labels.get((w, m), 0) == 1 for w in range(week - 4, week + 1))
            records.append(dict(week=week, material=m, demand=demand[t], served=served, cost=cost,
                                purchase=filled @ landed[t], stock=stock, ref=ref,
                                shock=shock, diversification=(1 - hhi) / (1 - 1 / sellers)))
    return pd.DataFrame(records)


def hindsight(tables, start, end, sim=Sim()):
    """Cost-optimal plan with perfect knowledge of the window (LP per material).

    Returns (total cost, decisions frame). The decisions reproduce the cost in
    `simulate`, so they score F = 1.
    """
    total, rows = 0.0, []
    for m in MATERIALS:
        countries, cap, lead, landed = _supply(tables, m, start, end)
        demand, series = _demand(tables, m, start, end)
        ref, (T, C) = landed.mean(), cap.shape
        nx = T * C  # variables: orders x[t, c], served s[t], ending stock I[t]
        cost = np.concatenate([landed.ravel(), np.full(T, -sim.shortage * ref), np.full(T, sim.holding * ref)])
        A, b = np.zeros((T, nx + 2 * T)), np.zeros(T)
        for t in range(T):
            for c in range(C):
                if t + lead[t, c] < T:
                    A[t + lead[t, c], t * C + c] -= 1
                else:
                    cost[t * C + c] -= sim.salvage * ref  # still in transit at the end
            A[t, nx + t] = A[t, nx + T + t] = 1
            if t:
                A[t, nx + T + t - 1] = -1
        b[0] = _opening(sim, series, start)
        cost[-1] -= sim.salvage * ref
        bounds = [(0, u) for u in cap.ravel()] + [(0, d) for d in demand] + [(0, None)] * T
        res = linprog(cost, A_eq=A, b_eq=b, bounds=bounds, method="highs")
        if not res.success:
            raise RuntimeError(res.message)
        total += res.fun + sim.shortage * ref * demand.sum()
        x = res.x[:nx].reshape(T, C)
        for t, week in enumerate(range(start, end + 1)):
            units = float(x[t].sum())
            shares = x[t] / units if units > 1e-9 else np.eye(C)[np.argmin(landed[t])]
            row = {f"share_{c}": 0.0 for c in COUNTRIES}
            row.update({f"share_{c}": float(s) for c, s in zip(countries, shares)})
            rows.append(dict(week=week, material=m, order_units=units, **row))
    return total, pd.DataFrame(rows)


def naive(tables, cutoff, weeks):
    """The organizer's naive reference at `cutoff` (halcyon.naive; reproduces
    sample_submission.csv at cutoff 208)."""
    from halcyon import naive as reference
    from halcyon.submit import plan_window
    return plan_window(tables, cutoff, list(weeks), reference.MODELS)


def _clip(x):
    return float(np.clip(x, 0, 1))


def _frame(frame, start, end):
    """Accept a submission (with `id`) or a plan (with week/material)."""
    if "week" not in frame:
        parts = frame.id.str.extract(r"^w(\d+)_(.+)$")
        frame = frame.assign(week=parts[0].astype(int), material=parts[1])
    return _window(frame, start, end).reset_index(drop=True)


def score(frame, tables, start, end, reference=None, sim=Sim()):
    """Local P/F/R estimate of `frame` on weeks start..end.

    `tables` must hold realized labels and supply for the window. `reference`
    is the naive plan; it defaults to `naive` standing at start - 1.
    """
    weeks = list(range(start, end + 1))
    frame = _frame(frame, start, end)
    reference = naive(tables, start - 1, weeks) if reference is None else _frame(reference, start, end)
    truth = _window(tables["outcomes"], start, end)
    you, base = (f.merge(truth, on=KEY, validate="one_to_one") for f in (frame, reference))
    if len(you) != len(weeks) * len(MATERIALS):
        raise ValueError(f"need one row per material for weeks {start}-{end}")
    brier = lambda f: ((f.disruption_prob - f.disrupted) ** 2).mean()
    mape = lambda f: ((f.price_forecast - f.benchmark_price).abs() / f.benchmark_price).mean()
    b_base, m_base = brier(base), mape(base)
    brier_skill = 1 - brier(you) / b_base if b_base else 0.0
    price_skill = 1 - mape(you) / m_base if m_base else 0.0
    P = _clip(0.6 * _clip(brier_skill) + 0.4 * _clip(price_skill))

    sim_you, sim_base = simulate(frame, tables, start, end, sim), simulate(reference, tables, start, end, sim)
    cost, naive_cost = sim_you.cost.sum(), sim_base.cost.sum()
    best = hindsight(tables, start, end, sim)[0]
    F_raw = (naive_cost - cost) / (naive_cost - best) if naive_cost > best else 0.0
    fill = lambda s: s.loc[s.shock].served.sum() / s.loc[s.shock].demand.sum() if s.shock.any() else np.nan
    f_you, f_base = fill(sim_you), fill(sim_base)
    fill_skill = _clip((f_you - f_base) / (1 - f_base)) if np.isfinite(f_base) and f_base < 1 else 0.0
    diversification = sim_you.diversification.mean()
    R = _clip(0.7 * fill_skill + 0.3 * diversification)
    return dict(start=start, end=end, score=100 * (0.3 * P + 0.4 * _clip(F_raw) + 0.3 * R),
                P=P, F=_clip(F_raw), R=R, brier_skill=brier_skill, price_skill=price_skill,
                F_raw=F_raw, fill_skill=fill_skill, shock_fill=f_you, naive_shock_fill=f_base,
                diversification=diversification, cost=cost, naive_cost=naive_cost,
                hindsight_cost=best)


def backtest(cutoffs=DEFAULT_CUTOFFS, tables=None, planner=None, horizon=13, sim=Sim()):
    """Score `planner(tables, cutoff, weeks)` (default: `submit.plan_window`, the
    current pipeline) at each cutoff on weeks cutoff+1..cutoff+horizon."""
    if planner is None:
        from halcyon.submit import plan_window as planner
    tables = read_all() if tables is None else tables
    rows = []
    for c in cutoffs:
        weeks = list(range(c + 1, c + horizon + 1))
        rows.append(dict(cutoff=c, **score(planner(tables, c, weeks), tables, weeks[0], weeks[-1], sim=sim)))
    return pd.DataFrame(rows)


def summary(results):
    cols = ["score", "P", "F", "R", "brier_skill", "price_skill", "F_raw", "fill_skill", "diversification"]
    return pd.concat([results[cols].mean().rename("mean"), results[cols].min().rename("worst")], axis=1).T


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cutoffs", default=",".join(map(str, DEFAULT_CUTOFFS)))
    parser.add_argument("--file", type=Path, action="append", help="score fixed submission CSV(s)")
    parser.add_argument("--start", type=int, default=209)
    parser.add_argument("--end", type=int, default=221)
    parser.add_argument("--naive", type=Path, help="naive file for --file (default: naive at start-1)")
    parser.add_argument("--opening", choices=["first_week", "sum"], default="first_week")
    args = parser.parse_args()
    tables, sim = read_all(args.data_dir), Sim(opening=args.opening)
    pd.set_option("display.width", 200)
    if args.file:
        reference = pd.read_csv(args.naive) if args.naive else None
        rows = [dict(file=f.name, **score(pd.read_csv(f), tables, args.start, args.end, reference, sim))
                for f in args.file]
        print(pd.DataFrame(rows).set_index("file").round(4).T.to_string())
        return
    results = backtest([int(c) for c in args.cutoffs.split(",")], tables, sim=sim)
    print(results.set_index("cutoff").round(4).to_string())
    print("\nlocal estimate (not official)\n" + summary(results).round(4).to_string())


if __name__ == "__main__":
    main()
