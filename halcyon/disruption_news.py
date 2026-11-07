"""Warning-ladder challenger with horizon-specific historical hit/decoy rates.

The shared event parser resolves supplier scopes; this module independently
learns future disrupted occupancy from clean-state warning/horizon pairs.
Family/stage/age estimates shrink toward pooled stage/age rates, then toward
the material base rate. Reports without a subsequent hit count as negatives.
Repeated material exposures count once per origin/family, though consecutive
weeks of the same episode remain correlated. These are not independent trials.

Exploratory selection: origins65..195, mean clipped Brier .31418 -> .32083.
Only origin156 supplies the original ladder's clipped gain; warning coverage
is sparse at the fixed origins. AV owns primary wiring.

AV authorized structured tariff schedules in the primary at a 0.6 cap on the
board (Nov7,18:48Z), despite insufficient leave-one-event-out evidence: the
selection gain relies on one mature prior event. This is an explicit judgment
call about dated structured announcements, not demonstrated robustness to
organizer reversals. No announcement raises risk before its effective week.
"""

import re

import numpy as np
import pandas as pd

from . import disruption
from .data import MATERIALS
from .events import _reports

FAMILIES = ('tariff', 'export', 'clash', 'strike', 'shortage', 'sanctions')


def _signals(data, cutoff, expiry=13):
    """Weekly family/stage/age cells; cancellations close matching supplier scopes."""
    reports = [(int(a.week), family, stage, scope)
               for a, _, family, stage, scope in _reports(data, cutoff)]
    # This cancellation template is absent from the shared event table.
    suppliers = data['suppliers']
    for row in data['news'].loc[lambda f: f.week <= cutoff].itertuples(index=False):
        match = re.fullmatch(r'Tensions ease after talks with (.+)', row.headline)
        if match:
            scope = tuple(suppliers.loc[suppliers.country_name == match[1],
                                        ['material', 'country']].itertuples(index=False, name=None))
            reports.append((int(row.week), 'clash', 'averted', scope))
            reports.append((int(row.week), 'sanctions', 'averted', scope))
    reports.sort(key=lambda r: r[0])
    by_week = {}
    for report in reports:
        by_week.setdefault(report[0], []).append(report)
    # 0 = no active warning; 1..6 = early/recent, early/older, imminent etc.
    cells = np.zeros((cutoff, len(MATERIALS), len(FAMILIES)), dtype=int)
    active = {}
    for week in range(1, cutoff + 1):
        for _, family, stage, scope in by_week.get(week, []):
            if stage in ('active', 'averted', 'recovery'):
                for key in list(active):
                    if (family in ('ongoing', key[0]) and set(key[1]).issubset(scope)):
                        del active[key]
            elif stage in ('early', 'imminent') and family in FAMILIES:
                key = (family, scope)
                previous = active.get(key)
                # New early reports do not downgrade a still-live imminent warning.
                if previous and previous[0] == 'imminent' and week - previous[1] <= expiry:
                    stage = 'imminent'
                active[key] = (stage, week)
        for (family, scope), (stage, observed) in active.items():
            age = week - observed
            if age > expiry:
                continue
            cell = 1 + int(age > 2) + int(age > 6) + 3 * int(stage == 'imminent')
            f = FAMILIES.index(family)
            for material in {m for m, _ in scope}:
                j = MATERIALS.index(material)
                cells[week - 1, j, f] = max(cells[week - 1, j, f], cell)
    return cells


