"""Kestria-escalation specialist (#150), never a replacement for the champion.

An open KES export warning plus an open KES clash warning activates a declared
specialist scenario bet, not fitted probabilities: 55% MERROW disruption at
0.75x normal capacity/+3 lead, 25% KES-wide sanctions at 0.20x/+3 lead. The
remaining mass keeps the historical scenario planner. Onsets span cutoff+1,+4,+7;
duration is four weeks or the remaining window. These conditional weights are
deliberately more defensive than the unconditional #152 calibration. A country
export debate is NOT parsed as a country-wide export ban.

Material-specific basis bans remain in the nominal path. Only the export-warned
material gets an additional 26% benchmark-price hypothesis; MERROW closures do
not imply a price jump. Prices use the inverse-price-weighted median appropriate
for MAPE, not a mean. Existing higher forecasts survive. Orders use the exact
fill/service MILP with all capacity/lead paths, not average-capacity substitutes.
The solver retains the nominal landed-cost path plus announced tariffs; it does
not model scenario-specific shock-price costs. Nominal-only rebalancing is
disabled on escalated materials because it can undo scenario protection.

Use submit.build(tables, models=MODELS); public cutoff 208 and private cutoff 221
are independent. There is no absolute private date, raw file access or live-default
mutation. Warning expiry, country scope and cancellations reuse the incumbent.
"""

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from halcyon import disruption_news, policy, price
from halcyon import policy_scenarios as ps
from halcyon.data import MATERIALS, as_of

ONSETS = (0, 3, 6)
DURATIONS = (4, 13)
LANE_MASS, WIDE_MASS, EXPORT_MASS, PRICE_JUMP = 0.55, 0.25, 0.85, 0.26


def _escalation(data, cutoff):
    """Return exposed MERROW and specifically export-warned KES materials."""
    keys = list(data["suppliers"][["material", "country"]].itertuples(index=False, name=None))
    signals = disruption_news._signals(data, cutoff, supplier_keys=keys)[-1]
    exports, clashes = set(), set()
    for key, cells in zip(keys, signals):
        material, country = key
        if country != "KES":
            continue
        if cells[disruption_news.FAMILIES.index("export")]:
            exports.add(material)
        if cells[disruption_news.FAMILIES.index("clash")]:
            clashes.add(material)
    if not exports or not clashes:
        return set(), set()
    eligible = set(data["suppliers"].loc[lambda f: f.lane == "MERROW", "material"])
    return eligible, exports


def _occupancy(weeks, cutoff, probability):
    weeks = np.asarray(weeks)
    occupancy = np.zeros(len(weeks))
    for offset in ONSETS:
        for duration in DURATIONS:
            onset = cutoff + 1 + offset
            occupancy += (weeks >= onset) & (weeks < onset + duration)
    return probability * occupancy / (len(ONSETS) * len(DURATIONS))


def predict_disruption(data, cutoff, weeks):
    data, weeks = as_of(data, cutoff), list(weeks)
    frame = disruption_news.predict(data, cutoff, weeks)
    eligible, scoped = _escalation(data, cutoff)
    kes = set(data["suppliers"].loc[lambda f: f.country == "KES", "material"])
    for material in eligible:
        selected = frame.material == material
        mass = max(LANE_MASS + (WIDE_MASS if material in kes else 0.0),
                   EXPORT_MASS if material in scoped else 0.0)
        floor = _occupancy(frame.loc[selected, "week"], cutoff, mass)
        frame.loc[selected, "disruption_prob"] = np.maximum(frame.loc[selected, "disruption_prob"], floor)
    return frame


