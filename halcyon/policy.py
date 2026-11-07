"""Origin-local ordering heuristics; these are not the organizer's naive policy.

Only static eligibility, known demand, forecasts and history through the origin
are used. Every call starts with five times its first week's demand and no
transit, including a private window separated from the cutoff by a gap.
"""

from dataclasses import dataclass
import math
from numbers import Integral

import numpy as np
import pandas as pd


from halcyon.constants import COUNTRIES, SHARE_COLUMNS
_EPSILON = 1e-9


@dataclass(frozen=True, kw_only=True)
class PolicyConfig:
    """Explicit inventory-cover and supplier-preference settings.

    Cover is historical maximum lead plus one review week, safety cover,
    disruption probability times risk buffer, and positive forecast price growth
    times price cover. Diversification blends the best cost/lead supplier with
    a smooth eligible-supplier allocation; lane_weight discounts shared lanes.
    """

    trailing_weeks: int = 8
    safety_cover_weeks: float = 1.0
    risk_buffer_weeks: float = 2.0
    price_cover_weeks: float = 2.0
    cost_weight: float = 1.0
    lead_weight: float = 0.2
    diversification_weight: float = 0.75
    lane_weight: float = 1.0

    def __post_init__(self):
        if (isinstance(self.trailing_weeks, bool)
                or not isinstance(self.trailing_weeks, Integral)
                or self.trailing_weeks <= 0):
            raise ValueError("trailing_weeks must be a positive integer")
        for name in ("safety_cover_weeks", "risk_buffer_weeks", "price_cover_weeks",
                     "cost_weight", "lead_weight", "diversification_weight", "lane_weight"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.diversification_weight > 1:
            raise ValueError("diversification_weight must be in [0, 1]")


def _columns(frame, columns, name):
    missing = set(columns).difference(frame.columns)
    if missing:
        raise ValueError(f"{name} missing columns: {sorted(missing)}")


def _unique(frame, keys, name):
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError(f"{name} must have non-null unique keys {keys}")


def _numeric(frame, columns, name, *, positive=False, integers=False):
    for column in columns:
        try:
            values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name}.{column} must be numeric") from exc
        if (not np.isfinite(values).all()
                or (values <= 0 if positive else values < 0).any()
                or (integers and (values != np.floor(values)).any())):
            raise ValueError(f"{name}.{column} has invalid values")
        frame[column] = values


def _prepare(forecasts, demand, suppliers, cutoff, target_weeks):
    weeks = list(target_weeks)
    if (isinstance(cutoff, bool) or not isinstance(cutoff, Integral)
            or not weeks or any(isinstance(w, bool) or not isinstance(w, Integral) for w in weeks)
            or weeks != list(range(weeks[0], weeks[-1] + 1)) or weeks[0] <= cutoff):
        raise ValueError("target_weeks must be a nonempty consecutive increasing window after cutoff")
    _columns(suppliers, ("material", "country", "lane", "normal_capacity_units", "base_lead_weeks"), "suppliers")
    suppliers = suppliers.copy()
    _unique(suppliers, ["material", "country"], "suppliers")
    if (suppliers.empty or not suppliers.country.isin(COUNTRIES).all()
            or not suppliers.material.map(lambda x: isinstance(x, str) and bool(x)).all()
            or not suppliers.lane.map(lambda x: isinstance(x, str) and bool(x)).all()):
        raise ValueError("suppliers requires materials, lanes and known countries")
    _numeric(suppliers, ["normal_capacity_units"], "suppliers")
    _numeric(suppliers, ["base_lead_weeks"], "suppliers", integers=True)
    if (suppliers.groupby("material").normal_capacity_units.sum() <= 0).any():
        raise ValueError("each material requires positive normal capacity")
    materials = sorted(suppliers.material.unique())
    expected = pd.MultiIndex.from_product([weeks, materials], names=["target_week", "material"])
    _columns(forecasts, ("target_week", "material", "disruption_prob", "price_forecast"), "forecasts")
    forecasts = forecasts.copy()
    _unique(forecasts, ["target_week", "material"], "forecasts")
    _numeric(forecasts, ["target_week"], "forecasts", integers=True)
    _numeric(forecasts, ["disruption_prob"], "forecasts")
    _numeric(forecasts, ["price_forecast"], "forecasts", positive=True)
    if (forecasts.disruption_prob > 1).any():
        raise ValueError("forecasts.disruption_prob must be in [0, 1]")
    forecasts = forecasts.set_index(["target_week", "material"])
    if len(forecasts) != len(expected) or set(forecasts.index) != set(expected):
        raise ValueError("forecasts must exactly cover target weeks and static materials")
    _columns(demand, ("week", "material", "demand_units"), "demand")
    demand = demand.copy()
    _unique(demand, ["week", "material"], "demand")
    _numeric(demand, ["week"], "demand", integers=True)
    _numeric(demand, ["demand_units"], "demand")
    demand = demand.set_index(["week", "material"])
    if not set(expected).issubset(set(demand.index)):
        raise ValueError("known demand must cover every target week and material")
    return weeks, materials, forecasts, demand, suppliers


