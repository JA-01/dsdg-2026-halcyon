"""Private-window scenario matrix (phase-2 run, #148) and best-of-two pair selection.

    python -m halcyon.scenarios_p2 --candidate kes=halcyon.strategy_kes:MODELS ...

Every scenario starts from the cutoff-221 supplier state (`stress._calm`; no supplier
is hit at 221) and adds shocks implied by the four correlated episodes open at 221,
with weights from the #152 calibration (judgment on small samples, not measured
frequencies):

- KES tariffs 0.10 -> 0.35 on aluminum + semiconductors at 224 (95%; 3/3 past
  campaigns honored); a reversal tail otherwise.
- VAL cobalt export restriction (80%; basis 11.6%, strategic-priority and license
  headlines; clean basis flags hit 6/6 historically), central onset 223.
- KES rare-earths-only export restriction (70%; lawmakers' debate body names rare
  earths, basis 9.3%), central onset 224. KES-wide restriction only 10%, on its
  historical comparator: 0.20x capacity, +3 weeks lead, persisting.
- Merrow lane disruption, all KES + SUN suppliers (35%): 0.75x capacity, +3 weeks
  lead, 3 or 8 weeks.
- An extra production shortage (stress allowance) and a "tricky" tail (old
  KES-wide-ban hypotheses, NORTH/SOUTH lane shocks) with small weight.

Export bans follow the warned-ban signature: 0.05x capacity for 6 weeks and +26% on all
three spot prices of the material; partial-severity and late-onset variants keep the
phase-2 lessons (longer lags, warnings that fizzle). All scores are local estimates.
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

# Weights: calibrated spine (85%) = KES export {none .20, rare earths .70, wide .10}
# x VAL cobalt {none .20, ban .80} x Merrow {no .65, yes .35}, with timing/severity
# variants; plus production shortage 5%, tariff reversal 3%, tricky tail 7%.
SPINE, SHORTAGE, REVERSAL, TAIL = 0.85, 0.05, 0.03, 0.07


def _hit(path, normal, material, country, start, weeks=6, ratio=0.05, jump=0.26, extra_lead=0):
    """Capacity `ratio` x normal and extra lead for one supplier; spot of all three
    suppliers of the material jumps by `jump` over the same weeks."""
    stress._ban(path, material, country, start, weeks=min(weeks, END - start + 1), ratio=ratio, jump=jump,
                normal=normal)
    span = path.week.between(start, start + weeks - 1) & (path.material == material) & (path.country == country)
    path.loc[span, "lead_time_weeks"] += extra_lead


def _lane(path, tables, lane, start, weeks, ratio, extra_lead):
    countries = set(tables["suppliers"].loc[tables["suppliers"].lane == lane, "country"])
    hit = path.week.between(start, start + weeks - 1) & path.country.isin(countries)
    path.loc[hit, "capacity_units"] *= ratio
    path.loc[hit, "lead_time_weeks"] += extra_lead


def _kes(materials, start, weeks=END, ratio=0.05, jump=0.26, extra_lead=0):
    return lambda p, t, n: [_hit(p, n, m, "KES", start, weeks, ratio, jump, extra_lead) for m in materials]


_VAL_COBALT = lambda start, ratio=0.05, jump=0.26: lambda p, t, n: _hit(p, n, "cobalt", "VAL", start, 6, ratio, jump)
_KES_RARE = lambda start, ratio=0.05, jump=0.26: lambda p, t, n: _hit(p, n, "rare_earths", "KES", start, 6, ratio, jump)
_MERROW = lambda start, weeks: lambda p, t, n: _lane(p, t, "MERROW", start, weeks, 0.75, 3)
_KES_WIDE = _kes(KES_ALL, 225, ratio=0.20, jump=0.14, extra_lead=3)

# name -> (group, weight, apply announced tariffs?, shocks); spine weights before scaling.
_SPINE = {
    "calm: tariffs only, both export warnings fizzle": ("calm", .026, []),
    "merrow: lane 223-230 only": ("merrow", .014, [_MERROW(223, 8)]),
    "signals: VAL cobalt 223 only": ("signals", .104, [_VAL_COBALT(223)]),
    "merrow: VAL cobalt 223 + lane 223-230": ("merrow", .056, [_VAL_COBALT(223), _MERROW(223, 8)]),
    "signals: KES rare earths 224 only": ("signals", .091, [_KES_RARE(224)]),
    "merrow: KES rare earths 224 + lane 223-230": ("merrow", .049, [_KES_RARE(224), _MERROW(223, 8)]),
    "signals: VAL cobalt 223 + KES rare earths 224": ("signals", .244, [_VAL_COBALT(223), _KES_RARE(224)]),
    "signals: late, VAL cobalt 225 + KES rare earths 226": ("signals", .060, [_VAL_COBALT(225), _KES_RARE(226)]),
    "signals: partial 0.30x, VAL cobalt 223 + KES rare earths 224": ("signals", .060, [
        _VAL_COBALT(223, 0.30, 0.19), _KES_RARE(224, 0.30, 0.19)]),
    "merrow: both bans + lane 223-230": ("merrow", .098, [_VAL_COBALT(223), _KES_RARE(224), _MERROW(223, 8)]),
    "merrow: both bans + lane 223-225": ("merrow", .098, [_VAL_COBALT(223), _KES_RARE(224), _MERROW(223, 3)]),
    "kes_wide: KES 0.20x +3 lead from 225": ("kes_wide", .020, [_KES_WIDE]),
    "kes_wide: KES 0.20x +3 lead from 225 + VAL cobalt 223": ("kes_wide", .080, [_KES_WIDE, _VAL_COBALT(223)]),
}
_TAIL = {
    "tail: KES all 5% from 224 + MERROW closure": [_kes(KES_ALL, 224), _MERROW(224, 7)],
    "tail: KES all 7 at 37% from 224 (v1 hedge hypothesis)": [_kes(KES_ALL, 224, ratio=0.37, jump=0.14)],
    "tail: NORTH lane closure 225-231 + VAL cobalt": [
        _VAL_COBALT(223), lambda p, t, n: _lane(p, t, "NORTH", 225, 7, 0.75, 3)],
    "tail: SOUTH strike repeat 226-228 + both bans": [
        _VAL_COBALT(223), _KES_RARE(224), lambda p, t, n: _lane(p, t, "SOUTH", 226, 3, 0.8, 3)],
}
SCENARIOS = {name: (group, SPINE * w, True, shocks) for name, (group, w, shocks) in _SPINE.items()}
SCENARIOS["shortage: both bans + KES lithium 0.3x 225-230"] = ("shortage", SHORTAGE, True, [
    _VAL_COBALT(223), _KES_RARE(224), _kes(("lithium",), 225, weeks=6, ratio=0.3, jump=0.0)])
SCENARIOS["calm: tariff reversed, warnings fizzle"] = ("calm", REVERSAL, False, [])
SCENARIOS.update({name: ("tail", TAIL / len(_TAIL), True, shocks) for name, shocks in _TAIL.items()})


def weights():
    return {name: w for name, (_, w, _, _) in SCENARIOS.items()}


def build(tables, name):
    """Full tables whose weeks 222-234 follow scenario `name`."""
    _, _, tariffs, shocks = SCENARIOS[name]
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
    for name, (group, _, _, _) in SCENARIOS.items():
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
