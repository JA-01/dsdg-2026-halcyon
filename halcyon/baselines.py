"""Provisional baselines owned by the integrator, so the pipeline runs before owner modules land.

Replace through config with halcyon/forecasting (Tejas) and halcyon/policy.py (AV). These are not
the organizer's naive policy and make no claim about score.
"""
from __future__ import annotations

import pandas as pd

from .constants import COUNTRIES


class ProvisionalForecaster:
    """Each material's historical disruption rate and last known benchmark price at the cutoff."""

    model_id = "provisional_origin_naive"

    def predict(self, data, cutoff: int, target_weeks: list[int]) -> pd.DataFrame:
        outcomes = data["outcomes"]
        outcomes = outcomes[outcomes["week"] <= cutoff].sort_values("week")
        by_material = outcomes.groupby("material")
        rates, prices = by_material["disrupted"].mean(), by_material["benchmark_price"].last()
        return pd.DataFrame(
            [{"target_week": week, "material": material, "disruption_prob": float(rates[material]),
              "price_forecast": float(prices[material]), "model_id": self.model_id}
             for week in target_weeks for material in rates.index])


class ProvisionalPolicy:
    """Order each week's known demand, split across suppliers by normal capacity."""

    policy_id = "provisional_capacity_split"

    def decide(self, data, forecasts: pd.DataFrame, cutoff: int, target_weeks: list[int]) -> pd.DataFrame:
        suppliers = data["suppliers"]
        totals = suppliers.groupby("material")["normal_capacity_units"].sum()
        shares = {
            material: {row.country: row.normal_capacity_units / totals[material] for row in group.itertuples()}
            for material, group in suppliers.groupby("material")}
        demand = data["demand"].set_index(["week", "material"])["demand_units"]
        keys = forecasts[["target_week", "material"]].itertuples(index=False)
        return pd.DataFrame(
            [{"target_week": week, "material": material, "order_units": float(demand[(week, material)]),
              **{f"share_{c}": shares[material].get(c, 0.0) for c in COUNTRIES},
              "policy_id": self.policy_id}
             for week, material in keys])
