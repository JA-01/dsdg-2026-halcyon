"""Controlled test of whether news helps: one estimator, with and without news-derived states.

P(disrupted at origin + h) = material rate x lift(state at origin, horizon bucket). Lifts are pooled
across materials and shrunk toward 1, which suits about 200 weeks of clustered shocks; a logistic fit
extrapolated one long shock into months of near-certain disruption. Every training pair has
origin + horizon <= cutoff and uses the origin's own past. Smoothing constants are fixed, not tuned.
Beyond 13 weeks the forecast is the plain rate: on development origins, longer lifts lost to it because
they rest on a handful of clustered events. Prices stay at the carry-forward baseline, so this measures
only the effect on disruption probability.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..baselines import ProvisionalForecaster
from ..policy import OptimizedPolicy
from .signals import news_signals

HORIZON_EDGES = (0, 2, 4, 8, 13)
TRAINING_HORIZONS = tuple(range(1, 14))
MIN_ORIGIN = 26
RATE_PRIOR_WEEKS = 26
LIFT_PRIOR = 5.0
PROB_FLOOR, PROB_CEILING = 0.005, 0.98


def _states(data, cutoff: int, use_news: bool) -> pd.DataFrame:
    """One state per origin week and material, from labels and articles visible at that origin."""
    outcomes = data["outcomes"]
    state = outcomes.loc[outcomes["week"] <= cutoff, ["week", "material", "disrupted"]].rename(
        columns={"week": "origin"})
    if not use_news:
        return state.assign(state=np.where(state["disrupted"] == 1, "active", "quiet"))[["origin", "material", "state"]]
    signals = news_signals(data["news"], data["suppliers"], last_week=cutoff).rename(columns={"week": "origin"})
    merged = state.merge(signals, on=["origin", "material"], validate="one_to_one")
    labels = np.select(
        [(merged["disrupted"] == 1) & (merged["news_recovery"] > 0),
         merged["disrupted"] == 1,
         (merged["news_imminent"] > 0) | (merged["news_active"] > 0),
         merged["news_early"] > 0],
        ["ending", "active", "imminent", "early"], default="quiet")
    return merged.assign(state=labels)[["origin", "material", "state"]]


def _bucket(horizon) -> pd.Series:
    return pd.cut(pd.Series(horizon), bins=list(HORIZON_EDGES), labels=False)


class HistoricalRiskPolicy:
    """OptimizedPolicy planned on historical rates, whatever disruption_prob the submission carries.

    Keeps orders independent of the news probabilities, so those can only affect the Prediction score.
    """

    policy_id = "inventory_milp_historical_risk"

    def __init__(self):
        self.policy = OptimizedPolicy()

    def decide(self, data, forecasts: pd.DataFrame, cutoff: int, target_weeks: list[int]) -> pd.DataFrame:
        outcomes = data["outcomes"]
        rates = outcomes[outcomes["week"] <= cutoff].groupby("material")["disrupted"].mean()
        planned = forecasts.assign(disruption_prob=forecasts["material"].map(rates))
        return self.policy.decide(data, planned, cutoff, target_weeks)


class DisruptionModel:
    """State-and-horizon lift over each material's smoothed rate; news on or off, nothing else differs."""

    def __init__(self, use_news: bool = True):
        self.use_news = use_news
        self.model_id = "state_lift_news" if use_news else "state_lift_no_news"
        self.base = ProvisionalForecaster()

    def predict(self, data, cutoff: int, target_weeks: list[int]) -> pd.DataFrame:
        output = self.base.predict(data, cutoff, target_weeks).assign(model_id=self.model_id)
        outcomes = data["outcomes"]
        outcomes = outcomes[outcomes["week"] <= cutoff]
        overall = outcomes["disrupted"].mean()
        grouped = outcomes.groupby("material")["disrupted"]
        rates = (grouped.sum() + RATE_PRIOR_WEEKS * overall) / (grouped.size() + RATE_PRIOR_WEEKS)

        states = _states(data, cutoff, self.use_news)
        pairs = states[states["origin"] >= MIN_ORIGIN].merge(pd.DataFrame({"horizon": TRAINING_HORIZONS}), how="cross")
        pairs["week"] = pairs["origin"] + pairs["horizon"]
        pairs = pairs[pairs["week"] <= cutoff].merge(outcomes[["week", "material", "disrupted"]],
                                                     on=["week", "material"], validate="many_to_one")
        pairs["bucket"] = _bucket(pairs["horizon"]).to_numpy()
        pairs["expected"] = pairs["material"].map(rates)
        if pairs.empty:  # Too little history to learn any lift.
            return output.assign(disruption_prob=np.clip(output["material"].map(rates), PROB_FLOOR, PROB_CEILING))
        cells = pairs.groupby(["state", "bucket"])[["disrupted", "expected"]].sum()
        lifts = (cells["disrupted"] + LIFT_PRIOR) / (cells["expected"] + LIFT_PRIOR)

        current = states[states["origin"] == cutoff].set_index("material")["state"]
        buckets = _bucket(output["target_week"] - cutoff).to_numpy()
        keys = pd.MultiIndex.from_arrays([output["material"].map(current).to_numpy(), buckets])
        lift = lifts.reindex(keys).fillna(1.0).to_numpy()  # Long horizons and unseen cells are neutral.
        probability = np.clip(output["material"].map(rates).to_numpy() * lift, PROB_FLOOR, PROB_CEILING)
        # Long horizons carry no signal, so they equal the competition's unsmoothed reference rate.
        long_horizon = (output["target_week"] - cutoff > TRAINING_HORIZONS[-1]).to_numpy()
        return output.assign(disruption_prob=np.where(long_horizon, output["disruption_prob"], probability))
