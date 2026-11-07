"""Finite news templates and exploratory, not calibrated, warning evidence.

Run: python -m halcyon.events --data data --cutoff 208 --max-lead 13
Only early/imminent templates enter the table. An episode joins warnings of
one family and exact supplier scope when successive warnings are <= max_lead
weeks apart; an active/averted report closes that scope. Each template contributes
only its first warning per episode, never one replicate per affected material.
All labels through warning + max_lead must exist as of cutoff, including the
preceding label needed to identify a 0->1 onset. Same-week onsets have lead 0.
Any eligible material onset counts: labels cannot attribute causality to a
supplier/event, so overlapping shocks can inflate hits, especially broad lanes.
Different templates in one episode are correlated; sources are retained but
syndication is not independent confirmation. Two pseudo-events at the historical
onset-window rate and a 0.7 cap are caution, not forecast calibration.
Unknown/routine headlines are ignored; explicit cancellation stops hit credit.

Build the scenario using disruption.predict(..., variant="shock") together with
plan_shock; primary forecasts/policy are unchanged. Exploratory fixed-origin
best-of-two mean: 52.63 vs primary+challenger 51.04 at main 2ee50fc; pair worst
falls 36.00 -> 33.18. These are local estimates, not official scores.
Once labels reach 221, generate the requested situation report with:
python -m halcyon.events --data data --cutoff 221 --report docs/phase2-situation.md
The command refuses unreleased cutoffs rather than inventing a situation.
"""

import re

import numpy as np
import pandas as pd

_COUNTRIES = dict(Kestria="KES", Kestrian="KES", Valdmar="VAL", Orinoque="ORI",
                  Halvard="HAL", Aurelia="AUR", Aurelian="AUR", **{"Sunda Coast": "SUN"})
_LANES = {"Merrow Strait": "MERROW", "Northern Sea route": "NORTH",
          "Southern route": "SOUTH", "Atlantic route": "ATLANTIC",
          "domestic rail network": "RAIL", "domestic rail": "RAIL"}
# Family/stage groups are deliberately independent of historical event metadata.
_GROUPS = {
    ("tariff", "early"): ["Importers watch {} trade dispute closely"],
    ("tariff", "imminent"): ["Buyers rush to front-load {} {} orders ahead of tariff", "{} confirms new duties on {} {}", "Tariff schedule on {} {} published"],
    ("tariff", "active"): ["New duties on {} {} take effect"],
    ("export", "early"): ["Lawmakers in {} debate limits on raw material exports", "{} ministry calls {} a strategic priority", "{} {} exporters report slower license approvals"],
    ("export", "imminent"): ["{} drafts restrictions on {} shipments abroad", "{} signals {} export curbs within weeks", "Traders brace for {} {} export halt"],
    ("export", "active"): ["{} halts {} exports", "{} abruptly suspends {} export licenses"],
    ("export", "averted"): ["{} officials rule out new restrictions"],
    ("clash", "early"): ["Tensions rise between {} and neighbors", "Naval patrols increase near the {}", "Insurers raise war risk premiums for the {}", "Warning shots fired near the {}"],
    ("clash", "active"): ["Traffic through the {} suspended after clashes"],
    ("clash", "averted"): ["Calm returns near the {}"],
    ("strike", "early"): ["Port waiting times creep up along the {}", "Congestion builds at ports on the {}", "Port labor talks drag on for the {}", "Dockworkers on the {} vote on contract offer"],
    ("strike", "imminent"): ["Union sets strike date for {} ports", "Strike on the {} looks likely, mediators say", "Shippers rush cargo ahead of {} strike"],
    ("strike", "active"): ["Strike shuts ports along the {}"],
    ("strike", "averted"): ["Deal reached, {} disruption averted"],
    ("shortage", "early"): ["{} {} producers flag maintenance delays", "Workers at {} {} sites threaten walkout"],
    ("shortage", "imminent"): ["{} rations water to {} producers", "{} {} output forecast cut sharply"],
    ("shortage", "active"): ["Accident halts major {} {} site", "{} {} production falls amid shortage"],
    ("sanctions", "early"): ["Diplomatic talks between {} and {} break down", "{} currency slips as investors grow cautious", "{} lawmakers criticize {} government", "{} officials review {} trade practices"],
    ("sanctions", "imminent"): ["Companies told to prepare for {} sanctions", "Sanctions vote on {} scheduled"],
    ("sanctions", "active"): ["Sanctions on {} take effect"],
    ("ongoing", "active"): ["{} {} disruption continues", "No quick fix for {} {} supply problems", "{} disruption drags on"],
    ("ongoing", "recovery"): ["Disruption in {} {} supply eases", "{} {} flows return to normal", "Traffic returns to the {}"],
}
_TEMPLATES = {t: key for key, templates in _GROUPS.items() for t in templates}
_COLUMNS = ["week", "material", "template", "stage", "source", "article_id"]


