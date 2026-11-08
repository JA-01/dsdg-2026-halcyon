import pandas as pd
import pytest

from halcyon import scenarios_p2 as s
from halcyon.data import read_all


@pytest.fixture(scope="module")
def tables():
    return read_all("data")


def test_scenario_labels_follow_the_shocks(tables):
    calm = s.build(tables, "calm: tariff reversed, warnings fizzle")["outcomes"]
    assert calm.loc[calm.week >= s.START, "disrupted"].sum() == 0
    wide = s.build(tables, "kes_wide: KES 0.20x +3 lead from 225")["outcomes"].set_index(["week", "material"])
    for material in s.KES_ALL:
        assert wide.loc[(225, material), "disrupted"] == 1
    # aluminum carries the announced KES tariff from 224; before the restriction only it is flagged
    assert wide.loc[(224, "lithium"), "disrupted"] == 0
    assert wide.loc[(224, "aluminum"), "disrupted"] == 1
    assert wide.loc[(234, "specialty_glass"), "disrupted"] == 0  # SUN-only material, no lane shock
    lane = s.build(tables, "merrow: lane 223-230 only")["outcomes"].set_index(["week", "material"])
    assert lane.loc[(223, "specialty_glass"), "disrupted"] == 1 and lane.loc[(231, "specialty_glass"), "disrupted"] == 0


def test_overlapping_shocks_take_the_most_restrictive_capacity_not_the_product(tables):
    sh = s.build(tables, "merrow: both bans + lane 223-230")["supply_history"]
    row = sh.loc[(sh.week == 225) & (sh.material == "rare_earths") & (sh.country == "KES")].iloc[0]
    assert row.capacity_units == pytest.approx(0.05 * 560)  # ban 0.05 and lane 0.75 -> 0.05, not 0.0375
    assert row.lead_time_weeks == 4 + 3


def test_select_trades_expected_score_for_lower_regret_within_tolerance():
    # Specialists a, b, c each win one scenario; all-rounder d is 10 below the best everywhere.
    scores = {"x": {"a": 100, "b": 50, "c": 50, "d": 90},
              "y": {"a": 50, "b": 100, "c": 50, "d": 90},
              "z": {"a": 50, "b": 50, "c": 100, "d": 90}}
    weight = {"x": .46, "y": .44, "z": .10}
    results = pd.DataFrame([dict(scenario=sc, weight=weight[sc], file=f, score=v)
                            for sc, row in scores.items() for f, v in row.items()])
    p = s.pairs(results).set_index(["a", "b"])
    assert p.loc[("a", "b"), "expected"] == pytest.approx(95)  # best on average...
    assert p.loc[("a", "b"), "max_regret"] == 50                 # ...but 50 short if z happens
    assert p.loc[("a", "d"), "expected"] == pytest.approx(94.6)
    chosen = s.select(results, tolerance=1.0)
    assert (chosen.a, chosen.b) == ("a", "d")
    chosen = s.select(results, tolerance=0.1)
    assert (chosen.a, chosen.b) == ("a", "b")
