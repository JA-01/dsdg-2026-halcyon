from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from halcyon.contracts import validate_forecasts
from halcyon.data import Dataset
from halcyon.news import SIGNAL_COLUMNS, affected_suppliers, extract_events, news_signals
from halcyon.news.extract import ROUTINE_TEMPLATES, SIGNAL_TEMPLATES, STAGES, template_of
from halcyon.forecasting.baseline import HistoricalForecaster
from halcyon.news.forecaster import DisruptionModel, HistoricalRiskPolicy
from halcyon.policy import OptimizedPolicy

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def data():
    return Dataset.from_csv_dir(DATA)


@pytest.fixture(scope="module")
def events(data):
    return extract_events(data["news"])


def article(headline, body="", week=10, article_id="a1", date="2022-03-07"):
    return pd.DataFrame([{"article_id": article_id, "week": week, "date": date, "source": "s",
                          "headline": headline, "body": body}])


def test_every_supplied_article_is_classified(data, events):
    templates = data["news"]["headline"].map(template_of)
    assert templates.isin(set(SIGNAL_TEMPLATES) | ROUTINE_TEMPLATES).all()
    assert (events["category"] != "unmapped").all()
    assert set(events["stage"]) <= set(STAGES)


def test_tables_do_not_overlap():
    assert not set(SIGNAL_TEMPLATES) & ROUTINE_TEMPLATES


def test_unknown_template_is_flagged_not_guessed():
    frame = extract_events(article("Meteor strikes Kestria"))
    assert frame.loc[0, "category"] == "unmapped"
    assert affected_suppliers(frame, pd.DataFrame(columns=["material", "country"])).empty


def test_entities_and_evidence_come_from_the_article(data):
    frame = extract_events(article("Valdmar abruptly suspends rare earth export licenses",
                                   "In a surprise move, Valdmar froze rare earth export permits without prior notice."))
    row = frame.iloc[0]
    assert (row["category"], row["stage"]) == ("export_ban", "active")
    assert row["countries"] == ["VAL"] and row["materials"] == ["rare_earths"]
    assert "surprise move" in row["evidence"]


def test_aurelia_is_buyer_when_another_country_is_named():
    frame = extract_events(article("Sanctions on Kestria take effect", "Aurelia's sanctions on Kestria are now in force."))
    assert frame.loc[0, "countries"] == ["KES"]


def test_repeated_text_keeps_each_articles_own_week():
    first = article("Strike shuts ports along the Merrow Strait", "Walkout.", week=70, article_id="a")
    second = article("Strike shuts ports along the Merrow Strait", "Walkout.", week=109, article_id="b", date="2024-01-29")
    frame = extract_events(pd.concat([first, second]))
    assert frame["week"].tolist() == [70, 109] and frame["date"].nunique() == 2


def test_lane_event_hits_both_merrow_countries(data):
    frame = extract_events(article("Strike shuts ports along the Merrow Strait", "Dockworkers walked off."))
    hits = affected_suppliers(frame, data["suppliers"])
    assert set(hits["country"]) == {"KES", "SUN"}


def test_named_material_narrows_a_country_event(data):
    frame = extract_events(article("Kestria rations water to steel producers", "Authorities in Kestria ordered steel cuts."))
    hits = affected_suppliers(frame, data["suppliers"])
    assert set(zip(hits["material"], hits["country"])) == {("steel", "KES")}


def test_signals_do_not_read_future_articles(data):
    all_rows = news_signals(data["news"], data["suppliers"])
    cut = news_signals(data.as_of(100)["news"], data["suppliers"], last_week=100)
    past = all_rows[all_rows["week"] <= 100].reset_index(drop=True)
    pd.testing.assert_frame_equal(past, cut.reset_index(drop=True), check_dtype=False)


def test_signals_cover_each_week_and_material_once(data):
    rows = news_signals(data["news"], data["suppliers"])
    assert len(rows) == rows["week"].max() * 10 and not rows.duplicated(["week", "material"]).any()
    assert np.isfinite(rows[list(SIGNAL_COLUMNS)].to_numpy()).all()


