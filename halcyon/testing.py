"""Contract-shaped example frames, so each module can be tested before its neighbours land."""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from .constants import COUNTRIES, MATERIALS


def example_forecasts(target_weeks: Iterable[int], materials: Iterable[str] = MATERIALS) -> pd.DataFrame:
    return pd.DataFrame(
        [{"target_week": w, "material": m, "disruption_prob": 0.2, "price_forecast": 10.0, "model_id": "example"}
         for w in target_weeks for m in materials])


def example_decisions(target_weeks: Iterable[int], suppliers: pd.DataFrame,
                      order_units: float = 100.0) -> pd.DataFrame:
    """Even split across each material's three eligible suppliers. Not a real policy."""
    rows = []
    countries = suppliers.groupby("material")["country"].apply(set).to_dict()
    for week in target_weeks:
        for material, eligible in countries.items():
            shares = {f"share_{c}": (1 / 3 if c in eligible else 0.0) for c in COUNTRIES}
            rows.append({"target_week": week, "material": material, "order_units": order_units,
                         **shares, "policy_id": "example"})
    return pd.DataFrame(rows)
