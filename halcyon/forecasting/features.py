"""Origin-safe numeric features shared by pandas models and native Spark jobs.

One row per requested (target_week, material). Observations are reduced once per
origin, never once per target. Demand is a published plan; tariff announcements
are usable only after their publication week. Missing core history is an error,
not a synthetic zero-price training example. Short rolling windows use available
history, and unavailable lags use the earliest available benchmark.
"""
from __future__ import annotations

from numbers import Integral

import numpy as np
import pandas as pd

from halcyon.constants import MATERIALS
from halcyon.contracts import ContractError

FEATURE_VERSION = "origin_numeric_v1"
CONTEXT_COLUMNS = ("target_week", "material", "cutoff_week", "horizon", "feature_version")
NUMERIC_FEATURES = (
    "latest_benchmark_price", "benchmark_lag_1", "benchmark_lag_4",
    "benchmark_mean_4", "benchmark_mean_13", "benchmark_mean_26",
    "benchmark_std_13", "benchmark_change_4", "disruption_rate_all",
    "disruption_rate_4", "disruption_rate_13", "disruption_rate_26",
    "latest_disrupted", "history_weeks", "outcome_age_weeks",
    "spot_price_mean", "futures_4w_mean", "futures_spot_ratio",
    "spot_mean_4", "spot_mean_13", "tariff_rate_mean", "target_tariff_mean",
    "tariff_announced_delta_mean", "container_rate_mean", "transit_days_mean",
    "congestion_index_mean", "pmi_mean", "fx_rate_mean", "cpi_yoy_mean",
    "policy_rate_mean", "tension_index_mean", "capacity_units_sum",
    "capacity_ratio", "lead_time_weeks_mean", "landed_cost_mean",
    "capacity_mean_4", "lead_time_mean_4", "demand_units", "demand_mean_4",
    "demand_ratio", "base_lead_weeks_mean", "normal_capacity_units_sum",
)
FEATURE_COLUMNS = (*CONTEXT_COLUMNS, *NUMERIC_FEATURES)


def validate_request(cutoff: int, target_weeks: list[int]) -> list[int]:
    """Validate identity without silently collapsing duplicate target keys."""
    if isinstance(cutoff, bool) or not isinstance(cutoff, Integral) or cutoff < 1:
        raise ContractError("cutoff must be a positive integer")
    weeks = list(target_weeks)
    if not weeks or any(isinstance(w, bool) or not isinstance(w, Integral) or w <= cutoff for w in weeks):
        raise ContractError("target_weeks must contain integers strictly after cutoff")
    if len(set(weeks)) != len(weeks):
        raise ContractError("target_weeks contains duplicate weeks")
    return sorted(int(w) for w in weeks)


def _history(frame: pd.DataFrame, material: str, name: str) -> pd.DataFrame:
    result = frame.loc[frame["material"] == material].sort_values("week")
    if result.empty:
        raise ContractError(f"{name}: no observed history for {material}")
    return result


