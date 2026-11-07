import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from halcyon import disruption_fx, disruption_news
from halcyon.data import read_all


def _articles(*rows):
    return pd.DataFrame(
        [(f"N{i}", week, "2022-01-01", source, headline, "")
         for i, (week, source, headline) in enumerate(rows)],
        columns=["article_id", "week", "date", "source", "headline", "body"],
    )


def _event_data():
    materials = ("lithium", "cobalt", "copper")
    suppliers = pd.DataFrame(
        [("lithium", "KES", "Kestria", "MERROW"),
         ("cobalt", "KES", "Kestria", "MERROW"),
         ("copper", "VAL", "Valdmar", "NORTH")],
        columns=["material", "country", "country_name", "lane"],
    )
    outcomes = pd.DataFrame(
        [(week, material, int(material != "copper" and 11 <= week <= 20))
         for week in range(1, 51) for material in materials],
        columns=["week", "material", "disrupted"],
    )
    macro = pd.DataFrame(
        [(week, "KES", 0.98 if week == 10 else 0.95 if week == 30 else 1.0)
         for week in range(1, 51)],
        columns=["week", "country", "fx_rate"],
    )
    news = _articles(
        (10, "wire-a", "Diplomatic talks between Aurelia and Kestria break down"),
        (12, "wire-a", "Sanctions on Kestria take effect"),
        (30, "wire-b", "Diplomatic talks between Aurelia and Kestria break down"),
    )
    return {"suppliers": suppliers, "outcomes": outcomes, "macro": macro, "news": news}


def test_warning_onset_is_event_level_fx_confirmed_and_scope_specific():
    data = _event_data()
    frame = pd.DataFrame(
        [(31, material, 0.1) for material in ("lithium", "cobalt", "copper")],
        columns=["week", "material", "disruption_prob"],
    )
    result = disruption_fx.sanction_probabilities(data, 30, frame).set_index("material")
    assert result.loc["lithium", "disruption_prob"] == 0.85
    assert result.loc["cobalt", "disruption_prob"] == 0.85
    assert result.loc["copper", "disruption_prob"] == 0.1

    # Missing current state is unknown, not evidence that a material is clean.
    incomplete = {name: table.copy() for name, table in data.items()}
    incomplete["outcomes"] = incomplete["outcomes"].loc[
        ~((incomplete["outcomes"].week == 30)
          & (incomplete["outcomes"].material == "lithium"))
    ]
    missing = disruption_fx.sanction_probabilities(incomplete, 30, frame).set_index("material")
    assert missing.loc["lithium", "disruption_prob"] == 0.1
    assert missing.loc["cobalt", "disruption_prob"] == 0.85

    def base_predict(_data, _cutoff, _weeks):
        return frame

    composed = disruption_fx.predict(data, 30, [31], base=base_predict).set_index("material")
    assert_frame_equal(composed, result)

    # Without the current FX confirmation, warning chronology alone is a no-op.
    data["macro"].loc[data["macro"].week == 30, "fx_rate"] = 1.0
    assert_frame_equal(disruption_fx.sanction_probabilities(data, 30, frame), frame)


def test_active_persistence_uses_only_mature_event_offsets_and_deduplicates_sources():
    data = _event_data()
    active = "Sanctions on Kestria take effect"
    data["news"] = _articles((40, "wire-a", active), (40, "wire-b", active))
    data["outcomes"].loc[
        (data["outcomes"].material.isin(["lithium", "cobalt"]))
        & data["outcomes"].week.between(40, 43), "disrupted"] = 1
    data["macro"].loc[data["macro"].week.between(40, 43), "fx_rate"] = 0.8
    frame = pd.DataFrame(
        [(week, material, 0.1)
         for week in range(44, 48) for material in ("lithium", "cobalt", "copper")],
        columns=["week", "material", "disruption_prob"],
    )
    result = disruption_fx.sanction_probabilities(data, 43, frame)
    kes = result.material.isin(["lithium", "cobalt"])
    assert result.loc[kes & result.week.between(44, 46), "disruption_prob"].eq(0.85).all()
    # Active+4 is after cutoff, so no target is invented for forecast horizon four.
    assert result.loc[kes & result.week.eq(47), "disruption_prob"].eq(0.1).all()
    assert result.loc[result.material.eq("copper"), "disruption_prob"].eq(0.1).all()

    # A currency rebound separates recovery risk from active-shock persistence.
    data["macro"].loc[data["macro"].week == 43, "fx_rate"] = 0.9
    assert_frame_equal(disruption_fx.sanction_probabilities(data, 43, frame), frame)



def test_same_week_activation_closes_warning_and_repeated_activation_keeps_anchor():
    data = _event_data()
    warning = "Diplomatic talks between Aurelia and Kestria break down"
    active = "Sanctions on Kestria take effect"
    data["news"] = _articles((40, "wire-a", warning), (40, "wire-b", active))
    frame = pd.DataFrame(
        [(41, material, 0.1) for material in ("lithium", "cobalt", "copper")],
        columns=["week", "material", "disruption_prob"],
    )
    assert_frame_equal(disruption_fx.sanction_probabilities(data, 40, frame), frame)

    data["news"] = _articles((40, "wire-a", active), (41, "wire-b", active))
    data["outcomes"].loc[
        (data["outcomes"].material.isin(["lithium", "cobalt"]))
        & data["outcomes"].week.between(40, 43), "disrupted"] = 1
    data["macro"].loc[data["macro"].week == 40, "fx_rate"] = 0.8
    data["macro"].loc[data["macro"].week == 41, "fx_rate"] = 0.9
    data["macro"].loc[data["macro"].week == 43, "fx_rate"] = 0.85
    frame = pd.DataFrame(
        [(44, material, 0.1) for material in ("lithium", "cobalt", "copper")],
        columns=["week", "material", "disruption_prob"],
    )
    assert_frame_equal(disruption_fx.sanction_probabilities(data, 43, frame), frame)

def test_real_inference_schema_scope_and_post_cutoff_tamper_invariance():
    data = read_all()
    weeks = [118, 124, 130]
    base = disruption_news.predict(data, 117, weeks)
    expected = disruption_fx.predict(data, 117, weeks)
    assert list(expected.columns) == ["week", "material", "disruption_prob"]
    assert np.isfinite(expected.disruption_prob).all()
    assert expected.disruption_prob.between(0, 1).all()
    changed = expected.disruption_prob > base.disruption_prob
    kes_materials = set(data["suppliers"].loc[lambda table: table.country == "KES", "material"])
    assert changed.any()
    assert set(expected.loc[changed, "material"]) <= kes_materials

    tampered = {name: table.copy() for name, table in data.items()}
    future = tampered["news"].week.between(118, 208)
    tampered["news"].loc[future, "headline"] = "Sanctions on Kestria take effect"
    future = tampered["macro"].week.between(118, 208)
    tampered["macro"].loc[future, "fx_rate"] = 999.0
    future = tampered["outcomes"].week.between(118, 208)
    tampered["outcomes"].loc[future, "disrupted"] = 1
    assert_frame_equal(expected, disruption_fx.predict(tampered, 117, weeks))
