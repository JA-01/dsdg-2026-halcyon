import numpy as np
import pandas as pd
import pytest

from halcyon.data import SHARE_COLUMNS
from halcyon.ensemble import blend

S = list(SHARE_COLUMNS)


def plan(units, shares):
    rows = [dict(week=209 + i, material="lithium", order_units=u, **dict(zip(S, s)))
            for i, (u, s) in enumerate(zip(units, shares))]
    return pd.DataFrame(rows)


KES, VAL, ORI = [1, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0], [0, 0, 0, 1, 0, 0]


def test_each_supplier_gets_the_average_units():
    a = plan([100.0], [KES])
    b = plan([300.0], [[0, 0.5, 0, 0.5, 0, 0]])
    out = blend(a, b, weight=0.5).iloc[0]
    assert out.order_units == 200.0
    per_supplier = out.order_units * out[S].to_numpy(float)
    np.testing.assert_allclose(per_supplier, [50, 75, 0, 75, 0, 0])


def test_one_sided_and_idle_rows_stay_valid():
    a = plan([0.0, 0.0], [KES, KES])
    b = plan([80.0, 0.0], [VAL, ORI])
    out = blend(a, b)
    np.testing.assert_allclose(out[S].sum(axis=1), 1.0)
    np.testing.assert_allclose(out.loc[0, S].to_numpy(float), VAL)  # only b orders
    np.testing.assert_allclose(out.loc[1, S].to_numpy(float), [0.5, 0, 0, 0.5, 0, 0])


def test_mismatched_rows_are_rejected():
    with pytest.raises(ValueError, match="different"):
        blend(plan([1.0], [KES]), plan([1.0, 2.0], [KES, KES]))
