import numpy as np
import pytest

from halcyon import naive, policy_scenarios as ps, submit
from halcyon.data import MATERIALS, SHARE_COLUMNS, as_of, read_all

CUTOFF = 169
WEEKS = list(range(CUTOFF + 1, CUTOFF + 14))


@pytest.fixture(scope="module")
def tables():
    return read_all("data")


@pytest.fixture(scope="module")
def forecasts(tables):
    data = as_of(tables, CUTOFF)
    return naive.disruption(data, CUTOFF, WEEKS).merge(naive.price(data, CUTOFF, WEEKS))


def test_event_library_uses_only_completed_history(tables):
    library, observed = ps.events(as_of(tables, CUTOFF), CUTOFF)
    assert observed == CUTOFF and library
    for ev in library:
        assert ev["start"] <= CUTOFF
        for ratios, extras in ev["hits"].values():
            assert ev["start"] + len(ratios) - 1 < CUTOFF  # completed before the cutoff
            assert ((ratios < 0.9) | (extras > 0)).all()


def test_plan_is_valid_and_ignores_future_rows(tables, forecasts):
    data = as_of(tables, CUTOFF)
    plan = ps.plan(data, CUTOFF, WEEKS, forecasts)
    assert len(plan) == len(WEEKS) * len(MATERIALS)
    shares = plan[list(SHARE_COLUMNS)].to_numpy()
    assert np.isfinite(plan.order_units).all() and (plan.order_units >= 0).all()
    assert (shares >= 0).all() and np.allclose(shares.sum(axis=1), 1)
    sellers = tables["suppliers"].groupby("material").country.apply(set)
    for column in SHARE_COLUMNS:
        sold = plan.material.map(lambda m: column[6:] in sellers[m])
        assert (plan.loc[~sold, column] == 0).all()
    tampered = {k: v.copy() for k, v in tables.items()}
    future = tampered["supply_history"].week > CUTOFF
    tampered["supply_history"].loc[future, ["capacity_units", "lead_time_weeks"]] = [1, 9]
    assert plan.equals(ps.plan(as_of(tampered, CUTOFF), CUTOFF, WEEKS, forecasts))


def test_scenarios_hedge_more_than_the_nominal_path(tables, forecasts):
    """With no event weight the plan is the nominal-path LP; scenarios add stock or sources."""
    data = as_of(tables, CUTOFF)
    hedged = ps.plan(data, CUTOFF, WEEKS, forecasts)
    flat = ps.plan(data, CUTOFF, WEEKS, forecasts, ps.Params(weight_scale=0.0))
    assert hedged.order_units.sum() > flat.order_units.sum()


def test_challenger_builds_a_valid_submission(tables):
    frame = submit.build(tables, models=(submit.MODELS[0], submit.MODELS[1], ps.plan))
    submit.validate(frame, tables)
    assert len(frame) == 260
