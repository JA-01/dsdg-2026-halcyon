"""Point-in-time access to the competition CSVs."""

from pathlib import Path

import pandas as pd

MATERIALS = ("lithium", "cobalt", "copper", "aluminum", "steel", "rare_earths",
             "semiconductors", "polymer_resin", "specialty_glass", "natural_gas")
COUNTRIES = ("KES", "VAL", "SUN", "ORI", "HAL", "AUR")
SHARE_COLUMNS = tuple(f"share_{c}" for c in COUNTRIES)
SUBMISSION_COLUMNS = ("id", "disruption_prob", "price_forecast", "order_units", *SHARE_COLUMNS)
# Weekly tables that are only released up to the current cutoff.
TIMED_TABLES = ("news", "prices", "tariffs", "shipping", "macro", "outcomes", "supply_history")
# Known for every week (demand) or static.
STATIC_TABLES = ("demand", "suppliers", "sample_submission")
WINDOWS = ((209, 221), (222, 234))


def read_all(data_dir="data"):
    """Every CSV in `data_dir`, unfiltered."""
    root = Path(data_dir)
    return {name: pd.read_csv(root / f"{name}.csv") for name in TIMED_TABLES + STATIC_TABLES}


def release_cutoff(tables):
    """Last week with released labels (208 in Phase 1, 221 in Phase 2)."""
    return int(tables["outcomes"].week.max())


def as_of(tables, cutoff):
    """Tables as a forecaster standing at the end of `cutoff` would see them.

    Weekly tables keep rows with week <= cutoff. Demand stays complete because
    the production plan is published for all 234 weeks.
    """
    view = {name: tables[name] for name in STATIC_TABLES}
    for name in TIMED_TABLES:
        frame = tables[name]
        view[name] = frame.loc[frame.week <= cutoff].reset_index(drop=True)
    return view


def load(data_dir="data", cutoff=None):
    """Tables as of `cutoff` (default: the release cutoff)."""
    tables = read_all(data_dir)
    return as_of(tables, release_cutoff(tables) if cutoff is None else cutoff)
