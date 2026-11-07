"""Pandas-only, evaluator-side inventory economics; not the official score."""

from dataclasses import asdict, dataclass
from numbers import Integral
from collections.abc import Mapping

import numpy as np
import pandas as pd


from halcyon.constants import COUNTRIES, SHARE_COLUMNS, SHARE_SUM_TOLERANCE


@dataclass(frozen=True)
class SimulatorConfig:
    """Explicit assumptions where the competition does not fully specify timing."""

    initial_stock_mode: str = "first_week"
    holding_rate: float = 0.02
    shortage_multiple: float = 5.0
    salvage_rate: float = 0.7
    quantity_rounding: str = "fractional"
    holding_timing: str = "end_stock"

    def __post_init__(self):
        if self.initial_stock_mode not in ("first_week", "five_week_sum"):
            raise ValueError("initial_stock_mode must be first_week or five_week_sum")
        if self.quantity_rounding not in ("fractional", "floor"):
            raise ValueError("quantity_rounding must be fractional or floor")
        if self.holding_timing not in ("end_stock", "pre_demand"):
            raise ValueError("holding_timing must be end_stock or pre_demand")
        for field in ("holding_rate", "shortage_multiple", "salvage_rate"):
            value = getattr(self, field)
            if not isinstance(value, (int, float, np.number)) or not np.isfinite(value) or value < 0:
                raise ValueError(f"{field} must be finite and nonnegative")
        if self.salvage_rate > 1:
            raise ValueError("salvage_rate must be at most 1")


@dataclass(frozen=True)
class SimulationResult:
    metrics: pd.DataFrame
    material_metrics: pd.DataFrame
    weekly: pd.DataFrame
    assumptions: dict
    score_status: str = "proxy"


def _columns(frame, name, columns):
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    if not frame.columns.is_unique:
        raise ValueError(f"{name} has duplicate columns")
    missing = set(columns).difference(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {sorted(missing)}")


def _numbers(frame, name, columns, *, integer=False):
    for column in columns:
        try:
            values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name}.{column} must be numeric") from exc
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"{name}.{column} must be finite and nonnegative")
        if integer and ((values != np.floor(values)).any() or (values >= 2**63).any()):
            raise ValueError(f"{name}.{column} must contain representable integers")
        frame[column] = values.astype(np.int64) if integer else values


def _window_frame(frame, name, columns, week_column, start, end):
    _columns(frame, name, columns)
    frame = frame.loc[:, list(columns)].copy()
    _numbers(frame, name, (week_column,), integer=True)
    return frame.loc[frame[week_column].between(start, end)].copy()


def _coverage(frame, name, keys, expected):
    if frame.loc[:, list(keys)].isna().any().any():
        raise ValueError(f"{name} has null keys")
    if frame.duplicated(list(keys)).any():
        row = frame.loc[frame.duplicated(list(keys), keep=False), list(keys)].iloc[0]
        raise ValueError(f"{name} has duplicate key {tuple(row)}")
    actual = pd.MultiIndex.from_frame(frame.loc[:, list(keys)])
    missing = expected.difference(actual)
    extra = actual.difference(expected)
    if len(missing) or len(extra):
        raise ValueError(
            f"{name} coverage mismatch: missing={list(missing[:3])}, extra={list(extra[:3])}"
        )


def _aggregate(frame, window_id, material):
    totals = (
        "demand_units", "fulfilled_units", "stockout_units", "ordered_units",
        "filled_order_units", "cancelled_units", "purchase_cost", "holding_cost",
        "shortage_cost", "salvage_credit", "total_cost",
    )
    result = {"window_id": window_id, "material": material}
    result.update({column: float(frame[column].sum()) for column in totals})
    shock = frame.loc[frame["shock_recovery"]]
    shock_demand = float(shock["demand_units"].sum())
    shock_fulfilled = float(shock["fulfilled_units"].sum())
    result.update(
        fill_rate=(result["fulfilled_units"] / result["demand_units"]
                   if result["demand_units"] else np.nan),
        shock_demand_units=shock_demand,
        shock_fulfilled_units=shock_fulfilled,
        shock_fill_rate=shock_fulfilled / shock_demand if shock_demand else np.nan,
        mean_concentration=float(frame["concentration"].mean()),
        mean_diversification=float(frame["diversification"].mean()),
    )
    return result