def _historical_suppliers(supply_history, suppliers, cutoff, config):
    _columns(supply_history, ("week", "material", "country", "capacity_units", "lead_time_weeks", "landed_cost"), "supply_history")
    # Filter before validating values or aggregating: even poisoned future truth
    # must not affect a historical-origin policy.
    try:
        observed = supply_history.loc[pd.to_numeric(supply_history.week, errors="raise") <= cutoff].copy()
    except (TypeError, ValueError) as exc:
        raise ValueError("supply_history.week must be numeric") from exc
    _unique(observed, ["week", "material", "country"], "supply_history")
    _numeric(observed, ["week", "lead_time_weeks"], "supply_history", integers=True)
    _numeric(observed, ["capacity_units"], "supply_history")
    _numeric(observed, ["landed_cost"], "supply_history", positive=True)
    eligible = set(zip(suppliers.material, suppliers.country))
    if not set(zip(observed.material, observed.country)).issubset(eligible):
        raise ValueError("supply_history contains ineligible suppliers")
    recent = observed.loc[observed.week > cutoff - config.trailing_weeks]
    stats = recent.groupby(["material", "country"])[["capacity_units", "lead_time_weeks", "landed_cost"]].mean()
    if set(stats.index) != eligible:
        raise ValueError("each eligible supplier requires history in the trailing window")
    result = suppliers.merge(stats.reset_index(), on=["material", "country"], validate="one_to_one")
    result["lead_time_weeks"] = np.ceil(result.lead_time_weeks).astype(int)
    # Do not promise more than static normal capacity or recent observed supply.
    result["capacity_units"] = np.minimum(result.capacity_units, result.normal_capacity_units)
    return result


def _weights(suppliers, config):
    costs = suppliers.landed_cost.to_numpy(dtype=float)
    leads = suppliers.lead_time_weeks.to_numpy(dtype=float)
    penalties = (config.cost_weight * costs / costs.mean()
                 + config.lead_weight * leads / max(1.0, leads.max()))
    lanes = suppliers.groupby("lane").lane.transform("size").to_numpy(dtype=float)
    logits = -penalties - config.lane_weight * np.log(lanes)
    smooth = np.exp(logits - logits.max())
    smooth /= smooth.sum()
    weights = config.diversification_weight * smooth
    weights[int(np.argmin(penalties))] += 1.0 - config.diversification_weight
    return weights


def _needed(stock, arrivals, demands, now, arrival, stop):
    """Lost sales projected before arrival; additional useful units until stop.

    The last review week may be fractional. Its demand is reduced rather than
    multiplying its shortage, so additional units reduce the deficit one-to-one.
    """
    shortage = 0.0
    for week in range(now, min(len(demands), math.ceil(stop))):
        stock += arrivals[week]
        required = demands[week] * min(1.0, max(0.0, stop - week))
        if week >= arrival:
            shortage += max(0.0, required - stock)
        stock = max(0.0, stock - required)
    return shortage


def _record(week, material, orders, countries, zero_weights):
    total = float(sum(orders))
    shares = np.asarray(orders, dtype=float) / total if total > 0 else zero_weights
    result = {"target_week": week, "material": material, "order_units": total}
    result.update(dict.fromkeys(SHARE_COLUMNS, 0.0))
    for country, share in zip(countries, shares):
        result[f"share_{country}"] = float(share)
    return result


