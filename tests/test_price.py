import numpy as np
import pandas as pd
import pytest

from halcyon.data import MATERIALS, read_all
from halcyon.price import predict


def test_horizon_and_cutoff_filter():
    history = pd.DataFrame([(w, m, 10.0 if w == 1 else 20.0)
                            for w in (1, 2, 3) for m in MATERIALS],
                           columns=['week', 'material', 'benchmark_price'])
    expected = predict({'outcomes': history}, 3, [4, 29])
    future = pd.DataFrame([(4, m, 99999.0) for m in MATERIALS], columns=history.columns)
    actual = predict({'outcomes': pd.concat([history, future])}, 3, [4, 29])
    pd.testing.assert_frame_equal(expected, actual)
    assert expected.price_forecast.between(15, 20).all()


def test_real_data_future_mutation():
    tables = read_all()
    expected = predict(tables, 130, [131, 143, 156])
    tables['outcomes'].loc[tables['outcomes'].week > 130, 'benchmark_price'] *= 100
    tables['outcomes'].loc[tables['outcomes'].week > 130, 'disrupted'] = 1
    tables['prices'].loc[tables['prices'].week > 130, 'futures_4w'] *= 1000
    tables['prices'].loc[tables['prices'].week > 130, 'spot_price'] *= 100
    tables['supply_history'].loc[tables['supply_history'].week > 130,
                                ['capacity_units', 'lead_time_weeks']] = [1, 99]
    pd.testing.assert_frame_equal(expected, predict(tables, 130, [131, 143, 156]))
    assert len(expected) == 30
    assert np.isfinite(expected.price_forecast).all()
    assert expected.price_forecast.gt(0).all()


def test_missing_history_and_invalid_horizon():
    tables = read_all()
    with pytest.raises(ValueError, match='missing price history'):
        predict(tables, 0, [1])
    with pytest.raises(ValueError, match='after cutoff'):
        predict(tables, 130, [130])


def test_single_quote_and_extreme_jump_remain_positive():
    history = pd.DataFrame([(1, m, 1.0) for m in MATERIALS],
                           columns=['week', 'material', 'benchmark_price'])
    assert predict({'outcomes': history}, 1, [2, 100]).price_forecast.eq(1).all()
    jump = pd.DataFrame([(2, m, 1000.0) for m in MATERIALS], columns=history.columns)
    result = predict({'outcomes': pd.concat([history, jump])}, 2, [3, 100])
    assert np.isfinite(result.price_forecast).all()
    assert result.price_forecast.between(0, 1000, inclusive='neither').all()


def _basis_tables(*, onset=None, recovery=None, saturated=False):
    """One flagged supplier; the benchmark jump may be masked by an older shock."""
    weeks = range(1, 25)
    level = lambda w: 12.0 if onset is not None and w >= onset and (
        recovery is None or w < recovery) else 10.0
    suppliers = pd.DataFrame([('lithium', 'VAL', 100.0, 1)],
                             columns=['material', 'country', 'normal_capacity_units',
                                      'base_lead_weeks'])
    outcomes = pd.DataFrame(
        [(w, m, level(w) if m == 'lithium' else 10.0, 0)
         for w in weeks for m in MATERIALS],
        columns=['week', 'material', 'benchmark_price', 'disrupted'])
    quotes = pd.DataFrame(
        [(w, 'lithium', 'VAL', level(w), level(w) * (1.2 if 5 <= w <= 7 else 1))
         for w in weeks],
        columns=['week', 'material', 'country', 'spot_price', 'futures_4w'])
    supply = pd.DataFrame(
        [(w, 'lithium', 'VAL', 20.0 if saturated or level(w) > 10 else 100.0, 1)
         for w in weeks],
        columns=['week', 'material', 'country', 'capacity_units', 'lead_time_weeks'])
    return {'outcomes': outcomes, 'prices': quotes, 'suppliers': suppliers,
            'supply_history': supply}


def test_basis_warning_adds_temporary_not_permanent_price_premium():
    result = predict(_basis_tables(), 6, range(7, 25))
    lithium = result.loc[result.material == 'lithium'].set_index('week').price_forecast
    assert lithium.max() > 11
    assert lithium.loc[24] == pytest.approx(10)
    assert result.loc[result.material != 'lithium', 'price_forecast'].eq(10).all()


def test_weak_basis_requires_two_consecutive_observations():
    tables = _basis_tables()
    quotes = tables['prices']
    quotes['futures_4w'] = quotes.spot_price
    quotes.loc[quotes.week == 5, 'futures_4w'] = 10.4
    single = predict(tables, 6, range(7, 25))
    quotes.loc[quotes.week == 6, 'futures_4w'] = 10.4
    confirmed = predict(tables, 6, range(7, 25))
    assert single.price_forecast.eq(10).all()
    assert confirmed.price_forecast.max() > single.price_forecast.max() + .1


@pytest.mark.parametrize('saturated', [False, True])
def test_observed_price_jump_is_not_added_twice(saturated):
    result = predict(_basis_tables(onset=8, saturated=saturated), 9, [10, 24])
    lithium = result.loc[result.material == 'lithium'].set_index('week').price_forecast
    assert lithium.loc[10] <= 12 * 1.01
    assert lithium.loc[24] == pytest.approx(10, rel=.05)


def test_recovered_price_episode_does_not_replay():
    tables = _basis_tables(onset=8, recovery=12, saturated=True)
    actual = predict(tables, 14, range(15, 25))
    tables['prices']['futures_4w'] = tables['prices'].spot_price
    pd.testing.assert_frame_equal(actual, predict(tables, 14, range(15, 25)))


def test_delay_and_disruption_label_without_basis_do_not_add_price_jump():
    tables = _basis_tables()
    tables['prices']['futures_4w'] = tables['prices'].spot_price
    tables['outcomes']['disrupted'] = 1
    tables['supply_history']['capacity_units'] = 75.0
    tables['supply_history']['lead_time_weeks'] = 4
    assert predict(tables, 10, range(11, 25)).price_forecast.eq(10).all()
