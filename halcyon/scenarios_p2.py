"""Private-window scenario matrix (phase-2 run, #148) and best-of-two pair selection.

    python -m halcyon.scenarios_p2 --candidate kes=halcyon.strategy_kes:MODELS ...

Every scenario starts from the cutoff-221 supplier state (`stress._calm`) and adds
shocks suggested by the signals open at week 221: the KES tariff schedule
(0.10 -> 0.35 on aluminum and semiconductors from 224), futures-basis flags on VAL
cobalt (11.6%) and KES rare earths (9.3%), Kestrian lawmakers debating raw-material
export limits, and phase-2 behaviour (a 3-week headline-to-onset lag, a cancelled
false alarm). "Tricky" variants cover fizzled warnings, a reversed tariff, late or
immediate onsets, broader or harsher KES limits, lane closures and production
shortages. Bans follow the historical signature (#114): 5% capacity and +26% on all
three spot prices of the material. Scenarios and weights are judgments, not
forecasts; all scores are local estimates.
"""

import argparse
from importlib import import_module
from itertools import combinations

import pandas as pd

from halcyon import score, stress, submit
from halcyon.data import read_all

START, END = stress.START, stress.END
KES_ALL = ("aluminum", "cobalt", "lithium", "polymer_resin", "rare_earths", "semiconductors", "steel")
KES_RAW = ("cobalt", "lithium", "rare_earths")

# Probability mass per scenario group; split equally inside a group.
GROUP_WEIGHTS = {"calm": 0.20, "signals": 0.30, "kes": 0.25, "other": 0.15, "severe": 0.10}


def _ban(path, normal, material, country, start, weeks=8, ratio=0.05, jump=0.26):
    stress._ban(path, material, country, start, weeks=min(weeks, END - start + 1), ratio=ratio, jump=jump,
                normal=normal)


def _lane(path, tables, lane, start, weeks, ratio, extra_lead):
    countries = set(tables["suppliers"].loc[tables["suppliers"].lane == lane, "country"])
    hit = path.week.between(start, start + weeks - 1) & path.country.isin(countries)
    path.loc[hit, "capacity_units"] *= ratio
    path.loc[hit, "lead_time_weeks"] += extra_lead


def _kes(materials, start, weeks=END, ratio=0.05, jump=0.26):
    return lambda p, t, n: [_ban(p, n, m, "KES", start, weeks, ratio, jump) for m in materials]


_VAL_COBALT = lambda start: lambda p, t, n: _ban(p, n, "cobalt", "VAL", start)
_KES_RARE = lambda start: lambda p, t, n: _ban(p, n, "rare_earths", "KES", start)

# name -> (group, apply announced tariffs?, shocks)
SCENARIOS = {
    "calm: tariff reversed, nothing else": ("calm", False, []),
    "calm: tariffs only, warnings fizzle": ("calm", True, []),
    "signals: VAL cobalt 222 + KES rare earths 223": ("signals", True, [_VAL_COBALT(222), _KES_RARE(223)]),
    "signals: late, VAL cobalt 225 + KES rare earths 226": ("signals", True, [_VAL_COBALT(225), _KES_RARE(226)]),
    "signals: VAL cobalt 223 only": ("signals", True, [_VAL_COBALT(223)]),
    "signals: KES rare earths 224 only": ("signals", True, [_KES_RARE(224)]),
    "kes: raw materials 5% from 224 to end": ("kes", True, [_kes(KES_RAW, 224)]),
    "kes: all 7 at 5% for 8 weeks from 224": ("kes", True, [_kes(KES_ALL, 224, weeks=8)]),
    "kes: all 7 at 37% from 224 to end": ("kes", True, [_kes(KES_ALL, 224, ratio=0.37, jump=0.14)]),
    "kes: all 7 at 5% from 222 to end": ("kes", True, [_kes(KES_ALL, 222)]),
    "kes: late, all 7 at 5% from 227 to end": ("kes", True, [_kes(KES_ALL, 227)]),
    "other: MERROW closure 224-230 + both bans": ("other", True, [
        _VAL_COBALT(223), _KES_RARE(224), lambda p, t, n: _lane(p, t, "MERROW", 224, 7, 0.75, 3)]),
    "other: SOUTH strike repeat 226-228": ("other", True, [lambda p, t, n: _lane(p, t, "SOUTH", 226, 3, 0.8, 3)]),
    "other: KES lithium shortage 0.3x 225-230": ("other", True, [_kes(("lithium",), 225, weeks=6, ratio=0.3, jump=0.0)]),
    "other: NORTH lane closure 225-231 + VAL cobalt": ("other", True, [
        _VAL_COBALT(223), lambda p, t, n: _lane(p, t, "NORTH", 225, 7, 0.75, 3)]),
    "severe: KES all 5% from 224 + MERROW closure": ("severe", True, [
        _kes(KES_ALL, 224), lambda p, t, n: _lane(p, t, "MERROW", 224, 7, 0.75, 3)]),
    "severe: KES all 5% + VAL cobalt + SOUTH strike": ("severe", True, [
        _kes(KES_ALL, 224), _VAL_COBALT(223), lambda p, t, n: _lane(p, t, "SOUTH", 226, 3, 0.8, 3)]),
}


