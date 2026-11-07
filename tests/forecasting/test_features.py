"""Consumer-facing feature invariants, independent of pipeline/model wiring."""
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

from halcyon.constants import MATERIALS
from halcyon.contracts import ContractError
from halcyon.data import Dataset, SCHEMAS
from halcyon.forecasting.features import (
    CONTEXT_COLUMNS, FEATURE_COLUMNS, FEATURE_VERSION, NUMERIC_FEATURES, build_features,
)

DATA = Path(__file__).resolve().parents[2] / "data"
TARGETS = [131, 143, 144, 156]


@pytest.fixture(scope="module")
def data():
    return Dataset.from_csv_dir(DATA)


def tables_from(data):
    return {name: data[name] for name in data}


def test_exact_keys_stable_schema_and_numeric_consumer(data):
    features = build_features(data, 130, list(reversed(TARGETS)))
    assert tuple(features.columns) == FEATURE_COLUMNS
    assert set(features[["target_week", "material"]].itertuples(index=False, name=None)) == {
        (week, material) for week in TARGETS for material in MATERIALS
    }
    assert features["feature_version"].eq(FEATURE_VERSION).all()
    assert features["cutoff_week"].eq(130).all()
    assert features["horizon"].equals(features["target_week"] - 130)
    # A consumer can discover numeric model inputs by excluding context; metadata
    # strings do not become numeric predictors, and horizon remains available.
    predictors = features.drop(columns=list(CONTEXT_COLUMNS)).to_numpy(dtype=float)
    assert predictors.shape == (40, len(NUMERIC_FEATURES))
    assert np.isfinite(predictors).all()
    assert (features["latest_benchmark_price"] > 0).all()
    assert features["disruption_rate_13"].between(0, 1).all()


def test_future_observations_cannot_change_inner_origin(data):
    tables = tables_from(data)
    columns = {
        "outcomes": ["benchmark_price", "disrupted"],
        "prices": ["spot_price", "futures_4w"],
        "tariffs": ["tariff_rate", "announced_rate"],
        "shipping": ["container_rate", "transit_days", "congestion_index"],
        "macro": ["pmi", "fx_rate", "cpi_yoy", "policy_rate", "tension_index"],
        "supply_history": ["capacity_units", "lead_time_weeks", "landed_cost"],
    }
    for name, fields in columns.items():
        for field in fields:
            tables[name].loc[tables[name]["week"] > 130, field] = 999
    mutated = Dataset(tables).as_of(156)
    pd.testing.assert_frame_equal(
        build_features(data.as_of(156), 130, TARGETS),
        build_features(mutated, 130, TARGETS),
    )


def test_changed_observed_history_changes_features(data):
    tables = tables_from(data)
    mask = (tables["outcomes"]["week"] == 130) & (tables["outcomes"]["material"] == "lithium")
    tables["outcomes"].loc[mask, "benchmark_price"] *= 2
    before = build_features(data, 130, [131]).set_index("material")
    after = build_features(Dataset(tables), 130, [131]).set_index("material")
    assert after.loc["lithium", "latest_benchmark_price"] == 2 * before.loc["lithium", "latest_benchmark_price"]
    assert after.loc["lithium", "benchmark_mean_4"] != before.loc["lithium", "benchmark_mean_4"]
    assert after.loc["lithium", "benchmark_lag_1"] == before.loc["lithium", "benchmark_lag_1"]
    pd.testing.assert_frame_equal(before.drop(index="lithium"), after.drop(index="lithium"))


def test_tariff_announcement_uses_publication_and_effective_cutoffs(data):
    tables = tables_from(data)
    tariffs = tables["tariffs"]
    selected = tariffs["material"] == "lithium"
    tariffs.loc[selected, "announced_rate"] = np.nan
    tariffs.loc[selected, "announced_effective_week"] = pd.NA
    tariffs.loc[selected, "tariff_rate"] = 0.1
    countries = sorted(tariffs.loc[selected, "country"].unique())
    for publication, country, rate, effective in (
        (130, countries[0], 0.7, 143),
        (131, countries[1], 0.9, 131),  # Not yet published at this origin.
        (130, countries[2], 0.8, 157),  # Published, but not effective in these targets.
    ):
        mask = selected & (tariffs["country"] == country) & (tariffs["week"] == publication)
        tariffs.loc[mask, "announced_rate"] = rate
        tariffs.loc[mask, "announced_effective_week"] = effective
    features = build_features(Dataset(tables), 130, [131, 143, 156])
    lithium = features.loc[features["material"] == "lithium"].set_index("target_week")
    assert lithium.loc[131, "target_tariff_mean"] == pytest.approx(0.1)
    assert lithium.loc[143, "target_tariff_mean"] == pytest.approx(0.3)
    assert lithium.loc[156, "tariff_announced_delta_mean"] == pytest.approx(0.2)


