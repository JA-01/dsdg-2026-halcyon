"""Benchmark price forecasts. Owner: see docs/adr/0001-architecture.md.

Contract: predict(data, cutoff, weeks) -> DataFrame[week, material, price_forecast]
with one row per (week, material), price_forecast > 0. `data` is
`halcyon.data.as_of(..., cutoff)`; never read rows after `cutoff`.
"""

import pandas as pd

from halcyon.data import MATERIALS


def predict(data, cutoff, weeks):
    """Naive reference: last known benchmark price carried forward."""
    last = data["outcomes"].sort_values("week").groupby("material").benchmark_price.last()
    return pd.DataFrame([(w, m, float(last[m])) for w in weeks for m in MATERIALS],
                        columns=["week", "material", "price_forecast"])
