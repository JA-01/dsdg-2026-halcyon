import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from halcyon import disruption, disruption_news as news
from halcyon.data import MATERIALS, read_all


def articles(*rows):
    return pd.DataFrame([(f'N{i}', week, '2022-01-01', 'test', headline, '')
                         for i, (week, headline) in enumerate(rows)],
                        columns=['article_id', 'week', 'date', 'source', 'headline', 'body'])


def test_lane_scope_and_cancellation_are_specific():
    data = read_all()
    data['news'] = articles(
        (10, 'Congestion builds at ports on the Southern route'),
        (10, 'Tensions rise between Valdmar and neighbors'),
        (11, 'Tensions ease after talks with Valdmar'))
    cells = news._signals(data, 11)
    strike, clash = news.FAMILIES.index('strike'), news.FAMILIES.index('clash')
    exposed = set(data['suppliers'].loc[lambda f: f.lane == 'SOUTH'].material)
    assert {MATERIALS[j] for j in np.flatnonzero(cells[-1, :, strike])} == exposed
    assert cells[9, :, clash].any()
    assert not cells[-1, :, clash].any()
    # A different family's cancellation must not erase the strike warning.
    assert cells[-1, :, strike].any()


def test_ladder_upgrade_expiry_and_duplicate_reports():
    data = read_all()
    early = 'Port labor talks drag on for the Southern route'
    imminent = 'Union sets strike date for Southern route ports'
    data['news'] = articles((2, early), (3, imminent), (4, early))
    expected = news._signals(data, 18)
    j, f = MATERIALS.index('lithium'), news.FAMILIES.index('strike')
    assert expected[1, j, f] == 1
    assert expected[2, j, f] == 4
    assert expected[3, j, f] == 4
    assert expected[-1, j, f] == 0
    data['news'] = pd.concat([data['news'], data['news']], ignore_index=True)
    np.testing.assert_array_equal(expected, news._signals(data, 18))


def test_mature_warning_pairs_raise_calm_risk_and_preserve_persistence():
    data = read_all()
    data['outcomes'] = pd.DataFrame(
        [(w, m, int((14 <= w <= 20 or 34 <= w <= 40) and m in ('lithium', 'cobalt', 'copper', 'natural_gas')))
         for w in range(1, 51) for m in MATERIALS], columns=['week', 'material', 'disrupted'])
    headline = 'Union sets strike date for Southern route ports'
    data['news'] = articles((10, headline), (30, headline), (50, headline))
    weeks = [51, 54, 63]
    baseline = disruption.predict(data, 50, weeks).set_index(['week', 'material'])
    result = news.predict(data, 50, weeks).set_index(['week', 'material'])
    assert result.loc[(54, 'lithium'), 'disruption_prob'] > baseline.loc[(54, 'lithium'), 'disruption_prob']
    assert result.disruption_prob.between(0, .7).all()
    assert result.loc[(54, 'steel'), 'disruption_prob'] == baseline.loc[(54, 'steel'), 'disruption_prob']
    data['outcomes'].loc[lambda f: (f.week >= 45) & (f.material == 'lithium'), 'disrupted'] = 1
    primary = disruption.predict(data, 50, weeks).query("material == 'lithium'")
    challenger = news.predict(data, 50, weeks).query("material == 'lithium'")
    assert_frame_equal(primary.reset_index(drop=True), challenger.reset_index(drop=True))


def test_future_news_and_labels_cannot_change_forecasts():
    data = read_all()
    expected = news.predict(data, 156, [157, 160, 169])
    data['news'].loc[data['news'].week > 156, 'headline'] = 'Strike shuts ports along the Southern route'
    data['outcomes'].loc[data['outcomes'].week > 156, 'disrupted'] = 1
    assert_frame_equal(expected, news.predict(data, 156, [157, 160, 169]))
    assert np.isfinite(expected.disruption_prob).all()
    assert expected.disruption_prob.between(0, 1).all()


def test_no_warning_matches_primary():
    data = read_all()
    data['news'] = articles()
    assert_frame_equal(disruption.predict(data, 100, [101, 113]), news.predict(data, 100, [101, 113]))


