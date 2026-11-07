import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from halcyon.contracts import ContractError
from halcyon.data import Dataset
from halcyon.forecasting.baseline import HistoricalForecaster
from halcyon.forecasting import models
from halcyon.forecasting.models import PooledForecaster

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def data():
    return Dataset.from_csv_dir(DATA)


def candidate(**kwargs):
    return PooledForecaster(min_history=26, origin_stride=26, max_horizon=6,
                            min_training_rows=20, n_estimators=8,
                            min_samples_leaf=2, **kwargs)


def changed_after(data, cutoff):
    tables = {name: data[name] for name in data}
    for name, frame in tables.items():
        if name in ("demand", "suppliers") or "week" not in frame:
            continue
        future = frame["week"] > cutoff
        for column in frame.select_dtypes(include="number").columns:
            if column == "week":
                continue
            if column == "disrupted":
                frame.loc[future, column] = 1 - frame.loc[future, column]
            else:
                frame.loc[future, column] = frame.loc[future, column] * 7
    return Dataset(tables)


def test_predict_exact_coverage_valid_values_and_determinism(data):
    model = candidate()
    result = model.predict(data, 130, [131, 134, 136])
    expected = {(week, material) for week in [131, 134, 136]
                for material in data["suppliers"]["material"].unique()}
    assert set(result[["target_week", "material"]].itertuples(index=False, name=None)) == expected
    assert len(result) == len(expected)
    assert result["disruption_prob"].between(0, 1).all()
    assert np.isfinite(result["price_forecast"]).all()
    assert (result["price_forecast"] > 0).all()
    assert model.metadata_["fallback"] is None
    assert "horizon" in model.feature_columns_
    assert not ({"target_week", "cutoff_week", "feature_version", "material"} & set(model.feature_columns_))
    pd.testing.assert_frame_equal(result, candidate().predict(data.as_of(130), 130, [131, 134, 136]))


def test_future_realizations_cannot_change_fit_or_predictions(data):
    first, second = candidate(), candidate()
    expected = first.predict(data, 130, [131, 136])
    actual = second.predict(changed_after(data, 130), 130, [131, 136])
    assert first.metadata_["fallback"] is second.metadata_["fallback"] is None
    assert first.price_model_ is not None and first.disruption_model_ is not None
    assert second.price_model_ is not None and second.disruption_model_ is not None
    pd.testing.assert_frame_equal(expected, actual)
    assert first.metadata_ == second.metadata_
    assert first.metadata_["training_target_bounds"][1] <= 130
    assert first.metadata_["training_origin_bounds"][1] < 130


def test_each_inner_origin_is_filtered_and_price_target_is_relative(data, monkeypatch):
    original_builder = models.build_features
    frames = []

    def checked_builder(view, cutoff, targets):
        assert view.cutoff == cutoff
        for name in view:
            if name not in ("suppliers", "demand"):
                assert view[name].empty or view[name]["week"].max() <= cutoff
        result = original_builder(view, cutoff, targets)
        if cutoff < 130:
            assert max(targets) <= 130
            assert (result["cutoff_week"] == cutoff).all()
            frames.append(result.copy())
        return result

    original_fit = models.ExtraTreesRegressor.fit
    captured = {}

    def capture_fit(estimator, x, y, **kwargs):
        captured["target"] = np.asarray(y).copy()
        return original_fit(estimator, x, y, **kwargs)

    monkeypatch.setattr(models, "build_features", checked_builder)
    monkeypatch.setattr(models.ExtraTreesRegressor, "fit", capture_fit)
    model = candidate()
    model.predict(data, 130, [131, 136])
    examples = pd.concat(frames, ignore_index=True).merge(
        data.as_of(130)["outcomes"][["week", "material", "benchmark_price"]].rename(
            columns={"week": "target_week"}), on=["target_week", "material"], validate="many_to_one")
    expected = np.log(examples["benchmark_price"]) - np.log(examples["latest_benchmark_price"])
    np.testing.assert_allclose(captured["target"], expected)
    first_origin_features = frames[0].copy()
    frames.clear()
    model.predict(changed_after(data, 26), 130, [131, 136])
    # Later observations are legitimate later labels but cannot enter the first origin's features.
    pd.testing.assert_frame_equal(first_origin_features, frames[0])


