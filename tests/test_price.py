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
    # At one half-life the prediction is halfway between last and mean.
    assert np.allclose(expected.loc[expected.week == 29, 'price_forecast'], 55 / 3)
    future = pd.DataFrame([(4, m, 99999.0) for m in MATERIALS], columns=history.columns)
    actual = predict({'outcomes': pd.concat([history, future])}, 3, [4, 29])
    pd.testing.assert_frame_equal(expected, actual)
    assert expected.price_forecast.between(15, 20).all()


def test_real_data_future_mutation():
    tables = read_all()
    expected = predict(tables, 130, [131, 143, 156])
    tables['outcomes'].loc[tables['outcomes'].week > 130, 'benchmark_price'] *= 100
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


def test_lag_response_ignores_future_news_and_disruption_labels():
    tables = read_all()
    expected = predict(tables, 156, [157, 160, 169])
    tables['outcomes'].loc[tables['outcomes'].week > 156, 'disrupted'] = 1
    tables['news'].loc[tables['news'].week > 156, 'headline'] = 'Strike shuts ports along the Merrow Strait'
    tables['tariffs'].loc[tables['tariffs'].week > 156, 'announced_rate'] = .99
    pd.testing.assert_frame_equal(expected, predict(tables, 156, [157, 160, 169]))


def test_learned_lag_raises_prices_after_the_onset(monkeypatch):
    from halcyon import disruption_news
    from halcyon.price import _lag_premium

    tables = read_all()
    state = lambda w: int(w > 0 and 8 <= (w - 1) % 20 + 1 <= 15)
    tables['outcomes'] = pd.DataFrame(
        [(w, m, 10 * np.exp(.08 * state(w - 3)), state(w))
         for w in range(1, 81) for m in MATERIALS],
        columns=['week', 'material', 'benchmark_price', 'disrupted'])
    # Known future states are a controlled test fixture, not production inputs.
    def future(data, cutoff, weeks):
        return pd.DataFrame([(w, m, state(w)) for w in weeks for m in MATERIALS],
                            columns=['week', 'material', 'disruption_prob'])
    monkeypatch.setattr(disruption_news, 'predict', future)
    premium = _lag_premium(tables, 69, [70, 71, 72])
    assert (premium[1] > premium[0]).all()
    assert (premium[1] > 0).all() and (premium <= .2).all()


def test_ongoing_shock_level_is_not_added_twice(monkeypatch):
    from halcyon import disruption_news
    from halcyon.price import _lag_premium

    tables = read_all()
    tables['outcomes'] = pd.DataFrame(
        [(w, m, 10 if w < 30 else 12, int(w >= 30)) for w in range(1, 51) for m in MATERIALS],
        columns=['week', 'material', 'benchmark_price', 'disrupted'])
    monkeypatch.setattr(disruption_news, 'predict', lambda data, cutoff, weeks: pd.DataFrame(
        [(w, m, 1.0) for w in weeks for m in MATERIALS],
        columns=['week', 'material', 'disruption_prob']))
    assert np.allclose(_lag_premium(tables, 50, [51, 55, 63]), 0)
