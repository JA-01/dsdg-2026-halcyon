"""Consumer-level checks with small, hand-calculated inventory ledgers."""


import numpy as np
import pandas as pd
import pytest

from halcyon.constants import COUNTRIES
from halcyon.simulator import SimulatorConfig, simulate_window



def inputs(demands, *, countries=("KES",), start=1, cost=10.0, lead=1, capacity=100.0):
    weeks = list(range(start, start + len(demands)))
    suppliers = pd.DataFrame({"material": ["ore"] * len(countries), "country": countries})
    demand = pd.DataFrame({"week": weeks, "material": "ore", "demand_units": np.asarray(demands, dtype=float)})
    decisions = pd.DataFrame({"target_week": weeks, "material": "ore", "order_units": 0.0})
    for country in COUNTRIES:
        decisions[f"share_{country}"] = 1 / len(countries) if country in countries else 0.0
    supply = pd.DataFrame([
        {"week": week, "material": "ore", "country": country, "capacity_units": capacity,
         "lead_time_weeks": float(lead), "landed_cost": cost}
        for week in weeks for country in countries
    ])
    outcomes = pd.DataFrame({
        "week": range(max(1, start - 4), weeks[-1] + 1),
        "material": "ore", "disrupted": 0.0,
    })
    return decisions, demand, supply, suppliers, outcomes


def run(frames, *, config=None, reference_costs=None, start=None, end=None):
    demand = frames[1]
    start = int(demand.week.min()) if start is None else start
    end = int(demand.week.max()) if end is None else end
    return simulate_window(*frames, start, end, config=config, reference_costs=reference_costs)


def test_independent_caps_unpaid_cancellation_and_zero_lead_arrivals():
    frames = inputs([0, 4, 5], countries=("KES", "VAL"))
    decisions, _, supply, _, _ = frames
    decisions.loc[0, "order_units"] = 10
    supply.loc[supply.country.eq("KES"), ["capacity_units", "lead_time_weeks"]] = [2, 0]
    supply.loc[supply.country.eq("VAL"), ["landed_cost", "lead_time_weeks"]] = [20, 2]
    result = run(frames)
    weekly = result.weekly
    # Requests 5/5 fill 2/5, not 2/8: the cancelled KES slice is not reassigned.
    assert weekly.filled_order_units.tolist() == [7, 0, 0]
    assert weekly.cancelled_units.tolist() == [3, 0, 0]
    assert weekly.ending_stock.tolist() == [2, 0, 0]
    assert weekly.ending_transit.tolist() == [5, 5, 0]
    assert weekly.fulfilled_units.tolist() == [0, 2, 5]
    assert weekly.stockout_units.tolist() == [0, 2, 0]
    # Mean reference = (10 + 20)/2 = 15; purchase = 2*10 + 5*20 = 120.
    # Week-1 holding = 2*.02*15 = .6; shortage = 2*5*15 = 150.
    assert weekly.purchase_cost.tolist() == [120, 0, 0]
    assert weekly.holding_cost.tolist() == pytest.approx([0.6, 0, 0])
    assert weekly.shortage_cost.tolist() == [0, 150, 0]
    assert result.metrics.loc[0, "total_cost"] == pytest.approx(270.6)
    assert result.metrics.loc[0, "fill_rate"] == pytest.approx(7 / 9)
    assert result.metrics.loc[0, "mean_concentration"] == 0.5
    assert result.metrics.loc[0, "mean_diversification"] == 1
    assert result.score_status == "proxy"
    assert result.assumptions["reference_cost_source"] == "window_mean_realized_landed_cost_evaluator_only"
    assert result.assumptions["reference_costs"] == {"ore": 15.0}


def test_positive_lead_arrival_is_available_before_demand():
    frames = inputs([0, 3, 0], lead=1)
    frames[0].loc[0, "order_units"] = 3
    result = run(frames)
    assert result.weekly.fulfilled_units.tolist() == [0, 3, 0]
    assert result.weekly.ending_transit.tolist() == [3, 0, 0]
    assert result.metrics.loc[0, "total_cost"] == 30


def test_zero_lead_fills_current_week_demand_after_initial_stock_runs_out():
    frames = inputs([0, 3], lead=0)
    frames[0].loc[1, "order_units"] = 3
    result = run(frames)
    assert result.weekly.fulfilled_units.tolist() == [0, 3]
    assert result.weekly.ending_transit.tolist() == [0, 0]
    assert result.metrics.loc[0, "stockout_units"] == 0


