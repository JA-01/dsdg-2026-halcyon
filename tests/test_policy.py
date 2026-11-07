"""Behavioral fixtures for origin-local policies, without simulator coupling."""

from dataclasses import asdict, replace
import json

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from halcyon.constants import COUNTRIES, MATERIALS, SHARE_COLUMNS
from halcyon.policy import (
    InventoryPolicy, NaivePolicy, OptimizationConfig, OptimizedPolicy, PolicyConfig,
    optimize_orders, plan_orders,
)


def fixture_tables(*, materials=("lithium",), weeks=range(11, 37), lead=2, capacity=12.0):
    suppliers = pd.DataFrame([
        {"material": material, "country": country, "lane": lane,
         "normal_capacity_units": capacity, "base_lead_weeks": lead}
        for material in materials
        for country, lane in (("KES", "MERROW"), ("SUN", "MERROW"), ("ORI", "SOUTH"))
    ])
    history = pd.DataFrame([
        {"week": week, "material": row.material, "country": row.country,
         "capacity_units": capacity, "lead_time_weeks": lead, "landed_cost": 10.0}
        for week in range(1, 11) for row in suppliers.itertuples(index=False)
    ])
    demand = pd.DataFrame([
        {"week": week, "material": material, "demand_units": 10.0}
        for week in weeks for material in materials
    ])
    return {"suppliers": suppliers, "supply_history": history, "demand": demand}


def forecast_frame(weeks=range(11, 24), materials=("lithium",), risk=0.0):
    return pd.DataFrame([
        {"target_week": week, "material": material,
         "disruption_prob": risk, "price_forecast": 10.0}
        for week in weeks for material in materials
    ])


def plan(tables, forecasts=None, weeks=range(11, 24), config=None):
    forecasts = forecast_frame(weeks) if forecasts is None else forecasts
    return plan_orders(forecasts, tables["demand"], tables["supply_history"],
                       tables["suppliers"], 10, list(weeks), config=config)


def assert_feasible(decisions, tables):
    assert np.isfinite(decisions[["order_units", *SHARE_COLUMNS]].to_numpy()).all()
    assert (decisions.order_units >= 0).all()
    np.testing.assert_allclose(decisions[list(SHARE_COLUMNS)].sum(axis=1), 1, atol=1e-12)
    for material, rows in decisions.groupby("material"):
        sources = tables["suppliers"].query("material == @material").set_index("country")
        for country in COUNTRIES:
            shares = rows[f"share_{country}"]
            assert shares.between(0, 1).all()
            if country not in sources.index:
                assert (shares == 0).all()
            else:
                units = rows.order_units * shares
                assert (units <= sources.loc[country, "normal_capacity_units"] + 1e-8).all()


@pytest.mark.parametrize("policy_type", [InventoryPolicy, NaivePolicy])
def test_complete_ten_material_windows_and_valid_zero_orders(policy_type):
    tables = fixture_tables(materials=MATERIALS)
    policy = policy_type()
    blocks = []
    for weeks in (range(11, 24), range(24, 37)):
        block = policy.decide(tables, forecast_frame(weeks, MATERIALS), 10, list(weeks))
        assert len(block) == 130
        assert not block.duplicated(["target_week", "material"]).any()
        assert_feasible(block, tables)
        blocks.append(block)
    assert len(pd.concat(blocks)) == 260
    if policy_type is InventoryPolicy:
        assert (blocks[0].order_units == 0).any()


@pytest.mark.parametrize("policy_type", [InventoryPolicy, NaivePolicy])
def test_all_zero_demand_keeps_normalized_eligible_shares(policy_type):
    tables = fixture_tables()
    tables["demand"]["demand_units"] = 0.0
    decisions = policy_type().decide(tables, forecast_frame(), 10, list(range(11, 24)))
    assert decisions.order_units.eq(0).all()
    assert_feasible(decisions, tables)


@pytest.mark.parametrize("policy_type", [InventoryPolicy, NaivePolicy])
def test_future_supply_poison_cannot_change_origin_decisions(policy_type):
    tables = fixture_tables()
    expected = policy_type().decide(tables, forecast_frame(), 10, list(range(11, 24)))
    poisoned = tables.copy()
    future = tables["supply_history"].iloc[:3].copy()
    future["week"] = 11
    future["material"] = "not_an_eligible_material"
    future["capacity_units"] = np.nan
    future["landed_cost"] = -1e12
    future["lead_time_weeks"] = 10000
    # Future duplicates and bad truth are irrelevant, not just future means.
    poisoned["supply_history"] = pd.concat([tables["supply_history"], future, future], ignore_index=True)
    actual = policy_type().decide(poisoned, forecast_frame(), 10, list(range(11, 24)))
    assert_frame_equal(actual, expected)


def test_private_gap_and_repeated_calls_reset_stock_and_transit():
    tables = fixture_tables()
    policy = InventoryPolicy()
    first = policy.decide(tables, forecast_frame(), 10, list(range(11, 24)))
    private = policy.decide(tables, forecast_frame(range(24, 37)), 10, list(range(24, 37)))
    private["target_week"] -= 13
    assert_frame_equal(private, first)
    assert_frame_equal(policy.decide(tables, forecast_frame(), 10, list(range(11, 24))), first)
    assert first.iloc[0].order_units == 0


