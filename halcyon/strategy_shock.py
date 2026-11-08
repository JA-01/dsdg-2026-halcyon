"""Broad-shock duration insurance (experiment #151; never a live default).

Replay completed supplier/country/lane outages at the incumbent event rate,
with half the probability on their observed duration and half on a duration
that is twice as long. Onset uncertainty is unchanged. This is insurance
against persistent closures and delayed recovery, not a fitted outcome claim.
Only observations available at the planning cutoff enter the event library.
Forecasts and the nominal sourcing/basis-ban model remain the incumbent's;
only physical-path uncertainty changes. The saved v1 models are untouched.

Measured on the 11 historical selection origins: mean 49.484595, worst
23.892465; best-of-two with the champion 53.981993 versus saved v1 53.993500.
The fixed private scenario matrix also falls below the saved pair (74.124218
versus 74.406458). Retained only as the requested isolated experiment, not a
recommended replacement. Full precision, regressions and caveats are on #151.
"""

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from halcyon import disruption_news, policy, policy_scenarios as scenarios, price
from halcyon.data import MATERIALS, as_of


def duration_library(data, cutoff):
    """Observed/long-duration mixture; doubling exposure preserves event mass."""
    library, observed = scenarios.events(data, cutoff)
    longer = [dict(start=event["start"], hits={
        key: (np.repeat(ratios, 2), np.repeat(extras, 2))
        for key, (ratios, extras) in event["hits"].items()
    }) for event in library]
    return library + longer, 2 * observed


def plan(data, cutoff, weeks, forecasts):
    """One executable request plan across nominal and duration-mixture paths."""
    data = as_of(data, cutoff)
    weeks = list(weeks)
    params = scenarios.Params()
    bp = params.base
    library, observed = duration_library(data, cutoff)
    demand = data["demand"].set_index(["week", "material"]).demand_units
    probs = forecasts.set_index(["week", "material"]).disruption_prob
    sellers = data["suppliers"].groupby("country").material.apply(list)
    bans = policy._basis_bans(data, cutoff, bp)
    cost_weight = 40 / policy._f_denominator(data, cutoff)

    def solve(material):
        nominal = scenarios.nominal(data, cutoff, weeks, material, bp, bans,
                                    probs, demand, bp.base_buffer)
        paths = scenarios._scenarios(
            library, observed, material, nominal["countries"], nominal["normal"],
            nominal["base_lead"], nominal["cap0"], nominal["lead"], weeks, params, sellers)
        requests = scenarios._solve(
            nominal["demand"], nominal["opening"], nominal["cap0"],
            [(weight, cap, lead) for _, weight, cap, lead in paths],
            nominal["landed_t"], nominal["landed"].mean(), nominal["buffer"],
            bp.buffer_penalty, bp.diversity)
        requests = policy._rebalance(
            requests, nominal["cap0"], nominal["lead"], nominal["landed_t"],
            nominal["landed"].mean(), cost_weight, bp.merge_back)
        return scenarios.rows_from(requests, nominal["countries"], weeks, material)

    with ThreadPoolExecutor(max_workers=len(MATERIALS)) as pool:
        rows = [row for material_rows in pool.map(solve, MATERIALS) for row in material_rows]
    return pd.DataFrame(rows)


MODELS = (disruption_news.predict, price.predict, plan)
