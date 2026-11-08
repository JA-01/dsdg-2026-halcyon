import numpy as np
import pytest

from halcyon import naive, submit
from halcyon.data import as_of, read_all


@pytest.fixture(scope="module")
def tables():
    return read_all("data")


@pytest.fixture(scope="module")
def built(tables):
    return submit.build(tables)


def test_build_passes_validator(built, tables):
    submit.validate(built, tables)
    assert list(built.id) == list(tables["sample_submission"].id)


def test_naive_reference_reproduces_sample(tables):
    """halcyon.naive at the Phase 1 cutoff equals the organizer's naive file, so it
    scores 0. The organizer kept the Phase 1 file as the reference in Phase 2."""
    built = submit.build(tables, cutoff=208, models=naive.MODELS)
    sample = tables["sample_submission"]
    numeric = sample.columns.drop("id")
    diff = (built[numeric] - sample[numeric]).abs()
    assert diff[["disruption_prob", "price_forecast"]].max().max() < 1e-3
    assert (diff[["order_units", *submit.SHARE_COLUMNS]].max() == 0).all()


def test_as_of_hides_future_rows(tables):
    view = as_of(tables, 100)
    assert all(view[n].week.max() <= 100 for n in ("news", "prices", "outcomes", "supply_history"))
    assert view["demand"].week.max() == 234


@pytest.mark.parametrize("column, value, message", [
    ("disruption_prob", 1.5, "outside"),
    ("price_forecast", 0.0, "> 0"),
    ("order_units", -1.0, "negative"),
    ("share_KES", 0.5, "sum to 1"),
])
def test_validator_rejects_bad_values(built, tables, column, value, message):
    bad = built.copy()
    bad.loc[3, column] = value
    with pytest.raises(ValueError, match=message):
        submit.validate(bad, tables)


def test_validator_rejects_non_seller_share(built, tables):
    bad = built.copy()
    lithium = bad.id.str.endswith("_lithium").idxmax()  # lithium is not sold by HAL
    bad.loc[lithium, submit.SHARE_COLUMNS] = 0.0
    bad.loc[lithium, "share_HAL"] = 1.0
    with pytest.raises(ValueError, match="does not sell"):
        submit.validate(bad, tables)


def test_validator_rejects_missing_row(built, tables):
    with pytest.raises(ValueError, match="missing ids"):
        submit.validate(built.drop(index=0), tables)


def test_released_block_uses_released_truth_and_valid_shares(tables):
    block = submit.released_block(tables, 209, 221)
    truth = tables["outcomes"].set_index(["week", "material"])
    key = block.set_index(["week", "material"])
    assert (key.disruption_prob == truth.disrupted.reindex(key.index)).all()
    assert (key.price_forecast == truth.benchmark_price.reindex(key.index)).all()
    shares = block[list(submit.SHARE_COLUMNS)]
    assert ((shares.sum(axis=1) - 1).abs() < 1e-6).all()
    idle = block.order_units <= 1e-6
    # Rows that order nothing are spread evenly over the material's 3 sellers.
    assert (shares[idle].max(axis=1) - 1 / 3).abs().max() < 1e-9


def test_optimized_released_block_beats_plain_hindsight(tables):
    if tables["outcomes"].week.max() < 221:
        pytest.skip("Phase 2 data not present")
    from halcyon import score
    plain = submit.released_block(tables, 209, 221, optimize=False)
    best = submit.released_block(tables, 209, 221)
    a, b = score.score(plain, tables, 209, 221), score.score(best, tables, 209, 221)
    assert b["score"] > a["score"] and b["fill_skill"] == a["fill_skill"] and b["P"] == 1


@pytest.fixture(scope="module")
def hedge(tables):
    return submit.build(tables, models=submit.HEDGE_MODELS)


def _parts(frame):
    parts = frame.id.str.extract(r"^w(\d+)_(.+)$")
    return parts[0].astype(int), parts[1]


def test_hedge_kes_floor_is_country_specific_and_starts_at224(tables, built, hedge):
    week, material = _parts(built)
    supplied = tables["suppliers"].loc[lambda f: f.country == "KES"].material
    eligible = (week >= 224) & material.isin(supplied)
    assert np.array_equal(hedge.loc[~eligible, "disruption_prob"], built.loc[~eligible, "disruption_prob"])
    assert (hedge.loc[eligible, "disruption_prob"] >= .6).all()
    assert (hedge.loc[eligible, "disruption_prob"] >= built.loc[eligible, "disruption_prob"]).all()


def test_hedge_respects_reduced_kes_capacity_after224(tables, hedge):
    submit.validate(hedge, tables)
    week, material = _parts(hedge)
    normal = tables["suppliers"].loc[lambda f: f.country == "KES"].set_index("material").normal_capacity_units
    affected = (week >= 224) & material.isin(normal.index)
    requested = hedge.loc[affected, "order_units"] * hedge.loc[affected, "share_KES"]
    assert (requested <= .37 * material[affected].map(normal) + 1e-6).all()
