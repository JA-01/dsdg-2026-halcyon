"""Competition constants. Import from here; do not redefine them per module."""
from __future__ import annotations

MATERIALS = (
    "lithium", "cobalt", "copper", "aluminum", "steel",
    "rare_earths", "semiconductors", "polymer_resin", "specialty_glass", "natural_gas",
)
COUNTRIES = ("KES", "VAL", "SUN", "ORI", "HAL", "AUR")
COUNTRY_LANE = {
    "KES": "MERROW", "VAL": "NORTH", "SUN": "MERROW",
    "ORI": "SOUTH", "HAL": "ATLANTIC", "AUR": "RAIL",
}
LANES = ("MERROW", "NORTH", "SOUTH", "ATLANTIC", "RAIL")

SHARE_COLUMNS = tuple(f"share_{c}" for c in COUNTRIES)
FORECAST_COLUMNS = ("target_week", "material", "disruption_prob", "price_forecast")
DECISION_COLUMNS = ("target_week", "material", "order_units", *SHARE_COLUMNS)
SUBMISSION_COLUMNS = ("id", "disruption_prob", "price_forecast", "order_units", *SHARE_COLUMNS)

SHARE_SUM_TOLERANCE = 1e-6

LAST_WEEK = 234
PUBLIC_WEEKS = tuple(range(209, 222))
PRIVATE_WEEKS = tuple(range(222, 235))
SUBMISSION_WEEKS = PUBLIC_WEEKS + PRIVATE_WEEKS
DEVELOPMENT_ORIGINS = (130, 156)
FINAL_HOLDOUT_ORIGIN = 182
