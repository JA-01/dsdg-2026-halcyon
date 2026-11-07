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
