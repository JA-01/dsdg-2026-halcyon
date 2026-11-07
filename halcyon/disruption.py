"""Disruption probability forecasts. Owner: see docs/adr/0001-architecture.md.

Contract: predict(data, cutoff, weeks) -> DataFrame[week, material, disruption_prob]
with one row per (week, material) for every week in `weeks` and every material.
`data` is `halcyon.data.as_of(..., cutoff)`; never read rows after `cutoff`.
"""

import pandas as pd

from halcyon.data import MATERIALS


def predict(data, cutoff, weeks):
    """Naive reference: each material's historical disruption rate, flat."""
    rate = data["outcomes"].groupby("material").disrupted.mean()
    return pd.DataFrame([(w, m, float(rate[m])) for w in weeks for m in MATERIALS],
                        columns=["week", "material", "disruption_prob"])
