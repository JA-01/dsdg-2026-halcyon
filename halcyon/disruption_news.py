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

Structured tariff schedules are an explicit judgment call (AV, board), capped
at TARIFF_CAP. The label rule is exact (disrupted = 1 whenever a supplier's
tariff exceeds its base, 2210/2210 rows, issue #114) and every announced hike
so far took effect, so the cap was raised from 0.6 to 0.85. The selection gain
still rests on few mature events; reversal risk is the reason for any cap.
No announcement raises risk before its effective week.

Futures-basis flags (market_probabilities) add a learned hazard for clean
materials whose supplier basis is elevated at the cutoff.
"""

import re

import numpy as np
import pandas as pd

from . import disruption
from .data import MATERIALS
from .events import _reports, _COUNTRIES, _LANES, _pattern

FAMILIES = ('tariff', 'export', 'clash', 'strike', 'shortage', 'sanctions')
TARIFF_CAP = .85



def _scoped_reports(data, cutoff):
    """Headline geography sets scope; body material references can narrow it.

    A country headline is not expanded to a lane merely because the body
    mentions its geography. A lane headline covers the lane's suppliers.
    """
    suppliers = data['suppliers']
    countries = {k.lower(): v for k, v in _COUNTRIES.items()}
    lanes = {k.lower(): v for k, v in _LANES.items()}
    materials = {m.replace('_', ' '): m for m in MATERIALS}
    materials.update({'rare earth': 'rare_earths', 'semiconductor': 'semiconductors'})
    country_pattern, lane_pattern, material_pattern = map(_pattern, (countries, lanes, materials))

    def scoped(article, fallback=()):
        headline = article.headline
        named_countries = {countries[m.lower()] for m in country_pattern.findall(headline)}
        if len(named_countries) > 1:
            named_countries.discard('AUR')
        named_lanes = {lanes[m.lower()] for m in lane_pattern.findall(headline)}
        named_materials = {materials[m.lower()] for m in material_pattern.findall(
            headline + '. ' + str(article.body))}
        if named_lanes:
            selected = suppliers.lane.isin(named_lanes)
        elif named_countries:
            selected = suppliers.country.isin(named_countries)
        else:
            return fallback
        if named_materials:
            selected &= suppliers.material.isin(named_materials)
        return tuple(sorted(suppliers.loc[selected, ['material', 'country']].itertuples(
            index=False, name=None)))

    for article, template, family, stage, scope in _reports(data, cutoff):
        scope = scoped(article, scope)
        if scope:
            yield article, template, family, stage, scope
    # Previously unseen wording gets the ordinary tariff/early prior only.
    for article in data['news'].loc[lambda f: f.week <= cutoff].itertuples(index=False):
        if re.fullmatch(r'Trade talks between .+ and .+ stall', article.headline):
            scope = scoped(article)
            if scope:
                yield article, 'Trade talks between {} and {} stall', 'tariff', 'early', scope

def _signals(data, cutoff, expiry=4, supplier_keys=None):
    """Weekly family/stage/age cells; cancellations close matching supplier scopes."""
    reports = [(int(a.week), family, stage, scope)
               for a, _, family, stage, scope in _scoped_reports(data, cutoff)]
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
    keys = MATERIALS if supplier_keys is None else tuple(supplier_keys)
    positions = {key: j for j, key in enumerate(keys)}
    cells = np.zeros((cutoff, len(keys), len(FAMILIES)), dtype=int)
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
            targets = {m for m, _ in scope} if supplier_keys is None else set(scope)
            for target in targets:
                j = positions[target]
                cells[week - 1, j, f] = max(cells[week - 1, j, f], cell)
    return cells



def _warning_risk(labels, signals, reference, j, h, prior, cap=.7):
    """Shared matured warning-pair estimate for material or supplier labels."""
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
        estimates.append(min(cap, risk))
    return max(estimates, default=0.0)


def predict(data, cutoff, weeks, *, prior=2, cap=.85, weight=1.0, expiry=4):
    """Estimate future disruption from mature warning/horizon pairs.

    Unconfirmed warnings expire after four weeks without a fresh report.
    Current disruptions retain the primary persistence estimate. Clean states
    receive a capped warning lift, learned only from targets released by cutoff.
    No warnings, missing historical pairs or distant horizons retain the primary.
    Family-specific rates shrink toward the pooled rate with ``prior`` pseudo
    pairs (2; was 20) and are capped at ``cap`` (0.85; was 0.7): origins 65..195
    +0.09 with no regressions (AV HonestP exploration, Nov 7). This lets
    decoy-heavy families (lane tension) fall and reliable ones rise.
    """
    weeks = list(weeks)
    base = disruption.predict(data, cutoff, weeks)
    history = data['outcomes'].loc[lambda f: f.week <= cutoff]
    labels = history.pivot(index='week', columns='material', values='disrupted').reindex(
        index=range(1, cutoff + 1), columns=MATERIALS).to_numpy(float)
    signals = _signals(data, cutoff, expiry)
    latest = labels[-1]
    reference = np.nanmean(labels, axis=0)
    # A published schedule fixes the tariff start (labels begin exactly at the
    # effective week, issue #114), so the tariff-family ladder must not raise
    # risk before it; tariff_probabilities covers the weeks from it on.
    tariffs = data['tariffs'].loc[lambda f: f.week == cutoff]
    scheduled = tariffs.loc[(tariffs.announced_rate > tariffs.tariff_rate)
                            & (tariffs.announced_effective_week > cutoff)].groupby(
        'material').announced_effective_week.min()
    unscheduled = signals.copy()
    unscheduled[-1, :, FAMILIES.index('tariff')] = 0
    rows = []
    indexed = base.set_index(['week', 'material']).disruption_prob
    for week in weeks:
        h = week - cutoff
        for j, material in enumerate(MATERIALS):
            probability = float(indexed.loc[(week, material)])
            if latest[j] == 0 and 1 <= h < cutoff:
                cells = unscheduled if week < scheduled.get(material, -1) else signals
                risk = _warning_risk(labels, cells, reference, j, h, prior, cap)
                probability += weight * max(0, risk - probability)
            rows.append((week, material, float(probability)))
    frame = pd.DataFrame(rows, columns=['week', 'material', 'disruption_prob'])
    frame = _abrupt_persistence(data, cutoff, frame)
    frame = market_probabilities(data, cutoff, frame)
    return tariff_probabilities(data, cutoff, frame)


# Market precursor (exploration, issue #114): a supplier's futures basis
# (futures_4w / spot - 1) rises 2-4 weeks before that supplier is physically
# hit (6/6 on weeks <= 208, 0 false alarms). Thresholds from that discovery.
# Country tension (> 40) and lane congestion (>= 50) were tested the same way
# on origins 65..195: tension lowered the mean (49.65 vs 50.12), congestion
# never fired; neither is used.
BASIS_HIGH, BASIS_TWO_WEEK = .05, .035


def basis_flags(data, cutoff):
    """(weeks 1..cutoff) x materials bool: any supplier's basis is elevated."""
    prices = data['prices'].loc[lambda f: f.week <= cutoff]
    basis = (prices.futures_4w / prices.spot_price - 1).groupby(
        [prices.week, prices.material, prices.country]).first().unstack(['material', 'country'])
    basis = basis.reindex(pd.RangeIndex(1, cutoff + 1))
    flags = np.zeros((cutoff, len(MATERIALS)), bool)
    for (material, _), series in basis.items():
        b = series.to_numpy(float)
        two = np.r_[False, (b[1:] > BASIS_TWO_WEEK) & (b[:-1] > BASIS_TWO_WEEK)]
        flags[:, MATERIALS.index(material)] |= (b > BASIS_HIGH) | two
    return flags


def market_probabilities(data, cutoff, frame, *, prior=4):
    """Raise clean materials with an elevated basis at the cutoff to the learned hazard.

    For each horizon h, the hazard is the share of past clean, flagged weeks t
    (t + h <= cutoff) whose material was disrupted at t + h, pooled across
    materials (flags are rare) and shrunk toward the mean base rate with
    ``prior`` pseudo-weeks. Probabilities only rise; materials disrupted at the
    cutoff are untouched.
    """
    labels = data['outcomes'].loc[lambda f: f.week <= cutoff].pivot(
        index='week', columns='material', values='disrupted').reindex(
        index=range(1, cutoff + 1), columns=MATERIALS).to_numpy(float)
    flag = basis_flags(data, cutoff)
    clean = labels == 0
    active = flag[-1] & clean[-1]
    if not active.any():
        return frame
    base = float(np.nanmean(labels))
    result = frame.copy()
    for week in result.week.unique():
        h = int(week) - cutoff
        if not 1 <= h < cutoff:
            continue
        use = flag[:-h] & clean[:-h]
        hazard = (np.where(use, labels[h:], 0).sum() + prior * base) / (use.sum() + prior)
        mask = (result.week == week) & result.material.isin([MATERIALS[j] for j in np.flatnonzero(active)])
        result.loc[mask, 'disruption_prob'] = np.maximum(result.loc[mask, 'disruption_prob'], hazard)
    return result



def _abrupt_persistence(data, cutoff, frame):
    """Short-recovery evidence for known abrupt export suspensions.

    Mature matching episodes can reduce, but never raise, generic persistence.
    Two prior episode-equivalents retain the generic forecast. Evidence is
    sparse: the first selected improvement has only one historical episode;
    overlapping shocks can confound these material-level survival labels.
    """
    labels = data['outcomes'].loc[lambda f: f.week <= cutoff].set_index(['week', 'material']).disrupted
    episodes = {}
    for article, template, _, _, scope in _scoped_reports(data, cutoff):
        if 'abruptly suspends' not in template:
            continue
        if scope not in episodes or article.week - episodes[scope][-1] > 13:
            episodes.setdefault(scope, []).append(int(article.week))
    events = [(week, scope) for scope, starts in episodes.items() for week in starts]
    if not events:
        return frame
    result = frame.copy()
    for material in result.material.unique():
        current = [week for week, scope in events if material in {m for m, _ in scope}
                   and 0 <= cutoff - week < 13 and labels.get((cutoff, material), 0) == 1]
        if not current:
            continue
        age = cutoff - max(current)
        for week in result.week.unique():
            h = week - cutoff
            if not 1 <= h <= 13:
                continue
            evidence = []
            for start, scope in events:
                if start + age + h > cutoff:
                    continue
                hits = [labels.get((start + age + h, m), np.nan) for m, _ in scope
                        if labels.get((start + age, m), 0) == 1]
                hits = [value for value in hits if np.isfinite(value)]
                if hits:
                    evidence.append(float(np.mean(hits)))
            if evidence:
                mask = (result.week == week) & (result.material == material)
                base = result.loc[mask, 'disruption_prob']
                risk = (sum(evidence) + 2 * base) / (len(evidence) + 2)
                result.loc[mask, 'disruption_prob'] = np.minimum(base, risk)
    return result

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
                probability = min(TARIFF_CAP, (sum(evidence) + 1) / (len(evidence) + 2))
                mask = (result.week == week) & (result.material == schedule.material)
                result.loc[mask, 'disruption_prob'] = np.maximum(
                    result.loc[mask, 'disruption_prob'], probability)
    return result


def supplier_risk(data, cutoff, weeks):
    """Physical supplier-hit risk: capacity <90% normal or lead above base.

    Returns week/material/country/risk for eligible suppliers only. This is
    separate from any-shock labels: a tariff can raise costs without reducing
    capacity, so a tariff announcement alone does not force a physical haircut.
    Country/state/run-age pairs supply persistence; scoped warning ladders lift
    clean suppliers. Every fit target and feature is observed by cutoff.
    """
    weeks = list(weeks)
    if any(not isinstance(w, (int, np.integer)) or w <= cutoff for w in weeks):
        raise ValueError('target weeks must be integers after cutoff')
    suppliers = data['suppliers']
    keys = [(m, c) for m in MATERIALS
            for c in sorted(suppliers.loc[suppliers.material == m, 'country'])]
    supply = data['supply_history'].loc[lambda f: f.week <= cutoff].merge(
        suppliers[['material', 'country', 'normal_capacity_units', 'base_lead_weeks']],
        on=['material', 'country'], validate='many_to_one')
    supply['hit'] = ((supply.capacity_units < .9 * supply.normal_capacity_units)
                     | (supply.lead_time_weeks > supply.base_lead_weeks)).astype(float)
    history = supply.pivot(index='week', columns=['material', 'country'], values='hit').reindex(
        index=range(1, cutoff + 1), columns=pd.MultiIndex.from_tuples(keys))
    labels = history.to_numpy(float)
    if not len(labels) or not np.isfinite(labels).all():
        raise ValueError('missing supplier history through cutoff')
    age = np.ones(labels.shape, dtype=int)
    for t in range(1, len(labels)):
        age[t] = np.where(labels[t] == labels[t - 1], age[t - 1] + 1, 1)
    ages = np.digitize(age, (2, 5, 10, 20))
    signals = _signals(data, cutoff, supplier_keys=keys)
    reference = labels.mean(axis=0)
    countries = np.array([c for m, c in keys])
    transitions = {}
    for country in np.unique(countries):
        values = labels[:, countries == country]
        rates = []
        for state in (0, 1):
            use = values[:-1] == state
            weights = np.broadcast_to(
                1 / np.maximum(use.sum(axis=1, keepdims=True), 1), use.shape)[use]
            targets = values[1:][use]
            rates.append(float((targets @ weights + .5) / (weights.sum() + 1)))
        transitions[country] = rates
    rows = []
    for week in weeks:
        h = week - cutoff
        for j, (material, country) in enumerate(keys):
            same_country = countries == country
            rate = float(labels[:, same_country].mean())
            probability = rate
            if 0 < rate < 1:
                probability = float(labels[-1, j])
                enter, stay = transitions[country]
                for _ in range(h):
                    probability = enter + (stay - enter) * probability
            if h < cutoff:
                use = ((labels[:-h, same_country] == labels[-1, j])
                       & (ages[:-h, same_country] == ages[-1, j]))
                weights = np.broadcast_to(
                    1 / np.maximum(use.sum(axis=1, keepdims=True), 1), use.shape)[use]
                targets = labels[h:, same_country][use]
                probability = float((targets @ weights + 20 * probability) / (weights.sum() + 20))
                if labels[-1, j] == 0:
                    risk = _warning_risk(labels, signals, reference, j, h, 20)
                    probability = max(probability, risk)
            rows.append((week, material, country, probability))
    return pd.DataFrame(rows, columns=['week', 'material', 'country', 'risk'])
