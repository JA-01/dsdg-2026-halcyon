"""Slow benchmark reversion plus causal futures-basis capacity-price steps."""

import numpy as np
import pandas as pd

from halcyon.data import MATERIALS


def predict(data, cutoff, weeks):
    """Partially reverse noisy quotes; anticipate temporary capacity-price jumps.

    A supplier basis above 5%, or above 3.5% in two consecutive weeks, signals
    a capacity episode: predict a 1.3*basis premium starting three weeks after
    the first flag, lasting eight weeks. Already-observed benchmark jumps are
    not added twice, including when an older capacity floor masks the onset.
    Observed price recovery cancels the episode. Tariff/disruption probabilities
    do not create a price premium. Every time-varying input is cutoff-filtered.
    """
    weeks = list(weeks)
    history = data["outcomes"].loc[lambda f: f.week <= cutoff].sort_values("week")
    last = history.groupby("material").benchmark_price.last()
    center = history.loc[history.week > cutoff - 104].groupby("material").benchmark_price.mean()
    previous = history.groupby("material").tail(2).groupby("material").benchmark_price.first()
    reversal = (last / previous - 1).clip(-1, 1)
    missing = set(MATERIALS) - set(last.index)
    if missing:
        raise ValueError(f"missing price history for {sorted(missing)}")
    rows = []
    for week in weeks:
        if not isinstance(week, (int, np.integer)) or week <= cutoff:
            raise ValueError("target weeks must be integers after cutoff")
        weight = 1 - 2 ** (-(week - cutoff) / 26)
        correction = 0.25 * (1 - 2 ** (-(week - cutoff) / 4))
        rows.extend((week, m, float(((1 - weight) * last[m] + weight * center[m])
                                   * (1 - correction * reversal[m])))
                    for m in MATERIALS)
    frame = pd.DataFrame(rows, columns=["week", "material", "price_forecast"])
    for material, (_, onset, amplitude, priced) in _basis_steps(data, cutoff, history).items():
        mask = frame.material == material
        query = frame.loc[mask, "week"].to_numpy()
        end = max(cutoff + 1, onset + 8)
        factor = np.where((query >= onset) & (query < end), 1 + amplitude, 1.)
        frame.loc[mask, "price_forecast"] = last[material] * factor / (
            1 + amplitude if priced else 1.)
    return frame


def _basis_steps(data, cutoff, history):
    """Select the strongest recent supplier episode per material, not their sum."""
    if not {"prices", "suppliers", "supply_history"}.issubset(data):
        return {}
    quotes = data["prices"].loc[lambda f: f.week <= cutoff].sort_values(
        ["material", "country", "week"])
    supply = data["supply_history"].loc[lambda f: f.week <= cutoff]
    normal = data["suppliers"].set_index(["material", "country"]).normal_capacity_units
    selected = {}
    for (material, country), group in quotes.groupby(["material", "country"]):
        basis = group.futures_4w / group.spot_price - 1
        flag = (basis > .05) | ((basis > .035) & (basis.shift() > .035)
                                & (group.week.diff() == 1))
        hits = group.loc[flag, ["week"]].assign(basis=basis.loc[flag])
        if hits.empty:
            continue
        physical = supply.loc[(supply.material == material) & (supply.country == country)
                              ].sort_values("week")
        if physical.empty:
            continue
        physical = physical.assign(
            ratio=physical.capacity_units / normal.loc[(material, country)])
        benchmark = history.loc[history.material == material].set_index("week").benchmark_price
        returns = benchmark.pct_change()
        for _, event in hits.groupby((hits.week.diff().fillna(99) > 1).cumsum()):
            first, latest = int(event.week.min()), int(event.week.max())
            if cutoff - first > 16:
                continue
            previous = physical.loc[physical.week < first]
            pre_cap = float(previous.ratio.iloc[-1]) if len(previous) else 1.
            pre_lead = float(previous.lead_time_weeks.iloc[-1]) if len(previous) else float(
                physical.lead_time_weeks.iloc[0])
            changed = physical.loc[(physical.week >= first) & (
                (physical.ratio < .9 * pre_cap) | (physical.lead_time_weeks > pre_lead))]
            onset, recovered, amplitude = None, False, None
            if len(changed):
                onset = int(changed.week.iloc[0])
                # Lane closures and strikes delay supply without the capacity-price step.
                if changed.ratio.iloc[0] >= .7:
                    continue
                recovered = bool((physical.loc[physical.week > onset, "ratio"]
                                  >= .9 * pre_cap).any())
                amplitude = max(0., float(benchmark.loc[onset] / benchmark.loc[onset - 1] - 1)
                                ) if onset in benchmark and onset - 1 in benchmark else None
            before = group.loc[(group.week >= first) & (
                group.week < (onset if onset is not None else cutoff + 1))]
            peak = float((before.futures_4w / before.spot_price - 1).max()
                         ) if len(before) else float(event.basis.max())
            # Price confirmation is necessary when overlapping losses share a capacity floor.
            confirmed = returns.loc[(returns.index >= first) & (returns >= .05)]
            if len(confirmed):
                onset, amplitude = int(confirmed.index[0]), float(confirmed.iloc[0])
                anchor = benchmark.loc[onset] / (1 + amplitude)
                recovered = bool((benchmark.loc[benchmark.index > onset]
                                  <= anchor * (1 + .25 * amplitude)).any())
            if recovered or (onset is None and cutoff - latest > 2):
                continue
            priced = onset is not None
            if not priced:
                onset, amplitude = max(cutoff + 1, first + 3), 1.3 * peak
            elif amplitude is None:
                amplitude = 1.3 * peak
            if material not in selected or peak > selected[material][0]:
                selected[material] = peak, onset, amplitude, priced
    return selected
