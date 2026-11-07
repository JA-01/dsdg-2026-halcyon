"""Module boundaries from docs/contracts.md: protocols, windows and frame checks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Protocol, runtime_checkable

import numpy as np
import pandas as pd

from .constants import (
    COUNTRIES, DECISION_COLUMNS, FORECAST_COLUMNS, MATERIALS, PRIVATE_WEEKS, PUBLIC_WEEKS,
    SHARE_COLUMNS, SHARE_SUM_TOLERANCE,
)

if TYPE_CHECKING:
    from .data import Dataset


class ContractError(ValueError):
    """A frame or dataset violates docs/contracts.md."""


@runtime_checkable
class Forecaster(Protocol):
    def predict(self, data: "Dataset", cutoff: int, target_weeks: list[int]) -> pd.DataFrame:
        """Return one row per target_week/material; see validate_forecasts."""
        ...


@runtime_checkable
class Policy(Protocol):
    def decide(
        self, data: "Dataset", forecasts: pd.DataFrame, cutoff: int, target_weeks: list[int]
    ) -> pd.DataFrame:
        """Plan one window from fresh predicted inventory; see validate_decisions."""
        ...


@dataclass(frozen=True)
class Window:
    """One independently initialized scoring window, forecast from `cutoff`."""

    window_id: str
    cutoff: int
    target_weeks: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.target_weeks or min(self.target_weeks) <= self.cutoff:
            raise ContractError(f"{self.window_id}: targets must be after cutoff {self.cutoff}")


def phase1_windows(cutoff: int = 208) -> tuple[Window, Window]:
    return Window("public", cutoff, PUBLIC_WEEKS), Window("private", cutoff, PRIVATE_WEEKS)


def phase2_windows(cutoff: int = 221) -> tuple[Window]:
    """Only private is planned; public rows are retained from an archived Phase 1 run."""
    return (Window("private", cutoff, PRIVATE_WEEKS),)


def historical_windows(origin: int) -> tuple[Window, Window]:
    """Backtest mirror of Phase 1: both windows are forecast from the same origin."""
    return (
        Window(f"origin{origin}_h01_13", origin, tuple(range(origin + 1, origin + 14))),
        Window(f"origin{origin}_h14_26", origin, tuple(range(origin + 14, origin + 27))),
    )


def eligibility(suppliers: pd.DataFrame) -> dict[str, set[str]]:
    """Map material -> eligible country codes."""
    return {m: set(g["country"]) for m, g in suppliers.groupby("material")}


def _check_keys(df: pd.DataFrame, columns: Iterable[str], target_weeks: Iterable[int], name: str,
                materials: Iterable[str]) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ContractError(f"{name}: missing columns {missing}")
    keys = df[["target_week", "material"]]
    duplicated = keys[keys.duplicated()]
    if len(duplicated):
        raise ContractError(f"{name}: duplicate key {tuple(duplicated.iloc[0])}")
    expected = {(int(w), m) for w in target_weeks for m in materials}
    actual = {(int(w), m) for w, m in keys.itertuples(index=False)}
    if expected - actual:
        raise ContractError(f"{name}: missing key {min(expected - actual)}")
    if actual - expected:
        raise ContractError(f"{name}: unexpected key {min(actual - expected)}")


def _first_bad(df: pd.DataFrame, mask: pd.Series) -> tuple:
    row = df.loc[mask].iloc[0]
    return int(row["target_week"]), row["material"]


def validate_forecasts(df: pd.DataFrame, target_weeks: Iterable[int],
                       materials: Iterable[str] = MATERIALS) -> pd.DataFrame:
    """Raise ContractError naming the first bad key; return df unchanged when valid."""
    _check_keys(df, FORECAST_COLUMNS, target_weeks, "forecasts", materials)
    prob = pd.to_numeric(df["disruption_prob"], errors="coerce").astype(float)
    price = pd.to_numeric(df["price_forecast"], errors="coerce").astype(float)
    bad = ~np.isfinite(prob) | (prob < 0) | (prob > 1)
    if bad.any():
        raise ContractError(f"forecasts: disruption_prob invalid at {_first_bad(df, bad)}")
    bad = ~np.isfinite(price) | (price <= 0)
    if bad.any():
        raise ContractError(f"forecasts: price_forecast invalid at {_first_bad(df, bad)}")
    return df


def validate_decisions(df: pd.DataFrame, target_weeks: Iterable[int], suppliers: pd.DataFrame,
                       materials: Iterable[str] = MATERIALS) -> pd.DataFrame:
    """Raise ContractError naming the first bad key. Never repairs values."""
    _check_keys(df, DECISION_COLUMNS, target_weeks, "decisions", materials)
    orders = pd.to_numeric(df["order_units"], errors="coerce").astype(float)
    bad = ~np.isfinite(orders) | (orders < 0)
    if bad.any():
        raise ContractError(f"decisions: order_units invalid at {_first_bad(df, bad)}")
    shares = df[list(SHARE_COLUMNS)].apply(pd.to_numeric, errors="coerce").astype(float)
    values = shares.to_numpy()
    bad = pd.Series(~np.isfinite(values).all(axis=1) | (values < 0).any(axis=1) | (values > 1).any(axis=1),
                    index=df.index)
    if bad.any():
        raise ContractError(f"decisions: share outside [0, 1] at {_first_bad(df, bad)}")
    bad = (shares.sum(axis=1) - 1).abs() > SHARE_SUM_TOLERANCE
    if bad.any():
        raise ContractError(f"decisions: shares do not sum to 1 at {_first_bad(df, bad)}")
    allowed = eligibility(suppliers)
    for country, column in zip(COUNTRIES, SHARE_COLUMNS):
        bad = (shares[column] != 0) & ~df["material"].map(lambda m: country in allowed[m])
        if bad.any():
            raise ContractError(f"decisions: {column} on ineligible supplier at {_first_bad(df, bad)}")
    return df
