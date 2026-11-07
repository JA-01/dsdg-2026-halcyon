"""Origin-local ordering heuristics; these are not the organizer's naive policy.

Only static eligibility, known demand, forecasts and history through the origin
are used. Every call starts with five times its first week's demand and no
transit, including a private window separated from the cutoff by a gap.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import math
from numbers import Integral, Real

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


@dataclass(frozen=True, kw_only=True)
class OptimizationConfig:
    """Origin-local MILP estimates and proxy inventory-economics settings.

    Diversification is an L1 preference for lane-balanced supplier orders, not
    the evaluator's concentration metric. Forecast prices scale historical
    landed costs only by relative growth, not as landed-cost predictions.
    ``cost_tilt`` > 0 re-splits each positive weekly MILP total toward cheaper
    trailing landed cost after the solve; 0 keeps the MILP's own split.
    """

    trailing_weeks: int = 13
    capacity_quantile: float = 0.25
    lead_quantile: float = 0.75
    base_buffer_weeks: float = 2.0
    risk_buffer_weeks: float = 2.0
    buffer_penalty: float = 0.5
    diversification_penalty: float = 0.2
    holding_rate: float = 0.02
    shortage_multiple: float = 5.0
    salvage_rate: float = 0.7
    cost_tilt: float = 0.0

    def __post_init__(self):
        if (isinstance(self.trailing_weeks, bool)
                or not isinstance(self.trailing_weeks, Integral)
                or self.trailing_weeks <= 0):
            raise ValueError("trailing_weeks must be a positive integer")
        for name in ("capacity_quantile", "lead_quantile", "base_buffer_weeks",
                     "risk_buffer_weeks", "buffer_penalty", "diversification_penalty",
                     "holding_rate", "shortage_multiple", "salvage_rate", "cost_tilt"):
            value = getattr(self, name)
            try:
                valid = (not isinstance(value, bool) and isinstance(value, Real)
                         and math.isfinite(value) and value >= 0)
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"{name} must be finite and nonnegative")
        for name in ("capacity_quantile", "lead_quantile", "salvage_rate"):
            if getattr(self, name) > 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.shortage_multiple <= 0:
            raise ValueError("shortage_multiple must be positive")
        if self.buffer_penalty >= self.shortage_multiple:
            raise ValueError("buffer_penalty must be less than shortage_multiple")


def _optimization_config(config):
    if config is None:
        return OptimizationConfig()
    if isinstance(config, OptimizationConfig):
        return config
    if isinstance(config, Mapping):
        return OptimizationConfig(**dict(config))
    raise TypeError("config must be OptimizationConfig or a mapping of its settings")


def _optimization_suppliers(supply_history, suppliers, cutoff, config):
    # Reuse the heuristic's point-in-time validation and historical mean costs.
    result = _historical_suppliers(supply_history, suppliers, cutoff, config)
    weeks = pd.to_numeric(supply_history.week, errors="raise")
    recent = supply_history.loc[(weeks <= cutoff) & (weeks > cutoff - config.trailing_weeks),
                                ["material", "country", "capacity_units", "lead_time_weeks"]].copy()
    for column in ("capacity_units", "lead_time_weeks"):
        recent[column] = pd.to_numeric(recent[column], errors="raise")
    grouped = recent.groupby(["material", "country"])
    estimates = pd.DataFrame({
        "capacity_units": grouped.capacity_units.quantile(config.capacity_quantile),
        "lead_time_weeks": np.ceil(grouped.lead_time_weeks.quantile(config.lead_quantile)),
    }).reset_index()
    result = result.drop(columns=["capacity_units", "lead_time_weeks"]).merge(
        estimates, on=["material", "country"], validate="one_to_one")
    result["capacity_units"] = np.minimum(result.capacity_units, result.normal_capacity_units)
    return result


def _solve_inventory_milp(demands, prices, risks, sources, config, material):
    """Solve one material with exact lost-sales inventory complementarity."""
    try:
        from scipy.optimize import Bounds, LinearConstraint, milp
    except ImportError as exc:
        raise RuntimeError("inventory_milp requires the pinned SciPy dependency") from exc

    horizon, count = len(demands), len(sources)
    order_count = horizon * count
    stock_start = order_count
    unmet_start = stock_start + horizon
    deviation_start = unmet_start + horizon
    buffer_start = deviation_start + order_count
    binary_start = buffer_start + horizon
    variable_count = binary_start + horizon
    capacities = sources.capacity_units.to_numpy(dtype=float)
    leads = sources.lead_time_weeks.to_numpy(dtype=float)
    costs = sources.landed_cost.to_numpy(dtype=float)
    lane_sizes = sources.groupby("lane").lane.transform("size").to_numpy(dtype=float)
    weights = 1.0 / lane_sizes
    weights /= weights.sum()
    objective = np.zeros(variable_count, dtype=float)
    equalities = np.zeros((horizon, variable_count), dtype=float)
    inequalities = np.zeros((2 * order_count + 3 * horizon, variable_count), dtype=float)
    inequality_rhs = np.zeros(len(inequalities), dtype=float)
    lower = np.zeros(variable_count, dtype=float)
    upper = np.full(variable_count, np.inf, dtype=float)
    integrality = np.zeros(variable_count, dtype=np.uint8)
    integrality[binary_start:] = 1
    upper[binary_start:] = 1.0
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        opening = 5.0 * demands[0]
        total_demand = demands.sum()
        terminal = max(opening - total_demand, 0.0)
        # Terminal stock is fixed and every purchase arrives in the window.
        # Summing balances bounds total purchases by max(total_demand-opening, 0),
        # so max(opening, total_demand) safely bounds stock at every week.
        stock_bound = max(opening, total_demand)
        upper[stock_start:unmet_start] = stock_bound
        reference = costs.mean()
        objective[:order_count] = (prices[:, None] / prices[0] * costs).ravel()
        objective[stock_start:unmet_start] = config.holding_rate * reference
        objective[unmet_start:deviation_start] = config.shortage_multiple * reference
        objective[deviation_start:buffer_start] = config.diversification_penalty * reference
        objective[buffer_start:binary_start] = config.buffer_penalty * reference
        objective[unmet_start - 1] -= config.salvage_rate * reference
        equality_rhs = -demands.copy()
        equality_rhs[0] += opening
        for now in range(horizon):
            equalities[now, stock_start + now] = 1.0
            equalities[now, unmet_start + now] = -1.0
            if now:
                equalities[now, stock_start + now - 1] = -1.0
            upper[unmet_start + now] = demands[now]
            order_slice = slice(now * count, (now + 1) * count)
            upper[order_slice] = capacities
            for supplier in range(count):
                order = now * count + supplier
                arrival = now + leads[supplier]
                if arrival >= horizon:
                    upper[order] = 0.0
                else:
                    equalities[int(arrival), order] = -1.0
                # x_c - w_c * sum(x), and its negative, are bounded by d_c.
                row = 2 * order
                inequalities[row, order_slice] = -weights[supplier]
                inequalities[row, order] += 1.0
                inequalities[row + 1] = -inequalities[row]
                inequalities[row:row + 2, deviation_start + order] = -1.0
            future = demands[now + 1:]
            target = (
                min(future.sum(), (config.base_buffer_weeks + config.risk_buffer_weeks * risks[now])
                    * future[:2].mean())
                if len(future) else 0.0
            )
            row = 2 * order_count + now
            inequalities[row, stock_start + now] = -1.0
            inequalities[row, buffer_start + now] = -1.0
            inequality_rhs[row] = -target
            # Lost sales cannot coexist with stock: U <= demand*z and
            # I <= stock_bound*(1-z), where z is binary.
            row = 2 * order_count + horizon + 2 * now
            inequalities[row, unmet_start + now] = 1.0
            inequalities[row, binary_start + now] = -demands[now]
            inequalities[row + 1, stock_start + now] = 1.0
            inequalities[row + 1, binary_start + now] = stock_bound
            inequality_rhs[row + 1] = stock_bound
    lower[unmet_start - 1] = upper[unmet_start - 1] = terminal
    # Only diversification and buffer penalty slacks are unbounded above.
    finite_required = np.r_[upper[:deviation_start], upper[binary_start:]]
    if (not all(np.isfinite(values).all() for values in
                (objective, equalities, equality_rhs, inequalities, inequality_rhs, lower,
                 finite_required, leads, costs))
            or np.isnan(upper).any() or (upper < lower).any()):
        raise RuntimeError(f"inventory_milp for {material}: nonfinite or invalid MILP coefficients; "
                           "check the scale of demand, historical supply and forecast prices")
    try:
        result = milp(
            objective, integrality=integrality, bounds=Bounds(lower, upper),
            constraints=(
                LinearConstraint(equalities, equality_rhs, equality_rhs),
                LinearConstraint(inequalities, np.full(len(inequalities), -np.inf), inequality_rhs),
            ),
            options={"time_limit": 60.0, "mip_rel_gap": 0.0},
        )
    except Exception as exc:
        raise RuntimeError(f"inventory_milp for {material}: HiGHS could not solve the MILP: {exc}") from exc
    if not result.success or result.status != 0:
        raise RuntimeError(f"inventory_milp for {material}: HiGHS failed "
                           f"(status={result.status}): {result.message}")
    solution = np.asarray(result.x, dtype=float)
    if (solution.shape != (variable_count,) or not np.isfinite(solution).all()
            or not np.isfinite(result.fun)):
        raise RuntimeError(f"inventory_milp for {material}: HiGHS returned a nonfinite or malformed solution")
    tolerance = 1e-7
    # Only negative numerical dust may be removed, never meaningful violations.
    if (solution < -tolerance).any():
        raise RuntimeError(f"inventory_milp for {material}: HiGHS returned negative variables "
                           f"below the numerical tolerance {tolerance}")
    solution = np.maximum(solution, 0.0)
    with np.errstate(over="ignore", invalid="ignore"):
        equality_error = np.abs(equalities @ solution - equality_rhs).max()
        inequality_error = np.maximum(inequalities @ solution - inequality_rhs, 0.0).max()
        bound_error = max(float(np.maximum(lower - solution, 0.0).max()),
                          float(np.maximum(solution - upper, 0.0).max()))
        solved_objective = objective @ solution
        integer_error = np.abs(solution[binary_start:] - np.rint(solution[binary_start:])).max()
        physics_error = np.minimum(solution[stock_start:unmet_start],
                                   solution[unmet_start:deviation_start]).max()
    if (not np.isfinite([equality_error, inequality_error, bound_error, solved_objective,
                         integer_error, physics_error]).all()
            or max(equality_error, inequality_error, bound_error, integer_error, physics_error) > tolerance):
        raise RuntimeError(
            f"inventory_milp for {material}: invalid HiGHS solution after numerical-dust removal; "
            f"balance residual={equality_error:g}, inequality violation={inequality_error:g}, "
            f"bound violation={bound_error:g}, integrality violation={integer_error:g}, "
            f"stock/unmet coexistence={physics_error:g}, tolerance={tolerance:g}"
        )
    return (solution[:order_count].reshape(horizon, count),
            solution[stock_start:unmet_start], solution[unmet_start:deviation_start])


def _tilt_orders(orders, sources, k):
    """Re-split each positive week's MILP total by exp(-k x relative trailing cost).

    Weekly totals are kept; units above an estimated capacity spill to the other
    suppliers by the same preference. Unlike the MILP, a slice may go to a
    supplier whose estimated lead lands after the window: it is then salvaged,
    a cost the tested candidate accepts for row diversification.
    """
    costs = sources.landed_cost.to_numpy(dtype=float)
    capacities = sources.capacity_units.to_numpy(dtype=float)
    weights = np.exp(-k * (costs / costs.mean() - 1.0))
    tilted = orders.copy()
    for now, total in enumerate(orders.sum(axis=1)):
        if total <= 0:
            continue
        units = total * weights / weights.sum()
        free = np.ones(len(weights), dtype=bool)
        while (over := free & (units > capacities)).any():
            spill = float((units[over] - capacities[over]).sum())
            units[over] = capacities[over]
            free &= ~over
            if not free.any():
                break
            units[free] += spill * weights[free] / weights[free].sum()
        tilted[now] = units * total / units.sum()
    return tilted


def optimize_orders(forecasts, demand, supply_history, suppliers, cutoff, target_weeks, *, config=None):
    """Optimize one fresh window using known demand and origin-local estimates.

    Opening stock is five times first-window demand with no transit, even after
    a private-window gap. Recent capacity/lead quantiles and mean landed costs
    use only history through cutoff. No orders arrive beyond the window, and
    terminal stock is fixed to unavoidable opening excess to prevent salvage
    buying. Binary constraints forbid unmet demand while stock remains.
    Quantities remain fractional; a 60-second solver limit or any solver failure
    raises RuntimeError without fallback. ``attrs["projection"]`` contains a
    JSON-safe weekly stock/shortage ledger of the MILP plan without changing
    decision columns; it is omitted when ``cost_tilt`` re-splits that plan.
    """
    config = _optimization_config(config)
    weeks, materials, forecasts, demand, suppliers = _prepare(
        forecasts, demand, suppliers, cutoff, target_weeks)
    suppliers = _optimization_suppliers(supply_history, suppliers, cutoff, config)
    records = []
    projection = []
    for material in materials:
        sources = suppliers.loc[suppliers.material == material].sort_values("country").reset_index(drop=True)
        demands = np.array([demand.loc[(week, material), "demand_units"] for week in weeks], dtype=float)
        prices = np.array([forecasts.loc[(week, material), "price_forecast"] for week in weeks], dtype=float)
        risks = np.array([forecasts.loc[(week, material), "disruption_prob"] for week in weeks], dtype=float)
        orders, stocks, shortages = _solve_inventory_milp(
            demands, prices, risks, sources, config, material)
        if config.cost_tilt:
            orders = _tilt_orders(orders, sources, config.cost_tilt)
        # No units ship on zero-order rows: maximize country diversification
        # without changing the lane-aware preference for positive purchases.
        zero_weights = np.full(len(sources), 1.0 / len(sources))
        for now, week in enumerate(weeks):
            records.append(_record(week, material, orders[now], sources.country, zero_weights))
            projection.append({"week": int(week), "material": material,
                               "projected_stock": float(stocks[now]),
                               "projected_shortage": float(shortages[now])})
    decisions = pd.DataFrame.from_records(records).sort_values(["target_week", "material"]).reset_index(drop=True)
    if not config.cost_tilt:
        decisions.attrs["projection"] = sorted(projection, key=lambda row: (row["week"], row["material"]))
    return decisions


class OptimizedPolicy:
    """Deterministic, origin-local finite-horizon mixed-integer inventory model."""

    policy_id = "inventory_milp"

    def __init__(self, *, config=None):
        self.config = _optimization_config(config)

    def decide(self, data, forecasts, cutoff, target_weeks):
        return optimize_orders(forecasts, data["demand"], data["supply_history"],
                               data["suppliers"], cutoff, target_weeks, config=self.config)