def _pattern(names):
    return re.compile(r"\b(?:" + "|".join(map(re.escape, sorted(names, key=len, reverse=True))) + r")\b", re.I)


def _reports(data, cutoff):
    suppliers = data["suppliers"]
    materials = {m.replace("_", " "): m for m in suppliers.material.unique()}
    materials.update({"rare earth": "rare_earths", "semiconductor": "semiconductors"})
    lookups = [{k.lower(): v for k, v in d.items()} for d in (_COUNTRIES, _LANES, materials)]
    patterns = [_pattern(d) for d in lookups]
    entities = _pattern({**_COUNTRIES, **_LANES, **materials})
    news = data["news"].loc[lambda d: d.week <= cutoff].sort_values(["week", "article_id"])
    for a in news.itertuples(index=False):
        template = entities.sub("{}", a.headline)
        if template not in _TEMPLATES:
            continue
        text = a.headline + ". " + str(a.body)
        countries, lanes, mats = [{lookup[m.lower()] for m in pattern.findall(text)}
                                 for lookup, pattern in zip(lookups, patterns)]
        countries = countries - {"AUR"} if len(countries) > 1 else countries
        mask = suppliers.lane.isin(lanes) if lanes else (
            suppliers.country.isin(countries) & (suppliers.material.isin(mats) if mats else True))
        scope = tuple(sorted(set(suppliers.loc[mask, ["material", "country"]].itertuples(index=False, name=None))))
        if scope:
            family, stage = _TEMPLATES[template]
            yield a, template, family, stage, scope


def articles(data, cutoff):
    """One row per eligible article/material; lane scope overrides country scope."""
    return pd.DataFrame([(int(a.week), m, t, stage, a.source, a.article_id)
                         for a, t, _, stage, scope in _reports(data, cutoff)
                         for m in sorted({m for m, _ in scope})], columns=_COLUMNS)


def template_table(data, cutoff, max_lead=13):
    """Mature first-template warnings per episode, using only labels <= cutoff."""
    if max_lead < 0:
        raise ValueError("max_lead must be nonnegative")
    labels = data["outcomes"].loc[lambda d: d.week <= cutoff]
    wide = labels.pivot(index="week", columns="material", values="disrupted").sort_index()
    onsets = wide.eq(1) & wide.shift().eq(0) & wide.index.to_series().diff().eq(1).to_numpy()[:, None]
    episodes, current = [], {}
    for a, template, family, stage, scope in _reports(data, cutoff):
        key = (family, scope)
        if stage in ("active", "averted"):
            # A country-wide denial also cancels its narrower material warnings.
            closing = [key for key in current
                       if key[0] == family and set(key[1]).issubset(scope)]
            for closing_key in closing:
                closed = current.pop(closing_key)
                if stage == "averted":
                    closed["averted_week"] = int(a.week)
        if stage not in ("early", "imminent"):
            continue
        if key not in current or a.week - current[key]["last"] > max_lead:
            current[key] = {"last": a.week, "scope": scope, "warnings": {}}
            episodes.append(current[key])
        episode = current[key]
        episode["last"] = a.week
        episode["warnings"].setdefault(template, int(a.week))
    evidence = []
    for episode in episodes:
        mats = sorted({m for m, _ in episode["scope"]})
        for template, week in episode["warnings"].items():
            end = week + max_lead
            window = wide.reindex(index=range(week - 1, end + 1), columns=mats)
            if end > cutoff or window.isna().any().any():
                continue
            hit_end = min(end, episode.get("averted_week", end))
            hits = onsets.reindex(index=range(week, hit_end + 1), columns=mats).any(axis=1)
            lead = int(hits[hits].index[0] - week) if hits.any() else float("nan")
            evidence.append((template, int(hits.any()), lead))
    columns = ["template", "event_count", "onset_count", "decoy_rate", "median_lead", "beta_probability"]
    if not evidence:
        return pd.DataFrame(columns=columns)
    table = pd.DataFrame(evidence, columns=["template", "hit", "lead"]).groupby("template").agg(
        event_count=("hit", "size"), onset_count=("hit", "sum"), median_lead=("lead", "median"))
    table["decoy_rate"] = 1 - table.onset_count / table.event_count
    weekly_rate = onsets.iloc[1:].to_numpy().mean() if len(onsets) > 1 else 0.0
    window_rate = 1 - (1 - weekly_rate) ** (max_lead + 1)
    table["beta_probability"] = ((table.onset_count + 2 * window_rate)
                                  / (table.event_count + 2)).clip(upper=0.7)
    return table.reset_index()[columns]


