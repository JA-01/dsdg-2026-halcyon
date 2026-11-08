"""Expected-world strategy (issue #149): the best plan if the phase-2 signals open at
the cutoff play out as history says, or fizzle.

Candidate = MODELS = (predict, price.predict, plan), usable by submit.build.

Disruption probabilities start from the champion (disruption_news.predict) and
commit to the hard, structured signals only:
- a material disrupted at the cutoff, or with a futures-basis flag (historically
  6/6 followed by an onset) keeps the champion's learned probability;
- an announced tariff hike makes the material disrupted by the label rule from its
  effective week (tariff > base); all 5 historical announcements took effect, so
  p = max(champion, Jeffreys posterior mean (5 + 1/2) / (5 + 1) = 0.917);
- every other material is capped at the clean-state onset hazard by horizon,
  P(disrupted at t + h | not disrupted at t), learned from labels up to the
  cutoff. News-ladder warnings without a hard signal (decoy-prone historically)
  cannot lift a material above what an unwarned material gets.
P skill is clipped at 0, so a sharper forecast risks little in worlds where it is
wrong and gains Brier skill in the expected ones.

Orders keep the champion's nominal estimates but use the exact MILP (fills and
service as the simulator) with a 1.5-week safety stock instead of 1.75.
"""


import numpy as np
import pandas as pd

from halcyon import disruption_news, policy_scenarios, price
from halcyon.data import MATERIALS

TARIFF_HELD = (5 + 0.5) / (5 + 1)  # Jeffreys posterior mean: 5 of 5 announced hikes took effect


def clean_hazard(outcomes, cutoff, horizons):
    """P(disrupted at t + h | not disrupted at t), pooled over materials, weeks t + h <= cutoff."""
    x = outcomes.loc[outcomes.week <= cutoff].pivot(index="week", columns="material", values="disrupted")
    x = x.sort_index().to_numpy()
    out = {}
    for h in horizons:
        clean = x[:-h] == 0
        out[h] = float(x[h:][clean].mean()) if clean.any() else 0.0
    return out


def hard_signals(data, cutoff):
    """(materials disrupted or basis-flagged at the cutoff, {material: tariff effective week})."""
    out = data["outcomes"]
    now = out.loc[out.week == cutoff]
    held = set(now.loc[now.disrupted == 1, "material"])
    flags = disruption_news.basis_flags(data, cutoff)
    last = np.asarray(flags)[-1] if len(flags) else np.zeros(len(MATERIALS), bool)
    held |= {m for m, f in zip(MATERIALS, last) if f}
    tar = data["tariffs"]
    tar = tar.loc[(tar.week == cutoff) & tar.announced_rate.notna() & (tar.announced_rate > tar.tariff_rate)]
    tariffs = {}
    for r in tar.itertuples():
        tariffs[r.material] = min(tariffs.get(r.material, np.inf), int(r.announced_effective_week))
    return held, tariffs


def predict(data, cutoff, weeks):
    base = disruption_news.predict(data, cutoff, weeks)
    held, tariffs = hard_signals(data, cutoff)
    hz = clean_hazard(data["outcomes"], cutoff, sorted({w - cutoff for w in weeks}))
    p = []
    for w, m, q in zip(base.week, base.material, base.disruption_prob):
        if m in tariffs and w >= tariffs[m]:
            q = max(q, TARIFF_HELD)
        elif m not in held:
            q = min(q, hz[w - cutoff])
        p.append(float(np.clip(q, 0.0, 1.0)))
    return base.assign(disruption_prob=p)


BUFFER_WEEKS = 1.5  # expected-world safety stock (the champion holds 1.75); chosen on the #148 matrix


def plan(data, cutoff, weeks, forecasts):
    """Champion estimates (bans, announced tariffs, tiers, rebalance) solved with exact
    service and fills (policy_scenarios MILP on the nominal path only) and a leaner
    1.5-week safety stock: the expected world holds less stock against unwarned shocks,
    which the paired hedge insures instead."""
    params = policy_scenarios.Params(weight_scale=0.0, buffer=BUFFER_WEEKS)
    return policy_scenarios.plan(data, cutoff, weeks, forecasts, params)


MODELS = (predict, price.predict, plan)