def test_initial_stock_is_five_times_each_windows_first_week_demand():
    tables = fixture_tables(weeks=range(11, 15))
    tables["demand"].loc[tables["demand"].week == 11, "demand_units"] = 20.0
    # Fresh 100 units cover 20+10+10+10; no future demand average is used.
    decisions = plan(tables, weeks=range(11, 15))
    assert (decisions.order_units == 0).all()


def test_naive_is_known_weekly_demand_on_largest_static_supplier():
    tables = fixture_tables()
    tables["suppliers"].loc[tables["suppliers"].country == "SUN", "normal_capacity_units"] = 25
    tables["demand"].loc[tables["demand"].week == 13, "demand_units"] = 15
    decisions = NaivePolicy().decide(tables, forecast_frame(), 10, list(range(11, 24)))
    assert (decisions.share_SUN == 1).all()
    assert decisions.loc[decisions.target_week == 13, "order_units"].item() == 15
    assert decisions.loc[decisions.target_week != 13, "order_units"].eq(10).all()
    assert NaivePolicy.policy_id == "local_origin_naive"
    # The equal-capacity tie uses canonical country order, not input row order.
    tied = fixture_tables()
    tied["suppliers"] = tied["suppliers"].iloc[::-1]
    tie_decisions = NaivePolicy().decide(tied, forecast_frame(), 10, list(range(11, 24)))
    assert (tie_decisions.share_KES == 1).all()


def test_capacity_caps_and_no_future_arrival_orders():
    tables = fixture_tables(capacity=3)
    tables["supply_history"].loc[tables["supply_history"].country == "KES", "capacity_units"] = 1
    decisions = plan(tables, forecast_frame(risk=1))
    assert_feasible(decisions, tables)
    assert (decisions.order_units * decisions.share_KES <= 1 + 1e-8).all()
    assert decisions.loc[decisions.target_week >= 22, "order_units"].eq(0).all()
    too_slow = fixture_tables(lead=20)
    assert plan(too_slow).order_units.eq(0).all()


def test_terminal_stock_reduction_buys_only_demand_not_salvage():
    tables = fixture_tables()
    decisions = plan(tables, forecast_frame(risk=1))
    arrivals = {week: 0.0 for week in range(11, 24)}
    stock = 50.0
    lost = 0.0
    for row in decisions.itertuples(index=False):
        for country in ("KES", "SUN", "ORI"):
            units = row.order_units * getattr(row, f"share_{country}")
            if units > 1e-8:
                assert row.target_week + 2 <= 23
                arrivals[row.target_week + 2] += units
        stock += arrivals[row.target_week]
        lost += max(0, 10 - stock)
        stock = max(0, stock - 10)
    assert lost == pytest.approx(0, abs=1e-8)
    assert stock == pytest.approx(0, abs=1e-8)
    assert decisions.order_units.sum() == pytest.approx(80, abs=1e-8)


def test_unequal_leads_do_not_double_count_pipeline_or_terminal_need():
    tables = fixture_tables(capacity=100)
    tables["supply_history"].loc[tables["supply_history"].country == "KES", "lead_time_weeks"] = 1
    tables["supply_history"].loc[tables["supply_history"].country == "ORI", "lead_time_weeks"] = 7
    decisions = plan(tables, forecast_frame(risk=1))
    arrivals = np.zeros(13)
    stock = 50.0
    leads = {"KES": 1, "SUN": 2, "ORI": 7}
    lost = 0.0
    for now, row in enumerate(decisions.itertuples(index=False)):
        for country, lead in leads.items():
            units = row.order_units * getattr(row, f"share_{country}")
            if units > 1e-8:
                assert now + lead < 13
                arrivals[now + lead] += units
        stock += arrivals[now]
        lost += max(0, 10 - stock)
        stock = max(0, stock - 10)
    assert decisions.order_units.sum() <= 80 + 1e-8
    assert stock == pytest.approx(0, abs=1e-8)
    assert decisions.order_units.sum() + lost == pytest.approx(80, abs=1e-8)


def test_lane_weight_diversifies_correlated_suppliers_not_just_country_count():
    tables = fixture_tables(capacity=100)
    config = PolicyConfig(diversification_weight=1, lane_weight=0)
    uniform = plan(tables, forecast_frame(risk=1), config=config)
    lane_aware = plan(tables, forecast_frame(risk=1), config=replace(config, lane_weight=1))
    row = lane_aware.loc[lane_aware.order_units > 0].iloc[0]
    original = uniform.loc[uniform.order_units > 0].iloc[0]
    assert row.share_ORI > original.share_ORI
    assert row.share_KES == pytest.approx(row.share_SUN)
    assert row.share_KES + row.share_SUN == pytest.approx(row.share_ORI)


def test_cost_and_lead_preferences_and_diversification_are_used():
    tables = fixture_tables(capacity=100)
    tables["supply_history"].loc[tables["supply_history"].country == "ORI", "landed_cost"] = 30
    tables["supply_history"].loc[tables["supply_history"].country == "SUN", "lead_time_weeks"] = 4
    config = PolicyConfig(diversification_weight=1, lane_weight=0, cost_weight=2, lead_weight=1)
    diversified = plan(tables, forecast_frame(risk=1), config=config)
    row = diversified.loc[diversified.order_units > 0].iloc[0]
    assert row.share_KES > row.share_ORI
    assert row.share_KES > row.share_SUN
    greedy = plan(tables, forecast_frame(risk=1), config=replace(config, diversification_weight=0))
    assert greedy.loc[greedy.order_units > 0, "share_KES"].eq(1).all()


