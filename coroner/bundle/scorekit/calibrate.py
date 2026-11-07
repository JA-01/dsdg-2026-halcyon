"""Throwaway calibration, not organizer parity, not validation.

Item 9 of docs/agents/jaseer-v2-improvements.md. Scores one realized window;
--relabel-shift only exercises mechanics, not meaningful forecast performance.
"""

import argparse
import hashlib
from io import BytesIO
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.optimize import linprog

# Permit the documented direct invocation without installing the repository.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from halcyon.constants import SHARE_COLUMNS
from halcyon.data import Dataset
from halcyon.simulator import simulate_window


def hindsight_cost(data, start, end):
    """The realized-supply LP copied from sibling estimate.py, with explicit data."""
    supply = data["supply_history"]
    demand = data["demand"].set_index(["week", "material"]).demand_units
    total = 0.0
    for material, rows in supply[supply.week.between(start, end)].groupby("material"):
        ref = rows.landed_cost.mean()
        weeks = list(range(start, end + 1))
        T = len(weeks)
        countries = sorted(rows.country.unique())
        C = len(countries)
        rows = rows.set_index(["week", "country"])
        d = np.array([demand[(w, material)] for w in weeks], float)
        nx = T * C
        n = nx + 2 * T  # orders x[t,c], served s[t], ending stock I[t]
        cost = np.zeros(n)
        upper = np.full(n, np.inf)
        A = np.zeros((T, n))
        b = np.zeros(T)
        for t, week in enumerate(weeks):
            for c, country in enumerate(countries):
                cap, lead, landed = rows.loc[(week, country),
                                            ["capacity_units", "lead_time_weeks", "landed_cost"]]
                k = t * C + c
                cost[k] = landed
                upper[k] = cap
                if t + int(lead) < T:
                    A[t + int(lead), k] -= 1.0
                else:
                    cost[k] -= 0.7 * ref  # salvage orders still in transit
            cost[nx + t] = -5.0 * ref
            upper[nx + t] = d[t]
            cost[nx + T + t] = 0.02 * ref
            A[t, nx + t] += 1.0
            A[t, nx + T + t] += 1.0
            if t:
                A[t, nx + T + t - 1] -= 1.0
        b[0] = 5.0 * d[0]
        cost[nx + 2 * T - 1] -= 0.7 * ref
        result = linprog(cost, A_eq=A, b_eq=b,
                         bounds=list(zip(np.zeros(n), upper)), method="highs")
        if not result.success:
            raise RuntimeError(result.message)
        total += result.fun + 5.0 * ref * d.sum()
    return total


def load_submission(path, shift, start, end):
    original = path.read_bytes()
    frame = pd.read_csv(BytesIO(original))
    ids = frame["id"].str.extract(r"^w(\d+)_(.+)$")
    frame["target_week"] = ids[0].astype(int) - shift
    frame["material"] = ids[1]
    frame = frame.loc[frame.target_week.between(start, end)].copy()
    return frame, hashlib.sha256(original).hexdigest()


def simulate(frame, data, start, end):
    # Submission order_units is the total order; shares are passed unchanged.
    # No unit columns per supplier or forecast columns are required by the simulator.
    decisions = frame.loc[:, ["target_week", "material", "order_units", *SHARE_COLUMNS]]
    weekly = simulate_window(decisions, data["demand"], data["supply_history"],
                             data["suppliers"], data["outcomes"], start, end).weekly
    shock = weekly.loc[weekly.shock_recovery]
    demand = shock.demand_units.sum()
    fill = float(shock.fulfilled_units.sum() / demand) if demand else np.nan
    return float(weekly.total_cost.sum()), fill, float(weekly.diversification.mean())


def prediction_skills(frame, truth, history):
    joined = frame.merge(truth, left_on=["target_week", "material"],
                         right_on=["week", "material"], validate="one_to_one")
    historical_rate = history.groupby("material").disrupted.mean()
    last_price = history.sort_values("week").groupby("material").benchmark_price.last()
    brier = ((joined.disruption_prob - joined.disrupted) ** 2).mean()
    baseline_brier = ((joined.material.map(historical_rate) - joined.disrupted) ** 2).mean()
    mape = ((joined.price_forecast - joined.benchmark_price).abs() / joined.benchmark_price).mean()
    baseline_mape = ((joined.material.map(last_price) - joined.benchmark_price).abs()
                     / joined.benchmark_price).mean()
    # A perfect baseline leaves no attainable positive skill; worse gets -inf raw.
    brier_skill = (1 - brier / baseline_brier if baseline_brier
                   else (0.0 if brier == 0 else -np.inf))
    price_skill = (1 - mape / baseline_mape if baseline_mape
                   else (0.0 if mape == 0 else -np.inf))
    return tuple(float(value) for value in
                 (brier_skill, price_skill, brier, baseline_brier, mape, baseline_mape))


def clip(value):
    return float(np.clip(value, 0, 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--naive", type=Path, required=True)
    parser.add_argument("--relabel-shift", type=int, default=0)
    parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    data = Dataset.from_csv_dir(args.data_dir)
    outcomes = data["outcomes"]
    truth = outcomes.loc[outcomes.week.between(args.start, args.end)]
    history = outcomes.loc[outcomes.week <= args.start - 1]
    naive, naive_sha = load_submission(args.naive, args.relabel_shift, args.start, args.end)
    naive_cost, naive_fill, naive_diversification = simulate(naive, data, args.start, args.end)
    hindsight = hindsight_cost(data, args.start, args.end)
    rows = []
    for path in [args.naive, *args.files]:
        if path == args.naive:
            frame, sha = naive, naive_sha
            cost, fill, diversification = naive_cost, naive_fill, naive_diversification
        else:
            frame, sha = load_submission(path, args.relabel_shift, args.start, args.end)
            cost, fill, diversification = simulate(frame, data, args.start, args.end)
        brier_raw, price_raw, brier_error, baseline_brier, mape, baseline_mape = prediction_skills(
            frame, truth, history)
        # Clip the two prediction skills separately before weighting, then clip
        # P/F/R as published. Report raw skills and raw weighted P for visibility.
        brier, price = clip(brier_raw), clip(price_raw)
        P_raw = 0.6 * brier_raw + 0.4 * price_raw
        P = clip(0.6 * brier + 0.4 * price)
        F_raw = (naive_cost - cost) / (naive_cost - hindsight) if cost != naive_cost else 0.0
        F = clip(F_raw)
        # No shock demand or a perfect naive fill offers no fill improvement.
        fill_skill = (0.0 if not np.isfinite(naive_fill) or naive_fill >= 1
                      else clip((fill - naive_fill) / (1 - naive_fill)))
        R = clip(0.7 * fill_skill + 0.3 * diversification)
        score = 100 * (0.3 * P + 0.4 * F + 0.3 * R)
        rows.append(dict(file=path.name, sha256=sha, P=P, P_unclipped=P_raw,
                         brier_skill=brier, brier_skill_unclipped=brier_raw,
                         price_skill=price, price_skill_unclipped=price_raw,
                         brier=brier_error, baseline_brier=baseline_brier,
                         mape=mape, baseline_mape=baseline_mape,
                         F=F, F_unclipped=F_raw, fill_skill=fill_skill,
                         shock_fill=fill, naive_shock_fill=naive_fill,
                         diversification=diversification, R=R, total_cost=cost,
                         naive_cost=naive_cost, hindsight_cost=hindsight, score=score))
    print(pd.DataFrame(rows).to_csv(index=False, float_format="%.9f"), end="")


if __name__ == "__main__":
    main()