def test_late_transit_salvage_and_no_transit_holding():
    frames = inputs([0, 0], lead=5)
    frames[0].loc[0, "order_units"] = 8
    result = run(frames)
    # Eight units cost 80, stay in transit, and recover 8*10*.7 = 56 only at end.
    assert result.weekly.ending_stock.tolist() == [0, 0]
    assert result.weekly.ending_transit.tolist() == [8, 8]
    assert result.weekly.holding_cost.tolist() == [0, 0]
    assert result.weekly.salvage_credit.tolist() == [0, 56]
    assert result.metrics.loc[0, "total_cost"] == 24
    assert np.isnan(result.metrics.loc[0, "fill_rate"])
    assert np.isnan(result.metrics.loc[0, "shock_fill_rate"])


def test_end_stock_holding_free_initial_stock_and_terminal_salvage():
    result = run(inputs([2, 2]))
    # Initial 10 units are free; ending stocks 8,6 cost 1.6+1.2; salvage is 42.
    assert result.weekly.ending_stock.tolist() == [8, 6]
    assert result.weekly.holding_cost.tolist() == pytest.approx([1.6, 1.2])
    assert result.metrics.loc[0, "purchase_cost"] == 0
    assert result.metrics.loc[0, "salvage_credit"] == 42
    assert result.metrics.loc[0, "total_cost"] == pytest.approx(-39.2)


def test_shortage_cost_and_fresh_inventory_on_every_call():
    frames = inputs([1] * 12, lead=50)
    frames[0].loc[0, "order_units"] = 2
    first = run(frames, start=1, end=6)
    second = run(frames, start=7, end=12)
    repeat = run(frames, start=7, end=12)
    # Fresh five units: ending stocks 4,3,2,1,0,0; holding total 2, shortage 50.
    assert second.weekly.ending_stock.tolist() == [4, 3, 2, 1, 0, 0]
    assert second.weekly.ending_transit.tolist() == [0] * 6
    assert second.metrics.loc[0, "total_cost"] == 52
    assert second.metrics.loc[0, "fill_rate"] == pytest.approx(5 / 6)
    assert set(second.weekly.window_id) == {"7-12"}
    assert first.weekly.ending_transit.iloc[-1] == 2
    pd.testing.assert_frame_equal(second.weekly, repeat.weekly)


def test_recovery_tail_includes_prior_shocks_and_exactly_four_following_weeks():
    frames = list(inputs([1] * 8, start=7))
    frames[4].loc[frames[4].week.isin([5, 10]), "disrupted"] = 1
    result = run(frames)
    # A shock at 5 flags 5..9, and a shock at 10 flags 10..14.
    assert result.weekly.shock_recovery.tolist() == [True] * 8
    assert result.metrics.loc[0, "shock_fill_rate"] == pytest.approx(5 / 8)
    frames[4].loc[frames[4].week.eq(10), "disrupted"] = 0
    tail = run(frames)
    assert tail.weekly.shock_recovery.tolist() == [True, True, True, False, False, False, False, False]
    assert tail.metrics.loc[0, "shock_fill_rate"] == 1


def test_initial_stock_modes_and_custom_cost_rates():
    frames = inputs([1, 2, 3, 4, 5])
    first = run(frames)
    summed = run(frames, config=SimulatorConfig(initial_stock_mode="five_week_sum"))
    # Five initial units: holding .8+.4 and shortage (1+4+5)*50 = 500.
    assert first.metrics.loc[0, "total_cost"] == pytest.approx(501.2)
    # Fifteen initial units: stocks 14,12,9,5,0; holding .2*40 = 8.
    assert summed.metrics.loc[0, "total_cost"] == 8
    assert summed.assumptions["initial_stock_units"] == {"ore": 15}
    customized = run(inputs([1, 1]), config=SimulatorConfig(
        holding_rate=0.1, shortage_multiple=2, salvage_rate=0.5,
    ))
    # Stocks 4,3: holding 7 and terminal salvage 15.
    assert customized.metrics.loc[0, "total_cost"] == -8
    shortage = run(inputs([0, 2]), config=SimulatorConfig(shortage_multiple=2))
    assert shortage.metrics.loc[0, "shortage_cost"] == 40