def test_demand_and_risk_and_price_outlook_change_ordering():
    tables = fixture_tables(capacity=100)
    low_risk = plan(tables)
    high_risk = plan(tables, forecast_frame(risk=1))
    assert high_risk.iloc[0].order_units > low_risk.iloc[0].order_units
    rising_prices = forecast_frame()
    rising_prices.loc[rising_prices.target_week > 11, "price_forecast"] = 30
    price_plan = plan(tables, rising_prices)
    assert price_plan.iloc[0].order_units > low_risk.iloc[0].order_units
    larger_demand = {name: frame.copy() for name, frame in tables.items()}
    larger_demand["demand"].loc[larger_demand["demand"].week >= 17, "demand_units"] = 20
    assert plan(larger_demand).order_units.sum() > low_risk.order_units.sum()


def test_trailing_window_changes_estimates_but_old_history_does_not():
    tables = fixture_tables(capacity=100)
    config = PolicyConfig(trailing_weeks=2)
    expected = plan(tables, forecast_frame(risk=1), config=config)
    tables["supply_history"].loc[tables["supply_history"].week < 9, "capacity_units"] = 0
    assert_frame_equal(plan(tables, forecast_frame(risk=1), config=config), expected)
    tables["supply_history"].loc[tables["supply_history"].week >= 9, "capacity_units"] = 0
    assert plan(tables, forecast_frame(risk=1), config=config).order_units.eq(0).all()


@pytest.mark.parametrize("error", ["missing_forecast", "duplicate_forecast", "extra_forecast",
                                    "missing_demand", "duplicate_demand", "duplicate_supplier",
                                    "unknown_supplier", "duplicate_history", "missing_history",
                                    "nan_price", "bad_risk"])
def test_rejects_incomplete_ambiguous_or_invalid_inputs(error):
    tables = fixture_tables()
    forecasts = forecast_frame()
    if error == "missing_forecast":
        forecasts = forecasts.iloc[1:]
    elif error == "duplicate_forecast":
        forecasts = pd.concat([forecasts, forecasts.iloc[:1]])
    elif error == "extra_forecast":
        forecasts = pd.concat([forecasts, forecast_frame(range(24, 25))])
    elif error == "missing_demand":
        tables["demand"] = tables["demand"].iloc[1:]
    elif error == "duplicate_demand":
        tables["demand"] = pd.concat([tables["demand"], tables["demand"].iloc[:1]])
    elif error == "duplicate_supplier":
        tables["suppliers"] = pd.concat([tables["suppliers"], tables["suppliers"].iloc[:1]])
    elif error == "unknown_supplier":
        tables["suppliers"].loc[0, "country"] = "UNKNOWN"
    elif error == "duplicate_history":
        tables["supply_history"] = pd.concat([tables["supply_history"], tables["supply_history"].iloc[:1]])
    elif error == "missing_history":
        tables["supply_history"] = tables["supply_history"].query("country != 'ORI'")
    elif error == "nan_price":
        forecasts.loc[0, "price_forecast"] = np.nan
    elif error == "bad_risk":
        forecasts.loc[0, "disruption_prob"] = 1.1
    with pytest.raises(ValueError):
        plan(tables, forecasts)


@pytest.mark.parametrize("weeks", [[], [11, 11], [11, 13], [12, 11], [10, 11], [11.0, 12.0]])
def test_rejects_invalid_window_identity(weeks):
    with pytest.raises(ValueError):
        plan(fixture_tables(), weeks=weeks)


@pytest.mark.parametrize("kwargs", [{"trailing_weeks": 0}, {"trailing_weeks": 1.5},
                                   {"cost_weight": -1}, {"risk_buffer_weeks": np.nan},
                                   {"diversification_weight": 1.1}])
def test_rejects_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        PolicyConfig(**kwargs)


def test_policy_does_not_mutate_inputs():
    tables = fixture_tables()
    originals = {name: frame.copy(deep=True) for name, frame in tables.items()}
    forecasts = forecast_frame()
    forecast_original = forecasts.copy(deep=True)
    plan(tables, forecasts)
    for name, frame in tables.items():
        assert_frame_equal(frame, originals[name])
    assert_frame_equal(forecasts, forecast_original)


def economic_config(**overrides):
    """Turn off preference terms so the economic optimum is hand-calculable."""
    values = {
        "base_buffer_weeks": 0,
        "risk_buffer_weeks": 0,
        "buffer_penalty": 0,
        "diversification_penalty": 0,
        "holding_rate": 0,
    }
    values.update(overrides)
    return OptimizationConfig(**values)


def optimized_plan(tables, forecasts=None, weeks=range(11, 24), config=None):
    forecasts = forecast_frame(weeks) if forecasts is None else forecasts
    return optimize_orders(
        forecasts, tables["demand"], tables["supply_history"],
        tables["suppliers"], 10, list(weeks),
        config=economic_config() if config is None else config,
    )


def source_units(decisions, country):
    return decisions.order_units.to_numpy() * decisions[f"share_{country}"].to_numpy()


