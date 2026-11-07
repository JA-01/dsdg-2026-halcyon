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
