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
    for extreme quotes. A shrunk delayed disruption-response premium uses the
    live news probabilities, without assuming that a recovery cuts prices.
    Filtering here also protects direct callers.
    """
    weeks = list(weeks)
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
    frame = pd.DataFrame(rows, columns=["week", "material", "price_forecast"])
    frame['price_forecast'] *= np.exp(_lag_premium(data, cutoff, weeks).reshape(-1))
    return frame


def _lag_premium(data, cutoff, weeks):
    """Fit pooled delayed price responses; forecast states come from live news.

    The level-response kernel is learned from one-week log-price residuals and
    lagged disruption changes, with ridge shrinkage. Its future level change is
    measured relative to cutoff, so an already-priced shock is not counted twice.
    Uncertain recoveries never add a price discount to the existing forecast.
    """
    zeros = np.zeros((len(weeks), len(MATERIALS)))
    history = data['outcomes'].loc[lambda f: f.week <= cutoff]
    if (not weeks or cutoff < 26 or 'disrupted' not in history
            or not {'news', 'suppliers', 'tariffs'}.issubset(data)):
        return zeros
    prices = history.pivot(index='week', columns='material', values='benchmark_price').reindex(
        index=range(1, cutoff + 1), columns=MATERIALS).to_numpy(float)
    states = history.pivot(index='week', columns='material', values='disrupted').reindex(
        index=range(1, cutoff + 1), columns=MATERIALS).to_numpy(float)
    if not np.isfinite(prices).all() or not np.isfinite(states).all():
        return zeros
    last, previous = prices[:-1], np.concatenate([prices[:1], prices[:-2]])
    center = pd.DataFrame(prices).rolling(104, min_periods=1).mean().to_numpy()[:-1]
    baseline = last + (center - last) * (1 - 2 ** (-1 / 26))
    baseline *= 1 - .25 * np.clip(last / previous - 1, -1, 1) * (1 - 2 ** (-1 / 4))
    residual = np.log(prices[1:] / baseline)[4:]
    changes = np.diff(states, axis=0)
    design = np.stack([changes[4 - lag:len(changes) - lag] for lag in range(5)], axis=-1)
    x, y = design.reshape(-1, 5), residual.reshape(-1)
    kernel = np.linalg.solve(x.T @ x + 10 * np.eye(5), x.T @ y)
    from .disruption_news import predict as predict_disruption

    future = predict_disruption(data, cutoff, range(cutoff + 1, max(weeks) + 1))
    future = future.pivot(index='week', columns='material', values='disruption_prob').reindex(
        columns=MATERIALS).to_numpy(float)
    path = np.concatenate([states, future])
    response = np.array([sum(kernel[lag] * (path[week - 1 - lag] - path[cutoff - 1 - lag])
                             for lag in range(5)) for week in weeks])
    return np.clip(response, 0, .2)
