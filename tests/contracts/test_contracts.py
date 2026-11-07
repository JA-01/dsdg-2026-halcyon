from pathlib import Path

import numpy as np
import pandas as pd

import pytest

from halcyon.constants import MATERIALS, PRIVATE_WEEKS, PUBLIC_WEEKS
from halcyon.contracts import (
    ContractError, Window, historical_windows, phase1_windows, phase2_windows,
    validate_decisions, validate_forecasts,
)
from halcyon.data import Dataset
from halcyon.testing import example_decisions, example_forecasts

DATA = Path(__file__).resolve().parents[2] / "data"
WEEKS = [209, 210]


@pytest.fixture(scope="module")
def suppliers():
    return Dataset.from_csv_dir(DATA)["suppliers"]


def test_windows_match_the_contract():
    public, private = phase1_windows()
    assert (public.cutoff, private.cutoff) == (208, 208)
    assert public.target_weeks == PUBLIC_WEEKS and private.target_weeks == PRIVATE_WEEKS
    only = phase2_windows()
    assert len(only) == 1 and only[0].cutoff == 221 and only[0].target_weeks == PRIVATE_WEEKS
    early, late = historical_windows(130)
    assert (early.target_weeks[0], early.target_weeks[-1]) == (131, 143)
    assert (late.target_weeks[0], late.target_weeks[-1]) == (144, 156)


def test_window_targets_must_follow_cutoff():
    with pytest.raises(ContractError):
        Window("bad", 221, PUBLIC_WEEKS)


def test_example_frames_are_valid(suppliers):
    assert len(validate_forecasts(example_forecasts(WEEKS), WEEKS)) == 20
    assert len(validate_decisions(example_decisions(WEEKS, suppliers), WEEKS, suppliers)) == 20


@pytest.mark.parametrize("column,value,match", [
    ("disruption_prob", 1.5, "disruption_prob"),
    ("disruption_prob", float("nan"), "disruption_prob"),
    ("price_forecast", 0.0, "price_forecast"),
    ("price_forecast", float("inf"), "price_forecast"),
])
def test_bad_forecast_values(column, value, match):
    frame = example_forecasts(WEEKS)
    frame.loc[3, column] = value
    with pytest.raises(ContractError, match=match):
        validate_forecasts(frame, WEEKS)


def test_forecast_key_coverage():
    frame = example_forecasts(WEEKS)
    with pytest.raises(ContractError, match="missing key"):
        validate_forecasts(frame.iloc[1:], WEEKS)
    with pytest.raises(ContractError, match="unexpected key"):
        validate_forecasts(frame, [209])
    with pytest.raises(ContractError, match="duplicate key"):
        validate_forecasts(example_forecasts([209, 209]), [209])
    with pytest.raises(ContractError, match="missing columns"):
        validate_forecasts(frame.drop(columns="price_forecast"), WEEKS)


def test_decisions_reject_without_repairing(suppliers):
    frame = example_decisions(WEEKS, suppliers)
    frame.loc[0, "order_units"] = -1.0
    with pytest.raises(ContractError, match="order_units"):
        validate_decisions(frame, WEEKS, suppliers)
    assert frame.loc[0, "order_units"] == -1.0


def test_decisions_share_sum_applies_to_zero_orders(suppliers):
    frame = example_decisions(WEEKS, suppliers, order_units=0.0)
    validate_decisions(frame, WEEKS, suppliers)
    columns = [c for c in frame.columns if c.startswith("share_")]
    frame.loc[0, columns] = 0.0
    with pytest.raises(ContractError, match="sum to 1"):
        validate_decisions(frame, WEEKS, suppliers)


def test_decisions_reject_ineligible_supplier(suppliers):
    frame = example_decisions(WEEKS, suppliers)
    row = frame.index[frame["material"] == "lithium"][0]  # lithium sells from VAL, ORI, KES
    columns = [c for c in frame.columns if c.startswith("share_")]
    frame.loc[row, columns] = 0.0
    frame.loc[row, "share_AUR"] = 1.0
    with pytest.raises(ContractError, match="ineligible"):
        validate_decisions(frame, WEEKS, suppliers)


def test_material_constant_matches_suppliers(suppliers):
    assert set(MATERIALS) == set(suppliers["material"])


@pytest.mark.parametrize("kind", ["forecasts", "decisions"])
@pytest.mark.parametrize("week", [209.5, float("nan"), float("inf"), -float("inf"),
                                  None, pd.NA, True, np.bool_(False), "209"])
def test_frame_week_keys_rejected_before_coverage(kind, week, suppliers):
    frame = example_forecasts(WEEKS) if kind == "forecasts" else example_decisions(WEEKS, suppliers)
    frame["target_week"] = frame["target_week"].astype(object)
    frame.loc[0, "target_week"] = week
    before = frame.copy(deep=True)
    with pytest.raises(ContractError, match=rf"{kind}\.target_week: invalid week key"):
        if kind == "forecasts":
            validate_forecasts(frame, WEEKS)
        else:
            validate_decisions(frame, WEEKS, suppliers)
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("kind", ["forecasts", "decisions"])
@pytest.mark.parametrize("week", [209.5, float("nan"), float("inf"), None, True, "209"])
def test_request_week_keys_are_not_silently_coerced(kind, week, suppliers):
    with pytest.raises(ContractError, match=rf"{kind}\.target_weeks: invalid week key"):
        if kind == "forecasts":
            validate_forecasts(example_forecasts(WEEKS), [week, 210])
        else:
            validate_decisions(example_decisions(WEEKS, suppliers), [week, 210], suppliers)


@pytest.mark.parametrize("dtype", ["float64", "Float64", "Int64"])
def test_integer_valued_numeric_week_representations_preserve_frames(dtype, suppliers):
    forecasts = example_forecasts(WEEKS)
    decisions = example_decisions(WEEKS, suppliers)
    for frame in (forecasts, decisions):
        frame["target_week"] = frame["target_week"].astype(dtype)
    before_forecasts, before_decisions = forecasts.copy(deep=True), decisions.copy(deep=True)
    validate_forecasts(forecasts, [np.int64(209), 210.0])
    validate_decisions(decisions, [np.int64(209), 210.0], suppliers)
    pd.testing.assert_frame_equal(forecasts, before_forecasts)
    pd.testing.assert_frame_equal(decisions, before_decisions)
