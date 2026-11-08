"""Private-window stress test: score final files on synthetic weeks 222-234.

    python -m halcyon.stress

Weeks 222-234 are unreleased, so each scenario builds a synthetic supply path
from the cutoff-221 state and then applies shock signatures from issue #114:
an export ban leaves 0.05x capacity for 8 weeks and lifts all three spot prices
by 26%; a strait closure leaves 0.75x capacity lane-wide with +3 weeks lead and
no price jump; a tariff changes the rate only. Labels follow the exact rule:
disrupted if any supplier has capacity < 0.9x normal, lead > base, or tariff
> base. These are scenarios, not forecasts; the scores are local estimates.
"""

import numpy as np
import pandas as pd

from halcyon import score, submit
from halcyon.data import read_all

START, END, CUTOFF = 222, 234, 221
BAN, BAN_WEEKS, BAN_JUMP = 0.05, 8, 0.26


def _calm(tables):
    """Weeks 222-234 with every supplier as it was at the cutoff."""
    sh = tables["supply_history"]
    recent = sh.loc[sh.week.between(CUTOFF - 3, CUTOFF)].groupby(["material", "country"])
    now = sh.loc[sh.week == CUTOFF].set_index(["material", "country"])
    base = tables["suppliers"].set_index(["material", "country"])
    state = pd.DataFrame({"capacity_units": now.capacity_units,  # the state AT the cutoff
                          "landed_cost": recent.landed_cost.mean()}).join(base[["base_lead_weeks"]])
    spot = tables["prices"].loc[tables["prices"].week == CUTOFF].set_index(["material", "country"]).spot_price
    tariff = tables["tariffs"].loc[tables["tariffs"].week == CUTOFF].set_index(["material", "country"]).tariff_rate
    rows = [dict(week=w, material=m, country=c, capacity_units=r.capacity_units,
                 lead_time_weeks=int(r.base_lead_weeks), landed_cost=r.landed_cost,
                 spot=spot[(m, c)], tariff=tariff[(m, c)])
            for w in range(START, END + 1) for (m, c), r in state.iterrows()]
    return pd.DataFrame(rows)


def _tariff(path, tables):
    """KES aluminum and semiconductors 0.10 -> 0.35 from week 224 (as announced)."""
    now = tables["tariffs"].loc[(tables["tariffs"].week == CUTOFF) & tables["tariffs"].announced_rate.notna()]
    for r in now.itertuples():
        hit = (path.material == r.material) & (path.country == r.country) & (path.week >= r.announced_effective_week)
        path.loc[hit, "landed_cost"] += path.loc[hit, "spot"] * (r.announced_rate - r.tariff_rate)
        path.loc[hit, "tariff"] = r.announced_rate


def _ban(path, material, country, start, weeks=BAN_WEEKS, ratio=BAN, jump=BAN_JUMP, normal=None):
    span = path.week.between(start, start + weeks - 1)
    sup = span & (path.material == material) & (path.country == country)
    path.loc[sup, "capacity_units"] = ratio * normal[(material, country)]
    mat = span & (path.material == material)  # all three spot prices jump together
    path.loc[mat, "landed_cost"] += path.loc[mat, "spot"] * jump
    path.loc[mat, "spot"] *= 1 + jump


def _closure(path, tables, lane, start, end):
    countries = set(tables["suppliers"].loc[tables["suppliers"].lane == lane, "country"])
    hit = path.week.between(start, end) & path.country.isin(countries)
    path.loc[hit, "capacity_units"] *= 0.75
    path.loc[hit, "lead_time_weeks"] += 3


def scenario(tables, name):
    """Full tables with synthetic supply_history and outcomes for weeks 222-234."""
    sup = tables["suppliers"].set_index(["material", "country"])
    normal = sup.normal_capacity_units
    path = _calm(tables)
    if name != "S0 calm":
        _tariff(path, tables)
    if name in ("S2 +VAL cobalt ban", "S3 +KES rare_earths ban", "S4 +MERROW closure"):
        _ban(path, "cobalt", "VAL", 223, normal=normal)
    if name in ("S3 +KES rare_earths ban", "S4 +MERROW closure"):
        _ban(path, "rare_earths", "KES", 224, normal=normal)
    if name == "S4 +MERROW closure":
        _closure(path, tables, "MERROW", 224, 230)
    if name == "S5 KES-wide ban":
        for m in sup.xs("KES", level="country").index:
            _ban(path, m, "KES", 224, weeks=END - 224 + 1, ratio=0.37, jump=0.14, normal=normal)
    return synthetic(tables, path)


def synthetic(tables, path):
    """Full tables whose weeks 222-234 follow `path`, with labels from the exact rule."""
    sup = tables["suppliers"].set_index(["material", "country"])
    flags = path.join(sup[["normal_capacity_units", "base_lead_weeks", "base_tariff"]], on=["material", "country"])
    flags["hit"] = ((flags.capacity_units < 0.9 * flags.normal_capacity_units)
                    | (flags.lead_time_weeks > flags.base_lead_weeks) | (flags.tariff > flags.base_tariff + 1e-9))
    outcomes = flags.groupby(["week", "material"]).agg(disrupted=("hit", "max"), benchmark_price=("spot", "mean"))
    outcomes = outcomes.reset_index().assign(disrupted=lambda f: f.disrupted.astype(int))
    out = dict(tables)
    keep = lambda f: f.loc[f.week <= CUTOFF]
    out["supply_history"] = pd.concat([keep(tables["supply_history"]),
                                       path[["week", "material", "country", "capacity_units",
                                             "lead_time_weeks", "landed_cost"]]], ignore_index=True)
    out["outcomes"] = pd.concat([keep(tables["outcomes"]), outcomes], ignore_index=True)
    return out


SCENARIOS = ("S0 calm", "S1 tariff", "S2 +VAL cobalt ban", "S3 +KES rare_earths ban",
             "S4 +MERROW closure", "S5 KES-wide ban")


def run(tables=None, files=None):
    tables = read_all() if tables is None else tables
    if files is None:
        files = {"primary": submit.build(tables), "hedge": submit.build(tables, models=submit.HEDGE_MODELS)}
    rows = []
    for name in SCENARIOS:
        synthetic = scenario(tables, name)
        for label, frame in files.items():
            r = score.score(frame, synthetic, START, END)
            rows.append(dict(scenario=name, file=label, score=r["score"], P=r["P"], F=r["F"], F_raw=r["F_raw"],
                             fill=r["shock_fill"], naive_fill=r["naive_shock_fill"], R=r["R"]))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    result = run()
    print(result.round(3).to_string(index=False))
    print("\nbest-of-2 per scenario:\n" + result.groupby("scenario").score.max().round(2).to_string())
