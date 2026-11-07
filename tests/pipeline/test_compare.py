from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from halcyon.baselines import ProvisionalForecaster
from halcyon.compare import backtest_pair, compare, comparison_manifest, forecast_metrics, summarize
from halcyon.contracts import ContractError
from halcyon.data import Dataset
from halcyon.policy import NaivePolicy

DATA = Path(__file__).resolve().parents[2] / "data"
PAIR = {"forecaster": {"class": "halcyon.baselines:ProvisionalForecaster"},
        "policy": {"class": "halcyon.policy:NaivePolicy"}}


@pytest.fixture(scope="module")
def data():
    return Dataset.from_csv_dir(DATA)


def test_reference_forecast_has_exactly_zero_skill(data):
    """The provisional forecaster is the scoring reference, so its skill must be exactly 0."""
    forecasts = ProvisionalForecaster().predict(data.as_of(130), 130, list(range(131, 144)))
    metrics = forecast_metrics(forecasts, data, 130)
    assert metrics["brier_skill"] == pytest.approx(0) and metrics["mape_skill"] == pytest.approx(0)


def test_better_forecast_has_positive_skill_from_known_truth(data):
    forecasts = ProvisionalForecaster().predict(data.as_of(130), 130, list(range(131, 144)))
    truth = data["outcomes"].rename(columns={"week": "target_week"})
    perfect = forecasts.drop(columns=["disruption_prob", "price_forecast"]).merge(truth, on=["target_week", "material"])
    perfect = perfect.rename(columns={"disrupted": "disruption_prob", "benchmark_price": "price_forecast"})
    metrics = forecast_metrics(perfect, data, 130)
    assert metrics["brier"] == 0 and metrics["mape"] == 0
    assert metrics["brier_skill"] == 1 and metrics["mape_skill"] == 1


def test_forecasts_past_released_outcomes_are_refused(data):
    forecasts = ProvisionalForecaster().predict(data.as_of(208), 208, [209])
    with pytest.raises(ContractError, match="no released outcomes"):
        forecast_metrics(forecasts, data, 208)


def test_holdout_is_locked_by_default(data):
    with pytest.raises(ContractError, match="locked holdout"):
        compare(data, {"a": PAIR}, [182])


def test_backtest_has_independent_windows_and_unique_keys(data):
    rows = pd.DataFrame(backtest_pair(data, "a", ProvisionalForecaster(), NaivePolicy(), 130))
    assert set(rows["window_id"]) == {"origin130_h01_13", "origin130_h14_26"}
    assert not rows.duplicated(["candidate", "origin", "window_id", "material", "metric"]).any()
    assert (rows["score_status"] == "proxy").all()


def test_later_rows_do_not_change_an_earlier_decision(data):
    """Policies get as_of views: rewriting supply after the origin cannot move their orders."""
    from halcyon.contracts import historical_windows
    from halcyon.pipeline import plan_windows
    from halcyon.policy import InventoryPolicy

    tables = {name: data[name] for name in data}
    future = tables["supply_history"]["week"] > 130
    tables["supply_history"].loc[future, "capacity_units"] = 1.0
    mutated = Dataset(tables)
    windows = historical_windows(130)
    _, before = plan_windows(data, windows, ProvisionalForecaster(), InventoryPolicy())
    _, after = plan_windows(mutated, windows, ProvisionalForecaster(), InventoryPolicy())
    pd.testing.assert_frame_equal(before, after)


def test_summary_has_one_row_per_candidate_window(data):
    summary = summarize(compare(data, {"a": PAIR, "b": PAIR}, [130]))
    assert len(summary) == 4
    assert np.isfinite(summary["total_cost"]).all()


def test_manifest_records_what_a_comparison_needs_to_be_reconstructed(data):
    manifest = comparison_manifest({"candidates": {}}, data, [130])
    assert len(manifest["source_sha256"]) == 9 and manifest["holdout_used"] is False
    assert {"git_sha", "dirty", "package_versions", "simulator_assumptions"} <= set(manifest)
    assert manifest["score_status"] == "proxy"
