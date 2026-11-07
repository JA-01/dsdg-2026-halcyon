"""Behavioral fixtures for origin-local policies, without simulator coupling."""

from dataclasses import replace

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from halcyon.constants import COUNTRIES, MATERIALS, SHARE_COLUMNS
from halcyon.policy import InventoryPolicy, NaivePolicy, PolicyConfig, plan_orders


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
