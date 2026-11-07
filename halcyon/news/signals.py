"""Trailing news signals per week and material. A row for week W reads only articles dated <= W."""
from __future__ import annotations

import pandas as pd

from ..constants import MATERIALS
from .extract import ACTIVE, AVERTED, RECOVERY, STAGES, affected_suppliers, extract_events

LOOKBACK_WEEKS = 4
SIGNAL_COLUMNS = ("news_early", "news_imminent", "news_active", "news_recovery", "news_averted", "news_open")


def news_signals(news: pd.DataFrame, suppliers: pd.DataFrame, last_week: int | None = None) -> pd.DataFrame:
    """Return (week, material) rows of trailing article counts for every week up to the data's end.

    Counts are distinct articles per stage over the last LOOKBACK_WEEKS weeks. `news_open` is 1 when
    an active report is newer than any recovery or averted report for that material in that span.
    Pass only articles visible at the cutoff (`view["news"]`): nothing here looks forward.
    """
    last_week = int(news["week"].max()) if last_week is None else last_week
    index = pd.MultiIndex.from_product([range(1, last_week + 1), MATERIALS], names=["week", "material"])
    hits = affected_suppliers(extract_events(news), suppliers).drop_duplicates(["article_id", "material"])
    counts = (hits.groupby(["week", "material", "stage"]).size().unstack("stage", fill_value=0)
              .reindex(index, fill_value=0).reindex(columns=list(STAGES), fill_value=0))
    rolled = counts.groupby(level="material", group_keys=False).apply(
        lambda group: group.rolling(LOOKBACK_WEEKS, min_periods=1).sum())
    frame = rolled.rename(columns={stage: f"news_{stage}" for stage in STAGES}).reset_index()

    def latest(stages) -> pd.Series:
        marked = counts[stages].sum(axis=1).gt(0)
        weeks = pd.Series(marked.index.get_level_values("week"), index=marked.index).where(marked)
        return weeks.groupby(level="material").ffill()

    active, closed = latest([ACTIVE]), latest([RECOVERY, AVERTED])
    open_now = active.notna() & (active > closed.fillna(0)) & (active.index.get_level_values("week") - active < LOOKBACK_WEEKS)
    frame["news_open"] = open_now.astype(float).to_numpy()
    return frame[["week", "material", *SIGNAL_COLUMNS]]