def replay_optimized_plan(decisions, tables, *, leads, capacities):
    """Reconstruct the predicted flow from public decisions, not solver attrs."""
    assert_feasible(decisions, tables)
    weeks = decisions.target_week.tolist()
    assert weeks == sorted(set(weeks))
    demand = tables["demand"].set_index(["week", "material"]).demand_units
    material = decisions.material.unique().item()
    needed = np.array([demand.loc[(week, material)] for week in weeks], dtype=float)
    arrivals = np.zeros(len(weeks))
    for country in COUNTRIES:
        units = source_units(decisions, country)
        if country not in leads:
            np.testing.assert_allclose(units, 0, atol=1e-8)
            continue
        assert (units <= capacities[country] + 1e-8).all()
        for now, quantity in enumerate(units):
            if quantity > 1e-8:
                arrival = now + leads[country]
                assert arrival < len(weeks), "orders must not arrive after the horizon"
                arrivals[arrival] += quantity
    stock = 5 * needed[0]
    stocks, shortages = [], []
    for arriving, required in zip(arrivals, needed):
        available = stock + arriving
        unmet = max(0.0, required - available)
        stock = max(0.0, available - required)
        assert -1e-8 <= unmet <= required + 1e-8
        stocks.append(stock)
        shortages.append(unmet)
    np.testing.assert_allclose(
        np.diff(np.r_[5 * needed[0], stocks]),
        arrivals + shortages - needed,
        atol=1e-8,
    )
    assert stocks[-1] == pytest.approx(max(5 * needed[0] - needed.sum(), 0), abs=1e-8)
    projection = pd.DataFrame(decisions.attrs["projection"])
    projection = projection.loc[projection.material == material].sort_values("week")
    assert projection.week.tolist() == weeks
    np.testing.assert_allclose(projection.projected_stock, stocks, atol=1e-8)
    np.testing.assert_allclose(projection.projected_shortage, shortages, atol=1e-8)
    return np.array(stocks), np.array(shortages)


def test_optimizer_uses_cheapest_capacity_before_more_expensive_suppliers():
    weeks = range(11, 17)
    tables = fixture_tables(weeks=weeks, lead=0, capacity=3)
    costs = {"KES": 6.0, "SUN": 10.0, "ORI": 14.0}
    caps = {"KES": 1.0, "SUN": 2.0, "ORI": 3.0}
    tables["supply_history"]["landed_cost"] = tables["supply_history"].country.map(costs)
    tables["suppliers"]["normal_capacity_units"] = tables["suppliers"].country.map(caps)
    decisions = optimized_plan(tables, weeks=weeks)
    assert set(decisions.columns) in (
        {"target_week", "material", "order_units", *SHARE_COLUMNS},
        {"target_week", "material", "order_units", *SHARE_COLUMNS, "policy_id"},
    )
    assert len(decisions) == 6
    # Opening stock is 50; six cheap one-unit opportunities and four SUN units
    # cover the remaining ten units for 6*6 + 4*10 = 76, with no ORI purchase.
    totals = {country: source_units(decisions, country).sum() for country in costs}
    assert totals == pytest.approx({"KES": 6, "SUN": 4, "ORI": 0}, abs=1e-8)
    assert sum(totals[country] * costs[country] for country in costs) == pytest.approx(76)
    _, shortages = replay_optimized_plan(
        decisions, tables, leads=dict.fromkeys(caps, 0), capacities=caps,
    )
    np.testing.assert_allclose(shortages, 0, atol=1e-8)


def tilt_tables(kes_capacity=100.0):
    tables = fixture_tables(weeks=range(11, 24), lead=1, capacity=100.0)
    costs = {"KES": 8.0, "SUN": 10.0, "ORI": 12.0}
    tables["supply_history"]["landed_cost"] = tables["supply_history"].country.map(costs)
    is_kes = tables["supply_history"].country.eq("KES")
    tables["supply_history"].loc[is_kes, "capacity_units"] = kes_capacity
    return tables, np.exp(-3.0 * (np.array([8.0, 10.0, 12.0]) / 10.0 - 1.0))


def test_cost_tilt_keeps_weekly_totals_and_splits_positive_orders_by_cost():
    tables, weights = tilt_tables()
    plain = optimized_plan(tables, config=OptimizationConfig())
    tilted = optimized_plan(tables, config=OptimizationConfig(cost_tilt=3.0))
    assert_feasible(tilted, tables)
    np.testing.assert_allclose(tilted.order_units, plain.order_units)
    positive = tilted.order_units > 0
    assert positive.any() and (~positive).any()
    shares = tilted[["share_KES", "share_SUN", "share_ORI"]].to_numpy()
    np.testing.assert_allclose(shares[positive], np.tile(weights / weights.sum(), (positive.sum(), 1)))
    np.testing.assert_allclose(shares[~positive], 1 / 3)
    # The MILP ledger no longer describes tilted slices, so it is not published.
    assert "projection" not in tilted.attrs and "projection" in plain.attrs


def test_cost_tilt_spills_units_above_estimated_capacity_by_the_same_preference():
    tables, weights = tilt_tables(kes_capacity=2.0)
    tilted = optimized_plan(tables, config=OptimizationConfig(cost_tilt=3.0))
    rows = tilted.loc[tilted.order_units > 2.0 / (weights[0] / weights.sum())]
    assert len(rows)
    np.testing.assert_allclose(source_units(rows, "KES"), 2.0)
    np.testing.assert_allclose(rows.share_SUN / rows.share_ORI, weights[1] / weights[2])
    np.testing.assert_allclose(rows[list(SHARE_COLUMNS)].sum(axis=1), 1.0)


