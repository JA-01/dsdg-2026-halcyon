import numpy as np
import pytest

from halcyon import naive, policy, score
from halcyon.data import MATERIALS, SHARE_COLUMNS, as_of, read_all

CUTOFF = 182
WEEKS = list(range(CUTOFF + 1, CUTOFF + 14))


@pytest.fixture(scope="module")
def tables():
    return read_all("data")


@pytest.fixture(scope="module")
def planned(tables):
    data = as_of(tables, CUTOFF)
    forecasts = naive.disruption(data, CUTOFF, WEEKS).merge(naive.price(data, CUTOFF, WEEKS))
    return policy.plan(data, CUTOFF, WEEKS, forecasts)


def test_plan_meets_contract(planned, tables):
    assert len(planned) == len(WEEKS) * len(MATERIALS)
    assert (planned.order_units >= 0).all()
    assert np.allclose(planned[list(SHARE_COLUMNS)].sum(axis=1), 1)
    sellers = tables["suppliers"].groupby("material").country.apply(set)
    for column in SHARE_COLUMNS:
        sold = planned.material.map(lambda m: column[6:] in sellers[m])
        assert (planned.loc[~sold, column] == 0).all()


def test_zero_order_rows_are_fully_diversified(planned):
    idle = planned.loc[planned.order_units == 0, list(SHARE_COLUMNS)]
    assert len(idle) and np.allclose((idle ** 2).sum(axis=1), 1 / 3)


def test_plan_beats_naive_on_cost(planned, tables):
    frame = planned.merge(score.naive(tables, CUTOFF, WEEKS)[["week", "material", "disruption_prob",
                                                               "price_forecast"]])
    result = score.score(frame, tables, WEEKS[0], WEEKS[-1])
    assert result["F"] > 0.5 and result["score"] > 0


def test_plan_ignores_future_rows(tables):
    """Planning at the cutoff must not change when post-cutoff data is altered."""
    data = as_of(tables, CUTOFF)
    forecasts = naive.disruption(data, CUTOFF, WEEKS).merge(naive.price(data, CUTOFF, WEEKS))
    tampered = {k: v.copy() for k, v in tables.items()}
    future = tampered["supply_history"].week > CUTOFF
    tampered["supply_history"].loc[future, "capacity_units"] = 0
    a = policy.plan(as_of(tables, CUTOFF), CUTOFF, WEEKS, forecasts)
    b = policy.plan(as_of(tampered, CUTOFF), CUTOFF, WEEKS, forecasts)
    assert a.equals(b)