def _market_confirmation(data, cutoff, material):
    """Count independent price/macro/shipping precursor families, at cutoff."""
    sellers = data["suppliers"].loc[lambda f: f.material == material]
    recent = lambda name: data[name].loc[lambda f: f.week.between(cutoff - 13, cutoff)]
    prices = recent("prices").loc[lambda f: f.material == material]
    macro = recent("macro").loc[lambda f: f.country.isin(sellers.country)]
    shipping = recent("shipping").loc[lambda f: f.lane.isin(sellers.lane)]
    price_hit = macro_hit = shipping_hit = False
    for _, rows in prices.groupby("country"):
        rows = rows.sort_values("week")
        ratio = rows.futures_4w / rows.spot_price
        price_hit |= bool(ratio.iloc[-1] - ratio.iloc[:-1].median() >= .02)
        if len(rows) >= 5:
            price_hit |= bool(rows.spot_price.iloc[-1] / rows.spot_price.iloc[-5] >= 1.05)
    for _, rows in macro.groupby("country"):
        rows = rows.sort_values("week")
        macro_hit |= bool(rows.tension_index.iloc[-1] >= 50
                          or rows.tension_index.iloc[-1] - rows.tension_index.iloc[:-1].median() >= 10)
        if len(rows) >= 5:
            macro_hit |= bool(abs(rows.fx_rate.iloc[-1] / rows.fx_rate.iloc[-5] - 1) >= .02)
    for _, rows in shipping.groupby("lane"):
        rows = rows.sort_values("week")
        shipping_hit |= bool(rows.congestion_index.iloc[-1] >= 50
                             or rows.congestion_index.iloc[-1] - rows.congestion_index.iloc[:-1].median() >= 10)
    return int(price_hit) + int(macro_hit) + int(shipping_hit)


def shock_probabilities(data, cutoff, frame):
    """A conditional stress scenario, NOT the primary's calibrated expectation.

    MERROW exposure carries a .35 scenario floor. Historical warning evidence
    can lift it only with two sources, a market precursor, and >=2 past hits.
    Future tariff schedules need two market families. Event floors are <=.7;
    existing high probabilities for observed ongoing shocks are never lowered.
    """
    output = frame.copy()
    exposed = data["suppliers"].loc[lambda f: f.lane == "MERROW"].material.unique()
    floors = pd.Series(np.where(output.material.isin(exposed), .35, 0.0), index=output.index)
    reports = articles(data, cutoff)
    evidence = template_table(data, cutoff)
    qualified = evidence.loc[(evidence.event_count >= 2) & (evidence.onset_count >= 2)]
    learned = qualified.set_index("template").beta_probability
    warnings = reports.loc[(reports.week > cutoff - 4) & reports.stage.isin(["early", "imminent"])]
    closed = reports.loc[reports.stage.isin(["averted", "recovery"])].groupby("material").week.max()
    schedules = data["tariffs"].loc[lambda f: (f.week == cutoff)
                                  & (f.announced_rate > f.tariff_rate)
                                  & (f.announced_effective_week > cutoff)]
    for material in output.material.unique():
        confirmation = _market_confirmation(data, cutoff, material)
        warning = warnings.loc[warnings.material == material]
        if not warning.empty and warning.week.max() > closed.get(material, 0):
            if warning.source.nunique() >= 2 and confirmation:
                risk = warning.template.map(learned).max()
                if pd.notna(risk):
                    mask = output.material == material
                    floors.loc[mask] = np.maximum(floors.loc[mask], min(.7, risk))
        if confirmation >= 2:
            for row in schedules.loc[schedules.material == material].itertuples(index=False):
                mask = ((output.material == material) & (output.week >= row.announced_effective_week)
                        & (output.week < row.announced_effective_week + 12))
                floors.loc[mask] = np.maximum(floors.loc[mask], .6)
    output["disruption_prob"] = np.maximum(output.disruption_prob, floors.clip(upper=.7))
    return output


