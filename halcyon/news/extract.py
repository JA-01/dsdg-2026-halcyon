"""Turn supplied articles into structured events using the corpus's finite headline templates.

The synthetic news has a small set of templates, so an exact lookup is both complete and auditable.
A template this table has not seen becomes `unmapped`, never a guess; check the count after a new
release. Each article keeps its own week: repeated text gives separate events, not a shared one.
"""
from __future__ import annotations

import re

import pandas as pd

from ..constants import COUNTRY_LANE

EXTRACTOR_VERSION = "templates-v1"

COUNTRY_NAMES = {"Kestrian": "KES", "Kestria": "KES", "Valdmar": "VAL", "Sunda Coast": "SUN", "Orinoque": "ORI",
                 "Halvard": "HAL", "Aurelian": "AUR", "Aurelia": "AUR"}
LANE_NAMES = {"Merrow Strait": "MERROW", "Northern Sea route": "NORTH", "Southern route": "SOUTH",
              "Atlantic route": "ATLANTIC", "domestic rail network": "RAIL", "domestic rail": "RAIL"}
MATERIAL_NAMES = {"lithium": "lithium", "cobalt": "cobalt", "copper": "copper", "aluminum": "aluminum",
                  "steel": "steel", "rare earths": "rare_earths", "rare earth": "rare_earths",
                  "semiconductors": "semiconductors", "semiconductor": "semiconductors",
                  "polymer resin": "polymer_resin", "specialty glass": "specialty_glass", "natural gas": "natural_gas"}

EARLY, IMMINENT, ACTIVE, RECOVERY, AVERTED = "early", "imminent", "active", "recovery", "averted"
STAGES = (EARLY, IMMINENT, ACTIVE, RECOVERY, AVERTED)

# Headline template -> (shock category, stage). "{}" stands for any named entity.
SIGNAL_TEMPLATES = {
    "Importers watch {} trade dispute closely": ("tariff", EARLY),
    "Buyers rush to front-load {} {} orders ahead of tariff": ("tariff", IMMINENT),
    "{} confirms new duties on {} {}": ("tariff", IMMINENT),
    "Tariff schedule on {} {} published": ("tariff", IMMINENT),
    "New duties on {} {} take effect": ("tariff", ACTIVE),
    "Lawmakers in {} debate limits on raw material exports": ("export_ban", EARLY),
    "{} ministry calls {} a strategic priority": ("export_ban", EARLY),
    "{} {} exporters report slower license approvals": ("export_ban", EARLY),
    "{} drafts restrictions on {} shipments abroad": ("export_ban", IMMINENT),
    "{} signals {} export curbs within weeks": ("export_ban", IMMINENT),
    "Traders brace for {} {} export halt": ("export_ban", IMMINENT),
    "{} halts {} exports": ("export_ban", ACTIVE),
    "{} abruptly suspends {} export licenses": ("export_ban", ACTIVE),
    "{} officials rule out new restrictions": ("export_ban", AVERTED),
    "Tensions rise between {} and neighbors": ("lane_closure", EARLY),
    "Naval patrols increase near the {}": ("lane_closure", EARLY),
    "Insurers raise war risk premiums for the {}": ("lane_closure", EARLY),
    "Warning shots fired near the {}": ("lane_closure", EARLY),
    "Traffic through the {} suspended after clashes": ("lane_closure", ACTIVE),
    "Calm returns near the {}": ("lane_closure", AVERTED),
    "Port waiting times creep up along the {}": ("port_strike", EARLY),
    "Congestion builds at ports on the {}": ("port_strike", EARLY),
    "Port labor talks drag on for the {}": ("port_strike", EARLY),
    "Dockworkers on the {} vote on contract offer": ("port_strike", EARLY),
    "Union sets strike date for {} ports": ("port_strike", IMMINENT),
    "Strike on the {} looks likely, mediators say": ("port_strike", IMMINENT),
    "Shippers rush cargo ahead of {} strike": ("port_strike", IMMINENT),
    "Strike shuts ports along the {}": ("port_strike", ACTIVE),
    "Deal reached, {} disruption averted": ("port_strike", AVERTED),
    "{} {} producers flag maintenance delays": ("shortage", EARLY),
    "Workers at {} {} sites threaten walkout": ("shortage", EARLY),
    "{} rations water to {} producers": ("shortage", IMMINENT),
    "{} {} output forecast cut sharply": ("shortage", IMMINENT),
    "Accident halts major {} {} site": ("shortage", ACTIVE),
    "{} {} production falls amid shortage": ("shortage", ACTIVE),
    "Diplomatic talks between {} and {} break down": ("sanctions", EARLY),
    "{} currency slips as investors grow cautious": ("sanctions", EARLY),
    "{} lawmakers criticize {} government": ("sanctions", EARLY),
    "{} officials review {} trade practices": ("sanctions", EARLY),
    "Companies told to prepare for {} sanctions": ("sanctions", IMMINENT),
    "Sanctions vote on {} scheduled": ("sanctions", IMMINENT),
    "Sanctions on {} take effect": ("sanctions", ACTIVE),
    "{} {} disruption continues": ("ongoing", ACTIVE),
    "No quick fix for {} {} supply problems": ("ongoing", ACTIVE),
    "{} disruption drags on": ("ongoing", ACTIVE),
    "Disruption in {} {} supply eases": ("ongoing", RECOVERY),
    "{} {} flows return to normal": ("ongoing", RECOVERY),
    "Traffic returns to the {}": ("ongoing", RECOVERY),
}
ROUTINE_TEMPLATES = {
    "Central bank of {} holds rates steady", "{} prices little changed in quiet trading",
    "Weather stays mild across {}", "{} trade surplus widens", "Logistics firms invest in tracking technology",
    "Freight rates steady on the {}", "Mining stocks mixed in {}", "Analysts expect stable {} demand this quarter",
    "New container terminal opens in {}", "{} unemployment rate dips", "{} announces infrastructure spending plan",
    "{} hosts regional trade fair", "Recycling of {} gains attention", "{} manufacturers report steady orders",
    "Opposition in {} criticizes budget", "{} signs cooperation agreement with neighbors",
    "{} factory activity edges up", "{} factory activity edges down",
}


