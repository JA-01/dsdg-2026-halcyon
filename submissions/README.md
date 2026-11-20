# Submissions

Every final candidate we built, with its SHA-256 prefix in the file name. Each file is a valid 260-row Kaggle submission covering weeks 209–234.

## The two files we selected

Kaggle counted the better private score (weeks 222–234) of these two. Together they placed **1st on the private leaderboard with 71.40**.

| File | Strategy | How to rebuild |
|---|---|---|
| [`final_primary_released_public_5f77482f.csv`](final_primary_released_public_5f77482f.csv) | **T**: news-ladder and futures-basis probabilities with the announced-tariff hold, price model, LP ordering policy | `python -m halcyon.submit --released-public` (byte-identical) |
| [`final_v3_minimax_SCEN_T_released_public_a647dfdb.csv`](final_v3_minimax_SCEN_T_released_public_a647dfdb.csv) | **SCEN_T**: the same forecasts, ordered by the scenario MILP that plans against historical shock paths | See below |

Both files fill the public weeks (209–221) with the released outcomes, so their public rows are identical and score about 96.9 locally. Those rows cannot change the private score. The honest version of the primary, which forecast the public weeks from week-208 data only, is `final_primary_b9ae48a9.csv` (70.76 official public).

To rebuild SCEN_T's private rows (they match the uploaded file exactly on our machines):

```python
from halcyon import submit, price, policy_scenarios, strategy_expected
from halcyon.data import read_all

tables = read_all("data")
scen_t = submit.build(tables, models=(strategy_expected.predict_tariff, price.predict, policy_scenarios.plan))
submit.validate(scen_t, tables)
```

The MILP accepts any plan within 0.01% of optimal, so another machine can return a different plan that is just as good. The file here holds the exact uploaded bytes.

## Other candidates

| File | Strategy | Why it wasn't selected |
|---|---|---|
| `final_primary_b9ae48a9.csv` | T with honest public rows | Same private rows as the selected primary |
| `final_hedge_86eb8095.csv` | **H_T**: scenario MILP plus a Kestria export-ban overlay from week 224, honest public rows (`--hedge`) | Our final-pair-v2 recommendation; SCEN_T replaced it at the last minute |
| `final_hedge_released_public_7233dfed.csv` | H_T with released public rows (`--hedge --released-public`) | As above |
| `final_v3_minimax_VAL_SCEN_released_public_38995329.csv` | Scenario MILP planning for a Valdmar collapse from week 223 | Top of the minimax-regret ranking, but not chosen |
| `final_v3_minimax_VAL_LP_released_public_e283e6bc.csv` | LP with the same Valdmar overlay | Identical to T on every historical window |
| `final_v3_minimax_E_full_released_public_4e6f9987.csv` | "Expected world" plan (`strategy_expected.MODELS`) | Lost 11 points on the real Phase 2 window |
| `final_v3_minimax_KES_released_public_fbc06536.csv` | Kestria escalation specialist (`strategy_kes`) | Weaker partner than H_T on the scenario matrix |
| `final_v3_minimax_SHOCK_released_public_715ce28a.csv` | Broad shock insurance (`strategy_shock`) | Weaker partner than H_T on the scenario matrix |
| `final_primary_0da997d7.csv`, `final_hedge_cf481a44.csv` | Final pair v1, before the tariff hold | Superseded by v2 |

[`handoff.md`](../handoff.md) has the full evidence: per-origin backtests, the 19-scenario private matrix, stress paths and every rejected alternative.