def test_optimizer_trades_future_price_growth_against_inventory_holding():
    weeks = range(11, 17)
    tables = fixture_tables(weeks=weeks, lead=0, capacity=100)
    costs = {"KES": 10.0, "SUN": 20.0, "ORI": 30.0}
    tables["supply_history"]["landed_cost"] = tables["supply_history"].country.map(costs)
    forecasts = forecast_frame(weeks)
    forecasts.loc[forecasts.target_week > 11, "price_forecast"] = 20
    early = optimized_plan(tables, forecasts, weeks, economic_config(holding_rate=0.02))
    late = optimized_plan(tables, forecasts, weeks, economic_config(holding_rate=0.2))
    # Reference landed cost is 20. Buying a unit at week 11 costs
    # 10 + five weeks * holding_rate * 20, versus 20 at week 16.
    np.testing.assert_allclose(early.order_units, [10, 0, 0, 0, 0, 0], atol=1e-8)
    np.testing.assert_allclose(late.order_units, [0, 0, 0, 0, 0, 10], atol=1e-8)
    for decisions in (early, late):
        np.testing.assert_allclose(source_units(decisions, "KES"), decisions.order_units, atol=1e-8)
        _, shortages = replay_optimized_plan(
            decisions, tables, leads=dict.fromkeys(COUNTRIES, 0),
            capacities=dict.fromkeys(COUNTRIES, 100),
        )
        np.testing.assert_allclose(shortages, 0, atol=1e-8)
    scaled = forecasts.copy()
    scaled["price_forecast"] *= 100
    assert_frame_equal(
        optimized_plan(tables, scaled, weeks, economic_config(holding_rate=0.02)), early,
    )


def test_optimizer_capacity_limited_shortages_are_real_and_bounded():
    weeks = range(11, 19)
    tables = fixture_tables(weeks=weeks, lead=2, capacity=1)
    decisions = optimized_plan(tables, weeks=weeks)
    # Only six order dates can arrive: 50 initial + 6*3 arrivals < 80 demand.
    np.testing.assert_allclose(decisions.order_units, [3, 3, 3, 3, 3, 3, 0, 0], atol=1e-8)
    stocks, shortages = replay_optimized_plan(
        decisions, tables, leads=dict.fromkeys(COUNTRIES, 2),
        capacities=dict.fromkeys(COUNTRIES, 1),
    )
    assert shortages.sum() == pytest.approx(12, abs=1e-8)
    assert decisions.order_units.sum() + shortages.sum() == pytest.approx(30, abs=1e-8)
    assert stocks[-1] == pytest.approx(0, abs=1e-8)


def test_optimizer_does_not_buy_unreachable_demand_or_salvage_only_inventory():
    weeks = range(11, 17)
    too_slow = fixture_tables(weeks=weeks, lead=20, capacity=100)
    decisions = optimized_plan(too_slow, weeks=weeks)
    np.testing.assert_allclose(decisions.order_units, 0, atol=1e-8)
    _, shortages = replay_optimized_plan(
        decisions, too_slow, leads=dict.fromkeys(COUNTRIES, 20),
        capacities=dict.fromkeys(COUNTRIES, 100),
    )
    assert shortages.sum() == pytest.approx(10, abs=1e-8)

    excess = fixture_tables(weeks=weeks, lead=0, capacity=100)
    excess["demand"].loc[excess["demand"].week > 11, "demand_units"] = 0
    excess["supply_history"]["landed_cost"] = excess["supply_history"].country.map(
        {"KES": 1.0, "SUN": 100.0, "ORI": 100.0},
    )
    # A 0.99 * 67 reference-cost salvage credit would make cheap speculative
    # purchases profitable without the fixed terminal-stock constraint.
    decisions = optimized_plan(excess, weeks=weeks, config=economic_config(salvage_rate=0.99))
    np.testing.assert_allclose(decisions.order_units, 0, atol=1e-8)
    stocks, shortages = replay_optimized_plan(
        decisions, excess, leads=dict.fromkeys(COUNTRIES, 0),
        capacities=dict.fromkeys(COUNTRIES, 100),
    )
    np.testing.assert_allclose(stocks, 40, atol=1e-8)
    np.testing.assert_allclose(shortages, 0, atol=1e-8)


@pytest.mark.parametrize(
    ("countries", "expected"),
    [
        (("KES", "SUN", "ORI"), {"KES": 1 / 3, "SUN": 1 / 3, "ORI": 1 / 3}),
        (("KES", "ORI"), {"KES": 0.5, "SUN": 0, "ORI": 0.5}),
        (("SUN",), {"KES": 0, "SUN": 1, "ORI": 0}),
    ],
)
def test_optimizer_zero_demand_maximizes_eligible_country_diversification(countries, expected):
    tables = fixture_tables(lead=0)
    tables["demand"]["demand_units"] = 0
    for name in ("suppliers", "supply_history"):
        tables[name] = tables[name].loc[tables[name].country.isin(countries)].copy()
    decisions = optimized_plan(tables)
    np.testing.assert_allclose(decisions.order_units, 0, atol=1e-8)
    assert_feasible(decisions, tables)
    for country, share in expected.items():
        np.testing.assert_allclose(decisions[f"share_{country}"], share, atol=1e-8)
    concentration = decisions[list(SHARE_COLUMNS)].pow(2).sum(axis=1)
    np.testing.assert_allclose(concentration, 1 / len(countries), atol=1e-12)


