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


def test_scenarios_move_volume_off_the_shocked_lane(tables, forecasts):
    """By 169 the library holds MERROW-lane events (KES sanctions, SUN strikes): the hedged
    plan relies less on KES+SUN than the nominal-path plan, and buys no later."""
    data = as_of(tables, CUTOFF)
    hedged = ps.plan(data, CUTOFF, WEEKS, forecasts)
    flat = ps.plan(data, CUTOFF, WEEKS, forecasts, ps.Params(weight_scale=0.0))
    merrow = lambda p: (p.order_units * (p.share_KES + p.share_SUN)).sum() / p.order_units.sum()
    timing = lambda p: (p.order_units * p.week).sum() / p.order_units.sum()
    assert merrow(hedged) < merrow(flat) - 0.05
    assert timing(hedged) <= timing(flat) + 1e-9


def test_challenger_builds_a_valid_submission(tables):
    frame = submit.build(tables, models=(submit.MODELS[0], submit.MODELS[1], ps.plan))
    submit.validate(frame, tables)
    assert len(frame) == 260


def test_kes_overlay_is_inert_before_week_224(tables, forecasts):
    data = as_of(tables, CUTOFF)  # window 170-182 never reaches week 224
    assert ps.plan_kes_overlay(data, CUTOFF, WEEKS, forecasts).equals(ps.plan(data, CUTOFF, WEEKS, forecasts))


def test_kes_overlay_caps_kes_requests_from_week_224(tables):
    if tables["outcomes"].week.max() < 221:
        pytest.skip("Phase 2 data not present")
    from halcyon import events
    cutoff, weeks = 221, list(range(222, 235))
    data = as_of(tables, cutoff)
    fc = naive.disruption(data, cutoff, weeks).merge(naive.price(data, cutoff, weeks))
    base, over = ps.plan(data, cutoff, weeks, fc), ps.plan_kes_overlay(data, cutoff, weeks, fc)
    normal = tables["suppliers"].set_index(["material", "country"]).normal_capacity_units
    kes = lambda p: p.order_units * p.share_KES
    late = over.week >= events._BAN_WEEK
    for row in over.loc[late & (over.share_KES > 0)].itertuples():
        bound = events._BAN_CAPACITY * 0.98 * normal[(row.material, "KES")]  # planned (cancellation-free) bound
        assert row.order_units * row.share_KES <= bound + 1e-6
    assert kes(over.loc[late]).sum() < kes(base.loc[base.week >= events._BAN_WEEK]).sum()


def test_compose_keeps_public_rows(tables):
    a = submit.build(tables)
    b = submit.build(tables, models=(submit.MODELS[0], submit.MODELS[1], ps.plan_kes_overlay))
    c = ps.compose(a, b)
    submit.validate(c, tables)
    public = c.id.str[1:4].astype(int) <= 221
    assert c[public].equals(a[public]) and c[~public].equals(b[~public])


def _true_expected_cost(r, demand, opening, scenarios, landed, ref):
    """Simulator economics of requests r under each scenario: fill = min(request, capacity)."""
    total = 0.0
    for w, cap, lead in scenarios:
        f = np.minimum(r, cap)
        T = len(demand)
        arrivals = np.zeros(T + 32)
        for t in range(T):
            np.add.at(arrivals, t + lead[t], f[t])
        stock, cost = opening, float((f * landed).sum())
        for t in range(T):
            stock += arrivals[t]
            served = min(stock, demand[t])
            stock -= served
            cost += ps.HOLDING * ref * stock + ps.SHORTAGE * ref * (demand[t] - served)
        total += w * (cost - ps.SALVAGE * ref * (stock + arrivals[T:].sum()))
    return total


def test_exact_min_forbids_refusing_requested_units():
    """A lead-time scenario pushes arrivals past the window: refusing them would 'save'
    the purchase, but the simulator always delivers min(request, capacity)."""
    T, demand = 4, np.array([0.0, 10.0, 10.0, 10.0])
    cap0 = np.full((T, 1), 40.0)
    landed, ref = np.ones((T, 1)), 1.0
    nominal = (0.5, np.full((T, 1), 44.0), np.ones((T, 1), int))
    delayed = (0.5, np.full((T, 1), 20.0), np.full((T, 1), 6, int))  # capped, arrives after the window
    scenarios = [nominal, delayed]
    const = ps.SHORTAGE * ref * demand.sum()  # the LP prices served units, not shortages
    args = (demand, 0.0, cap0, scenarios, landed, ref, np.zeros(T), 1.0, 0.0)
    r_lp, obj_lp = ps._solve(*args, exact=False, return_objective=True)
    r_ex, obj_ex = ps._solve(*args, exact=True, return_objective=True)
    true_lp = _true_expected_cost(r_lp, demand, 0.0, scenarios, landed, ref)
    true_ex = _true_expected_cost(r_ex, demand, 0.0, scenarios, landed, ref)
    assert obj_lp + const < true_lp - 1e-6           # before: the LP believes it can refuse
    assert obj_ex + const == pytest.approx(true_ex)   # after: objective is the simulator's cost