def plan_shock(data, cutoff, weeks, forecasts):
    """Pre-buy the shock scenario; never changes the primary ordering policy."""
    from .policy import Params, plan

    # Limit incremental inventory even when the forecast of an ongoing shock is
    # near one. Taper in policy.plan still prevents unconsumable terminal stock.
    planning = forecasts.assign(disruption_prob=forecasts.disruption_prob.clip(upper=.5))
    return plan(data, cutoff, weeks, planning,
                params=Params(buffer_weeks=3.0, diversity=.08))


def situation(data, cutoff):
    """One-page, cutoff-specific evidence; refuses to invent unreleased state."""
    from .data import MATERIALS

    labels = data["outcomes"].loc[lambda f: f.week <= cutoff]
    if labels.week.max() != cutoff:
        raise ValueError(f"outcomes reach {labels.week.max()}, not requested cutoff {cutoff}")
    reports = articles(data, cutoff)
    closed = reports.loc[reports.stage.isin(["averted", "recovery"])].groupby("material").week.max()
    warnings = reports.loc[(reports.week > cutoff - 12) & reports.stage.isin(["early", "imminent"])]
    tariffs = data["tariffs"].loc[lambda f: (f.week == cutoff)
                                & (f.announced_rate > f.tariff_rate)
                                & f.announced_effective_week.between(cutoff + 1, cutoff + 13)]
    supply = data["supply_history"].loc[lambda f: f.week == cutoff].merge(
        data["suppliers"][["material", "country", "normal_capacity_units", "base_lead_weeks"]],
        on=["material", "country"], validate="one_to_one")
    keys = {t: f"T{i + 1:02d}" for i, t in enumerate(_TEMPLATES)}
    used = set()
    lines = [f"# Situation at cutoff {cutoff}", "",
             f"Released evidence only; forecast window {cutoff + 1}–{cutoff + 13}. "
             "Warnings and announcements are not certain shocks.", "",
             "| Material | State / age (weeks) | Future tariffs | Active warning templates | Supplier hits now |",
             "|---|---|---|---|---|"]
    for material in MATERIALS:
        history = labels.loc[labels.material == material].sort_values("week").disrupted.to_numpy()
        state = int(history[-1])
        age = next((i for i, value in enumerate(history[::-1]) if value != state), len(history))
        first_censored = "+" if age == len(history) else ""
        warning = warnings.loc[(warnings.material == material)
                               & (warnings.week > closed.get(material, 0))]
        templates = sorted(warning.template.unique())
        used.update(templates)
        scheduled = tariffs.loc[tariffs.material == material]
        announcement = ", ".join(f"{r.country}@{int(r.announced_effective_week)}:{r.announced_rate:.0%}"
                                 for r in scheduled.itertuples(index=False)) or "—"
        hit = []
        for r in supply.loc[supply.material == material].itertuples(index=False):
            ratio, delay = r.capacity_units / r.normal_capacity_units, r.lead_time_weeks - r.base_lead_weeks
            if ratio < .9 or delay > 0:
                hit.append(f"{r.country} {ratio:.2f}×/{delay:+.0f}w")
        lines.append(f"| {material} | {state} / {age}{first_censored} | {announcement} | "
                     f"{', '.join(keys[t] for t in templates) or '—'} | {', '.join(hit) or '—'} |")
    lines += ["", "State 1 = disrupted. + = run began before observed history. "
              "Supplier hit: capacity <90% normal or lead above base; ratios/delay shown. "
              "Warnings: last12 weeks, excluding reports preceding a known recovery/cancellation.", ""]
    lines += [f"- {keys[t]}: {t}" for t in sorted(used, key=keys.get)]
    lines += ["", "Primary remains the base expectation; the shock hedge is an intentionally "
              "aggressive MERROW/event scenario. Small, correlated event samples do not establish causality."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    from .data import read_all

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data")
    parser.add_argument("--cutoff", type=int, required=True)
    parser.add_argument("--max-lead", type=int, default=13)
    parser.add_argument("--report", type=Path, help="write a cutoff situation report instead of the template table")
    args = parser.parse_args()
    data = read_all(args.data)
    if args.report:
        args.report.write_text(situation(data, args.cutoff))
        print(f"wrote {args.report}")
    else:
        print(template_table(data, args.cutoff, args.max_lead).to_string(index=False))
