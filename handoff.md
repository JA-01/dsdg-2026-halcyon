# Bay Area Builders - Phase 2 handoff

**Updated:** Nov 7, 2026, orchestrator continuation #124–126.  
**Sole orchestrator:** Tejas's Codex (@tbhojo), by human-directed handoff from AV's agent.  
**Read:** `summary.md`, `AGENTS.md`, `docs/adr/0001-architecture.md`, `kaggle_instructions.md`. **Board:** GitHub issue #75.

## Current state

- Verified `main` model revision: **`dcf10421d81a77add7794be2156aa35c58b5a7b1`**. This continuation changes documentation only; model code and the selected incumbent remain unchanged. The documentation PR closes #124; its merge revision is posted on the board.
- **80 tests pass**. All four documented CLI builds validate **260 rows** each.
- **Best official public: 70.76**, original `basecase_honest-public.csv` (recorded SHA prefix `984a0b19`, cutoff 208). Earlier official receipts: 60.75 and 68.96. Private result remains **unknown**. No Kaggle uploads or selections were made by agents.
- **Local estimate**, all 11 selection origins (65, 78, ..., 195): mean **51.674722**, worst **34.452428**; mean **P 0.259045 / F 0.719879 / R 0.503608**. Scorer approximation differs from Kaggle; do not label these official.
- Public rows remain cutoff-208-safe; private rows use cutoff 221. No 209–221 scoring or tuning occurred in this continuation.

## Independent experiments and disposition

| Issue / owner | Objective | Local mean / worst | Decision |
|---|---|---|---|
| #125 / @tbhojo, BasisOnset worker | First-supplier-flag-age Brier hazard | 51.686914 / 34.452428 | Reject: only +0.012192 mean; score gain only at 156 |
| #126 / @tbhojo, WarningHedge worker | Bolder warning-confidence candidate | Best 51.710197 / 34.452428 | Reject: only +0.035475 mean/best-of-two; gain only at 156 |

Both evaluated every historical selection origin, with zero total-score regressions and unchanged F/R. Neither reached the predeclared +0.2 adoption gate. #125's 11 inference/post-cutoff-tamper smokes passed. Both issues are closed; rejected code/tests were removed. Full per-origin evidence is recorded in the issues. No shared interface changed, no model was merged, and there are **no open worker assignments**. #124 closes with the documentation PR.

## Candidate files and preservation

| File in `artifacts/` | Public weeks 209–221 | Private weeks 222–234 | Local rebuilt SHA prefix |
|---|---|---|---|
| `basecase_honest-public.csv` | Honest forecast | Base | `0da997d7` |
| `KESban-hedge_honest-public.csv` | Same honest public block | KES-wide-ban hedge | `2103b136` |
| `basecase_copied-public.csv` | Released truth/hindsight orders | Same as honest base | `12e44e0c` |
| `KESban-hedge_copied-public.csv` | Same copied public block | Same as honest hedge | `d7b42a33` |

The checkout initially contained **no final artifacts**; these are local rebuilds, not newly scored official files. Original recorded prefixes were `984a0b19`, `bdbd1eb2`, `7d20c7cf`, `d7b42a33`, respectively. Three rebuilt hashes differ; original bytes are not available here to establish numerical parity. **Preserve the original submitted files on the prior workstation/Kaggle and the 70.76 receipt; do not replace an existing official selection merely because a rebuild exists.** Full rebuilt hashes and verification evidence are in `artifacts/release-verification.json` (local, gitignored).

Exercised checks:
- Exact numerical equality of base/hedge public rows within each public mode.
- Exact numerical equality of honest/copied private rows within each model.
- Both honest public blocks equal their cutoff-208 builds within 1e-12.
- All seller/share/forecast/order constraints; copied-public labels/prices match released truth.
- Base and hedge differ on 64 private rows. Synthetic stress reproduces `summary.md` §8: base wins S0–S3, hedge S4–S5; both **match** naive shock fill in S0–S2 and **beat** it in S3–S5. These are local scenarios, not private scores.

## Confirmed scoring rule and human next actions

**Confirmed:** only the higher private score of up to two selected submissions counts, not their average. The complementary honest base/hedge pair remains the recommendation; humans alone authorize uploads and final selections.

1. Retain the original 70.76 official base-case submission/receipt. Humans verify the desired base/hedge final selections in Kaggle and upload the hedge if still needed.
2. Copied-public permission remains unconfirmed here. Use those files only if humans confirm the organizers allow released-answer public rows; the private blocks are unchanged.
3. Humans complete the approximately 3-minute video and final selections before **Sunday Nov 8, 12:00 PM Central**, per competition instructions; verify the live competition deadline.
4. No agent work is waiting on another worker. Do not restart rejected experiments without new evidence or a new assignment.

## Databricks state and authentication blocker

- Existing job **838646686083545**, `workspace.halcyon`, AV's run-as identity. **Never create another job or change grants.**
- Last **recorded** successful run: **1000919729689519**; MLflow **`031a0c1acf834b40abb1d703bd5f76f7`**. Prior board reported local/remote parity within 2e-11. That remote result was **not reverified** this session.
- Exact committed-source preflight at `dcf1042` passed: **260 primary rows + 260 hedge rows, all 10 CSV schemas**.
- This workstation has **no `~/.databrickscfg` and no `DATABRICKS_*` environment credentials**; `databricks auth profiles` fails for missing configuration. No remote writes or new run were attempted. No model changed, so a fresh release run was unnecessary.
- If a future model is accepted, finish tests/11-origin evaluation, commit and push first. An authorized workstation must then run the **existing** job and compare downloaded CSV values within 1e-9; never claim remote parity from local preflight alone.

## Reproduce without overwriting original submissions

Choose a fresh output directory before rebuilding; preserve uploaded originals.

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m halcyon.score
.venv/bin/python -m halcyon.stress
.venv/bin/python tools/databricks/bootstrap.py --prepare-only --source-ref origin/main
# Repeat the documented modes into a NEW directory, not over original uploads:
.venv/bin/python -m halcyon.submit --out artifacts/rebuild/basecase_honest-public.csv
.venv/bin/python -m halcyon.submit --hedge --out artifacts/rebuild/KESban-hedge_honest-public.csv
.venv/bin/python -m halcyon.submit --released-public --out artifacts/rebuild/basecase_copied-public.csv
.venv/bin/python -m halcyon.submit --hedge --released-public --out artifacts/rebuild/KESban-hedge_copied-public.csv
# Only after a tested model change is pushed, on an authenticated workstation:
git fetch origin
.venv/bin/python tools/databricks/bootstrap.py --job-id 838646686083545
```

Board posts are assignments, decisions, measured results, real blockers, or necessary questions only. No ACK chains, worker waits, or perpetual watchers.

**Sign-off:** Tejas's Codex SIGNING OFF. Independent workers are released; the remaining actions above are human-owned or require authorized Databricks authentication.
