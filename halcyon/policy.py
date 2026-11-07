"""Ordering policy. Owner: see docs/adr/0001-architecture.md.

Contract: plan(data, cutoff, weeks, forecasts) ->
DataFrame[week, material, order_units, share_KES..share_AUR], one row per
(week, material). `forecasts` has columns week, material, disruption_prob,
price_forecast for the same weeks. Shares sum to 1 and are 0 for countries
that do not sell the material. `data` is `halcyon.data.as_of(..., cutoff)`.
"""

import pandas as pd

from halcyon.data import COUNTRIES, MATERIALS


def plan(data, cutoff, weeks, forecasts):
    """Naive reference: order each week's demand from the supplier with the lowest
    mean landed cost to date (reproduces sample_submission.csv)."""
    mean_cost = data["supply_history"].groupby(["material", "country"]).landed_cost.mean().reset_index()
    cheapest = mean_cost.loc[mean_cost.groupby("material").landed_cost.idxmin()].set_index("material").country
    demand = data["demand"].set_index(["week", "material"]).demand_units
    rows = []
    for w in weeks:
        for m in MATERIALS:
            shares = {f"share_{c}": float(c == cheapest[m]) for c in COUNTRIES}
            rows.append({"week": w, "material": m, "order_units": float(demand[(w, m)]), **shares})
    return pd.DataFrame(rows)
