"""Sanctions-specific FX precursor and active-shock persistence challenger.

The two paths deliberately answer different questions.  An open warning episode
can lift a clean material only from matured occupancy after earlier, FX-confirmed
warning episodes.  Once sanctions are active, matured post-activation occupancy
can floor an already-disrupted material while the sanctioned country's currency
remains near its activation low.  A rebound disables that persistence floor.

Reports are collapsed to country-level events before labels are read, so repeated
sources and the several materials supplied by one country are not extra trials.
Every feature, event, and target is filtered at ``cutoff``.
"""

import numpy as np
import pandas as pd

from . import disruption_news
from .events import _reports

FX_CONFIRMATION = 0.99
FX_ACTIVE_REBOUND = 1.02
MAX_WARNING_AGE = 13
MAX_ACTIVE_AGE = 26
PROBABILITY_CAP = 0.85


def _sanction_reports(data, cutoff):
    """Deduplicated ``(week, stage, scope, countries)`` sanctions reports."""
    reports = set()
    for article, _, family, stage, scope in _reports(data, cutoff):
        if family != "sanctions":
            continue
        scope = tuple(sorted(scope))
        countries = tuple(sorted({country for _, country in scope}))
        reports.add((int(article.week), stage, scope, countries))
    return sorted(reports)


def _country_events(reports, country):
    """Return warning episodes and deduplicated active events for one country."""
    by_week = {}
    for week, stage, scope, countries in reports:
        if country not in countries:
            continue
        country_scope = {(material, supplier) for material, supplier in scope
                         if supplier == country}
        stages = by_week.setdefault(week, {})
        stages.setdefault(stage, set()).update(country_scope)

    warnings, active, current, active_open = [], [], None, False
    for week in sorted(by_week):
        stages = by_week[week]
        warning_scope = stages.get("early", set()) | stages.get("imminent", set())
        if warning_scope:
            active_open = False
            if current is None:
                current = [week, tuple(sorted(warning_scope))]
            else:
                current[1] = tuple(sorted(set(current[1]) | warning_scope))
        if "active" in stages:
            active_scope = tuple(sorted(stages["active"]))
            if current is not None:
                warnings.append((current[0], current[1], week))
                current = None
            if active_open:
                start, scope = active[-1]
                active[-1] = (start, tuple(sorted(set(scope) | set(active_scope))))
            else:
                active.append((week, active_scope))
                active_open = True
        if "averted" in stages or "recovery" in stages:
            if current is not None:
                warnings.append((current[0], current[1], week))
                current = None
            active_open = False
    if current is not None:
        warnings.append((current[0], current[1], None))
    return warnings, active


def _fx_series(data, cutoff, country):
    macro = data["macro"].loc[lambda frame: (frame.week <= cutoff)
                              & (frame.country == country)]
    return macro.sort_values("week").drop_duplicates("week", keep="last").set_index("week").fx_rate


def _warning_fx_confirmed(fx, start, observed):
    """Require a one-percent fall from the last pre-warning observation."""
    before = fx.loc[fx.index < start]
    current = fx.get(observed, np.nan)
    return (not before.empty and np.isfinite(current)
            and current <= FX_CONFIRMATION * float(before.iloc[-1]))


def _event_occupancy(labels, week, scope):
    values = [labels.get((week, material), np.nan) for material, _ in scope]
    if not values or not np.isfinite(values).all():
        return None
    return float(np.mean(values))


def sanction_probabilities(data, cutoff, frame):
    """Apply event-level sanctions onset and persistence evidence to ``frame``.

    Warning evidence is aligned by the current warning's age.  Active evidence
    is aligned by forecast horizon from each activation report.  Targets that
    would end after ``cutoff`` are absent rather than imputed.  The empirical
    event mean is capped because the released chronology has few sanctions
    episodes; it can only raise the incumbent forecast.
    """
    result = frame.copy()
    reports = _sanction_reports(data, cutoff)
    if not reports:
        return result
    labels = data["outcomes"].loc[lambda table: table.week <= cutoff].set_index(
        ["week", "material"]).disrupted
    countries = sorted({country for report in reports for country in report[3]})

    for country in countries:
        warnings, active = _country_events(reports, country)
        fx = _fx_series(data, cutoff, country)
        current_warning = next((event for event in reversed(warnings)
                                if event[2] is None), None)

        # Onset path: only an open, fresh, FX-confirmed warning can affect clean
        # materials, and only earlier FX-confirmed episodes provide evidence.
        if current_warning is not None:
            start, scope, _ = current_warning
            age = cutoff - start
            if (0 <= age <= MAX_WARNING_AGE
                    and _warning_fx_confirmed(fx, start, cutoff)):
                historical = [event for event in warnings
                              if event[0] < start
                              and _warning_fx_confirmed(fx, event[0], event[0])]
                for week in result.week.unique():
                    horizon = int(week) - cutoff
                    if not 1 <= horizon <= 13:
                        continue
                    evidence = []
                    for old_start, old_scope, _ in historical:
                        target = old_start + age + horizon
                        if target <= cutoff:
                            occupancy = _event_occupancy(labels, target, old_scope)
                            if occupancy is not None:
                                evidence.append(occupancy)
                    if evidence:
                        probability = min(PROBABILITY_CAP, float(np.mean(evidence)))
                        materials = []
                        for material, _ in scope:
                            state = labels.get((cutoff, material), np.nan)
                            if np.isfinite(state) and state == 0:
                                materials.append(material)
                        mask = (result.week == week) & result.material.isin(materials)
                        result.loc[mask, "disruption_prob"] = np.maximum(
                            result.loc[mask, "disruption_prob"], probability)

        # Persistence path: the newest activation anchors the live FX state.
        # Earlier and current activation events each contribute one matured
        # country-level outcome, irrespective of articles or material count.
        if not active:
            continue
        anchor, scope = active[-1]
        anchor_fx, current_fx = fx.get(anchor, np.nan), fx.get(cutoff, np.nan)
        if (not 0 <= cutoff - anchor <= MAX_ACTIVE_AGE
                or not np.isfinite(anchor_fx) or not np.isfinite(current_fx)
                or current_fx > FX_ACTIVE_REBOUND * anchor_fx):
            continue
        materials = [material for material, _ in scope
                     if labels.get((cutoff, material), 0) == 1]
        for week in result.week.unique():
            horizon = int(week) - cutoff
            if not 1 <= horizon <= 13:
                continue
            evidence = []
            for event_week, event_scope in active:
                target = event_week + horizon
                if target <= cutoff:
                    occupancy = _event_occupancy(labels, target, event_scope)
                    if occupancy is not None:
                        evidence.append(occupancy)
            if evidence:
                probability = min(PROBABILITY_CAP, float(np.mean(evidence)))
                mask = (result.week == week) & result.material.isin(materials)
                result.loc[mask, "disruption_prob"] = np.maximum(
                    result.loc[mask, "disruption_prob"], probability)
    return result


def predict(data, cutoff, weeks, *, base=disruption_news.predict):
    """Apply sanctions/FX probability floors to an optional base predictor."""
    weeks = list(weeks)
    frame = base(data, cutoff, weeks)
    return sanction_probabilities(data, cutoff, frame)
