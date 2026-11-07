"""Blend of the two ordering policies (#76 primary, #85 challenger).

The two policies win on different backtest origins, so their average beats both
(local estimate, 11 origins: 46.72 mean / 34.25 worst vs 45.44 / 31.84 and
45.92 / 26.67). Orders are averaged; shares are the unit-weighted mix of each
policy's split, so the blended plan sends each supplier exactly the average of
what the two plans send it. Rows where neither policy orders get the even mix
of their shares.
"""

import numpy as np

from halcyon import policy, policy_challenger
from halcyon.data import SHARE_COLUMNS

KEY = ["week", "material"]
WEIGHT = 0.5  # on the primary policy; 0.3-0.7 is flat within 0.4 points


def blend(a, b, weight=WEIGHT):
    """Average two plan frames (same keys) into one valid plan."""
    a, b = a.set_index(KEY).sort_index(), b.set_index(KEY).sort_index()
    if not a.index.equals(b.index):
        raise ValueError("policies planned different (week, material) rows")
    shares = list(SHARE_COLUMNS)
    units_a = weight * a.order_units.to_numpy()
    units_b = (1 - weight) * b.order_units.to_numpy()
    total = units_a + units_b
    mixed = units_a[:, None] * a[shares].to_numpy() + units_b[:, None] * b[shares].to_numpy()
    idle = total <= 0
    mixed[~idle] /= total[~idle, None]
    mixed[idle] = 0.5 * (a[shares].to_numpy()[idle] + b[shares].to_numpy()[idle])
    out = a[[]].copy()
    out["order_units"] = total
    out[shares] = mixed
    return out.reset_index()


def plan(data, cutoff, weeks, forecasts):
    return blend(policy.plan(data, cutoff, weeks, forecasts),
                 policy_challenger.plan(data, cutoff, weeks, forecasts))