def test_five_week_initialization_for_short_window_uses_full_plan():
    frames = inputs([1, 2, 3, 4, 5])
    result = run(frames, end=1, config=SimulatorConfig(initial_stock_mode="five_week_sum"))
    assert result.weekly.ending_stock.tolist() == [14]
    with pytest.raises(ValueError, match="demand coverage"):
        run(inputs([1]), config=SimulatorConfig(initial_stock_mode="five_week_sum"))


def test_fractional_quantities_and_per_supplier_floor_option():
    frames = inputs([0], countries=("KES", "VAL"), lead=5)
    frames[0].loc[0, "order_units"] = 3.8
    fractional = run(frames)
    floored = run(frames, config=SimulatorConfig(quantity_rounding="floor"))
    assert fractional.weekly.filled_order_units.iloc[0] == pytest.approx(3.8)
    assert fractional.metrics.loc[0, "total_cost"] == pytest.approx(11.4)
    # Each 1.9-unit request floors to one unit: purchase 20, salvage 14.
    assert floored.weekly.ordered_units.iloc[0] == 3.8
    assert floored.weekly.filled_order_units.iloc[0] == 2
    assert floored.weekly.cancelled_units.iloc[0] == pytest.approx(1.8)
    assert floored.metrics.loc[0, "total_cost"] == 6


@pytest.mark.parametrize("reference", [{"ore": 20}, pd.Series({"ore": 20})])
def test_explicit_reference_costs_do_not_change_realized_purchase_price(reference):
    frames = inputs([0, 0], lead=5)
    frames[0].loc[0, "order_units"] = 2
    result = run(frames, reference_costs=reference)
    assert result.metrics.loc[0, "purchase_cost"] == 20
    assert result.metrics.loc[0, "salvage_credit"] == 28
    assert result.metrics.loc[0, "total_cost"] == -8
    assert result.assumptions["reference_cost_source"] == "explicit_evaluator_reference"


def test_multiple_materials_and_aggregate_fill_is_demand_weighted():
    first = inputs([1] * 6)
    second = tuple(frame.assign(material="metal") for frame in inputs([0, 2, 2, 2, 2, 2]))
    frames = tuple(pd.concat(pair, ignore_index=True) for pair in zip(first, second))
    result = run(frames)
    assert result.metrics.shape[0] == 1
    assert set(result.material_metrics.material) == {"ore", "metal"}
    assert result.metrics.loc[0, "material"] == "__all__"
    assert result.metrics.loc[0, "fill_rate"] == pytest.approx(5 / 16)
    assert result.metrics.loc[0, "total_cost"] == pytest.approx(552)
    assert len(result.weekly) == 12
    assert not result.weekly.duplicated(["window_id", "week", "material"]).any()


@pytest.mark.parametrize("change", ["negative", "nan", "over_one", "wrong_sum", "ineligible"])
def test_rejects_invalid_shares_even_with_zero_orders(change):
    frames = inputs([1])
    decisions = frames[0]
    if change == "negative":
        decisions.loc[0, "share_KES"] = -0.1
    elif change == "nan":
        decisions.loc[0, "share_KES"] = np.nan
    elif change == "over_one":
        decisions.loc[0, "share_KES"] = 1.1
    elif change == "wrong_sum":
        decisions.loc[0, "share_KES"] = 0.9
    else:
        decisions.loc[0, ["share_KES", "share_VAL"]] = [0.5, 0.5]
    with pytest.raises(ValueError, match="share"):
        run(frames)


def test_share_sum_tolerance_is_not_silently_renormalized():
    frames = inputs([0], countries=("KES", "VAL"), lead=5)
    frames[0].loc[0, "order_units"] = 1
    frames[0].loc[0, ["share_KES", "share_VAL"]] = [0.5, 0.4999995]
    result = run(frames)
    assert result.weekly.filled_order_units.iloc[0] == pytest.approx(0.9999995, abs=1e-10)
    frames[0].loc[0, "share_VAL"] = 0.499998
    with pytest.raises(ValueError, match="sum to 1"):
        run(frames)


@pytest.mark.parametrize("position", [0, 1, 2, 4])
@pytest.mark.parametrize("problem", ["missing", "duplicate"])
def test_requires_complete_unique_evaluation_keys(position, problem):
    frames = list(inputs([1, 1]))
    frame = frames[position]
    frames[position] = frame.iloc[1:].copy() if problem == "missing" else pd.concat([frame, frame.iloc[:1]])
    with pytest.raises(ValueError, match="coverage|duplicate"):
        run(frames, start=1, end=2)