def test_optimizer_private_gap_and_repeated_calls_reset_stock_and_transit():
    tables = fixture_tables()
    config = economic_config(holding_rate=0.02)
    policy = OptimizedPolicy(config=config)
    assert policy.policy_id == "inventory_milp"
    first = policy.decide(tables, forecast_frame(), 10, list(range(11, 24)))
    private = policy.decide(tables, forecast_frame(range(24, 37)), 10, list(range(24, 37)))
    private["target_week"] -= 13
    assert_frame_equal(private, first)
    assert_frame_equal(policy.decide(tables, forecast_frame(), 10, list(range(11, 24))), first)
    assert first.order_units.sum() == pytest.approx(80, abs=1e-8)
    np.testing.assert_allclose(first.iloc[:3].order_units, 0, atol=1e-8)
    # A different first demand resets opening stock to 100, not to old terminal
    # stock, the previous origin's stock, or five weeks' summed demand (60).
    changed = fixture_tables(weeks=range(24, 30))
    changed["demand"].loc[changed["demand"].week == 24, "demand_units"] = 20
    reset = policy.decide(changed, forecast_frame(range(24, 30)), 10, list(range(24, 30)))
    np.testing.assert_allclose(reset.order_units, 0, atol=1e-8)


def test_optimizer_future_supply_poison_cannot_change_public_decisions():
    tables = fixture_tables()
    config = economic_config(holding_rate=0.02)
    expected = optimized_plan(tables, config=config)
    future = tables["supply_history"].iloc[:3].copy()
    future["week"] = 11
    future["material"] = "not_an_eligible_material"
    future["capacity_units"] = np.nan
    future["landed_cost"] = -1e12
    future["lead_time_weeks"] = 10000
    poisoned = {
        **tables,
        "supply_history": pd.concat([tables["supply_history"], future, future], ignore_index=True),
    }
    assert_frame_equal(optimized_plan(poisoned, config=config), expected)


@pytest.mark.parametrize(("quantile", "capacity"), [(0.25, 3.5), (1.0, 5.0)])
def test_optimizer_uses_recent_capacity_quantile_capped_by_static_normal(quantile, capacity):
    weeks = range(11, 13)
    tables = fixture_tables(weeks=weeks, lead=0, capacity=100)
    for name in ("suppliers", "supply_history"):
        tables[name] = tables[name].query("country == 'KES'").copy()
    tables["suppliers"]["normal_capacity_units"] = 5
    history = tables["supply_history"]
    history.loc[history.week >= 7, "capacity_units"] = [2, 4, 8, 10]
    tables["demand"]["demand_units"] = [0, 20]
    config = economic_config(trailing_weeks=4, capacity_quantile=quantile)
    decisions = optimized_plan(tables, weeks=weeks, config=config)
    # Quantile(.25) of [2,4,8,10] is 3.5; quantile(1) is 10,
    # but normal capacity clips that estimate to five units per order.
    np.testing.assert_allclose(decisions.order_units, [capacity, capacity], atol=1e-8)
    _, shortages = replay_optimized_plan(
        decisions, tables, leads={"KES": 0}, capacities={"KES": capacity},
    )
    assert shortages.sum() == pytest.approx(20 - 2 * capacity, abs=1e-8)
    old_poison = history.copy()
    old_poison.loc[old_poison.week < 7, ["capacity_units", "landed_cost", "lead_time_weeks"]] = [
        1e6, 1e6, 1000,
    ]
    assert_frame_equal(
        optimized_plan({**tables, "supply_history": old_poison}, weeks=weeks, config=config),
        decisions,
    )


@pytest.mark.parametrize(
    ("quantile", "lead", "expected_orders", "expected_shortage"),
    [(0.75, 2, [10, 10, 0, 0], 10), (0.25, 0, [0, 10, 10, 10], 0)],
)
def test_optimizer_ceils_historical_lead_quantile_not_mean_or_static_lead(
    quantile, lead, expected_orders, expected_shortage,
):
    weeks = range(11, 15)
    tables = fixture_tables(weeks=weeks, lead=0, capacity=10)
    for name in ("suppliers", "supply_history"):
        tables[name] = tables[name].query("country == 'KES'").copy()
    history = tables["supply_history"]
    history.loc[history.week >= 7, "lead_time_weeks"] = [0, 0, 1, 3]
    tables["demand"]["demand_units"] = [0, 10, 10, 10]
    config = economic_config(trailing_weeks=4, lead_quantile=quantile, holding_rate=0.02)
    decisions = optimized_plan(tables, weeks=weeks, config=config)
    np.testing.assert_allclose(decisions.order_units, expected_orders, atol=1e-8)
    _, shortages = replay_optimized_plan(
        decisions, tables, leads={"KES": lead}, capacities={"KES": 10},
    )
    assert shortages.sum() == pytest.approx(expected_shortage, abs=1e-8)


