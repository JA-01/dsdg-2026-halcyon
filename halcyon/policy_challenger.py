"""Capacity-aware, just-in-time greedy purchasing; independent of the LP policy."""

import numpy as np
import pandas as pd

from halcyon.data import MATERIALS, SHARE_COLUMNS


def plan(data, cutoff, weeks, forecasts, *, buffer=1, diversity=.1, early_cost=.04):
    """Allocate demand to cutoff-estimated supplier slots, cheapest slots first.

    Opening inventory covers five first-week demands. An anticipation buffer
    brings replenishment forward; it adds no terminal stock. Increasing marginal
    sourcing costs favor supplier diversity without forcing expensive equal buys.
    """
    weeks = list(weeks)
    supply = data['supply_history'].loc[lambda f: f.week <= cutoff]
    demand = data['demand'].set_index(['week', 'material']).demand_units
    records = []
    for material in MATERIALS:
        suppliers = data['suppliers'].loc[lambda f: f.material == material].sort_values('country')
        countries = suppliers.country.tolist()
        n, count = len(weeks), len(countries)
        d = np.array([demand.loc[(w, material)] for w in weeks], float)
        recent = supply.loc[(supply.material == material) & (supply.week > cutoff - 4)]
        estimate = recent.groupby('country').agg(capacity=('capacity_units', 'median'),
                                                 lead=('lead_time_weeks', 'median'),
                                                 cost=('landed_cost', 'mean')).reindex(countries)
        if estimate.isna().any().any():
            raise ValueError(f'missing recent supplier history for {material}')
        capacities = estimate.capacity.to_numpy()
        leads = np.ceil(estimate.lead.to_numpy()).astype(int)
        costs = estimate.cost.to_numpy()
        ref = costs.mean()
        # Discretized convex sourcing cost: later chunks from a supplier cost
        # more, making a second supplier attractive before concentrating orders.
        offers = []
        for t in range(n):
            for c in range(count):
                arrival = t + leads[c]
                if arrival >= n:
                    continue
                chunk = max(d.mean() / 12, 1)
                remaining = capacities[c]
                tier = 0
                while remaining > 1e-8:
                    amount = min(chunk, remaining)
                    effective = costs[c] + diversity * ref * tier / 4
                    offers.append([t, c, arrival, amount, effective])
                    remaining -= amount
                    tier += 1
        orders = np.zeros((n, count))
        opening = 5 * d[0]
        for t, needed in enumerate(d):
            used = min(opening, needed)
            opening -= used
            needed -= used
            deadline = max(0, t - buffer)
            choices = sorted((o for o in offers if o[2] <= deadline and o[3] > 1e-8),
                             key=lambda o: o[4] + early_cost * ref * (t - o[2]))
            for offer in choices:
                if needed <= 1e-8:
                    break
                quantity = min(needed, offer[3])
                orders[offer[0], offer[1]] += quantity
                offer[3] -= quantity
                needed -= quantity
            # If a buffer cannot be met, use any supplier that can arrive in
            # time, rather than discarding otherwise feasible demand.
            if needed > 1e-8:
                choices = sorted((o for o in offers if deadline < o[2] <= t and o[3] > 1e-8),
                                 key=lambda o: o[4] + early_cost * ref * (t - o[2]))
                for offer in choices:
                    quantity = min(needed, offer[3])
                    orders[offer[0], offer[1]] += quantity
                    offer[3] -= quantity
                    needed -= quantity
                    if needed <= 1e-8:
                        break
        for t, week in enumerate(weeks):
            quantity = orders[t].sum()
            shares = orders[t] / quantity if quantity > 0 else np.full(count, 1/count)
            row = dict(week=week, material=material, order_units=float(quantity),
                       **dict.fromkeys(SHARE_COLUMNS, 0.0))
            row.update({f'share_{country}': float(share) for country, share in zip(countries, shares)})
            records.append(row)
    return pd.DataFrame(records)
