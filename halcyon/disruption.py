"""Disruption forecasts from matured horizon pairs and censored exit hazards.

``predict(data, cutoff, weeks)`` is the competition primary. ``variant="robust"``
selects a horizon-shrunk hedge using the same inputs/output contract.
Every training origin, target and observed transition ends by cutoff.

Selection origins 65,78,...,195 are exploratory, not independent validation.
The primary optimizes mean clipped Brier skill; large raw losses in recovery
windows remain possible. The hedge sacrifices clipped mean for lower tail loss.
Primary mean clipped Brier skill: 0.3314 (before calm shrinkage 0.3142;
duration-only 0.2613; U2 0.2142). Raw worst: -0.5225; robust -0.0505.
Horizon weights and calm shrinkage used only selection origins 65..195.
"""

import numpy as np
import pandas as pd

from halcyon.data import MATERIALS

# Coarse cells keep a few long, correlated shock episodes from dominating a fit.
AGE_EDGES = (2, 5, 10, 20)
PRIOR_PAIRS = 20
RATE_PRIOR_WEEKS = 26
MIN_TRAIN_WEEK = 14


def _transition_risk(values, age, age_specific):
    """Propagate state/run-age mass using only actually observed transitions.

    Ongoing runs contribute exposure but no invented ending. Exclude the first
    run of each material because its start predates our observations.
    """
    state = values[:-1].astype(int)
    exits = values[1:] != values[:-1]
    valid = np.ones(state.shape, dtype=bool)
    for j in range(values.shape[1]):
        changes = np.flatnonzero(exits[:, j])
        if len(changes):
            valid[:changes[0] + 1, j] = False
        else:
            valid[:, j] = False
    edges = (2, 4, 8, 16, 32) if age_specific else ()
    cells = np.digitize(age[:-1], edges)
    max_age = int(age[-1].max()) + 14
    hazards = np.empty((2, max_age + 1, values.shape[1]))
    age_bins = np.digitize(np.arange(max_age + 1), edges)
    for s in (0, 1):
        mask = valid & (state == s)
        pooled_rate = (exits[mask].sum() + 0.5) / (mask.sum() + 1)
        for b in range(len(edges) + 1):
            use = mask & (cells == b)
            count = use.sum(axis=0)
            events = (exits & use).sum(axis=0)
            if age_specific:
                pooled = (events.sum() + 2 * pooled_rate) / (count.sum() + 2)
                risk = (events + 10 * pooled) / (count + 10)
            else:
                risk = pooled_rate
            hazards[s, age_bins == b] = risk
    mass = np.zeros_like(hazards)
    mass[values[-1].astype(int), age[-1], np.arange(values.shape[1])] = 1
    output = []
    for _ in range(13):
        nxt = np.zeros_like(mass)
        for s in (0, 1):
            leaving = mass[s] * hazards[s]
            nxt[1 - s, 1] += leaving.sum(axis=0)
            nxt[s, 2:] += mass[s, 1:-1] * (1 - hazards[s, 1:-1])
        mass = nxt
        output.append(mass[1].sum(axis=0))
    return np.array(output)


def predict(data, cutoff, weeks, *, variant="primary"):
    """Blend horizon-pair and observed-exit estimates for horizons 1..13.

    The primary retains shock-persistence upside. The robust option shrinks
    h1–4 / h5–8 / h9–13 by 1 / 0.2 / 0.1 toward the historical reference.
    Beyond 13 weeks the primary is unchanged; the robust option is the reference.
    ``variant="shock"`` adds capped event and MERROW scenario floors; it is an
    intentionally different future for the scenario policy, not the primary.
    """
    if variant not in ("primary", "robust", "shock"):
        raise ValueError(f"unknown disruption variant: {variant}")
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
    transitions = _transition_risk(values, age, age_specific=variant != "robust")
    reference = values.mean(axis=0)
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
            if 1 <= horizon <= 13:
                probability = 0.5 * (probability + transitions[horizon - 1, j])
                if variant != "robust" and values[-1, j] == 0:
                    # Mild calm-state shrinkage beats both zero-risk and extra
                    # market/news models on mean clipped selection skill.
                    probability *= 0.5
            if variant == "robust":
                weight = (1.0 if horizon <= 4 else 0.2 if horizon <= 8
                          else 0.1 if horizon <= 13 else 0.0)
                probability = weight * probability + (1 - weight) * reference[j]
            rows.append((week, material, float(probability)))
    frame = pd.DataFrame(rows, columns=["week", "material", "disruption_prob"])
    if variant == "shock":
        from .events import shock_probabilities

        frame = shock_probabilities(data, cutoff, frame)
    return frame
