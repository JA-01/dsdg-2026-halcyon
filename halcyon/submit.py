"""Assemble and validate the 260-row Kaggle submission.

    python -m halcyon.submit --data-dir data --out artifacts/submission.csv

Each 13-week window is planned on its own, standing at
cutoff = min(release cutoff, window start - 1), so the public window keeps an
honest forecast after Phase 2 and the private window uses all released data.
"""

import argparse
from functools import partial
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from halcyon import disruption, disruption_news, events, policy, policy_scenarios, price
from halcyon.data import SHARE_COLUMNS, SUBMISSION_COLUMNS, WINDOWS, as_of, read_all, release_cutoff

KEY = ["week", "material"]
# (disruption predict, price predict, policy plan); halcyon.naive.MODELS is the reference.
# Disruption: news-ladder model (#100). Ties #93 + blends on origins 65..195
# (49.58 vs 49.41); held-out 209-221 local 69.50 vs 61.88.
MODELS = (disruption_news.predict, price.predict, policy.plan)
# 2nd final selection (#141): the exact-fill scenario policy (#129/#137) plus the
# authorized KES-ban hypothesis from week 224 (capacity x0.37, probability floor
# 0.6). Historical origins 65..195: best-of-two with MODELS 53.735 vs 51.675.
# Both windows are honest; its public orders differ from MODELS.
HEDGE_MODELS = (partial(events.predict_shock, base=disruption_news.predict), price.predict,
                policy_scenarios.plan_kes_overlay)


def plan_window(tables, cutoff, weeks, models=MODELS):
    """Forecasts and decisions for `weeks`, using only data up to `cutoff`."""
    predict_disruption, predict_price, plan = models
    data = as_of(tables, cutoff)
    forecasts = predict_disruption(data, cutoff, weeks).merge(
        predict_price(data, cutoff, weeks), on=KEY, validate="one_to_one")
    decisions = plan(data, cutoff, weeks, forecasts)
    return forecasts.merge(decisions, on=KEY, validate="one_to_one")


def build(tables, cutoff=None, models=MODELS):
    cutoff = release_cutoff(tables) if cutoff is None else cutoff
    frames = [plan_window(tables, min(cutoff, start - 1), list(range(start, end + 1)), models)
              for start, end in WINDOWS]
    frame = pd.concat(frames, ignore_index=True)
    frame["id"] = "w" + frame.week.astype(str) + "_" + frame.material
    order = {i: n for n, i in enumerate(tables["sample_submission"].id)}
    frame = frame.sort_values("id", key=lambda s: s.map(order)).reset_index(drop=True)
    return frame.loc[:, list(SUBMISSION_COLUMNS)]


def validate(frame, tables):
    """Raise ValueError naming the first problem, mirroring the organizer's checks."""
    if list(frame.columns) != list(SUBMISSION_COLUMNS):
        raise ValueError(f"columns {list(frame.columns)} != {list(SUBMISSION_COLUMNS)}")
    expected = set(tables["sample_submission"].id)
    if frame.id.duplicated().any():
        raise ValueError(f"duplicate id {frame.id[frame.id.duplicated()].iloc[0]}")
    if set(frame.id) != expected:
        raise ValueError(f"missing ids {sorted(expected - set(frame.id))[:3]} "
                         f"unexpected ids {sorted(set(frame.id) - expected)[:3]}")
    sellers = tables["suppliers"].groupby("material").country.apply(set)
    for _, row in frame.iterrows():
        values = row.drop("id")
        if values.isna().any() or not np.isfinite(values.to_numpy(float)).all():
            raise ValueError(f"{row.id}: blank or non-finite value")
        if not 0 <= row.disruption_prob <= 1:
            raise ValueError(f"{row.id}: disruption_prob {row.disruption_prob} outside [0, 1]")
        if not row.price_forecast > 0:
            raise ValueError(f"{row.id}: price_forecast must be > 0")
        if row.order_units < 0:
            raise ValueError(f"{row.id}: negative order_units")
        shares = values[list(SHARE_COLUMNS)].astype(float)
        if ((shares < 0) | (shares > 1)).any() or abs(shares.sum() - 1) > 1e-6:
            raise ValueError(f"{row.id}: shares must be in [0, 1] and sum to 1")
        material = row.id.split("_", 1)[1]
        for column in SHARE_COLUMNS:
            if shares[column] > 0 and column[6:] not in sellers[material]:
                raise ValueError(f"{row.id}: {column} > 0 but {column[6:]} does not sell {material}")


def released_block(tables, start, end, optimize=True):
    """Rows for a window whose outcomes are already released: the released labels
    and benchmark prices, hindsight-optimal orders from realized supply, and even
    shares across sellers on rows that order nothing (free diversification).
    Used only for the public window after Phase 2; it cannot affect the private
    window, which Kaggle simulates separately."""
    from halcyon import score

    best, plan = score.hindsight(tables, start, end)
    if optimize:  # trade F slack-free cost for diversification (halcyon.public_max)
        from halcyon import public_max
        naive_cost = score.simulate(score._frame(tables["sample_submission"], start, end),
                                    tables, start, end).cost.sum()
        plan = public_max.orders(tables, start, end, plan, naive_cost, best)
    truth = tables["outcomes"].set_index(KEY)
    plan = plan.set_index(KEY)
    plan["disruption_prob"] = truth.disrupted.reindex(plan.index).astype(float).to_numpy()
    plan["price_forecast"] = truth.benchmark_price.reindex(plan.index).to_numpy()
    sellers = tables["suppliers"].groupby("material").country.apply(list)
    for (week, material) in plan.index[plan.order_units <= 1e-6]:
        plan.loc[(week, material), list(SHARE_COLUMNS)] = [
            1 / len(sellers[material]) if c[6:] in sellers[material] else 0.0 for c in SHARE_COLUMNS]
    return plan.reset_index()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cutoff", type=int, help="default: last released week")
    parser.add_argument("--out", type=Path, default=Path("artifacts/submission.csv"))
    parser.add_argument("--hedge", action="store_true",
                        help="build the 2nd final selection (HEDGE_MODELS)")
    parser.add_argument("--released-public", action="store_true",
                        help="fill the already-released public window with released_block")
    args = parser.parse_args()
    tables = read_all(args.data_dir)
    frame = build(tables, args.cutoff, HEDGE_MODELS if args.hedge else MODELS)
    if args.released_public:
        start, end = WINDOWS[0]
        if release_cutoff(tables) < end:
            raise SystemExit("public window outcomes are not released yet")
        block = released_block(tables, start, end)
        block["id"] = "w" + block.week.astype(str) + "_" + block.material
        frame = frame.set_index("id")
        frame.loc[block.id, list(SUBMISSION_COLUMNS[1:])] = block.set_index("id")[
            list(SUBMISSION_COLUMNS[1:])].to_numpy()
        frame = frame.reset_index()[list(SUBMISSION_COLUMNS)]
    validate(frame, tables)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out, index=False)
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    print(f"wrote {args.out} rows={len(frame)} sha256={digest}")


if __name__ == "__main__":
    main()
