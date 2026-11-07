from pathlib import Path

import pandas as pd
import pytest

from halcyon.contracts import ContractError
from halcyon.data import Dataset

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def data():
    return Dataset.from_csv_dir(DATA)


def test_loads_with_expected_counts(data):
    assert len(data["prices"]) == 6240 and len(data["suppliers"]) == 30 and len(data["demand"]) == 2340
    assert data.observed_through == 208 and data.cutoff is None
    assert len(data.source_sha256) == 9


def test_as_of_truncates_observations_and_keeps_known_inputs(data):
    view = data.as_of(100)
    for name in ("news", "prices", "tariffs", "shipping", "macro", "outcomes", "supply_history"):
        assert view[name]["week"].max() <= 100, name
    assert view["demand"]["week"].max() == 234
    assert len(view["suppliers"]) == 30
    assert view.cutoff == 100 and view.observed_through == 100


def test_as_of_does_not_mutate_the_original(data):
    before = data["prices"]
    data.as_of(100)
    pd.testing.assert_frame_equal(data["prices"], before)
    assert data.cutoff is None


def test_returned_tables_are_copies(data):
    frame = data["outcomes"]
    frame["disrupted"] = -1
    assert (data["outcomes"]["disrupted"] != -1).all()


def test_inner_origin_can_narrow_but_never_widen(data):
    view = data.as_of(150)
    assert view.as_of(130).cutoff == 130
    with pytest.raises(ContractError, match="widen"):
        view.as_of(151)


def test_cutoff_beyond_release_is_refused(data):
    with pytest.raises(ContractError, match="observed through"):
        data.as_of(209)


def test_optional_table_without_week_fails_closed(data):
    tables = {name: data[name] for name in data}
    tables["news_events"] = data["suppliers"]
    with pytest.raises(ContractError, match="no week column"):
        Dataset(tables).as_of(100)


def test_optional_table_is_truncated_and_discoverable(data):
    tables = {name: data[name] for name in data}
    tables["news_events"] = data["news"][["article_id", "week"]]
    view = Dataset(tables).as_of(100)
    assert "news_events" in view and view["news_events"]["week"].max() <= 100


def test_duplicate_natural_key_is_rejected(data):
    tables = {name: data[name] for name in data}
    tables["outcomes"] = pd.concat([tables["outcomes"], tables["outcomes"].iloc[[0]]])
    with pytest.raises(ContractError, match="outcomes: duplicate key"):
        Dataset(tables)


def test_blank_tariff_announcements_are_null(data):
    tariffs = data["tariffs"]
    assert tariffs["announced_rate"].isna().any() and tariffs["announced_effective_week"].isna().any()
