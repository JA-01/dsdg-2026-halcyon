"""Origin-safe forecasting implementations (no network or Spark session required)."""
from .baseline import HistoricalForecaster

__all__ = ["HistoricalForecaster"]
