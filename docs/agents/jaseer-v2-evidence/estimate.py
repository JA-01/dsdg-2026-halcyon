"""Jaseer's V2 evidence: throwaway estimator of the published score formula.

NOT organizer parity and not calibrated to any Kaggle score. Compare candidates only.
  naive      = halcyon.policy.NaivePolicy (sample-shaped: demand, largest normal-capacity supplier)
  hindsight  = per-material LP on realized capacity/lead/landed cost inside the window
  F          = clip((naive - ours) / (naive - hindsight), 0, 1), costs from halcyon.simulator
  fill skill = clip((ours - naive) / (1 - naive), 0, 1) on shock+4 recovery weeks; 0 if naive fill is 1
  R          = 0.7 fill skill + 0.3 mean row diversification; P = 0 (policy-only comparison)
Windows: h1-13 from origins 52..169 step 13 (set A) and 58..162 step 13 (set B); no target past 182.

Run from the repository root:  python docs/agents/jaseer-v2-evidence/estimate.py
Writes per-window raw outcomes to docs/agents/jaseer-v2-evidence/windows.csv.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog

import halcyon.policy as P
from halcyon.data import Dataset
from halcyon.forecasting.baseline import HistoricalForecaster
from halcyon.simulator import simulate_window

DATA = Dataset.from_csv_dir("data")
SET_A = list(range(52, 170, 13))
SET_B = list(range(58, 163, 13))
OUT = Path(__file__).with_name("windows.csv")


def hindsight_cost(start, end):
    supply, demand = DATA["supply_history"], DATA["demand"].set_index(["week", "material"]).demand_units
    total = 0.0
    for material, rows in supply[supply.week.between(start, end)].groupby("material"):
        ref = rows.landed_cost.mean()
        weeks = list(range(start, end + 1)); T = len(weeks)
        countries = sorted(rows.country.unique()); C = len(countries)
        rows = rows.set_index(["week", "country"])
        d = np.array([demand[(w, material)] for w in weeks], float)
        nx = T * C; n = nx + 2 * T  # orders x[t,c], served s[t], ending stock I[t]
        cost = np.zeros(n); upper = np.full(n, np.inf); A = np.zeros((T, n)); b = np.zeros(T)
        for t, week in enumerate(weeks):
            for c, country in enumerate(countries):
                cap, lead, landed = rows.loc[(week, country), ["capacity_units", "lead_time_weeks", "landed_cost"]]
                k = t * C + c; cost[k] = landed; upper[k] = cap
                if t + int(lead) < T:
                    A[t + int(lead), k] -= 1.0
                else:
                    cost[k] -= 0.7 * ref  # arrives after the window: salvaged in transit
            cost[nx + t] = -5.0 * ref; upper[nx + t] = d[t]
            cost[nx + T + t] = 0.02 * ref
            A[t, nx + t] += 1.0; A[t, nx + T + t] += 1.0  # I_t = I_{t-1} + arrivals_t - s_t
            if t:
                A[t, nx + T + t - 1] -= 1.0
        b[0] = 5.0 * d[0]
        cost[nx + 2 * T - 1] -= 0.7 * ref
        result = linprog(cost, A_eq=A, b_eq=b, bounds=list(zip(np.zeros(n), upper)), method="highs")
        assert result.success, result.message
        total += result.fun + 5.0 * ref * d.sum()
    return total


def simulate(decisions, start, end):
    weekly = simulate_window(decisions, DATA["demand"], DATA["supply_history"], DATA["suppliers"],
                             DATA["outcomes"], start, end).weekly
    shock = weekly[weekly.shock_recovery]
    fill = shock.fulfilled_units.sum() / shock.demand_units.sum() if len(shock) else np.nan
    return weekly.total_cost.sum(), fill, weekly.diversification.mean()


class PostHocTilt:
    """Andrew's item 6: keep optimizer quantities; on positive rows split by exp(-k x relative
    trailing landed cost), spilling units above the optimizer's q25 capacity estimate."""

    def __init__(self, k, config=None):
        self.k, self.config = k, config

    def decide(self, data, forecasts, cutoff, target_weeks):
        decisions = P.OptimizedPolicy(config=self.config).decide(data, forecasts, cutoff, target_weeks)
        sources = P._optimization_suppliers(data["supply_history"], data["suppliers"], cutoff,
                                            P.OptimizationConfig())
        for material, src in sources.groupby("material"):
            src = src.sort_values("country")
            costs, caps = src.landed_cost.to_numpy(float), src.capacity_units.to_numpy(float)
            weights = np.exp(-self.k * (costs / costs.mean() - 1.0)); weights /= weights.sum()
            columns = [f"share_{c}" for c in src.country]
            for i in decisions.index[(decisions.material == material) & (decisions.order_units > 0)]:
                units = decisions.at[i, "order_units"] * weights; free = np.ones(len(weights), bool)
                while True:
                    over = (units > caps) & free
                    if not over.any():
                        break
                    spill = (units[over] - caps[over]).sum(); units[over] = caps[over]; free &= ~over
                    if not free.any():
                        break
                    units[free] += spill * weights[free] / weights[free].sum()
                decisions.loc[i, columns] = units / units.sum()
        return decisions


