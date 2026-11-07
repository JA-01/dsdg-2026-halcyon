import numpy as np
import pandas as pd
import pytest
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


@pytest.mark.parametrize("variant", ["primary", "robust"])
def test_future_outcomes_cannot_change_predictions(variant):
    history = ([0] * 12 + [1] * 8) * 5
    observed = dataset(history)
    mutated = dataset(history + [1] * 40)
    assert_frame_equal(predict(observed, 100, [101, 104, 113], variant=variant),
                       predict(mutated, 100, [101, 104, 113], variant=variant))


def test_horizons_without_matured_training_targets_use_prior():
    data = dataset([0] * 15 + [1] * 5)
    result = predict(data, 20, [60, 40])
    assert list(result.week.unique()) == [60, 40]
    assert len(result) == 2 * len(MATERIALS)
    assert np.allclose(result.disruption_prob, 0.25)


def test_ongoing_episode_has_no_invented_terminal_exit():
    data = dataset([0] * 50 + [1] * 50)
    result = predict(data, 100, [101, 113])
    assert np.all(result.disruption_prob > 0.9)


def test_robust_unvalidated_long_horizon_uses_material_reference():
    data = dataset([0] * 15 + [1] * 5)
    data["outcomes"].loc[data["outcomes"].material == "lithium", "disrupted"] = 1
    result = predict(data, 20, [34], variant="robust").set_index("material")
    assert result.loc["lithium", "disruption_prob"] == 1
    assert np.allclose(result.drop(index="lithium").disruption_prob, 0.25)