def _pattern(names) -> re.Pattern:
    ordered = sorted(names, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(map(re.escape, ordered)) + r")\b", re.IGNORECASE)


_COUNTRY = _pattern(COUNTRY_NAMES)
_LANE = _pattern(LANE_NAMES)
_MATERIAL = _pattern(MATERIAL_NAMES)
_ANY = _pattern([*COUNTRY_NAMES, *LANE_NAMES, *MATERIAL_NAMES])


def _found(pattern: re.Pattern, names: dict, text: str) -> list[str]:
    lookup = {k.lower(): v for k, v in names.items()}
    return sorted({lookup[m.lower()] for m in pattern.findall(text)})


def template_of(headline: str) -> str:
    return _ANY.sub("{}", headline)


def extract_events(news: pd.DataFrame) -> pd.DataFrame:
    """One row per non-routine article, preserving its own week/date, with supporting evidence."""
    rows = []
    for article in news.itertuples(index=False):
        template = template_of(article.headline)
        if template in ROUTINE_TEMPLATES:
            continue
        category, stage = SIGNAL_TEMPLATES.get(template, ("unmapped", "unmapped"))
        text = f"{article.headline}. {article.body}"
        countries = _found(_COUNTRY, COUNTRY_NAMES, text)
        # Aurelia is the buyer when it appears beside another country, as in "Aurelian officials".
        targets = [c for c in countries if c != "AUR"] or countries
        rows.append({
            "article_id": article.article_id, "week": int(article.week), "date": article.date,
            "category": category, "stage": stage, "countries": targets,
            "lanes": _found(_LANE, LANE_NAMES, text), "materials": _found(_MATERIAL, MATERIAL_NAMES, text),
            "template": template, "evidence": article.body, "extractor_version": EXTRACTOR_VERSION,
        })
    columns = ["article_id", "week", "date", "category", "stage", "countries", "lanes", "materials",
               "template", "evidence", "extractor_version"]
    return pd.DataFrame(rows, columns=columns)


def affected_suppliers(events: pd.DataFrame, suppliers: pd.DataFrame) -> pd.DataFrame:
    """Expand events to supplier rows: a lane hits every supplier on it, including KES and SUN on MERROW.

    An event naming a lane applies to that lane; otherwise to the named country's named materials,
    or all its materials when none is named. Events resolving to no real supplier produce no rows.
    """
    rows = []
    pairs = list(suppliers[["material", "country"]].itertuples(index=False, name=None))
    for event in events[events["category"] != "unmapped"].itertuples(index=False):
        if event.lanes:
            hits = [(m, c) for m, c in pairs if COUNTRY_LANE[c] in event.lanes]
        else:
            hits = [(m, c) for m, c in pairs if c in event.countries and (not event.materials or m in event.materials)]
        rows += [{"article_id": event.article_id, "week": event.week, "category": event.category,
                  "stage": event.stage, "material": m, "country": c} for m, c in hits]
    return pd.DataFrame(rows, columns=["article_id", "week", "category", "stage", "material", "country"])
