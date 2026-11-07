import numpy as np
import pandas as pd
import pytest

from halcyon import disruption, price, submit, policy_challenger
from halcyon.data import SHARE_COLUMNS, as_of, read_all


@pytest.fixture(scope='module')
def tables():
    return read_all()


def test_future_supply_cannot_change_policy(tables):
    weeks = list(range(131, 144))
    models = (disruption.predict, price.predict, policy_challenger.plan)
    expected = submit.plan_window(tables, 130, weeks, models)
    poisoned = {k: v.copy() for k, v in tables.items()}
    future = poisoned['supply_history'].week > 130
    poisoned['supply_history'].loc[future, ['capacity_units', 'lead_time_weeks', 'landed_cost']] = 999999
    actual = submit.plan_window(poisoned, 130, weeks, models)
    pd.testing.assert_frame_equal(actual, expected)


def test_orders_fit_estimated_capacity_and_eligible_shares(tables):
    cutoff = 130
    view = as_of(tables, cutoff)
    forecast = pd.DataFrame()  # This policy is independent of forecast-model output.
    result = policy_challenger.plan(view, cutoff, list(range(131, 144)), forecast)
    assert len(result) == 130
    assert np.isfinite(result[['order_units', *SHARE_COLUMNS]]).all().all()
    assert result.order_units.ge(0).all()
    assert np.allclose(result[list(SHARE_COLUMNS)].sum(axis=1), 1)
    capacity = view['supply_history'].loc[lambda f: f.week > cutoff-4].groupby(['material', 'country']).capacity_units.median()
    sellers = view['suppliers'].groupby('material').country.apply(set)
    for row in result.itertuples():
        for column in SHARE_COLUMNS:
            country = column[6:]
            share = getattr(row, column)
            if country not in sellers[row.material]:
                assert share == 0
            else:
                assert row.order_units * share <= capacity[row.material, country] + 1e-6


def test_opening_inventory_and_terminal_taper(tables):
    view = as_of(tables, 65)
    # A stationary world isolates inventory accounting from shocks and prices.
    view['demand'] = view['demand'].assign(demand_units=100)
    view['supply_history'] = view['supply_history'].assign(capacity_units=100, lead_time_weeks=1, landed_cost=10)
    result = policy_challenger.plan(view, 65, list(range(66, 79)), pd.DataFrame())
    assert np.allclose(result.groupby('material').order_units.sum(), 800)
    assert result.loc[result.week >= 77, 'order_units'].eq(0).all()
    assert result.loc[result.order_units == 0, list(SHARE_COLUMNS)].max().max() <= 1/3 + 1e-9