def test_open_signal_closes_on_recovery(data):
    suppliers = data["suppliers"]
    active = article("Strike shuts ports along the Merrow Strait", "x", week=5, article_id="a")
    over = article("Traffic returns to the Merrow Strait", "x", week=6, article_id="b")
    rows = news_signals(pd.concat([active, over]), suppliers, last_week=6)
    steel = rows[rows["material"] == "lithium"].set_index("week")["news_open"]  # lithium sells through KES
    assert steel[5] == 1 and steel[6] == 0


@pytest.mark.parametrize("use_news", [True, False])
def test_model_output_meets_contract_and_ignores_future_rows(data, use_news):
    weeks = list(range(131, 157))
    first = DisruptionModel(use_news).predict(data.as_of(130), 130, weeks)
    validate_forecasts(first, weeks)
    tables = {name: data[name] for name in data}
    tables["outcomes"].loc[tables["outcomes"]["week"] > 130, "disrupted"] = 1
    news = tables["news"]
    news.loc[news["week"] > 130, "headline"] = "Strike shuts ports along the Merrow Strait"
    second = DisruptionModel(use_news).predict(Dataset(tables).as_of(130), 130, weeks)
    pd.testing.assert_frame_equal(first, second)


def test_short_history_still_gives_valid_output(data):
    weeks = [11, 12]
    frame = DisruptionModel(True).predict(data.as_of(10), 10, weeks)
    validate_forecasts(frame, weeks)


def test_long_horizon_stays_near_the_rate_after_a_long_shock(data):
    """Regression: origin 130 sits inside a 35-week shock; a logistic fit gave 0.87 at horizon 26."""
    frame = DisruptionModel(False).predict(data.as_of(130), 130, [156])
    rates = DisruptionModel(False).base.predict(data.as_of(130), 130, [156])
    assert frame["disruption_prob"].max() < 0.5 and rates["disruption_prob"].max() < 0.5


def test_news_probabilities_cannot_change_orders(data):
    weeks = list(range(131, 144))
    view = data.as_of(130)
    historical = HistoricalForecaster().predict(view, 130, weeks)
    news = DisruptionModel(True).predict(view, 130, weeks)
    assert not np.allclose(news.sort_values(["target_week", "material"])["disruption_prob"],
                           historical.sort_values(["target_week", "material"])["disruption_prob"])
    expected = OptimizedPolicy().decide(view, historical, 130, weeks)
    actual = HistoricalRiskPolicy().decide(view, news, 130, weeks)
    pd.testing.assert_frame_equal(actual, expected)


def test_long_horizons_equal_the_historical_rate(data):
    weeks = list(range(144, 157))
    view = data.as_of(130)
    keys = ["target_week", "material"]
    news = DisruptionModel(True).predict(view, 130, weeks).sort_values(keys)
    historical = HistoricalForecaster().predict(view, 130, weeks).sort_values(keys)
    assert (news["disruption_prob"].to_numpy() == historical["disruption_prob"].to_numpy()).all()


def test_price_blend_changes_only_flat_prices_not_orders(data):
    weeks = list(range(131, 144))
    view = data.as_of(130)
    keys = ["target_week", "material"]
    plain = DisruptionModel(True).predict(view, 130, weeks).sort_values(keys).reset_index(drop=True)
    blended = DisruptionModel(True, price_blend=0.25).predict(view, 130, weeks).sort_values(keys).reset_index(drop=True)
    assert (plain["disruption_prob"] == blended["disruption_prob"]).all()
    assert (blended.groupby("material")["price_forecast"].nunique() == 1).all()

    outcomes = view["outcomes"]
    mean = outcomes[outcomes["week"] > 130 - 52].query("material == 'lithium'")["benchmark_price"].mean()
    last = outcomes[outcomes["week"] == 130].query("material == 'lithium'")["benchmark_price"].iloc[0]
    assert blended.query("material == 'lithium'")["price_forecast"].iloc[0] == pytest.approx(0.75 * last + 0.25 * mean)
    pd.testing.assert_frame_equal(HistoricalRiskPolicy().decide(view, blended, 130, weeks),
                                  HistoricalRiskPolicy().decide(view, plain, 130, weeks))


def test_short_history_long_horizon_equals_the_historical_rate(data):
    view = data.as_of(10)
    news = DisruptionModel(True).predict(view, 10, [24]).sort_values("material")
    historical = HistoricalForecaster().predict(view, 10, [24]).sort_values("material")
    assert (news["disruption_prob"].to_numpy() == historical["disruption_prob"].to_numpy()).all()