def plan_orders(forecasts, demand, supply_history, suppliers, cutoff, target_weeks, *, config=None):
    """Plan a single independent window without future realized supply.

    Inputs use the raw CSV schemas. Forecast keys are target_week/material;
    demand keys are week/material; supply keys are week/material/country.
    Predicted capacity and cost are trailing means, lead is the ceiling of its
    trailing mean. Quantities remain fractional. There is no simulator coupling.
    """
    config = config if config is not None else PolicyConfig()
    weeks, materials, forecasts, demand, suppliers = _prepare(forecasts, demand, suppliers, cutoff, target_weeks)
    suppliers = _historical_suppliers(supply_history, suppliers, cutoff, config)
    records = []
    for material in materials:
        sources = suppliers.loc[suppliers.material == material].sort_values("country").reset_index(drop=True)
        countries = sources.country.tolist()
        weights = _weights(sources, config)
        capacities = sources.capacity_units.to_numpy(dtype=float)
        leads = sources.lead_time_weeks.to_numpy(dtype=int)
        demands = np.array([demand.loc[(w, material), "demand_units"] for w in weeks], dtype=float)
        prices = np.array([forecasts.loc[(w, material), "price_forecast"] for w in weeks], dtype=float)
        risks = np.array([forecasts.loc[(w, material), "disruption_prob"] for w in weeks], dtype=float)
        stock = 5.0 * demands[0]
        arrivals = np.zeros(len(weeks), dtype=float)
        max_lead = int(leads.max())
        for now, week in enumerate(weeks):
            outlook_end = min(len(weeks), now + max_lead + 2)
            growth = max(0.0, float(prices[now:outlook_end].mean() / prices[now] - 1.0))
            cover = (max_lead + 1 + config.safety_cover_weeks
                     + config.risk_buffer_weeks * risks[now]
                     + config.price_cover_weeks * min(growth, 1.0))
            stop = min(float(len(weeks)), now + cover)
            orders = np.zeros(len(sources), dtype=float)
            remaining = capacities.copy()
            arrival_weeks = now + leads
            # Weighted capped allocation, recomputing predicted shortfalls after
            # each slice. This avoids double-counting pipeline or buying units
            # only useful as terminal salvage, including unequal supplier leads.
            while True:
                needs = np.array([
                    _needed(stock, arrivals, demands, now, int(a), stop)
                    if a < stop and a < len(weeks) and remaining[i] > _EPSILON else 0.0
                    for i, a in enumerate(arrival_weeks)
                ])
                active = needs > _EPSILON
                if not active.any():
                    break
                active_weights = weights * active
                if active_weights.sum() <= 0:
                    # Greedy diversification=0 still uses a second supplier when
                    # its preferred supplier is capacity constrained.
                    active_weights = active.astype(float)
                proposals = needs.max() * active_weights / active_weights.sum()
                placed = 0.0
                for i in np.flatnonzero(active):
                    needed = _needed(stock, arrivals, demands, now, int(arrival_weeks[i]), stop)
                    units = min(float(proposals[i]), float(remaining[i]), needed)
                    if units > 0:
                        orders[i] += units
                        remaining[i] -= units
                        arrivals[arrival_weeks[i]] += units
                        placed += units
                if placed <= _EPSILON:
                    break
            records.append(_record(week, material, orders, countries, weights))
            stock = max(0.0, stock + arrivals[now] - demands[now])
            arrivals[now] = 0.0
    return pd.DataFrame.from_records(records).sort_values(["target_week", "material"]).reset_index(drop=True)


class InventoryPolicy:
    """Deterministic forecast-driven finite-horizon inventory-cover heuristic."""

    policy_id = "inventory_cover"

    def __init__(self, *, config=None):
        self.config = config if config is not None else PolicyConfig()

    def decide(self, data, forecasts, cutoff, target_weeks):
        return plan_orders(forecasts, data["demand"], data["supply_history"],
                           data["suppliers"], cutoff, target_weeks, config=self.config)


class NaivePolicy:
    """Origin-local demand orders from the largest normal-capacity supplier.

    This intentionally is not claimed equivalent to the organizer sample. It
    orders each known week's demand, without realized future supply or state.
    """

    policy_id = "local_origin_naive"

    def decide(self, data, forecasts, cutoff, target_weeks):
        weeks, materials, _, demand, suppliers = _prepare(
            forecasts, data["demand"], data["suppliers"], cutoff, target_weeks)
        records = []
        for material in materials:
            sources = suppliers.loc[suppliers.material == material].copy()
            sources["_country_rank"] = sources.country.map({c: i for i, c in enumerate(COUNTRIES)})
            sources = sources.sort_values("_country_rank")
            weights = np.zeros(len(sources), dtype=float)
            weights[int(np.argmax(sources.normal_capacity_units.to_numpy()))] = 1.0
            for week in weeks:
                units = float(demand.loc[(week, material), "demand_units"])
                records.append(_record(week, material, weights * units, sources.country, weights))
        return pd.DataFrame.from_records(records).sort_values(["target_week", "material"]).reset_index(drop=True)


Policy = InventoryPolicy