def weights():
    counts = pd.Series([g for g, _, _ in SCENARIOS.values()]).value_counts()
    return {name: GROUP_WEIGHTS[g] / counts[g] for name, (g, _, _) in SCENARIOS.items()}


def build(tables, name):
    """Full tables whose weeks 222-234 follow scenario `name`."""
    _, tariffs, shocks = SCENARIOS[name]
    normal = tables["suppliers"].set_index(["material", "country"]).normal_capacity_units
    path = stress._calm(tables)
    if tariffs:
        stress._tariff(path, tables)
    for shock in shocks:
        shock(path, tables, normal)
    return stress.synthetic(tables, path)


def evaluate(files, tables=None):
    """Score each submission frame in `files` ({label: frame}) on every scenario."""
    tables = read_all() if tables is None else tables
    w = weights()
    rows = []
    for name, (group, _, _) in SCENARIOS.items():
        syn = build(tables, name)
        for label, frame in files.items():
            r = score.score(frame, syn, START, END)
            sim = score.simulate(score._frame(frame, START, END), syn, START, END)
            rows.append(dict(scenario=name, group=group, weight=w[name], file=label, score=r["score"], P=r["P"],
                             F=r["F"], R=r["R"], shock_fill=r["shock_fill"],
                             unmet=float((sim.demand - sim.served).sum())))
    return pd.DataFrame(rows)


def pairs(results):
    """Per pair of files: weighted best-of-two, worst scenario, and regret against the
    best single file in each scenario (what an oracle choosing any file would get)."""
    table = results.pivot(index="scenario", columns="file", values="score")
    w = results.drop_duplicates("scenario").set_index("scenario").weight.reindex(table.index)
    ceiling = table.max(axis=1)
    rows = []
    for a, b in combinations(table.columns, 2):
        best = table[[a, b]].max(axis=1)
        regret = ceiling - best
        rows.append(dict(a=a, b=b, expected=float((w * best).sum()), worst=float(best.min()),
                         max_regret=float(regret.max()), expected_regret=float((w * regret).sum())))
    return pd.DataFrame(rows).sort_values("expected", ascending=False).reset_index(drop=True)


def select(results, tolerance=1.0):
    """The pair with the smallest max regret among pairs within `tolerance` points of the
    best weighted best-of-two."""
    p = pairs(results)
    near = p.loc[p.expected >= p.expected.max() - tolerance]
    return near.sort_values(["max_regret", "expected"], ascending=[True, False]).iloc[0]


def _load(spec):
    module, attr = spec.split(":")
    return getattr(import_module(module), attr)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate", action="append", default=[], metavar="NAME=MODULE:ATTR",
                        help="model tuple to build and evaluate; the saved v1 champion and hedge are always included")
    parser.add_argument("--csv", action="append", default=[], metavar="NAME=PATH", help="evaluate an existing CSV")
    args = parser.parse_args()
    tables = read_all()
    files = {"champion": submit.build(tables, models=submit.MODELS),
             "hedge_v1": submit.build(tables, models=submit.HEDGE_MODELS)}
    for item in args.candidate:
        name, spec = item.split("=", 1)
        files[name] = submit.build(tables, models=_load(spec))
    for item in args.csv:
        name, path = item.split("=", 1)
        files[name] = pd.read_csv(path)
    for frame in files.values():
        submit.validate(frame, tables)
    results = evaluate(files, tables)
    pd.set_option("display.width", 250)
    print(results.pivot(index="scenario", columns="file", values="score").round(2).to_string())
    print("\nweighted by group:\n" + results.assign(ws=results.weight * results.score).groupby(
        ["group", "file"]).ws.sum().unstack().round(2).to_string())
    print("\npairs (local estimates):\n" + pairs(results).round(3).to_string(index=False))
    print("\nselected:\n" + select(results).to_string())


if __name__ == "__main__":
    main()