def _latest(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return frame.sort_values("week").groupby(keys, sort=False).tail(1)


def _mean(frame: pd.DataFrame, column: str) -> float:
    value = float(frame[column].mean())
    if not np.isfinite(value):
        raise ContractError(f"missing or nonfinite history for {column}")
    return value


def build_features(data, cutoff: int, target_weeks: list[int]) -> pd.DataFrame:
    """Build the versioned schema from a Dataset, narrowing even inner origins.

    ``data`` may already be an outer cutoff view; this call still invokes
    ``as_of(cutoff)`` exactly once. No Spark, network, or hidden persistent cache.
    Output covers each requested week and canonical material exactly once.
    """
    weeks = validate_request(cutoff, target_weeks)
    visible = data.as_of(cutoff)
    tables = {name: visible[name] for name in (
        "suppliers", "outcomes", "prices", "tariffs", "shipping", "macro",
        "supply_history", "demand",
    )}
    suppliers = tables["suppliers"]
    if set(suppliers["material"]) != set(MATERIALS):
        raise ContractError("suppliers must cover the ten competition materials")
    shipping = _latest(tables["shipping"], ["lane"])
    macro = _latest(tables["macro"], ["country"])
    rows = []
    for material in MATERIALS:
        eligible = suppliers.loc[suppliers["material"] == material]
        outcomes = _history(tables["outcomes"], material, "outcomes")
        benchmark = outcomes["benchmark_price"]
        if not np.isfinite(benchmark).all() or (benchmark <= 0).any():
            raise ContractError(f"outcomes: benchmark prices must be finite positive for {material}")
        recent = lambda n: outcomes.loc[outcomes["week"] > cutoff - n]
        if recent(4).empty:
            raise ContractError(f"outcomes: no history in the last four weeks for {material}")
        latest_price = float(benchmark.iloc[-1])
        lag = lambda n: float(benchmark.iloc[-n - 1] if len(benchmark) > n else benchmark.iloc[0])
        prices = _history(tables["prices"], material, "prices")
        prices = prices.merge(eligible[["country"]], on="country", validate="many_to_one")
        current_price = _latest(prices, ["country"])
        tariffs = _history(tables["tariffs"], material, "tariffs")
        tariffs = tariffs.merge(eligible[["country"]], on="country", validate="many_to_one")
        current_tariff = _latest(tariffs, ["country"])
        supply = _history(tables["supply_history"], material, "supply_history")
        supply = supply.merge(eligible[["country"]], on="country", validate="many_to_one")
        current_supply = _latest(supply, ["country"])
        lanes = eligible[["lane"]].merge(shipping, on="lane", how="left", validate="many_to_one")
        countries = eligible[["country"]].merge(macro, on="country", how="left", validate="one_to_one")
        for name, frame in (("prices", current_price), ("tariffs", current_tariff), ("supply_history", current_supply)):
            if set(frame["country"]) != set(eligible["country"]):
                raise ContractError(f"{name}: missing eligible supplier history for {material}")
        if lanes["week"].isna().any() or countries["week"].isna().any():
            raise ContractError(f"missing shipping/macro history for {material}")
        normal_capacity = float(eligible["normal_capacity_units"].sum())
        capacity = float(current_supply["capacity_units"].sum())
        spot = _mean(current_price, "spot_price")
        if normal_capacity <= 0 or spot <= 0:
            raise ContractError(f"nonpositive capacity or spot price for {material}")
        # Aggregate capacity per historical week before taking the rolling mean.
        supply4 = supply.loc[supply["week"] > cutoff - 4]
        demand = tables["demand"].loc[tables["demand"]["material"] == material]
        demand4 = demand.loc[demand["week"].between(cutoff - 3, cutoff)]
        base = {
            "latest_benchmark_price": latest_price,
            "benchmark_lag_1": lag(1), "benchmark_lag_4": lag(4),
            **{f"benchmark_mean_{n}": _mean(recent(n), "benchmark_price") for n in (4, 13, 26)},
            "benchmark_std_13": float(recent(13)["benchmark_price"].std(ddof=0)),
            "benchmark_change_4": latest_price / lag(4) - 1,
            "disruption_rate_all": _mean(outcomes, "disrupted"),
            **{f"disruption_rate_{n}": _mean(recent(n), "disrupted") for n in (4, 13, 26)},
            "latest_disrupted": float(outcomes["disrupted"].iloc[-1]),
            "history_weeks": float(len(outcomes)),
            "outcome_age_weeks": float(cutoff - outcomes["week"].iloc[-1]),
            "spot_price_mean": spot, "futures_4w_mean": _mean(current_price, "futures_4w"),
            "futures_spot_ratio": _mean(current_price, "futures_4w") / spot,
            **{f"spot_mean_{n}": _mean(prices.loc[prices["week"] > cutoff - n], "spot_price") for n in (4, 13)},
            "tariff_rate_mean": _mean(current_tariff, "tariff_rate"),
            **{f"{col}_mean": _mean(lanes, col) for col in ("container_rate", "transit_days", "congestion_index")},
            **{f"{col}_mean": _mean(countries, col) for col in ("pmi", "fx_rate", "cpi_yoy", "policy_rate", "tension_index")},
            "capacity_units_sum": capacity, "capacity_ratio": capacity / normal_capacity,
            "lead_time_weeks_mean": _mean(current_supply, "lead_time_weeks"),
            "landed_cost_mean": _mean(current_supply, "landed_cost"),
            "capacity_mean_4": float(supply4.groupby("week")["capacity_units"].sum().mean()),
            "lead_time_mean_4": _mean(supply4, "lead_time_weeks"),
            "demand_mean_4": _mean(demand4, "demand_units"),
            "base_lead_weeks_mean": _mean(eligible, "base_lead_weeks"),
            "normal_capacity_units_sum": normal_capacity,
        }
        for target in weeks:
            target_demand = demand.loc[demand["week"] == target, "demand_units"]
            if len(target_demand) != 1:
                raise ContractError(f"demand: missing/duplicate target {target}/{material}")
            target_tariff = current_tariff.set_index("country")["tariff_rate"].copy()
            announcements = tariffs.loc[
                tariffs["announced_rate"].notna()
                & (tariffs["announced_effective_week"] > cutoff)
                & (tariffs["announced_effective_week"] <= target)
            ]
            for country, announcement in _latest(announcements, ["country"]).set_index("country").iterrows():
                target_tariff.loc[country] = announcement["announced_rate"]
            demand_units = float(target_demand.iloc[0])
            rows.append({
                "target_week": target, "material": material, "cutoff_week": int(cutoff),
                "horizon": target - cutoff, "feature_version": FEATURE_VERSION, **base,
                "target_tariff_mean": float(target_tariff.mean()),
                "tariff_announced_delta_mean": float(target_tariff.mean()) - base["tariff_rate_mean"],
                "demand_units": demand_units,
                "demand_ratio": demand_units / base["demand_mean_4"] if base["demand_mean_4"] > 0 else 1.0,
            })
    result = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    if not np.isfinite(result[list(NUMERIC_FEATURES)].to_numpy(dtype=float)).all():
        raise ContractError("features contain nonfinite values; required history is incomplete")
    return result
