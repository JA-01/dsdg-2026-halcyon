import numpy as np
import pandas as pd
import pytest

from halcyon.data import MATERIALS, read_all
from halcyon.price import predict


def test_horizon_and_cutoff_filter():
    history = pd.DataFrame([(w, m, 10.0 if w == 1 else 20.0)
                            for w in (1, 2) for m in MATERIALS],
                           columns=['week', 'material', 'benchmark_price'])
    expected = predict({'outcomes': history}, 2, [3, 28])
    # At one half-life the prediction is halfway between last and mean.
    assert np.allclose(expected.loc[expected.week == 28, 'price_forecast'], 17.5)
    future = pd.DataFrame([(3, m, 99999.0) for m in MATERIALS], columns=history.columns)
    actual = predict({'outcomes': pd.concat([history, future])}, 2, [3, 28])
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