@pytest.mark.parametrize("position,column,value", [
    (0, "order_units", -1), (0, "order_units", np.inf),
    (1, "demand_units", -1), (1, "demand_units", np.nan),
    (2, "capacity_units", -1), (2, "capacity_units", np.inf),
    (2, "landed_cost", -1), (2, "landed_cost", np.nan),
    (2, "lead_time_weeks", -1), (2, "lead_time_weeks", 1.5),
    (2, "lead_time_weeks", np.inf), (4, "disrupted", 0.5),
])
def test_rejects_invalid_realized_numbers(position, column, value):
    frames = inputs([1])
    frames[position].loc[0, column] = value
    with pytest.raises(ValueError, match=column):
        run(frames)


@pytest.mark.parametrize("reference", [{}, {"ore": 0}, {"ore": -1}, {"ore": np.inf},
                                        {"ore": np.nan}, {"ore": "bad"}])
def test_rejects_invalid_explicit_references(reference):
    with pytest.raises(ValueError, match="reference_costs"):
        run(inputs([1]), reference_costs=reference)


@pytest.mark.parametrize("kwargs", [
    {"initial_stock_mode": "carry"}, {"quantity_rounding": "round"},
    {"holding_rate": -1}, {"shortage_multiple": np.inf}, {"salvage_rate": 1.1},
    {"holding_timing": "before_arrivals"},
])
def test_rejects_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        SimulatorConfig(**kwargs)


def test_zero_landed_cost_is_valid_for_default_reference():
    result = run(inputs([1], cost=0))
    assert result.assumptions["reference_costs"] == {"ore": 0}
    assert result.metrics.loc[0, "total_cost"] == 0


def test_inputs_are_not_mutated():
    frames = inputs([0, 2])
    snapshots = [frame.copy(deep=True) for frame in frames]
    run(frames)
    for frame, snapshot in zip(frames, snapshots):
        pd.testing.assert_frame_equal(frame, snapshot)



@pytest.mark.parametrize("position,column", [(0, "target_week"), (1, "week"), (2, "week"), (4, "week")])
@pytest.mark.parametrize("value", [1.5, np.nan, np.inf])
def test_week_keys_reject_fractional_nonfinite_or_null_values(position, column, value):
    frames = inputs([1, 1])
    frames[position][column] = frames[position][column].astype(float)
    frames[position].loc[0, column] = value
    with pytest.raises(ValueError, match=column):
        run(frames, start=1, end=2)


def test_missing_pre_window_outcomes_cannot_silently_drop_recovery():
    frames = list(inputs([1, 1], start=7))
    frames[4] = frames[4].loc[frames[4].week.ne(5)]
    with pytest.raises(ValueError, match="outcomes coverage"):
        run(frames)


def test_three_supplier_diversification_normalization():
    frames = inputs([0], countries=("KES", "VAL", "SUN"))
    equal = run(frames)
    assert equal.weekly.concentration.iloc[0] == pytest.approx(1 / 3)
    assert equal.weekly.diversification.iloc[0] == pytest.approx(1)
    frames[0].loc[0, ["share_KES", "share_VAL", "share_SUN"]] = [1, 0, 0]
    concentrated = run(frames)
    assert concentrated.weekly.concentration.iloc[0] == 1
    assert concentrated.weekly.diversification.iloc[0] == 0


def test_holding_timing_sensitivity_counts_arrivals_before_demand():
    frames = inputs([0, 3], lead=0)
    frames[0].loc[1, "order_units"] = 3
    end_stock = run(frames)
    pre_demand = run(frames, config=SimulatorConfig(holding_timing="pre_demand"))
    # Zero initial stock. Three units arrive and are consumed in week 2.
    # Both modes purchase 3*10=30 and leave no stock/transit to salvage.
    # End-stock holding is zero; pre-demand holding is 3*10*.02=.6.
    assert end_stock.weekly.holding_cost.tolist() == [0, 0]
    assert pre_demand.weekly.holding_cost.tolist() == pytest.approx([0, 0.6])
    assert end_stock.metrics.loc[0, "total_cost"] == 30
    assert pre_demand.metrics.loc[0, "total_cost"] == pytest.approx(30.6)
    assert pre_demand.weekly.fulfilled_units.tolist() == [0, 3]
    assert pre_demand.weekly.ending_stock.tolist() == [0, 0]
    assert pre_demand.assumptions["holding_timing"] == "pre_demand"