def test_optimizer_unequal_historical_leads_match_actual_predicted_arrival_balance():
    weeks = range(11, 14)
    tables = fixture_tables(weeks=weeks, lead=0, capacity=10)
    for name in ("suppliers", "supply_history"):
        tables[name] = tables[name].query("country != 'ORI'").copy()
    tables["suppliers"].loc[tables["suppliers"].country == "SUN", "base_lead_weeks"] = 2
    history = tables["supply_history"]
    history["landed_cost"] = history.country.map({"KES": 1.0, "SUN": 10.0})
    history["lead_time_weeks"] = history.country.map({"KES": 2, "SUN": 0})
    tables["demand"]["demand_units"] = [0, 10, 10]
    decisions = optimized_plan(tables, weeks=weeks, config=economic_config(holding_rate=0.02))
    np.testing.assert_allclose(source_units(decisions, "KES"), [10, 0, 0], atol=1e-8)
    np.testing.assert_allclose(source_units(decisions, "SUN"), [0, 10, 0], atol=1e-8)
    stocks, shortages = replay_optimized_plan(
        decisions, tables, leads={"KES": 2, "SUN": 0}, capacities={"KES": 10, "SUN": 10},
    )
    np.testing.assert_allclose(stocks, 0, atol=1e-8)
    np.testing.assert_allclose(shortages, 0, atol=1e-8)


def test_optimizer_risk_forecast_pays_for_buffer_without_buying_extra_terminal_stock():
    weeks = range(11, 19)
    tables = fixture_tables(weeks=weeks, lead=0, capacity=100)
    tables["supply_history"]["landed_cost"] = tables["supply_history"].country.map(
        {"KES": 10.0, "SUN": 20.0, "ORI": 30.0},
    )
    config = economic_config(risk_buffer_weeks=2, buffer_penalty=0.5, holding_rate=0.02)
    low = optimized_plan(tables, forecast_frame(weeks, risk=0), weeks, config)
    high = optimized_plan(tables, forecast_frame(weeks, risk=1), weeks, config)
    # Risk buys the same 30 units two weeks sooner, maintaining twenty units
    # after demand until remaining future demand forces the buffer to taper.
    np.testing.assert_allclose(low.order_units, [0, 0, 0, 0, 0, 10, 10, 10], atol=1e-8)
    np.testing.assert_allclose(high.order_units, [0, 0, 0, 10, 10, 10, 0, 0], atol=1e-8)
    for decisions in (low, high):
        _, shortages = replay_optimized_plan(
            decisions, tables, leads=dict.fromkeys(COUNTRIES, 0),
            capacities=dict.fromkeys(COUNTRIES, 100),
        )
        np.testing.assert_allclose(shortages, 0, atol=1e-8)


def test_optimizer_diversification_penalty_targets_shared_lane_balanced_weights():
    weeks = range(11, 17)
    tables = fixture_tables(weeks=weeks, lead=0, capacity=100)
    tables["supply_history"]["landed_cost"] = tables["supply_history"].country.map(
        {"KES": 10.0, "SUN": 11.0, "ORI": 12.0},
    )
    config = economic_config(holding_rate=0.02)
    cheap = optimized_plan(tables, weeks=weeks, config=config)
    balanced = optimized_plan(
        tables, weeks=weeks, config=replace(config, diversification_penalty=2),
    )
    np.testing.assert_allclose(source_units(cheap, "KES"), [0, 0, 0, 0, 0, 10], atol=1e-8)
    for country, quantity in {"KES": 2.5, "SUN": 2.5, "ORI": 5}.items():
        np.testing.assert_allclose(
            source_units(balanced, country), [0, 0, 0, 0, 0, quantity], atol=1e-8,
        )
    np.testing.assert_allclose(balanced.order_units, cheap.order_units, atol=1e-8)
    _, shortages = replay_optimized_plan(
        balanced, tables, leads=dict.fromkeys(COUNTRIES, 0),
        capacities=dict.fromkeys(COUNTRIES, 100),
    )
    np.testing.assert_allclose(shortages, 0, atol=1e-8)


def test_optimizer_json_mapping_constructor_matches_config_and_pure_helper_behavior():
    weeks = range(11, 17)
    tables = fixture_tables(weeks=weeks, lead=0, capacity=100)
    tables["supply_history"]["landed_cost"] = tables["supply_history"].country.map(
        {"KES": 10.0, "SUN": 20.0, "ORI": 30.0},
    )
    forecasts = forecast_frame(weeks)
    forecasts.loc[forecasts.target_week > 11, "price_forecast"] = 20
    config = economic_config(holding_rate=0.2)
    mapping = json.loads(json.dumps(asdict(config)))
    expected = optimized_plan(tables, forecasts, weeks, config)
    np.testing.assert_allclose(expected.order_units, [0, 0, 0, 0, 0, 10], atol=1e-8)
    for configured in (config, mapping):
        actual = OptimizedPolicy(config=configured).decide(tables, forecasts, 10, list(weeks))
        assert_frame_equal(actual, expected)
    default = OptimizedPolicy().decide(tables, forecasts, 10, list(weeks))
    explicit_default = OptimizedPolicy(config=OptimizationConfig()).decide(
        tables, forecasts, 10, list(weeks),
    )
    assert_frame_equal(default, explicit_default)
    assert default.iloc[0].order_units > expected.iloc[0].order_units


@pytest.mark.parametrize(
    "kwargs",
    [
        {"trailing_weeks": 0},
        {"trailing_weeks": 1.5},
        {"capacity_quantile": -0.01},
        {"capacity_quantile": 1.01},
        {"lead_quantile": -0.01},
        {"lead_quantile": 1.01},
        *[{name: np.nan} for name in (
            "capacity_quantile", "lead_quantile", "base_buffer_weeks", "risk_buffer_weeks",
            "buffer_penalty", "diversification_penalty", "holding_rate", "shortage_multiple",
            "salvage_rate",
        )],
        {"capacity_quantile": np.inf},
        {"holding_rate": -0.01},
    ],
)
def test_optimizer_rejects_invalid_config_values_in_dataclass_and_mapping(kwargs):
    with pytest.raises(ValueError):
        OptimizationConfig(**kwargs)
    with pytest.raises(ValueError):
        OptimizedPolicy(config=kwargs)


