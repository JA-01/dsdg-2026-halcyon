import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from halcyon.data import MATERIALS
from halcyon.disruption import predict


def dataset(values):
    return {"outcomes": pd.DataFrame(
        [(w + 1, m, v) for w, v in enumerate(values) for m in MATERIALS],
        columns=["week", "material", "disrupted"])}


def test_cutoff_state_changes_short_horizon_risk():
    # Same marginal rates, but opposite current states after repeated episodes.
    quiet = dataset(([1] * 10 + [0] * 10) * 4 + [1] * 5 + [0] * 5)
    active = dataset(([0] * 10 + [1] * 10) * 4 + [0] * 5 + [1] * 5)
    quiet_risk = predict(quiet, 90, [91]).disruption_prob.to_numpy()
    active_risk = predict(active, 90, [91]).disruption_prob.to_numpy()
    assert np.all(active_risk > quiet_risk + 0.4)


def test_future_outcomes_cannot_change_predictions():
    history = ([0] * 12 + [1] * 8) * 5
    observed = dataset(history)
    mutated = dataset(history + [1] * 40)
    assert_frame_equal(predict(observed, 100, [101, 104, 113]),
                       predict(mutated, 100, [101, 104, 113]))


def test_horizons_without_matured_training_targets_use_prior():
    data = dataset([0] * 15 + [1] * 5)
    result = predict(data, 20, [60, 40])
    assert list(result.week.unique()) == [60, 40]
    assert len(result) == 2 * len(MATERIALS)
    assert np.allclose(result.disruption_prob, 0.25)