def tariff_data():
    # Two correlated materials in one historical country/effective-date event.
    mats = ['aluminum', 'semiconductors']
    tariffs = []
    for w in range(1, 31):
        for m in mats:
            announced, effective = (np.nan, np.nan)
            if w in (8, 9):
                announced, effective = .3, 10
            if w in (19, 20):
                announced, effective = .4, 25
            tariffs.append((w, m, 'KES', .1 if w < 10 else .3, announced, effective))
    return {'tariffs': pd.DataFrame(tariffs, columns=['week', 'material', 'country', 'tariff_rate',
                                                     'announced_rate', 'announced_effective_week']),
            'outcomes': pd.DataFrame([(w, m, int(10 <= w <= 22)) for w in range(1, 31) for m in mats],
                                     columns=['week', 'material', 'disrupted'])}


def test_tariffs_start_at_effective_week_and_count_each_event_once():
    data = tariff_data()
    frame = pd.DataFrame([(w, 'aluminum', .1) for w in [24, 25, 27, 37]],
                         columns=['week', 'material', 'disruption_prob'])
    result = news.tariff_probabilities(data, 20, frame)
    # One event and Beta(1,1), capped at .6, despite repeated material reports.
    np.testing.assert_allclose(result.disruption_prob, [.1, .6, .6, .1])
    excluded = news.tariff_probabilities(data, 20, frame, exclude_events=(('KES', 10),))
    assert_frame_equal(excluded, frame)


def test_tariffs_observed_reversals_are_negative_and_future_is_hidden():
    data = tariff_data()
    frame = pd.DataFrame([(25, 'aluminum', .1)], columns=['week', 'material', 'disruption_prob'])
    expected = news.tariff_probabilities(data, 20, frame)
    data['tariffs'].loc[data['tariffs'].week > 20, ['tariff_rate', 'announced_rate']] = 999
    data['outcomes'].loc[data['outcomes'].week > 20, 'disrupted'] = 0
    assert_frame_equal(expected, news.tariff_probabilities(data, 20, frame))
    # A disruption from another cause does not count as an implemented tariff.
    data['tariffs'].loc[data['tariffs'].week == 10, 'tariff_rate'] = .1
    assert news.tariff_probabilities(data, 20, frame).disruption_prob.iloc[0] == pytest.approx(1/3)
    high = frame.assign(disruption_prob=.9)
    assert_frame_equal(high, news.tariff_probabilities(data, 20, high))


def test_tariff_without_announcements_is_noop():
    data = tariff_data()
    data['tariffs'][['announced_rate', 'announced_effective_week']] = np.nan
    frame = pd.DataFrame([(25, 'aluminum', .12)], columns=['week', 'material', 'disruption_prob'])
    assert_frame_equal(frame, news.tariff_probabilities(data, 20, frame))


def test_headline_country_overrides_lane_mentioned_only_in_body():
    data = read_all()
    data['news'] = articles((10, 'Tensions rise between Kestria and neighbors'))
    data['news'].loc[0, 'body'] = 'Officials watch territorial claims near the Merrow Strait.'
    reports = list(news._scoped_reports(data, 10))
    assert {c for m, c in reports[0][-1]} == {'KES'}
    assert {m for m, c in reports[0][-1]} == set(data['suppliers'].query("country == 'KES'").material)
    assert 'specialty_glass' not in {m for m, c in reports[0][-1]}


def test_body_material_scope_and_new_stalled_talks_template():
    data = read_all()
    data['news'] = articles(
        (10, 'Lawmakers in Kestria debate limits on raw material exports'),
        (10, 'Trade talks between Aurelia and Kestria stall'),
        (10, 'Congestion builds at ports on the Merrow Strait'))
    data['news'].loc[0, 'body'] = 'A committee discussed keeping more rare earth at home.'
    data['news'].loc[1, 'body'] = 'Duties on aluminum shipments came up repeatedly.'
    reports = list(news._scoped_reports(data, 10))
    by_template = {row[1]: row for row in reports}
    export = by_template['Lawmakers in {} debate limits on raw material exports']
    assert export[-1] == (('rare_earths', 'KES'),)
    stall = by_template['Trade talks between {} and {} stall']
    assert stall[2:4] == ('tariff', 'early')
    assert stall[-1] == (('aluminum', 'KES'),)
    lane = by_template['Congestion builds at ports on the {}']
    assert {country for material, country in lane[-1]} == {'KES', 'SUN'}


def test_unconfirmed_warning_expires_without_repeats():
    data = read_all()
    data['news'] = articles((10, 'Union sets strike date for Southern route ports'))
    cells = news._signals(data, 15)
    assert cells[13].any()  # Four weeks after the report.
    assert cells[14].sum() == 0  # Five weeks after it: no fresh confirmation.
