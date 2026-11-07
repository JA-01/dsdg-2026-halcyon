"""Historical disruption rates and carry-forward prices, recomputed at each origin."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from halcyon.constants import MATERIALS
from halcyon.contracts import ContractError, validate_forecasts


def validate_request(cutoff: int, target_weeks: list[int]) -> list[int]:
    if isinstance(cutoff, bool) or not isinstance(cutoff, (int, np.integer)) or cutoff < 1:
        raise ContractError("cutoff must be a positive integer")
    weeks = list(target_weeks)
    if not weeks or any(isinstance(w, bool) or not isinstance(w, (int, np.integer)) or w <= cutoff
                        for w in weeks):
        raise ContractError("target weeks must be integers strictly after cutoff")
    if len(set(weeks)) != len(weeks):
        raise ContractError("target weeks must be unique")
    return weeks


class HistoricalForecaster:
    """Competition reference forecasts; never reads the week-208 organizer sample."""

    model_id = "historical_rate_carry_forward_v1"

    def predict(self, data, cutoff: int, target_weeks: list[int]) -> pd.DataFrame:
        weeks = validate_request(cutoff, target_weeks)
        history = data.as_of(cutoff)["outcomes"].sort_values("week")
        grouped = history.groupby("material")
        rates = grouped["disrupted"].mean()
        prices = grouped["benchmark_price"].last()
        missing = set(MATERIALS) - set(rates.index)
        if missing:
            raise ContractError(f"no observed outcomes at cutoff {cutoff} for {sorted(missing)}")
        frame = pd.DataFrame([
            {"target_week": week, "material": material,
             "disruption_prob": float(rates[material]), "price_forecast": float(prices[material]),
             "model_id": self.model_id}
            for week in weeks for material in MATERIALS
        ])
        self.metadata_ = {"model_id": self.model_id, "cutoff_week": int(cutoff),
                          "training_min_week": int(history.week.min()),
                          "training_max_week": int(history.week.max()),
                          "rates": rates.to_dict(), "last_prices": prices.to_dict(),
                          "fallback_reason": None}
        return validate_forecasts(frame, weeks)

    def save_artifacts(self, directory: str | Path) -> None:
        if not hasattr(self, "metadata_"):
            raise RuntimeError("predict must run before saving artifacts")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "model_metadata.json").write_text(json.dumps(self.metadata_, indent=2) + "\n")