@pytest.mark.parametrize("error", ["missing_forecast", "duplicate_forecast", "missing_recent_history",
                                  "duplicate_history", "bad_risk", "nan_price"])
def test_optimizer_enforces_shared_input_validation(error):
    tables = fixture_tables()
    forecasts = forecast_frame()
    if error == "missing_forecast":
        forecasts = forecasts.iloc[1:]
    elif error == "duplicate_forecast":
        forecasts = pd.concat([forecasts, forecasts.iloc[:1]], ignore_index=True)
    elif error == "missing_recent_history":
        tables["supply_history"] = tables["supply_history"].query("country != 'ORI'")
    elif error == "duplicate_history":
        tables["supply_history"] = pd.concat(
            [tables["supply_history"], tables["supply_history"].iloc[:1]], ignore_index=True,
        )
    elif error == "bad_risk":
        forecasts.loc[0, "disruption_prob"] = 1.1
    elif error == "nan_price":
        forecasts.loc[0, "price_forecast"] = np.nan
    with pytest.raises(ValueError):
        optimized_plan(tables, forecasts)


def test_optimizer_preserves_input_frames_and_ignores_source_row_order():
    weeks = range(11, 17)
    tables = fixture_tables(weeks=weeks, lead=0, capacity=100)
    tables["supply_history"]["landed_cost"] = tables["supply_history"].country.map(
        {"KES": 10.0, "SUN": 11.0, "ORI": 12.0},
    )
    forecasts = forecast_frame(weeks)
    originals = {name: frame.copy(deep=True) for name, frame in tables.items()}
    original_forecasts = forecasts.copy(deep=True)
    config = economic_config(holding_rate=0.02, diversification_penalty=2)
    expected = optimized_plan(tables, forecasts, weeks, config)
    for name, frame in tables.items():
        assert_frame_equal(frame, originals[name])
    assert_frame_equal(forecasts, original_forecasts)
    reordered = {name: frame.iloc[::-1].reset_index(drop=True) for name, frame in tables.items()}
    assert_frame_equal(
        optimized_plan(reordered, forecasts.iloc[::-1].reset_index(drop=True), weeks, config),
        expected,
    )


def test_optimizer_keeps_material_opening_stock_and_orders_independent():
    weeks = range(11, 17)
    materials = ("lithium", "cobalt")
    tables = fixture_tables(weeks=weeks, materials=materials, lead=0, capacity=10)
    tables["demand"].loc[
        (tables["demand"].material == "lithium") & (tables["demand"].week == 11),
        "demand_units",
    ] = 0
    tables["supply_history"]["landed_cost"] = tables["supply_history"].country.map(
        {"KES": 10.0, "SUN": 20.0, "ORI": 30.0},
    )
    decisions = optimized_plan(tables, forecast_frame(weeks, materials), weeks)
    assert len(decisions) == 12
    assert not decisions.duplicated(["target_week", "material"]).any()
    assert decisions.groupby("material").order_units.sum().to_dict() == pytest.approx(
        {"lithium": 50, "cobalt": 10}, abs=1e-8,
    )
    for _, rows in decisions.groupby("material"):
        _, shortages = replay_optimized_plan(
            rows, tables, leads=dict.fromkeys(COUNTRIES, 0),
            capacities=dict.fromkeys(COUNTRIES, 10),
        )
        np.testing.assert_allclose(shortages, 0, atol=1e-8)


def test_optimizer_cannot_hold_buffer_stock_while_refusing_known_demand():
    tables = fixture_tables(lead=0)
    # Static eligibility remains positive, but every historical supplier has
    # zero available capacity. Buffer incentives cannot alter physical losses.
    tables["supply_history"]["capacity_units"] = 0
    decisions = optimized_plan(
        tables, forecast_frame(risk=1),
        config=OptimizationConfig(
            base_buffer_weeks=0.5, risk_buffer_weeks=1.5,
            buffer_penalty=4.5, shortage_multiple=5,
        ),
    )
    np.testing.assert_allclose(decisions.order_units, 0, atol=1e-8)
    stocks, shortages = replay_optimized_plan(
        decisions, tables, leads=dict.fromkeys(COUNTRIES, 0),
        capacities=dict.fromkeys(COUNTRIES, 0),
    )
    np.testing.assert_allclose(stocks, [40, 30, 20, 10, *([0] * 9)], atol=1e-8)
    np.testing.assert_allclose(shortages, [*([0] * 5), *([10] * 8)], atol=1e-8)
    # Diagnostics must survive ordinary JSON serialization for saved decisions.
    json.dumps(decisions.attrs["projection"], allow_nan=False)


def test_policy_evaluation_rejects_locked_holdout_before_data_access_or_output(tmp_path):
    from notebooks.policy.evaluate import evaluate_policies

    output = tmp_path / "must-not-be-created"
    with pytest.raises(ValueError, match="locked"):
        evaluate_policies(None, None, output, origins=(182,))
    assert not output.exists()
