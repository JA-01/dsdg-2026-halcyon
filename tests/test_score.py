import numpy as np
import pytest

from halcyon import score
from halcyon.data import MATERIALS, read_all

START, END = 183, 195


@pytest.fixture(scope="module")
def tables():
    return read_all("data")


def test_naive_reproduces_sample_submission(tables):
    sample = tables["sample_submission"]
    ours = score.naive(tables, 208, range(209, 235))
    ours["id"] = "w" + ours.week.astype(str) + "_" + ours.material
    ours = ours.set_index("id").loc[sample.id]
    numeric = sample.columns.drop("id")
    assert np.abs(ours[numeric].to_numpy() - sample[numeric].to_numpy()).max() < 1e-3


def test_naive_scores_zero(tables):
    result = score.score(score.naive(tables, START - 1, range(START, END + 1)), tables, START, END)
    assert result["score"] == 0
    assert result["P"] == 0 and result["F"] == 0 and result["fill_skill"] == 0
    assert result["diversification"] == 0  # single sourcing


def test_hindsight_plan_scores_full_f(tables):
    weeks = range(START, END + 1)
    best, plan = score.hindsight(tables, START, END)
    frame = plan.merge(score.naive(tables, START - 1, weeks)[["week", "material", "disruption_prob",
                                                               "price_forecast"]], on=score.KEY)
    result = score.score(frame, tables, START, END)
    assert result["cost"] == pytest.approx(best, rel=1e-6)
    assert result["F"] == pytest.approx(1.0, abs=1e-6)


def test_perfect_forecasts_score_full_p(tables):
    weeks = range(START, END + 1)
    frame = score.naive(tables, START - 1, weeks).drop(columns=["disruption_prob", "price_forecast"])
    truth = tables["outcomes"].rename(columns={"disrupted": "disruption_prob",
                                               "benchmark_price": "price_forecast"})
    frame = frame.merge(truth[["week", "material", "disruption_prob", "price_forecast"]], on=score.KEY)
    assert score.score(frame, tables, START, END)["P"] == pytest.approx(1.0)


def test_simulator_matches_hand_example(tables):
    """One material, one supplier, zero orders: stock runs down from 5x week-1 demand."""
    weeks = range(START, END + 1)
    plan = score.naive(tables, START - 1, weeks).assign(order_units=0.0)
    sim = score.simulate(plan, tables, START, END)
    lithium = sim.loc[sim.material == "lithium"]
    demand = lithium.demand.to_numpy()
    stock = 5 * demand[0] - np.cumsum(demand)
    expected_served = np.minimum(demand, np.maximum(stock + demand, 0))
    assert np.allclose(lithium.served.to_numpy(), expected_served)


def test_backtest_scores_each_cutoff(tables):
    results = score.backtest([156, 182], tables, planner=score.naive)
    assert list(results.cutoff) == [156, 182]
    assert (results.score == 0).all()
    assert len(score.simulate(score.naive(tables, 182, range(183, 196)), tables, 183, 195)) \
        == 13 * len(MATERIALS)
