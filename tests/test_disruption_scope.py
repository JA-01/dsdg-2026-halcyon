"""Consumer invariants for geography-aware joint disruption forecasts."""
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from halcyon import disruption_news, disruption_scope
from halcyon.data import MATERIALS, TIMED_TABLES, as_of, read_all


def _news(*rows):
    return pd.DataFrame([dict(week=w, headline=h, body='', source='test', article_id=i)
                         for i, (w, h) in enumerate(rows)])


def _signature(history, material, week):
    return history[week - 1][MATERIALS.index(material)][0]


def test_lane_recovery_preserves_country_event_and_partial_recovery_scope():
    tables = read_all()
    tables['news'] = _news(
        (1, 'Sanctions on Kestria take effect'),
        (2, 'Traffic through the Merrow Strait suspended after clashes'),
        (4, 'Traffic returns to the Merrow Strait'),
        (6, 'Disruption in Kestria cobalt supply eases'))
    history = disruption_scope.state_history(tables, 7)
    lithium = _signature(history, 'lithium', 7)
    cobalt = _signature(history, 'cobalt', 7)
    assert any(f == 'sanctions' and s == 3 and anchor == 'country'
               for f, s, _, anchor in lithium)
    assert any(f == 'clash' and s == 5 and anchor == 'lane'
               for f, s, _, anchor in lithium)
    assert not any(f == 'clash' and s == 3 for f, s, _, _ in lithium)
    assert any(f == 'sanctions' and s == 5 for f, s, _, _ in cobalt)


def test_syndication_does_not_reset_story_age_or_count_and_future_cannot_rewrite_history():
    tables = read_all()
    tables['news'] = _news(
        (1, 'Lawmakers in Orinoque debate limits on raw material exports'),
        (3, 'Orinoque drafts restrictions on copper shipments abroad'),
        (4, 'Orinoque drafts restrictions on copper shipments abroad'),
        (7, 'Orinoque officials rule out new restrictions'))
    expected = disruption_scope.state_history(tables, 5)
    assert any(f == 'export' and s == 2 and age == 1
               for f, s, age, _ in _signature(expected, 'copper', 5))
    assert disruption_scope.state_history(tables, 10)[:5] == expected
    tables['news'] = pd.concat([tables['news'], tables['news']], ignore_index=True)
    assert disruption_scope.state_history(tables, 5) == expected


def test_real_forecasts_are_cutoff_safe_bounded_and_leave_input_untouched():
    tables = read_all()
    snapshot = {k: v.copy(deep=True) for k, v in tables.items()}
    weeks = list(range(196, 209))
    expected = disruption_scope.predict(as_of(tables, 195), 195, weeks)
    for key in tables:
        assert_frame_equal(tables[key], snapshot[key])
    for key in TIMED_TABLES:
        future = tables[key].week > 195
        for column in tables[key].select_dtypes(include='number').columns:
            if column != 'week':
                tables[key].loc[future, column] = 999999
    tables['news'].loc[tables['news'].week > 195, 'headline'] = 'Sanctions on Kestria take effect'
    assert_frame_equal(expected, disruption_scope.predict(tables, 195, weeks))
    assert len(expected) == 130
    assert expected.disruption_prob.between(0, 1).all()
    assert np.isfinite(expected.disruption_prob).all()
    assert not expected.duplicated(['week', 'material']).any()


def test_no_event_evidence_preserves_incumbent_and_duplicate_forecasts():
    tables = as_of(read_all(), 156)
    tables['news'] = tables['news'].iloc[:0]
    weeks = [157, 160, 169]
    assert_frame_equal(disruption_news.predict(tables, 156, weeks),
                       disruption_scope.predict(tables, 156, weeks))
    tables = as_of(read_all(), 195)
    expected = disruption_scope.predict(tables, 195, [196, 201, 208])
    tables['news'] = pd.concat([tables['news'], tables['news']], ignore_index=True)
    assert_frame_equal(expected, disruption_scope.predict(tables, 195, [196, 201, 208]))


def test_real_news_cancellation_overlap_partial_recovery_and_repeated_story():
    tables = as_of(read_all(), 126)
    history = disruption_scope.state_history(tables, 126)
    # Northern route strike averted at77 after warnings74..76.
    assert any(f == 'strike' and s == 4 and anchor == 'lane'
               for f, s, _, anchor in _signature(history, 'copper', 77))
    # Merrow traffic recovery104 leaves Kestria sanctions99 active.
    overlap = _signature(history, 'aluminum', 104)
    assert any(f == 'clash' and s == 5 and anchor == 'lane'
               for f, s, _, anchor in overlap)
    assert any(f == 'sanctions' and s == 3 and anchor == 'country'
               for f, s, _, anchor in overlap)
    # Semiconductor recovery122 closes its country exposure only.
    assert any(s == 5 for _, s, _, _ in _signature(history, 'semiconductors', 122))
    assert any(f == 'sanctions' and s == 3
               for f, s, _, _ in _signature(history, 'aluminum', 122))
    # Sanctions story began92: repeated imminent reports97..98 do not restart
    # the age clock when the event becomes active99 (seven weeks => middle bin).
    assert any(f == 'sanctions' and s == 3 and age == 1
               for f, s, age, _ in _signature(history, 'aluminum', 99))
    tables['news'] = pd.concat([tables['news'], tables['news']], ignore_index=True)
    assert disruption_scope.state_history(tables, 126) == history