def predict_price(data, cutoff, weeks):
    data, weeks = as_of(data, cutoff), list(weeks)
    frame = price.predict(data, cutoff, weeks)
    _, scoped = _escalation(data, cutoff)
    anchor = data["prices"].loc[lambda f: f.week == cutoff].groupby("material").spot_price.mean()
    for material in scoped:
        selected = frame.material == material
        occupancy = _occupancy(frame.loc[selected, "week"], cutoff, EXPORT_MASS)
        # MAPE weights the upper level by 1/(1+jump): it wins only above this
        # threshold, not at probability 0.5 as an unweighted median would.
        jump = occupancy > (1 + PRICE_JUMP) / (2 + PRICE_JUMP)
        level = anchor[material] * (1 + PRICE_JUMP * jump)
        frame.loc[selected, "price_forecast"] = np.maximum(frame.loc[selected, "price_forecast"], level)
    return frame


def _paths(x, weeks, cutoff, lane_countries):
    """Explicit lane versus sanctions paths; combine with basis cuts by minimum."""
    base = x["cap0"] / policy.Params().cap_margin
    paths = []
    modes = [(LANE_MASS, lane_countries, 0.75)]
    if "KES" in x["countries"]:
        modes.append((WIDE_MASS, {"KES"}, 0.20))
    for mass, countries, ratio in modes:
        weight = mass / (len(ONSETS) * len(DURATIONS))
        for offset in ONSETS:
            for duration in DURATIONS:
                onset = cutoff + 1 + offset
                span = (np.asarray(weeks) >= onset) & (np.asarray(weeks) < onset + duration)
                cap = base.copy()
                lead = np.tile(x["lead"], (len(weeks), 1)).astype(int)
                for c, country in enumerate(x["countries"]):
                    if country in countries:
                        cap[span, c] = np.minimum(cap[span, c], ratio * x["normal"][c])
                        lead[span, c] = np.maximum(lead[span, c], x["base_lead"][c] + 3)
                paths.append((weight, cap, lead))
    return paths


def plan(data, cutoff, weeks, forecasts):
    data, weeks = as_of(data, cutoff), list(weeks)
    eligible, _ = _escalation(data, cutoff)
    if not eligible:
        return ps.plan(data, cutoff, weeks, forecasts)
    params, bp = ps.Params(), policy.Params()
    library, observed = ps.events(data, cutoff)
    sellers = data["suppliers"].groupby("country").material.apply(list)
    lane_countries = set(data["suppliers"].loc[lambda f: f.lane == "MERROW", "country"])
    demand = data["demand"].set_index(["week", "material"]).demand_units
    probs = forecasts.set_index(["week", "material"]).disruption_prob
    bans = policy._basis_bans(data, cutoff, bp)
    cost_weight = 40 / policy._f_denominator(data, cutoff)

    def solve(material):
        x = ps.nominal(data, cutoff, weeks, material, bp, bans, probs, demand, bp.base_buffer)
        historical = ps._scenarios(library, observed, material, x["countries"], x["normal"], x["base_lead"],
                                   x["cap0"], x["lead"], weeks, params, sellers)
        scenarios = [(weight, cap, lead) for _, weight, cap, lead in historical]
        landed = x["landed_t"].copy()
        if material in eligible:
            paths = _paths(x, weeks, cutoff, lane_countries)
            mass = sum(weight for weight, _, _ in paths)
            scenarios = [(weight * (1 - mass), cap, lead) for weight, cap, lead in scenarios] + paths
        requests = ps._solve(x["demand"], x["opening"], x["cap0"], scenarios, landed, x["landed"].mean(),
                             x["buffer"], bp.buffer_penalty, bp.diversity)
        if material not in eligible:
            requests = policy._rebalance(requests, x["cap0"], x["lead"], landed, x["landed"].mean(),
                                         cost_weight, bp.merge_back)
        return ps.rows_from(requests, x["countries"], weeks, material)

    with ThreadPoolExecutor(max_workers=len(MATERIALS)) as pool:
        rows = list(pool.map(solve, MATERIALS))
    return pd.DataFrame([row for material_rows in rows for row in material_rows])


MODELS = (predict_disruption, predict_price, plan)
