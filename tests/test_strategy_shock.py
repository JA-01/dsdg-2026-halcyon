import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from halcyon import policy_scenarios as scenarios, strategy_shock, submit
from halcyon.data import as_of, read_all


def test_duration_insurance_extends_loss_without_increasing_event_probability():
    suppliers = pd.DataFrame([
        ("lithium", "KES", 100.0, 1),
        ("lithium", "VAL", 100.0, 1),
    ], columns=["material", "country", "normal_capacity_units", "base_lead_weeks"])
    history = pd.DataFrame([
        (week, "lithium", country, 30.0 if country == "KES" and week in (2, 3) else 100.0,
         3 if country == "KES" and week in (2, 3) else 1)
        for week in range(1, 6) for country in ("KES", "VAL")
    ], columns=["week", "material", "country", "capacity_units", "lead_time_weeks"])
    data = {"suppliers": suppliers, "supply_history": history}
    library, observed = strategy_shock.duration_library(data, 5)
    params = scenarios.Params(onsets=(0,), generalize_single=False)
    cap = np.full((5, 2), 90.0)
    paths = scenarios._scenarios(library, observed, "lithium", ["KES", "VAL"],
                                np.array([100.0, 100.0]), np.array([1, 1]), cap,
                                np.array([1, 1]), list(range(6, 11)), params,
                                {"KES": ["lithium"], "VAL": ["lithium"]})
    # One event in five observed weeks: 1.0 window mass, capped at .95.
    assert np.isclose(sum(weight for key, weight, _, _ in paths if key is not None), .95)
    assert np.isclose(paths[1][1], paths[2][1])
    observed_cap, observed_lead = paths[1][2:]
    insured_cap, insured_lead = paths[2][2:]
    np.testing.assert_array_equal(observed_cap[:, 0], [30, 30, 100, 100, 100])
    np.testing.assert_array_equal(insured_cap[:, 0], [30, 30, 30, 30, 100])
    np.testing.assert_array_equal(observed_lead[:, 0], [3, 3, 1, 1, 1])
    np.testing.assert_array_equal(insured_lead[:, 0], [3, 3, 3, 3, 1])
    np.testing.assert_array_equal(insured_cap[:, 1], [100] * 5)


def test_plan_ignores_all_future_observations():
    tables = read_all()
    cutoff, weeks = 65, list(range(66, 79))
    data = as_of(tables, cutoff)
    base = submit.plan_window(tables, cutoff, weeks, models=strategy_shock.MODELS)
    poisoned = {key: frame.copy() for key, frame in tables.items()}
    for key in ("supply_history", "outcomes", "macro", "news"):
        future = poisoned[key].week > cutoff
        poisoned[key] = poisoned[key].loc[~future].copy()
    candidate = submit.plan_window(poisoned, cutoff, weeks, models=strategy_shock.MODELS)
    assert_frame_equal(base, candidate)
    # Direct planner callers get the same boundary enforcement as submit.plan_window.
    forecasts = base[["week", "material", "disruption_prob", "price_forecast"]]
    assert_frame_equal(strategy_shock.plan(tables, cutoff, weeks, forecasts),
                       strategy_shock.plan(data, cutoff, weeks, forecasts))
