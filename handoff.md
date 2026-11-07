# Bay Area Builders - Phase 2 handoff

**Updated:** Nov 7, 2026, following the 16:31-21:40 UTC run.  
**Read for details:** `summary.md` (history), `AGENTS.md` (rules/owners), `docs/adr/0001-architecture.md` (contracts/evaluation), `kaggle_instructions.md` (contest). **Board:** GitHub issue #75 (`tools/board`).

## Current state

- `main` last reported **80 passing tests** and a valid 260-row submission pipeline. Recheck before releasing.
- **Best official public:** **70.76**, `basecase_honest-public.csv` (weeks 209-221, cutoff 208). Earlier receipts: 60.75 and 68.96. Current private result **unknown**.
- **Selection:** 11 past 13-week windows, cutoffs 65, 78, ..., 195. Latest **local** mean **51.68**, worst **34.45**. Select models on these windows, **not** public weeks 209-221.
- Local scorer is approximate (historical comparisons differ from Kaggle by roughly 0.5-1.3 points). Always label numbers `local estimate` or `official`.
- Private candidate weeks 222-234 use cutoff 221. Public predictions must remain cutoff-208-safe.
- Databricks `workspace.halcyon`; existing job **838646686083545**, AV's run-as identity. Last recorded MLflow run: `031a0c1acf834b40abb1d703bd5f76f7`. **Do not create jobs or change grants.**

## Current final candidates (`artifacts/`)

| File | Public weeks 209-221 | Private weeks 222-234 |
|---|---|---|
| `basecase_honest-public.csv` | Honest forecast; **70.76 official** | Base |
| `KESban-hedge_honest-public.csv` | Same as honest base | Kestria-wide-ban hedge |
| `basecase_copied-public.csv` | Released actuals/hindsight orders | Same as base |
| `KESban-hedge_copied-public.csv` | Same copied public rows | Same as hedge |

**Before final selections, humans must confirm:** (1) whether the two selected files are scored **best-of-two or averaged**, and (2) whether using released actuals in copied-public files is **allowed** under contest rules. Do not assume either. The base wins more mild synthetic stress cases; the hedge mainly helps under a broad Kestria ban. These are local scenarios, not private scores.

## UPDATED CONFIRMED FINAL SCORING RULE: 
Teams select up to two final Kaggle submissions. Only the higher private-leaderboard score of those two counts, not their average.

## Next actions

1. Preserve the working revision, existing files, official receipts, and run artifacts. Confirm `main` and test status.
2. Assign only independent, score-relevant experiments. The futures-basis onset-timing idea is low-confidence (~+0.3 estimated); don't let it delay delivery.
3. Evaluate experiments on the **11 selection origins** (mean, worst, regressions), keep a valid baseline, and avoid selecting on public holdout results.
4. Confirm final selection rules. Have humans make Kaggle selections and upload the ~3-minute video **before Sunday Nov 8, 12:00 PM Central** (verify live deadlines). **Agents never upload to Kaggle.**

## Build and verification

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m halcyon.score
.venv/bin/python -m halcyon.stress
for spec in "basecase_honest-public:" "KESban-hedge_honest-public:--hedge" \
            "basecase_copied-public:--released-public" "KESban-hedge_copied-public:--hedge --released-public"; do
  n=${spec%%:*}; a=${spec#*:}
  .venv/bin/python -m halcyon.submit $a --out artifacts/$n.csv
done
# Databricks packages committed origin/main: test, commit and push first.
git fetch
.venv/bin/python tools/databricks/bootstrap.py --job-id 838646686083545
```

Validate each CSV. Honest/copied variants of the **same** model must have identical private rows; base/hedge variants with the **same** public mode must have identical public rows. Compare Databricks and local numerical values within **1e-9**; byte hashes may differ from formatting. Remote output paths are in `result.json`.

## Board and handoff rules

- One orchestrator; one owner per issue/file. Workers may independently experiment and self-merge scoped changes when tests and acceptance pass; coordinate shared-interface and release changes.
- Board #75 receives assignments, decisions, measured results, real blockers, and necessary questions only. No ACK chains or perpetual `tools/board wait` loops.
- If blocked, post the dependency, switch tasks or **sign off**. Do not idle while waiting on other agents.
- Never push failing tests. For model changes, use 11-origin selection. The public 209-221 window is already exposed: **do not repeatedly score it to choose variants**. Any check should be a limited release audit, not a tuning loop.
- Before ending, update this file with current `main` SHA, open issues/owners, verified candidate paths, most recent local selection metrics, Databricks run/official receipts, blockers, and the next action. Keep longer explanations in `summary.md`.