def test_short_history_falls_back_with_explicit_provenance(data):
    model = candidate()
    result = model.predict(data, 10, [11, 12])
    expected = HistoricalForecaster().predict(data, 10, [11, 12])
    pd.testing.assert_frame_equal(result.drop(columns="model_id"), expected.drop(columns="model_id"))
    assert model.metadata_["fallback"]["reason"] == "short_history"
    assert result["model_id"].str.contains("fallback:short_history").all()
    assert model.metadata_["training_rows"] == 0


@pytest.mark.parametrize("label", [0, 1])
def test_single_class_history_uses_explicit_baseline(data, label):
    tables = {name: data[name] for name in data}
    tables["outcomes"]["disrupted"] = label
    model = candidate()
    result = model.predict(Dataset(tables), 130, [131, 136])
    assert model.metadata_["fallback"]["reason"] == "single_class"
    assert model.metadata_["class_distribution"] == {str(label): model.metadata_["training_rows"]}
    assert result["model_id"].str.contains("fallback:single_class").all()
    assert np.isfinite(result[["disruption_prob", "price_forecast"]].to_numpy()).all()
    assert result["disruption_prob"].between(0, 1).all()
    assert (result["price_forecast"] > 0).all()


def test_insufficient_rows_and_fit_state_reset(data):
    model = PooledForecaster(min_training_rows=100000, origin_stride=26, n_estimators=8)
    result = model.predict(data, 130, [131])
    assert model.metadata_["fallback"]["reason"] == "insufficient_training_rows"
    assert result["model_id"].str.contains("fallback:insufficient_training_rows").all()
    model = candidate()
    model.predict(data, 130, [131])
    model.predict(data, 10, [11])
    assert model.preprocessor_ is model.price_model_ is model.disruption_model_ is None
    assert model.feature_columns_ == []


def test_artifacts_capture_fit_and_fallback(data, tmp_path):
    model = candidate()
    with pytest.raises(RuntimeError, match="predict"):
        model.save_artifacts(tmp_path)
    model.predict(data, 130, [131])
    model.save_artifacts(tmp_path)
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["training_target_bounds"][1] <= 130
    training_features = pd.read_csv(tmp_path / metadata["training_features_artifact"])
    assert training_features["target_week"].max() <= 130
    assert training_features["cutoff_week"].max() < 130
    assert not {"benchmark_price", "disrupted"} & set(training_features.columns)
    model.predict(data, 10, [11])
    model.save_artifacts(tmp_path)
    assert json.loads((tmp_path / "metadata.json").read_text())["fallback"]["reason"] == "short_history"
    with (tmp_path / "model.pkl").open("rb") as stream:
        assert pickle.load(stream).price_model_ is None
    assert pd.read_csv(tmp_path / "training_features.csv").empty


@pytest.mark.parametrize("weeks", [[130], [131, 131], [], [137], [131.5]])
def test_invalid_target_requests_fail(data, weeks):
    with pytest.raises(ContractError):
        candidate().predict(data, 130, weeks)


@pytest.mark.parametrize("kwargs", [{"origin_stride": 0}, {"min_history": 0},
                                     {"max_horizon": 0}, {"n_estimators": 0}])
def test_invalid_training_config_fails(kwargs):
    with pytest.raises(ValueError):
        PooledForecaster(**kwargs)


def test_historical_risk_mode_keeps_rates_and_fits_price(data):
    model = candidate(disruption_mode="historical")
    result = model.predict(data, 130, [131, 136]).sort_values(["target_week", "material"]).reset_index(drop=True)
    baseline = HistoricalForecaster().predict(data, 130, [131, 136]).sort_values(
        ["target_week", "material"]).reset_index(drop=True)
    np.testing.assert_array_equal(result.disruption_prob, baseline.disruption_prob)
    assert (result.price_forecast > 0).all()
    assert not np.allclose(result.price_forecast, baseline.price_forecast)
    tables = dict(data)
    tables["outcomes"]["disrupted"] = 0
    result = candidate(disruption_mode="historical").predict(Dataset(tables), 130, [131])
    assert result.disruption_prob.eq(0).all()
    assert not result.model_id.str.contains("fallback").any()
