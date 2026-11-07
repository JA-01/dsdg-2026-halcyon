"""Experimental joint event-state forecasts; all fitting targets end at cutoff.

Stories retain geography and supplier membership: a lane recovery cannot close
a country sanction, and a material cancellation closes only its intersection.
Joint material states count simultaneous stories without independent noisy-OR.

Experimental challenger only; no live-primary wiring. Selection local estimate
at cutoffs65..195: mean52.209609 versus51.674722, worst34.452428 unchanged;
5 improved/2 regressed origins, largest loss0.984929. Gains concentrate at195
(+6.719207); mean raw Brier .162239590 -> .161199488. Synthetic private S0..S5
score deltas [0, -.869045, -.721136, -.644959, -.085063, +.223259], unchanged
planning/fill. These are local estimates and scenarios, not official scores.
Removing closure transitions with the same learner gives mean52.170447 and
raw Brier .172774263: transitions improve raw accuracy, but explain only
0.039162 mean score. Omitting origin195 gives mean delta -0.083545 versus
the incumbent (concentration diagnostic, not independent validation).
"""

import re

import numpy as np

from . import disruption_news as incumbent
from .data import MATERIALS
from .events import _COUNTRIES, _LANES, _pattern


def _anchor(headline):
    for kind, names in (("lane", _LANES), ("country", _COUNTRIES)):
        lookup = {k.lower(): v for k, v in names.items()}
        found = {lookup[s.lower()] for s in _pattern(lookup).findall(headline)}
        if len(found) > 1:
            found.discard("AUR")
        if found:
            return kind, tuple(sorted(found))
    return "unknown", ()


def state_history(data, cutoff):
    """Joint signatures, with each supplier/story counted once regardless of sources.

    Codes 1/2/3/4/5 are early/imminent/active/averted/recovery. Story ages
    start at the first warning and survive syndication and stage escalation.
    Closed states last four weeks; live stories expire 13 weeks after updates.
    Ongoing reports update matching stories, preserving event family identity.
    """
    reports = []
    for article, _, family, stage, scope in incumbent._scoped_reports(data, cutoff):
        reports.append((int(article.week), _anchor(article.headline), family, stage, scope))
    suppliers = data['suppliers']
    for article in data['news'].loc[lambda f: f.week <= cutoff].itertuples(index=False):
        match = re.fullmatch(r'Tensions ease after talks with (.+)', article.headline)
        if match:
            scope = tuple(suppliers.loc[suppliers.country_name == match[1],
                                        ['material', 'country']].itertuples(index=False, name=None))
            for family in ('clash', 'sanctions'):
                reports.append((int(article.week), _anchor(article.headline), family, 'averted', scope))
    reports.sort(key=lambda x: (x[0], {'early': 0, 'imminent': 1, 'active': 2,
                                    'averted': 3, 'recovery': 4}[x[3]]))
    by_week = {}
    for report in reports:
        by_week.setdefault(report[0], []).append(report)
    stories, history = {}, []
    code = {'early': 1, 'imminent': 2, 'active': 3, 'averted': 4, 'recovery': 5}
    for week in range(1, cutoff + 1):
        for _, anchor, family, stage, scope in by_week.get(week, []):
            for supplier in set(scope):
                key = (anchor, family, supplier)
                matching = [k for k, v in stories.items()
                            if k[0] == anchor and k[2] == supplier
                            and (family == 'ongoing' or k[1] == family)
                            and week - v[2] <= 13]
                if family == 'ongoing' and stage == 'active':
                    matching = [k for k in matching if stories[k][0] == 3]
                targets = matching if stage in ('averted', 'recovery') or family == 'ongoing' else [key]
                if not targets:
                    targets = [key]
                for target in targets:
                    old = stories.get(target)
                    same_story = (old is not None and week - old[2] <= 13
                                  and (old[0] < 4 or old[0] == code[stage]))
                    first = old[1] if same_story else week
                    next_stage = code[stage]
                    if same_story and stage in ('early', 'imminent'):
                        next_stage = max(old[0], next_stage)
                    stories[target] = (next_stage, first, week)
        row = []
        for material in MATERIALS:
            signature = set()
            for (anchor, family, (m, _)), (stage, first, last) in stories.items():
                if m != material or week - last > (4 if stage >= 4 else 13):
                    continue
                age = int(np.digitize(week - first, (3, 8)))
                # Repeated country/lane supplier rows for a material are one story.
                signature.add((family, stage, age, anchor))
            # Keep geography type, but no country identity in learned cells.
            # Multiplicity is deliberate: distinct geographic stories can share
            # family/stage/age; one story's repeated articles cannot add entries.
            detailed = tuple(sorted((f, s, a, k[0]) for f, s, a, k in signature))
            broad = tuple(sorted(set((s, a) for _, s, a, _ in detailed)))
            row.append((detailed, broad))
        history.append(row)
    return history


def predict(data, cutoff, weeks):
    """Shrink joint event-state occupancy to the incumbent with four pseudo-weeks.

    Training rows have observed future labels. Pooled evidence weights sum to
    one per origin so broad lane exposures do not create ten independent hits.
    The detailed family signature shrinks to the joint stage/age signature;
    missing matches retain incumbent risk. Existing market/tariff floors survive.
    """
    weeks = list(weeks)
    if any(w <= cutoff or not isinstance(w, (int, np.integer)) for w in weeks):
        raise ValueError('target weeks must be integers after cutoff')
    result = incumbent.predict(data, cutoff, weeks)
    states = state_history(data, cutoff)
    labels = data['outcomes'].loc[lambda f: f.week <= cutoff].pivot(
        index='week', columns='material', values='disrupted').reindex(
            index=range(1, cutoff + 1), columns=MATERIALS).to_numpy(float)
    for index, row in result.iterrows():
        h = int(row.week) - cutoff
        j = MATERIALS.index(row.material)
        detailed, broad = states[-1][j]
        if not detailed or not 1 <= h < cutoff:
            continue
        sums = np.zeros(4)
        for t in range(cutoff - h):
            broad_matches, exact_matches = [], []
            for k in range(len(MATERIALS)):
                if labels[t, k] != labels[-1, j] or not np.isfinite(labels[t + h, k]):
                    continue
                d, b = states[t][k]
                if b == broad:
                    broad_matches.append(labels[t + h, k])
                    if d == detailed:
                        exact_matches.append(labels[t + h, k])
            if broad_matches:
                sums[0] += np.mean(broad_matches)
                sums[1] += 1
            if exact_matches:
                sums[2] += np.mean(exact_matches)
                sums[3] += 1
        pooled = (sums[0] + 4 * row.disruption_prob) / (sums[1] + 4)
        probability = (sums[2] + 2 * pooled) / (sums[3] + 2)
        result.loc[index, 'disruption_prob'] = probability
    result = incumbent.market_probabilities(data, cutoff, result)
    return incumbent.tariff_probabilities(data, cutoff, result)
