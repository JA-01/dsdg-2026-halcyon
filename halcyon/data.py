"""Typed competition tables with a point-in-time boundary.

    data = Dataset.from_csv_dir("data")
    visible = data.as_of(208)
    visible["prices"]                  # a DataFrame copy; weeks <= 208 only
    visible["demand"]                  # all 234 weeks: the plan is known in advance
    "news_events" in visible           # optional tables
    visible.as_of(130)                 # inner training origin; later cutoffs are refused

The mapping form `data[name]` is the one table accessor. Keep the unfiltered Dataset with
the evaluator and hand models/policies only the `as_of` view.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator, Mapping

import pandas as pd

from .contracts import ContractError

SCHEMAS: dict[str, dict] = {
    "news": {"article_id": "str", "week": "int64", "date": "str", "source": "str",
             "headline": "str", "body": "str"},
    "prices": {"week": "int64", "date": "str", "material": "str", "country": "str",
               "spot_price": "float64", "futures_4w": "float64"},
    "tariffs": {"week": "int64", "date": "str", "material": "str", "country": "str",
                "tariff_rate": "float64", "announced_rate": "float64",
                "announced_effective_week": "Int64"},
    "shipping": {"week": "int64", "date": "str", "lane": "str", "container_rate": "float64",
                 "transit_days": "float64", "congestion_index": "float64"},
    "macro": {"week": "int64", "date": "str", "country": "str", "pmi": "float64",
              "fx_rate": "float64", "cpi_yoy": "float64", "policy_rate": "float64",
              "tension_index": "float64"},
    "suppliers": {"material": "str", "country": "str", "country_name": "str", "lane": "str",
                  "base_lead_weeks": "int64", "normal_capacity_units": "float64",
                  "base_tariff": "float64"},
    "demand": {"week": "int64", "date": "str", "material": "str", "demand_units": "float64"},
    "outcomes": {"week": "int64", "date": "str", "material": "str",
                 "benchmark_price": "float64", "disrupted": "int64"},
    "supply_history": {"week": "int64", "date": "str", "material": "str", "country": "str",
                       "capacity_units": "float64", "lead_time_weeks": "int64",
                       "landed_cost": "float64"},
}
NATURAL_KEYS = {
    "news": ["article_id"],
    "prices": ["week", "material", "country"],
    "tariffs": ["week", "material", "country"],
    "shipping": ["week", "lane"],
    "macro": ["week", "country"],
    "suppliers": ["material", "country"],
    "demand": ["week", "material"],
    "outcomes": ["week", "material"],
    "supply_history": ["week", "material", "country"],
}
# Everything else must have a `week` column and is truncated: unknown tables fail closed.
UNFILTERED = {"suppliers", "demand"}
REQUIRED = tuple(SCHEMAS)


class Dataset(Mapping[str, pd.DataFrame]):
    def __init__(self, tables: Mapping[str, pd.DataFrame], cutoff: int | None = None,
                 source_sha256: Mapping[str, str] | None = None) -> None:
        missing = [t for t in REQUIRED if t not in tables]
        if missing:
            raise ContractError(f"Dataset: missing tables {missing}")
        self._tables = dict(tables)
        self.cutoff = cutoff
        self.source_sha256 = dict(source_sha256 or {})
        for name, frame in self._tables.items():
            _check_table(name, frame)
        per_material = self._tables["suppliers"].groupby("material")["country"].nunique()
        if not (per_material == 3).all():
            raise ContractError(f"suppliers: need 3 countries per material, got {per_material.to_dict()}")

    @classmethod
    def from_csv_dir(cls, directory: str | Path) -> "Dataset":
        directory = Path(directory)
        tables, hashes = {}, {}
        for name, schema in SCHEMAS.items():
            path = directory / f"{name}.csv"
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            tables[name] = pd.read_csv(path, dtype=schema)
        return cls(tables, source_sha256=hashes)

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self._tables[name].copy()

    def __iter__(self) -> Iterator[str]:
        return iter(self._tables)

    def __len__(self) -> int:
        return len(self._tables)

    @property
    def observed_through(self) -> int:
        """Last week with released labels, within this view."""
        return int(self._tables["outcomes"]["week"].max())

    def as_of(self, cutoff: int) -> "Dataset":
        """Return a filtered copy: observations through cutoff, plus known demand and suppliers."""
        if self.cutoff is not None and cutoff > self.cutoff:
            raise ContractError(f"as_of({cutoff}) would widen a view already cut at {self.cutoff}")
        if cutoff > self.observed_through:
            raise ContractError(f"as_of({cutoff}): data is only observed through {self.observed_through}")
        tables = {}
        for name, frame in self._tables.items():
            if name in UNFILTERED:
                tables[name] = frame.copy()
            elif "week" in frame.columns:
                tables[name] = frame.loc[frame["week"] <= cutoff].copy()
            else:
                raise ContractError(f"as_of: table {name!r} has no week column to filter on")
        return Dataset(tables, cutoff=cutoff, source_sha256=self.source_sha256)


def _check_table(name: str, frame: pd.DataFrame) -> None:
    if name in SCHEMAS:
        missing = [c for c in SCHEMAS[name] if c not in frame.columns]
        if missing:
            raise ContractError(f"{name}: missing columns {missing}")
    key = NATURAL_KEYS.get(name)
    if key:
        duplicated = frame[frame.duplicated(key)]
        if len(duplicated):
            raise ContractError(f"{name}: duplicate key {duplicated.iloc[0][key].to_dict()}")
