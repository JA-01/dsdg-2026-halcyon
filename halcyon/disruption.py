"""Pooled state-duration disruption forecasts, trained only on released outcomes.

Contract: predict(data, cutoff, weeks) -> week, material, disruption_prob.
Training examples use a historical cutoff's state and run length to predict a
specific future horizon. Both ends of every example must be <= cutoff.
"""

import numpy as np
import pandas as pd

from halcyon.data import MATERIALS

# Coarse cells keep a few long, correlated shock episodes from dominating a fit.
AGE_EDGES = (2, 5, 10, 20)
PRIOR_PAIRS = 20
RATE_PRIOR_WEEKS = 26
MIN_TRAIN_WEEK = 14


def predict(data, cutoff, weeks):
    """Estimate horizon-specific risk conditional on the current run's age.

    Pool state/age transitions across materials, shrinking sparse cells toward
    each material's historical rate. This learns both persistent shocks and
    their eventual recovery, without extrapolating a long shock indefinitely.
    """
    history = data["outcomes"]
    history = history.loc[history.week <= cutoff]
    labels = history.pivot(index="week", columns="material", values="disrupted")
    labels = labels.reindex(columns=MATERIALS).sort_index()
    observed_weeks = labels.index.to_numpy()
    values = labels.to_numpy(dtype=float)
    rates = (values.sum(axis=0) + RATE_PRIOR_WEEKS * values.mean()) / (
        len(values) + RATE_PRIOR_WEEKS)
    age = np.ones(values.shape, dtype=int)
    for t in range(1, len(values)):
        age[t] = np.where(values[t] == values[t - 1], age[t - 1] + 1, 1)
    age_cell = np.digitize(age, AGE_EDGES)
    rows = []
    for week in weeks:
        horizon = week - cutoff
        # Lookup by actual week, not row offset: no future target can enter fit.
        origins = np.flatnonzero((observed_weeks >= MIN_TRAIN_WEEK)
                                 & (observed_weeks + horizon <= cutoff))
        target_indices = labels.index.get_indexer(observed_weeks[origins] + horizon)
        valid = target_indices >= 0
        origins, target_indices = origins[valid], target_indices[valid]
        targets = values[target_indices]
        for j, material in enumerate(MATERIALS):
            cell = ((values[origins] == values[-1, j])
                    & (age_cell[origins] == age_cell[-1, j]))
            outcomes = targets[cell]
            probability = (outcomes.sum() + PRIOR_PAIRS * rates[j]) / (
                len(outcomes) + PRIOR_PAIRS)
            rows.append((week, material, float(probability)))
    return pd.DataFrame(rows, columns=["week", "material", "disruption_prob"])