def simulate_window(
    decisions, demand, supply_history, suppliers, outcomes, start_week, end_week,
    *, reference_costs=None, config=None,
):
    """Evaluate one fresh window against realized supply and shock labels.

    Decisions use ``target_week``; the other time-varying inputs use ``week``.
    Every static supplier material must have one decision and demand per week,
    and every eligible supplier must have realized supply per week. Inputs may
    contain other weeks; only the evaluated window and needed initialization /
    four-week shock lookback are consumed. Outcomes must cover every material
    from max(1, start_week - 4) through end_week, so an omitted prior shock
    cannot silently corrupt recovery metrics.

    Reference costs default to the unweighted mean realized supplier-week landed
    cost *inside this window*, an evaluator-only hindsight proxy, never a policy
    input. Explicit per-material references must be positive. Five-week-sum
    initialization requires demand for start_week through start_week + 4, even
    for a shorter evaluation window. Initial inventory is not purchased/charged.
    """
    config = SimulatorConfig() if config is None else config
    if not isinstance(config, SimulatorConfig):
        raise TypeError("config must be SimulatorConfig")
    for name, value in (("start_week", start_week), ("end_week", end_week)):
        if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if end_week < start_week:
        raise ValueError("end_week must not precede start_week")
    start_week, end_week = int(start_week), int(end_week)
    weeks = range(start_week, end_week + 1)
    window_id = f"{start_week}-{end_week}"

    _columns(suppliers, "suppliers", ("material", "country"))
    supplier_keys = suppliers.loc[:, ["material", "country"]].copy()
    if supplier_keys.empty or supplier_keys.isna().any().any():
        raise ValueError("suppliers must contain non-null material/country keys")
    if supplier_keys.duplicated().any():
        raise ValueError("suppliers has duplicate material/country keys")
    if not supplier_keys["country"].isin(COUNTRIES).all():
        raise ValueError("suppliers contains an unknown country")
    if not supplier_keys["material"].map(lambda value: isinstance(value, str) and bool(value)).all():
        raise ValueError("suppliers.material must contain nonempty strings")
    materials = sorted(supplier_keys["material"].unique())
    eligible = {
        material: tuple(supplier_keys.loc[supplier_keys["material"].eq(material), "country"])
        for material in materials
    }
    expected = pd.MultiIndex.from_product([weeks, materials], names=["week", "material"])
    decision_frame = _window_frame(
        decisions, "decisions", ("target_week", "material", "order_units", *SHARE_COLUMNS),
        "target_week", start_week, end_week,
    )
    _coverage(decision_frame, "decisions", ("target_week", "material"), expected)
    _numbers(decision_frame, "decisions", ("order_units", *SHARE_COLUMNS))
    shares = decision_frame.loc[:, list(SHARE_COLUMNS)].to_numpy()
    if (shares > 1).any() or (np.abs(shares.sum(axis=1) - 1) > SHARE_SUM_TOLERANCE).any():
        raise ValueError("decisions shares must be in [0, 1] and sum to 1 within 1e-6")
    for row in decision_frame.itertuples(index=False):
        for country in COUNTRIES:
            if country not in eligible[row.material] and getattr(row, f"share_{country}") != 0:
                raise ValueError(f"decisions has ineligible share for {row.material}/{country}")

    demand_end = max(end_week, start_week + 4) if config.initial_stock_mode == "five_week_sum" else end_week
    demand_frame = _window_frame(
        demand, "demand", ("week", "material", "demand_units"), "week", start_week, demand_end,
    )
    demand_expected = pd.MultiIndex.from_product(
        [range(start_week, demand_end + 1), materials], names=["week", "material"],
    )
    _coverage(demand_frame, "demand", ("week", "material"), demand_expected)
    _numbers(demand_frame, "demand", ("demand_units",))
    supply_frame = _window_frame(
        supply_history, "supply_history",
        ("week", "material", "country", "capacity_units", "lead_time_weeks", "landed_cost"),
        "week", start_week, end_week,
    )
    supply_expected = pd.MultiIndex.from_tuples(
        [(week, material, country) for week in weeks for material in materials
         for country in eligible[material]], names=["week", "material", "country"],
    )
    _coverage(supply_frame, "supply_history", ("week", "material", "country"), supply_expected)
    _numbers(supply_frame, "supply_history", ("capacity_units", "landed_cost"))
    _numbers(supply_frame, "supply_history", ("lead_time_weeks",), integer=True)
    outcome_frame = _window_frame(
        outcomes, "outcomes", ("week", "material", "disrupted"),
        "week", max(1, start_week - 4), end_week,
    )
    outcome_expected = pd.MultiIndex.from_product(
        [range(max(1, start_week - 4), end_week + 1), materials],
        names=["week", "material"],
    )
    _coverage(outcome_frame, "outcomes", ("week", "material"), outcome_expected)
    _numbers(outcome_frame, "outcomes", ("disrupted",))
    if not outcome_frame["disrupted"].isin([0, 1]).all():
        raise ValueError("outcomes.disrupted must be 0 or 1")

    if reference_costs is None:
        references = supply_frame.groupby("material")["landed_cost"].mean().to_dict()
        reference_source = "window_mean_realized_landed_cost_evaluator_only"
    else:
        if isinstance(reference_costs, pd.Series):
            if not reference_costs.index.is_unique:
                raise ValueError("reference_costs has duplicate materials")
            reference_costs = reference_costs.to_dict()
        if not isinstance(reference_costs, Mapping):
            raise TypeError("reference_costs must be a mapping or pandas Series")
        if set(reference_costs) != set(materials):
            raise ValueError("reference_costs must cover exactly the supplier materials")
        references = {}
        for material in materials:
            try:
                value = float(reference_costs[material])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"reference_costs[{material}] must be positive and finite") from exc
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"reference_costs[{material}] must be positive and finite")
            references[material] = value
        reference_source = "explicit_evaluator_reference"

    demand_values = demand_frame.set_index(["week", "material"])["demand_units"].to_dict()
    supply_values = {
        (row.week, row.material, row.country):
        (row.capacity_units, row.lead_time_weeks, row.landed_cost)
        for row in supply_frame.itertuples(index=False)
    }
    decision_values = {
        (row.target_week, row.material): row for row in decision_frame.itertuples(index=False)
    }
    shock_weeks = {
        (week, row.material)
        for row in outcome_frame.loc[outcome_frame["disrupted"].eq(1)].itertuples(index=False)
        for week in range(max(start_week, row.week), min(end_week, row.week + 4) + 1)
    }
    initial_stock = {}
    records = []
    for material in materials:
        reference = references[material]
        stock = (
            5 * demand_values[start_week, material]
            if config.initial_stock_mode == "first_week"
            else sum(demand_values[week, material] for week in range(start_week, start_week + 5))
        )
        initial_stock[material] = float(stock)
        transit = {}
        for week in weeks:
            decision = decision_values[week, material]
            filled_order = purchase = 0.0
            for country in eligible[material]:
                request = decision.order_units * getattr(decision, f"share_{country}")
                if config.quantity_rounding == "floor":
                    request = float(np.floor(request))
                capacity, lead, cost = supply_values[week, material, country]
                filled = min(request, capacity)
                filled_order += filled
                purchase += filled * cost
                arrival = week + int(lead)
                transit[arrival] = transit.get(arrival, 0.0) + filled
            stock += transit.pop(week, 0.0)
            demand_units = demand_values[week, material]
            fulfilled = min(stock, demand_units)
            holding_stock = stock if config.holding_timing == "pre_demand" else stock - fulfilled
            stock -= fulfilled
            stockout = demand_units - fulfilled
            ending_transit = sum(transit.values())
            holding = holding_stock * reference * config.holding_rate
            shortage = stockout * reference * config.shortage_multiple
            salvage = (stock + ending_transit) * reference * config.salvage_rate if week == end_week else 0.0
            concentration = sum(getattr(decision, column) ** 2 for column in SHARE_COLUMNS)
            supplier_count = len(eligible[material])
            diversification = (1 - concentration) / (1 - 1 / supplier_count) if supplier_count > 1 else 0.0
            records.append({
                "window_id": window_id, "week": week, "material": material,
                "demand_units": demand_units, "fulfilled_units": fulfilled,
                "stockout_units": stockout, "ending_stock": stock,
                "ending_transit": ending_transit, "ordered_units": decision.order_units,
                "filled_order_units": filled_order,
                "cancelled_units": max(0.0, decision.order_units - filled_order),
                "purchase_cost": purchase, "holding_cost": holding,
                "shortage_cost": shortage, "salvage_credit": salvage,
                "total_cost": purchase + holding + shortage - salvage,
                "shock_recovery": (week, material) in shock_weeks,
                "concentration": concentration, "diversification": diversification,
            })
    weekly = pd.DataFrame.from_records(records).sort_values(["week", "material"]).reset_index(drop=True)
    material_metrics = pd.DataFrame([
        _aggregate(weekly.loc[weekly["material"].eq(material)], window_id, material)
        for material in materials
    ])
    metrics = pd.DataFrame([_aggregate(weekly, window_id, "__all__")])
    assumptions = {
        **asdict(config),
        "reference_cost_source": reference_source,
        "reference_costs": {material: float(references[material]) for material in materials},
        "initial_stock_units": initial_stock,
        "inventory_reset": "fresh initial stock and no transit on every call; initial stock is free",
        "timing": "order t arrives t + lead; zero-lead and prior arrivals precede demand; holding_timing selects end-stock or after-arrivals/pre-demand stock",
        "terminal_salvage": "final ending stock plus all transit, including arrivals beyond window; no transit holding",
        "capacity": "independent supplier caps; cancellations unpaid and never reassigned",
        "rounding": "floor applies to each supplier request; cancelled_units includes discarded fractions; ordered_units is submitted order",
        "share_tolerance": SHARE_SUM_TOLERANCE,
        "share_handling": "shares used unchanged; tolerance can produce sub-tolerance quantity differences",
        "shock_recovery": "disrupted week plus four subsequent weeks; complete labels required from max(1, start_week - 4)",
        "diversification": "(1 - sum(shares**2)) / (1 - 1 / eligible_supplier_count); zero for one supplier",
        "aggregation": "costs/units summed; demand-weighted fill; unweighted material-week mean concentration/diversification",
        "undefined_fill": "NaN when the relevant demand denominator is zero",
        "score": "economics proxy only; no official F, P, R or hindsight/naive skill normalizers",
    }
    return SimulationResult(metrics, material_metrics, weekly, assumptions)
