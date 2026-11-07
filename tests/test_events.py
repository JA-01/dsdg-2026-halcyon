import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from halcyon import disruption, events
from halcyon.data import MATERIALS, read_all, release_cutoff


@pytest.fixture
def tables():
    return read_all("data")


def news(*rows):
    return pd.DataFrame([(f"A{i}", w, "2022-01-01", source, headline, body)
                         for i, (w, source, headline, body) in enumerate(rows)],
                        columns=["article_id", "week", "date", "source", "headline", "body"])


def label_history(tables):
    tables["outcomes"] = pd.DataFrame(
        [(w, m, int(w >= 7 and m == "cobalt")) for w in range(1, 31) for m in MATERIALS],
        columns=["week", "material", "disrupted"])
    return tables


def test_lane_mapping_and_country_material_intersection(tables):
    tables["news"] = news(
        (3, "S1", "Port labor talks drag on for the Merrow Strait", ""),
        (3, "S2", "Valdmar drafts restrictions on cobalt shipments abroad", "Aurelian buyers watch."),
        (4, "S3", "Deal reached, Merrow Strait disruption averted", ""))
    reports = events.articles(tables, 3)
    expected = set(tables["suppliers"].loc[lambda f: f.lane == "MERROW"].material)
    assert set(reports.loc[reports.article_id == "A0", "material"]) == expected
    assert list(reports.loc[reports.article_id == "A1", "material"]) == ["cobalt"]
    assert not (reports.stage == "averted").any()
    assert "averted" in set(events.articles(tables, 4).stage)


def test_warning_copies_are_one_event_and_censored_windows_are_excluded(tables):
    tables = label_history(tables)
    headline = "Valdmar drafts restrictions on cobalt shipments abroad"
    tables["news"] = news((3, "S1", headline, ""))
    one = events.template_table(tables, 30)
    tables["news"] = news((3, "S1", headline, ""), (4, "S2", headline, ""))
    assert_frame_equal(one, events.template_table(tables, 30))
    assert one.event_count.iloc[0] == 1
    assert one.onset_count.iloc[0] == 1
    assert one.median_lead.iloc[0] == 4
    assert events.template_table(tables, 10).empty


def test_averted_warning_cannot_claim_later_unrelated_onset(tables):
    tables = label_history(tables)
    tables["news"] = news(
        (3, "S1", "Valdmar drafts restrictions on cobalt shipments abroad", ""),
        (4, "S2", "Valdmar officials rule out new restrictions", ""))
    result = events.template_table(tables, 30)
    assert result.event_count.iloc[0] == 1
    assert result.onset_count.iloc[0] == 0
    assert result.decoy_rate.iloc[0] == 1


def test_shock_floor_is_scenario_specific_and_preserves_existing_high_risk(tables):
    base = pd.DataFrame([(101, m, .1) for m in MATERIALS],
                        columns=["week", "material", "disruption_prob"])
    base.loc[base.material == "lithium", "disruption_prob"] = .95
    tables["news"] = news()
    result = events.shock_probabilities(tables, 100, base).set_index("material")
    exposed = set(tables["suppliers"].loc[lambda f: f.lane == "MERROW"].material)
    for m in MATERIALS:
        probability = result.loc[m, "disruption_prob"]
        if m == "lithium":
            assert probability == .95
        elif m in exposed:
            assert .1 < probability <= .7
        else:
            assert probability == .1
    assert base.loc[base.material == "steel", "disruption_prob"].iloc[0] == .1


def test_announcements_need_confirmation_and_never_start_before_effective_week(tables):
    tables["news"] = news()
    tables["prices"].loc[:, ["spot_price", "futures_4w"]] = 1.0
    tables["macro"].loc[:, "tension_index"] = 10.0
    tables["macro"].loc[:, "fx_rate"] = 1.0
    tables["shipping"].loc[:, "congestion_index"] = 10.0
    target = ((tables["tariffs"].week == 100) & (tables["tariffs"].material == "lithium")
              & (tables["tariffs"].country == "VAL"))
    tables["tariffs"].loc[:, ["announced_rate", "announced_effective_week"]] = np.nan
    tables["tariffs"].loc[target, ["announced_rate", "announced_effective_week"]] = [.4, 102]
    frame = pd.DataFrame([(w, "lithium", .1) for w in [101, 102]],
                         columns=["week", "material", "disruption_prob"])
    unconfirmed = events.shock_probabilities(tables, 100, frame)
    assert unconfirmed.disruption_prob.iloc[0] == unconfirmed.disruption_prob.iloc[1]
    tables["macro"].loc[tables["macro"].week == 100, "tension_index"] = 80
    tables["prices"].loc[tables["prices"].week == 100, "futures_4w"] = 1.05
    confirmed = events.shock_probabilities(tables, 100, frame)
    assert confirmed.disruption_prob.iloc[0] == unconfirmed.disruption_prob.iloc[0]
    assert unconfirmed.disruption_prob.iloc[1] < confirmed.disruption_prob.iloc[1] <= .7
    tables["tariffs"].loc[target, ["announced_rate", "announced_effective_week"]] = np.nan
    assert_frame_equal(events.shock_probabilities(tables, 100, frame), unconfirmed)


def test_future_tables_cannot_change_shock_forecast(tables):
    before = disruption.predict(tables, 100, [101, 104, 113], variant="shock")
    tables["outcomes"].loc[tables["outcomes"].week > 100, "disrupted"] = 1
    tables["news"].loc[tables["news"].week > 100, "headline"] = "Strike shuts ports along the Merrow Strait"
    for name in ["prices", "macro", "shipping", "tariffs"]:
        frame = tables[name]
        numeric = frame.select_dtypes("number").columns.drop("week")
        frame.loc[frame.week > 100, numeric] = 999
    assert_frame_equal(before, disruption.predict(tables, 100, [101, 104, 113], variant="shock"))


def test_situation_refuses_unreleased_cutoff(tables):
    with pytest.raises(ValueError):
        events.situation(tables, 221)
