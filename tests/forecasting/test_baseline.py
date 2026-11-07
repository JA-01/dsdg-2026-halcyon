from pathlib import Path

import pandas as pd
import pytest

from halcyon.contracts import ContractError
from halcyon.data import Dataset
from halcyon.forecasting.baseline import HistoricalForecaster


@pytest.fixture(scope="module")
def data():
    return Dataset.from_csv_dir(Path(__file__).resolve().parents[2] / "data")


def test_baseline_matches_origin_history_not_organizer_sample(data):
    result = HistoricalForecaster().predict(data, 130, [131, 156])
    history = data["outcomes"].query("week <= 130").sort_values("week")
    rates = history.groupby("material").disrupted.mean()
    prices = history.groupby("material").benchmark_price.last()
    for row in result.itertuples():
        assert row.disruption_prob == rates[row.material]
        assert row.price_forecast == prices[row.material]


def test_future_mutation_cannot_change_baseline(data):
    tables = dict(data)
    tables["outcomes"].loc[tables["outcomes"].week > 130, "benchmark_price"] = 999999
    tables["outcomes"].loc[tables["outcomes"].week > 130, "disrupted"] = 1
    model = HistoricalForecaster()
    pd.testing.assert_frame_equal(model.predict(data, 130, [131]),
                                  model.predict(Dataset(tables), 130, [131]))


@pytest.mark.parametrize("weeks", [[130], [131, 131], [131.5], [], [True]])
def test_invalid_targets_rejected(data, weeks):
    with pytest.raises(ContractError):
        HistoricalForecaster().predict(data, 130, weeks)


def test_single_observation_history_is_valid(data):
    result = HistoricalForecaster().predict(data, 1, [2])
    truth = data["outcomes"].query("week == 1").set_index("material")
    for row in result.itertuples():
        assert row.price_forecast == truth.loc[row.material, "benchmark_price"]
        assert row.disruption_prob == truth.loc[row.material, "disrupted"]
