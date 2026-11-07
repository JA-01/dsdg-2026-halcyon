"""Historical disruption rates and carry-forward prices, recomputed at each origin."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from halcyon.constants import MATERIALS
from halcyon.contracts import ContractError, validate_forecasts

from .features import validate_request


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
