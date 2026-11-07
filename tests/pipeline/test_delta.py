from pathlib import Path

import pandas as pd
import pytest

from halcyon import delta
from halcyon.data import SCHEMAS, Dataset

DATA = Path(__file__).resolve().parents[2] / "data"
VERSIONS = {f"bronze_{name}": 1 for name in SCHEMAS}


class FakeResult:
    def __init__(self, frame):
        self.frame = frame

    def toPandas(self):
        return self.frame


class FakeSpark:
    """Serves bronze-shaped frames in a shuffled order, as Delta does not guarantee row order."""

    def __init__(self, data, empty=()):
        self.data, self.empty, self.queries = data, set(empty), []

    def sql(self, query, args=None):
        self.queries.append((query, args))
        table = query.split("`.")[2].split(" ")[0].replace("bronze_", "")
        frame = self.data[table].sample(frac=1, random_state=1)
        if table in self.empty:
            frame = frame.iloc[0:0]
        return FakeResult(frame.assign(release_id=args["release_id"], source_sha256=f"sha-{table}", ingested_at="now"))


@pytest.fixture(scope="module")
def data():
    return Dataset.from_csv_dir(DATA)


def test_every_read_pins_a_version_and_filters_release(data):
    spark = FakeSpark(data)
    delta.load_release(spark, "workspace", "halcyon", "rel", VERSIONS)
    assert len(spark.queries) == 9
    for query, args in spark.queries:
        assert "VERSION AS OF 1" in query and ":release_id" in query and args == {"release_id": "rel"}


def test_delta_and_csv_give_the_same_tables(data):
    loaded = delta.load_release(FakeSpark(data), "workspace", "halcyon", "rel", VERSIONS)
    for name in SCHEMAS:
        pd.testing.assert_frame_equal(loaded[name], data[name], check_dtype=False, obj=name)
    assert loaded.source_sha256["prices"] == "sha-prices"


def test_missing_pin_and_empty_release_fail(data):
    with pytest.raises(ValueError, match="no pinned"):
        delta.load_release(FakeSpark(data), "workspace", "halcyon", "rel", {})
    with pytest.raises(ValueError, match="no rows"):
        delta.load_release(FakeSpark(data, empty={"news"}), "workspace", "halcyon", "rel", VERSIONS)


def test_identifiers_are_checked(data):
    with pytest.raises(ValueError, match="invalid identifier"):
        delta.load_release(FakeSpark(data), "x`; DROP", "halcyon", "rel", VERSIONS)


class DroppingResult:
    def __init__(self):
        self.dropped = None

    def drop(self, *columns):
        self.dropped = columns
        return self


class PinnedSpark:
    def __init__(self):
        self.queries = []

    def sql(self, query, args=None):
        self.queries.append((query, args))
        return DroppingResult()


def test_pinned_tables_pin_versions_filter_release_and_drop_metadata():
    spark = PinnedSpark()
    tables = delta.pinned_tables(spark, "workspace", "halcyon", "rel", VERSIONS)
    assert set(tables) == set(SCHEMAS) and len(spark.queries) == 9
    for query, args in spark.queries:
        assert "VERSION AS OF 1" in query and args == {"release_id": "rel"}
    assert tables["prices"].dropped == tuple(delta.METADATA_COLUMNS)
    with pytest.raises(ValueError, match="no pinned"):
        delta.pinned_tables(spark, "workspace", "halcyon", "rel", {})


def _features():
    return pd.DataFrame({"target_week": [131, 131], "material": ["a", "b"], "x": [1.0, float("nan")]})


def test_parity_accepts_a_reordered_match():
    assert delta.check_feature_parity(_features().iloc[::-1], _features()) == 1


def test_parity_rejects_value_and_key_differences():
    changed = _features().assign(x=[1.5, float("nan")])
    with pytest.raises(ValueError, match="differ on feature x"):
        delta.check_feature_parity(changed, _features())
    with pytest.raises(ValueError, match="different keys"):
        delta.check_feature_parity(_features().assign(material=["a", "c"]), _features())
    with pytest.raises(ValueError, match="no shared numeric"):
        delta.check_feature_parity(_features().drop(columns="x"), _features())
