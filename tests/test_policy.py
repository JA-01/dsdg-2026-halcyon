import pandas as pd
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


def test_convex_sourcing_cost_raises_diversification(tables):
    data = as_of(tables, CUTOFF)
    forecasts = naive.disruption(data, CUTOFF, WEEKS).merge(naive.price(data, CUTOFF, WEEKS))
    hhi = lambda plan: (plan.loc[plan.order_units > 0, list(SHARE_COLUMNS)] ** 2).sum(axis=1).mean()
    flat = policy.plan(data, CUTOFF, WEEKS, forecasts, policy.Params(diversity=0.0))
    convex = policy.plan(data, CUTOFF, WEEKS, forecasts, policy.Params(diversity=0.1))
    assert hhi(convex) < hhi(flat)


def test_announced_tariff_raises_future_landed_cost(tables):
    """KES aluminum 0.10 -> 0.35 announced at week 221, effective 224."""
    if tables["outcomes"].week.max() < 221:
        pytest.skip("Phase 2 data not present")
    data, weeks = as_of(tables, 221), list(range(222, 235))
    landed = np.array([1.0, 1.0, 1.0])
    out = policy._announced(data, 221, "aluminum", ["AUR", "HAL", "KES"], weeks, landed)
    assert (out[:2] == 1).all() and (out[2:, 2] > 1.2).all() and (out[:, :2] == 1).all()


def test_country_capacity_empty_is_noop_and_haircut_shifts_orders(tables):
    data = as_of(tables, CUTOFF)
    forecasts = naive.disruption(data, CUTOFF, WEEKS).merge(naive.price(data, CUTOFF, WEEKS))
    base = policy.plan(data, CUTOFF, WEEKS, forecasts)
    assert base.equals(policy.plan(data, CUTOFF, WEEKS, forecasts, policy.Params(country_capacity={})))
    cut = policy.plan(data, CUTOFF, WEEKS, forecasts,
                      policy.Params(country_capacity={"KES": (WEEKS[3], 0.0)}))
    late = cut.week >= WEEKS[3]
    assert (cut.loc[late, "order_units"] * cut.loc[late, "share_KES"]).max() < 1e-6
    assert not cut.equals(base)


def test_risk_cost_shifts_volume_away_from_risky_supplier(tables):
    data = as_of(tables, CUTOFF)
    forecasts = naive.disruption(data, CUTOFF, WEEKS).merge(naive.price(data, CUTOFF, WEEKS))
    base = policy.plan(data, CUTOFF, WEEKS, forecasts)
    kes = lambda d, c, w: pd.DataFrame([(x, m, "KES", 1.0) for x in w for m in MATERIALS],
                                       columns=["week", "material", "country", "risk"])
    risky = policy.plan(data, CUTOFF, WEEKS, forecasts, policy.Params(risk_fn=kes, risk_cost=0.5))
    vol = lambda p: (p.order_units * p.share_KES).sum()
    assert vol(risky) < vol(base)


def test_basis_flags_at_221_plan_export_bans(tables):
    """#114: VAL cobalt and KES rare earths carry a futures-basis spike at 221."""
    if tables["outcomes"].week.max() < 221:
        pytest.skip("Phase 2 data not present")
    data, weeks = as_of(tables, 221), list(range(222, 235))
    assert policy._basis_bans(data, 221, policy.Params()) == {"cobalt": {"VAL": 222},
                                                              "rare_earths": {"KES": 223}}
    forecasts = naive.disruption(data, 221, weeks).merge(naive.price(data, 221, weeks))
    on = policy.plan(data, 221, weeks, forecasts)
    off = policy.plan(data, 221, weeks, forecasts, policy.Params(basis_haircut=False))
    val = lambda p: (p.loc[p.material == "cobalt"].eval("order_units * share_VAL")).sum()
    assert val(on) < val(off)


def test_rebalance_spreads_cheaply_and_respects_limits():
    # 3 suppliers: main (cheapest), a 1%-dearer peer with capacity, a slower one.
    r = np.array([[100.0, 0, 0], [0, 0, 0], [80.0, 0, 0]])
    cap = np.full((3, 3), 60.0)
    lead = np.array([3, 3, 5])
    landed = np.tile([10.0, 10.1, 10.0], (3, 1))
    out = policy._rebalance(r, cap, lead, landed, 10.0, cost_weight=40 / 1e6, merge_back=0)
    np.testing.assert_allclose(out.sum(axis=1), r.sum(axis=1))      # row units preserved
    assert (out[:, 0] <= r[:, 0] + 1e-9).all()                      # main only loses share
    assert (out[:, 2] == 0).all()                                   # slower supplier gains nothing
    assert out[0, 1] > 0 and out[0, 1] <= cap[0, 1] + 1e-9          # peer gains within capacity
    # A huge cost weight (tiny F denominator) leaves the plan unchanged.
    np.testing.assert_allclose(policy._rebalance(r, cap, lead, landed, 10.0, 1.0, 0), r)
    # Merge moves a row back only within capacity; total units are preserved.
    merged = policy._rebalance(r, np.full((3, 3), 1e9), lead, landed, 10.0, 40 / 1e6, 3)
    assert merged.sum() == pytest.approx(r.sum())
