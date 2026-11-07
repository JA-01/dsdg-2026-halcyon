import pytest

from halcyon import submit
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


def test_baselines_reproduce_naive_sample(built, tables):
    """The reference modules equal the organizer's naive file, so they score 0."""
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
