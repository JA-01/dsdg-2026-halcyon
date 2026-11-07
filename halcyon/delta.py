"""Pinned Delta reads and run-scoped gold writes. Needs a Spark session; nothing else here does."""
from __future__ import annotations

import re
from typing import Mapping

import pandas as pd

from .data import SCHEMAS, Dataset

METADATA_COLUMNS = ["release_id", "source_sha256", "ingested_at"]
IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def _namespace(catalog: str, schema: str) -> str:
    for name in (catalog, schema):
        if not IDENTIFIER.match(name):
            raise ValueError(f"invalid identifier {name!r}")
    return f"`{catalog}`.`{schema}`"


def load_release(spark, catalog: str, schema: str, release_id: str,
                 versions: Mapping[str, int]) -> Dataset:
    """Read one release at pinned table versions. Never reads a table's latest state."""
    namespace = _namespace(catalog, schema)
    tables, hashes = {}, {}
    for name, columns in SCHEMAS.items():
        table = f"bronze_{name}"
        if table not in versions:
            raise ValueError(f"no pinned Delta version for {table}")
        frame = spark.sql(
            f"SELECT * FROM {namespace}.{table} VERSION AS OF {int(versions[table])} "
            "WHERE release_id = :release_id", args={"release_id": release_id}).toPandas()
        if frame.empty:
            raise ValueError(f"{table}@{versions[table]} has no rows for release {release_id}")
        checksums = frame["source_sha256"].unique()
        if len(checksums) != 1:
            raise ValueError(f"{table}: expected one source checksum, found {len(checksums)}")
        hashes[name] = str(checksums[0])
        tables[name] = _coerce(frame.drop(columns=METADATA_COLUMNS), columns)
    return Dataset(tables, source_sha256=hashes)


def _coerce(frame: pd.DataFrame, columns: Mapping[str, str]) -> pd.DataFrame:
    frame = frame.copy()
    for column, dtype in columns.items():
        if dtype == "str":
            frame[column] = frame[column].astype(str)
        else:
            frame[column] = pd.to_numeric(frame[column]).astype(dtype)
    return frame


def write_gold(spark, catalog: str, schema: str, table: str, frame: pd.DataFrame) -> None:
    """Append this run's rows. A run ID is unique, so other runs and releases are preserved."""
    if not IDENTIFIER.match(table) or "run_id" not in frame.columns:
        raise ValueError("gold writes need a safe table name and a run_id column")
    plain = frame.astype({c: object for c in frame.columns if pd.api.types.is_string_dtype(frame[c])})
    (spark.createDataFrame(plain).write.format("delta").mode("append")
     .option("mergeSchema", "true").saveAsTable(f"{_namespace(catalog, schema)}.`{table}`"))
