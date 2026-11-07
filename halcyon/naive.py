"""The organizer's naive reference, which scores 0 (reproduces sample_submission.csv).

Shared by the scorer (naive at every backtest origin) and by the tests. Same
contracts as halcyon.disruption / halcyon.price / halcyon.policy.
"""

import pandas as pd

from halcyon.data import COUNTRIES, MATERIALS


def disruption(data, cutoff, weeks):
    """Each material's historical disruption rate, flat."""
    rate = data["outcomes"].groupby("material").disrupted.mean()
    return pd.DataFrame([(w, m, float(rate[m])) for w in weeks for m in MATERIALS],
                        columns=["week", "material", "disruption_prob"])


def price(data, cutoff, weeks):
    """Last known benchmark price carried forward."""
    last = data["outcomes"].sort_values("week").groupby("material").benchmark_price.last()
    return pd.DataFrame([(w, m, float(last[m])) for w in weeks for m in MATERIALS],
                        columns=["week", "material", "price_forecast"])


def plan(data, cutoff, weeks, forecasts):
    """Each week's demand from the supplier with the lowest mean landed cost to date."""
    mean_cost = data["supply_history"].groupby(["material", "country"]).landed_cost.mean().reset_index()
    cheapest = mean_cost.loc[mean_cost.groupby("material").landed_cost.idxmin()].set_index("material").country
    demand = data["demand"].set_index(["week", "material"]).demand_units
    rows = []
    for w in weeks:
        for m in MATERIALS:
            shares = {f"share_{c}": float(c == cheapest[m]) for c in COUNTRIES}
            rows.append({"week": w, "material": m, "order_units": float(demand[(w, m)]), **shares})
    return pd.DataFrame(rows)


MODELS = (disruption, price, plan)