def predict(data, cutoff, weeks, *, prior=20, weight=1.0, expiry=13):
    """Estimate future disruption from mature warning/horizon pairs.

    Current disruptions retain the primary persistence estimate. Clean states
    receive a capped warning lift, learned only from targets released by cutoff.
    No warnings, missing historical pairs or distant horizons retain the primary.
    """
    weeks = list(weeks)
    base = disruption.predict(data, cutoff, weeks)
    history = data['outcomes'].loc[lambda f: f.week <= cutoff]
    labels = history.pivot(index='week', columns='material', values='disrupted').reindex(
        index=range(1, cutoff + 1), columns=MATERIALS).to_numpy(float)
    signals = _signals(data, cutoff, expiry)
    latest = labels[-1]
    reference = np.nanmean(labels, axis=0)
    rows = []
    indexed = base.set_index(['week', 'material']).disruption_prob
    for week in weeks:
        h = week - cutoff
        for j, material in enumerate(MATERIALS):
            probability = float(indexed.loc[(week, material)])
            if latest[j] == 0 and 1 <= h < cutoff:
                estimates = []
                for f, cell in enumerate(signals[-1, j]):
                    if cell == 0:
                        continue
                    past = signals[:-h, :, f]
                    # Exclude warnings observed while already disrupted.
                    use = (past == cell) & (labels[:-h] == 0) & np.isfinite(labels[h:])
                    targets = labels[h:][use]
                    pooled_use = ((signals[:-h] == cell) & (labels[:-h, :, None] == 0)
                                  & np.isfinite(labels[h:, :, None]))
                    pooled_targets = np.broadcast_to(labels[h:, :, None], signals[:-h].shape)[pooled_use]
                    # Supplier-lane warnings can repeat across all ten materials.
                    # Count each origin/family once, rather than multiplying evidence.
                    pooled_weights = np.broadcast_to(
                        1 / np.maximum(pooled_use.sum(axis=1, keepdims=True), 1),
                        pooled_use.shape)[pooled_use]
                    family_weights = np.broadcast_to(
                        1 / np.maximum(use.sum(axis=1, keepdims=True), 1), use.shape)[use]
                    pooled = (pooled_targets @ pooled_weights + 2 * reference[j]) / (pooled_weights.sum() + 2)
                    risk = (targets @ family_weights + prior * pooled) / (family_weights.sum() + prior)
                    estimates.append(min(.7, risk))
                if estimates:
                    probability += weight * max(0, max(estimates) - probability)
            rows.append((week, material, float(probability)))
    frame = pd.DataFrame(rows, columns=['week', 'material', 'disruption_prob'])
    return tariff_probabilities(data, cutoff, frame)


def tariff_probabilities(data, cutoff, frame, *, exclude_events=()):
    """Capped tariff-schedule evidence, deduplicated by country/effective week.

    A historical success requires both the announced duty to be in force and
    the material to be disrupted. Reversals and clear-state targets are negative
    examples. Each correlated multi-material announcement counts as one event.
    Only matured event/offset pairs contribute; no evidence leaves the base.
    ``exclude_events`` supports leave-one-event-out diagnostics.
    """
    tariffs = data['tariffs'].loc[lambda f: f.week <= cutoff]
    announcements = tariffs.loc[(tariffs.announced_rate > tariffs.tariff_rate)
                               & (tariffs.announced_effective_week > tariffs.week)].copy()
    if announcements.empty:
        return frame
    labels = data['outcomes'].loc[lambda f: f.week <= cutoff].set_index(['week', 'material']).disrupted
    rates = tariffs.set_index(['week', 'material', 'country']).tariff_rate
    episodes = []
    for (country, effective), group in announcements.groupby(['country', 'announced_effective_week']):
        event = (country, int(effective))
        if event in exclude_events:
            continue
        announced = group.sort_values('week').groupby('material').last()
        episodes.append((event, announced))
    current = tariffs.loc[(tariffs.week == cutoff) & (tariffs.announced_rate > tariffs.tariff_rate)
                          & (tariffs.announced_effective_week > cutoff)]
    result = frame.copy()
    for schedule in current.itertuples(index=False):
        for week in result.week.unique():
            offset = week - int(schedule.announced_effective_week)
            if not 0 <= offset < 13:
                continue
            evidence = []
            for (country, effective), announced in episodes:
                target = effective + offset
                if target > cutoff:
                    continue
                hits = []
                for material, row in announced.iterrows():
                    label = labels.get((target, material), np.nan)
                    actual_rate = rates.get((target, material, country), np.nan)
                    if np.isfinite(label) and np.isfinite(actual_rate):
                        hits.append(float(label == 1 and actual_rate >= row.announced_rate - 1e-6))
                if hits:
                    evidence.append(float(np.mean(hits)))
            if evidence:
                probability = min(.6, (sum(evidence) + 1) / (len(evidence) + 2))
                mask = (result.week == week) & (result.material == schedule.material)
                result.loc[mask, 'disruption_prob'] = np.maximum(
                    result.loc[mask, 'disruption_prob'], probability)
    return result
