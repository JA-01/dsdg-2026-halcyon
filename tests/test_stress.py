import pytest

from halcyon import stress
from halcyon.data import read_all


@pytest.fixture(scope="module")
def tables():
    t = read_all("data")
    if t["outcomes"].week.max() < 221:
        pytest.skip("Phase 2 data not present")
    return t


def test_calm_scenario_has_no_disruption(tables):
    out = stress.scenario(tables, "S0 calm")["outcomes"]
    private = out.loc[out.week >= stress.START]
    assert len(private) == 130 and private.disrupted.sum() == 0


def test_bans_follow_label_rule(tables):
    out = stress.scenario(tables, "S3 +KES rare_earths ban")["outcomes"].set_index(["week", "material"])
    assert out.disrupted[(223, "cobalt")] == 1 and out.disrupted[(224, "rare_earths")] == 1
    assert out.disrupted[(224, "aluminum")] == 1  # tariff above base counts
    assert out.disrupted[(222, "rare_earths")] == 0