CANDIDATES = {
    "current": lambda: P.OptimizedPolicy(),
    "tilt_k3": lambda: PostHocTilt(3.0),
    "tilt_k3_risk_buffer_4": lambda: PostHocTilt(3.0, {"risk_buffer_weeks": 4.0}),
    "tilt_k5": lambda: PostHocTilt(5.0),
    "div_penalty_0.10": lambda: P.OptimizedPolicy(config={"diversification_penalty": 0.10}),
    "div_penalty_0.05": lambda: P.OptimizedPolicy(config={"diversification_penalty": 0.05}),
    "base_buffer_3": lambda: P.OptimizedPolicy(config={"base_buffer_weeks": 3.0}),
    "risk_buffer_4": lambda: P.OptimizedPolicy(config={"risk_buffer_weeks": 4.0}),
}


def main():
    rows = []
    for origin in SET_A + SET_B:
        weeks = list(range(origin + 1, origin + 14)); start, end = weeks[0], weeks[-1]
        forecasts = HistoricalForecaster().predict(DATA, origin, weeks)
        naive = simulate(P.NaivePolicy().decide(DATA, forecasts, origin, weeks), start, end)
        hindsight = hindsight_cost(start, end)
        for name, make in CANDIDATES.items():
            cost, fill, diversification = simulate(make().decide(DATA, forecasts, origin, weeks), start, end)
            F = float(np.clip((naive[0] - cost) / (naive[0] - hindsight), 0, 1))
            tie = np.isnan(naive[1]) or naive[1] >= 1 - 1e-12
            fill_skill = 0.0 if tie else float(np.clip((fill - naive[1]) / (1 - naive[1]), 0, 1))
            score = 100 * (0.4 * F + 0.3 * (0.7 * fill_skill + 0.3 * diversification))
            rows.append(dict(candidate=name, set="A" if origin in SET_A else "B", origin=origin,
                             window=f"{start}-{end}", score=score, F=F, fill_skill=fill_skill,
                             shock_fill=fill, diversification=diversification, total_cost=cost,
                             naive_cost=naive[0], naive_shock_fill=naive[1], hindsight_cost=hindsight))
    frame = pd.DataFrame(rows)
    frame.round(6).to_csv(OUT, index=False)
    current = frame[frame.candidate == "current"].set_index("origin").score
    summary = []
    for name, group in frame.groupby("candidate", sort=False):
        delta = group.set_index("origin").score - current
        shock = current > 50  # windows where naive misses shock demand and current scores high
        summary.append(dict(candidate=name, set_A=group[group.set == "A"].score.mean(),
                            set_B=group[group.set == "B"].score.mean(), delta_mean=delta.mean(),
                            delta_worst=delta.min(), wins=int((delta > 0.01).sum()),
                            delta_shock=delta[shock].mean(), delta_calm=delta[~shock].mean(),
                            hedged_gain=np.maximum(delta, 0).mean(),
                            diversification=group.diversification.mean()))
    print(pd.DataFrame(summary).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
