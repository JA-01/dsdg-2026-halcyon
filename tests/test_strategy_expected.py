import numpy as np
import pytest

from halcyon import disruption_news, strategy_expected as se, submit
from halcyon.data import as_of, read_all


@pytest.fixture(scope="module")
def tables():
    return read_all("data")


def test_expected_probabilities_follow_hard_signals_only(tables):
    """At 221: tariff rows held from the effective week, basis-flagged materials keep the
    champion, everything else is capped at the clean onset hazard."""
    if tables["outcomes"].week.max() < 221:
        pytest.skip("Phase 2 data not present")
    cutoff, weeks = 221, list(range(222, 235))
    data = as_of(tables, cutoff)
    champ = disruption_news.predict(data, cutoff, weeks).set_index(["week", "material"]).disruption_prob
    mine = se.predict(data, cutoff, weeks).set_index(["week", "material"]).disruption_prob
    held, tariffs = se.hard_signals(data, cutoff)
    assert tariffs == {"aluminum": 224, "semiconductors": 224} and {"cobalt", "rare_earths"} <= held
    hz = se.clean_hazard(data["outcomes"], cutoff, range(1, 14))
    for (w, m), q in mine.items():
        if m in tariffs and w >= tariffs[m]:
            assert q >= se.TARIFF_HELD - 1e-12
        elif m in held:
            assert q == champ[(w, m)]
        else:
            assert q <= hz[w - cutoff] + 1e-12 and q <= champ[(w, m)] + 1e-12


def test_plan_window_ignores_rows_after_the_cutoff(tables):
    cutoff, weeks = 130, list(range(131, 144))
    tampered = {k: v.copy() for k, v in tables.items()}
    for name in ("supply_history", "outcomes", "prices", "tariffs"):
        late = tampered[name].week > cutoff
        col = {"supply_history": "capacity_units", "outcomes": "disrupted",
               "prices": "futures_4w", "tariffs": "tariff_rate"}[name]
        tampered[name][col] = tampered[name][col].astype(float)
        tampered[name].loc[late, col] = 1.0 if name == "outcomes" else 0.5
    a = submit.plan_window(tables, cutoff, weeks, se.MODELS)
    b = submit.plan_window(tampered, cutoff, weeks, se.MODELS)
    assert a.equals(b)


def test_strategy_builds_a_valid_submission(tables):
    frame = submit.build(tables, models=se.MODELS)
    submit.validate(frame, tables)
    assert len(frame) == 260 and np.isfinite(frame.drop(columns="id").to_numpy(float)).all()
