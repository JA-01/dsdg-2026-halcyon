"""Horizon-aware benchmark price forecasts using released outcomes only."""

import numpy as np
import pandas as pd

from halcyon.data import MATERIALS


def predict(data, cutoff, weeks):
    """Revert prices slowly and partially reverse the latest weekly quote change.

    Slow reversion reduces sensitivity to a noisy last quote without assuming
    that an active price shock disappears immediately. Short histories use all
    available observations. A quarter of the latest weekly return reverses with
    a four-week half-life; bounding that return keeps forecasts positive even
    for extreme quotes. Filtering here also protects direct callers.
    """
    history = data["outcomes"].loc[lambda f: f.week <= cutoff].sort_values("week")
    last = history.groupby("material").benchmark_price.last()
    center = history.loc[history.week > cutoff - 104].groupby("material").benchmark_price.mean()
    previous = history.groupby("material").tail(2).groupby("material").benchmark_price.first()
    reversal = (last / previous - 1).clip(-1, 1)
    missing = set(MATERIALS) - set(last.index)
    if missing:
        raise ValueError(f"missing price history for {sorted(missing)}")
    rows = []
    for week in weeks:
        if not isinstance(week, (int, np.integer)) or week <= cutoff:
            raise ValueError("target weeks must be integers after cutoff")
        weight = 1 - 2 ** (-(week - cutoff) / 26)
        correction = 0.25 * (1 - 2 ** (-(week - cutoff) / 4))
        rows.extend((week, m, float(((1 - weight) * last[m] + weight * center[m])
                                   * (1 - correction * reversal[m])))
                    for m in MATERIALS)
    return pd.DataFrame(rows, columns=["week", "material", "price_forecast"])