def test_future_demand_is_known_but_only_requested_target_changes(data):
    tables = tables_from(data)
    mask = (tables["demand"]["material"] == "lithium") & (tables["demand"]["week"] == 143)
    tables["demand"].loc[mask, "demand_units"] *= 2
    before = build_features(data, 130, [131, 143]).set_index(["target_week", "material"])
    after = build_features(Dataset(tables), 130, [131, 143]).set_index(["target_week", "material"])
    assert after.loc[(143, "lithium"), "demand_units"] == 2 * before.loc[(143, "lithium"), "demand_units"]
    pd.testing.assert_frame_equal(before.drop(index=(143, "lithium")), after.drop(index=(143, "lithium")))


def test_outer_view_cannot_be_widened(data):
    with pytest.raises(ContractError, match="widen"):
        build_features(data.as_of(130), 156, [157])


def test_optional_news_is_not_a_core_dependency(data):
    baseline = build_features(data, 130, [131])
    tables = tables_from(data)
    # Raw news remains a required Dataset table, but optional parsed events are
    # neither required nor implicitly transformed into model inputs.
    tables["news"] = tables["news"].iloc[:0]
    tables["news_events"] = pd.DataFrame({"week": [130, 131], "signal": [999.0, -999.0]})
    pd.testing.assert_frame_equal(baseline, build_features(Dataset(tables), 130, [131]))


@pytest.mark.parametrize("cutoff,targets", [(130, []), (130, [131, 131]), (130, [130]), (130, [131.5]), (True, [131])])
def test_invalid_request_is_rejected(data, cutoff, targets):
    with pytest.raises(ContractError):
        build_features(data, cutoff, targets)


def test_short_history_has_finite_lags_and_population_std(data):
    features = build_features(data, 1, [2])
    assert np.isfinite(features[list(NUMERIC_FEATURES)].to_numpy(dtype=float)).all()
    assert features["benchmark_lag_4"].equals(features["latest_benchmark_price"])
    assert features["benchmark_std_13"].eq(0).all()


def test_missing_material_history_and_missing_target_demand_fail(data):
    tables = tables_from(data)
    tables["outcomes"] = tables["outcomes"].loc[tables["outcomes"]["material"] != "lithium"]
    with pytest.raises(ContractError, match="no observed history for lithium"):
        build_features(Dataset(tables), 130, [131])
    tables = tables_from(data)
    tables["demand"] = tables["demand"].loc[~((tables["demand"]["material"] == "lithium") & (tables["demand"]["week"] == 131))]
    with pytest.raises(ContractError, match="demand: missing/duplicate target"):
        build_features(Dataset(tables), 130, [131])


@pytest.fixture(scope="module")
def spark():
    pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession
    previous_python = os.environ.get("PYSPARK_PYTHON")
    os.environ["PYSPARK_PYTHON"] = sys.executable
    session = (SparkSession.builder.master("local[2]").appName("halcyon-feature-tests")
               .config("spark.sql.shuffle.partitions", "2")
               .config("spark.pyspark.python", sys.executable).getOrCreate())
    yield session
    session.stop()
    if previous_python is None:
        os.environ.pop("PYSPARK_PYTHON", None)
    else:
        os.environ["PYSPARK_PYTHON"] = previous_python


def test_native_spark_schema_numeric_parity_and_future_boundary(data, spark):
    from pyspark.sql import functions as F, types as T
    from halcyon.forecasting.spark import build_spark_features

    # Explicit source schemas keep empty announcement cells null rather than NaN.
    source = {}
    for name, schema in SCHEMAS.items():
        fields = [T.StructField(column, T.StringType() if dtype == "str" else T.LongType() if dtype in ("int64", "Int64") else T.DoubleType(), True) for column, dtype in schema.items()]
        source[name] = spark.read.option("header", True).schema(T.StructType(fields)).csv(str(DATA / f"{name}.csv"))
    identity = dict(run_id="test-run", release_id="test-release", window_id="development130")
    actual = build_spark_features(source, 130, TARGETS, **identity).toPandas()
    expected = build_features(data, 130, TARGETS)
    assert set(actual.columns) == {"run_id", "release_id", "window_id", *FEATURE_COLUMNS}
    for name, value in identity.items():
        assert actual[name].eq(value).all()
    keys = ["target_week", "material"]
    actual = actual.sort_values(keys).reset_index(drop=True)
    expected = expected.sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(actual[keys], expected[keys], check_dtype=False)
    np.testing.assert_allclose(actual[list(NUMERIC_FEATURES)], expected[list(NUMERIC_FEATURES)], rtol=1e-10, atol=1e-10)
    changed = dict(source)
    for name in ("outcomes", "prices", "tariffs", "shipping", "macro", "supply_history"):
        frame = changed[name]
        for field in frame.schema.fields:
            if isinstance(field.dataType, (T.LongType, T.DoubleType)) and field.name != "week":
                frame = frame.withColumn(field.name, F.when(F.col("week") > 130, F.lit(999).cast(field.dataType)).otherwise(F.col(field.name)))
        changed[name] = frame
    mutated = build_spark_features(changed, 130, TARGETS, **identity).toPandas().sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(actual, mutated)
