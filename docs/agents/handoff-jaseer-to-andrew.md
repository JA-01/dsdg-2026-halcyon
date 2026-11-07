# Handoff: Jaseer's Codex role → Andrew's agent

Prepared 2026-11-07 ~03:10Z by Jaseer's Codex, per Jaseer's instruction that
Andrew's agent takes over this role. Read this file, then post an ack on the
message board (`tools/board post "[Andrew's <agent>] ..."`; run
`tools/board unread` first). Repo `main` was `b7998d6` when written.

## 1. Role being transferred

Jaseer's Codex owned, after Andrew explicitly handed off #13 on the board:

- **#13 demo/release package**: `notebooks/demo/`, `docs/demo/`,
  `docs/release-checklist.md`, video script, exercised video artifact.
- **Release acceptance review**: independent readback of real artifacts
  (CSV/MLflow/Delta/gold), selection-rule verification, failure reproduction
  and follow-up with owners. Tracking issue: GitHub #16.
- **Environment support**: Databricks ACL grants/readback, schema SELECT,
  scoped job sharing, deployed notebook refresh. (Source edits in
  `tools/databricks/` still require Jaseer per AGENTS.md.)
- **Board coordination** for the above; ownership of code stays with module
  owners (Andrew: pipeline/Delta/MLflow; Tejas: forecasting; AV: policy).

Do not duplicate owner work. Verify, reproduce, route defects to owners, and
keep the acceptance list honest.

## 2. Current repo / PR state

- `main` = `b7998d6` (merge of PR #38, AV's week-key fix; authored `002b719`).
- **PR #38 already merged** while this handoff was being written. Jaseer's Codex
  verified it pre-merge at `002b719`: full suite **363 passed, 1 skipped**
  (optional native Spark), the original fractional-week defect rejected
  (`forecasts.target_week: invalid week key ...`), whole-valued floats
  (`209.0`) still accepted without mutating frames, and export bytes unchanged.
  Post-merge sanity on `main`: sample CSV valid (`689417b5…1dd7`), Spark-gate
  CSV valid (`112a589e…4cb0`), fractional input rejected with `ContractError`.
- **Branch `36-forecast-artifact-acceptance`** (Tejas, commit `500084c`) adds
  `notebooks/forecasting/validate_run.py` + test + modeling docs. No PR yet.
  Extract with
  `git show origin/36-forecast-artifact-acceptance:notebooks/forecasting/validate_run.py > /tmp/validate_run_36.py`.
  Jaseer's Codex ran it successfully (see §4). Merge is Tejas's call.
- Merged PRs from this role: #18 (evaluator recovery-history contract), #28
  (demo package), #31 (rehearsal labeling + stale demo-output cleanup), #33
  (canonical comparison manifest consumer). No open PRs by this role.

## 3. Verified evidence inventory (do not re-verify unless it changed)

Release for all Phase 1 artifacts: `weeks-1-208-18caf03f890c`; all 12 tables
pinned at Delta version 1; the 10 local CSVs match the remote immutable
manifest SHA-256s. Workspace `https://dbc-7e1d4af4-7a60.cloud.databricks.com`,
warehouse `ece93a7877e9e544`, experiment `/Shared/halcyon/runs`
(id `2562241450728952`), demo experiment `/Shared/halcyon/demo/runs`
(id `2562241450728971`). Run artifacts under
`/Volumes/workspace/halcyon/artifacts/runs/<run_id>/`. Local evidence tree:
`outputs/` (gitignored) — `final-evidence/`, `demo-source/`, `demo/`,
`demo-live/`, `demo-video/`.

| Evidence | IDs | Status checked by Jaseer's Codex |
| --- | --- | --- |
| Baseline run | job `793929914775702`, run `352305866720915`; MLflow `c0001ec0e4c847b3821ad74c3bf422b2`; CSV `3f5a17f3…486c` | SUCCESS; MLflow FINISHED; gold 130+130 per window per table via SQL |
| Policy candidate | run `1098642218506545`; MLflow `74752ffecc3449e29dfd7494ed47ad80`; CSV `734c30db…1247` | SUCCESS; CSV validated; `inventory_cover` + provisional forecast |
| **Frozen dev selection** | MLflow `16866c7e72844d24a16510f18d140f2d`, clean `1cc65b6`, `holdout_used=false` | recomputed sums: historical+optimized 19,122,665.23 vs price+optimized 19,126,449.51 — only these within 1%; mean shock-fill equal; selection = **historical+optimized** (simplicity tie-break), runner-up **price+optimized**, matches posted rule |
| **Holdout (once)** | MLflow `e4f7709b072745acb21e8e882cb87dfe`, clean `58392a3` | dev end_time < holdout start_time; only baseline+selected; specs/source hashes identical to dev; proxy Δcost −1.492% / −0.530%, fill regressions disclosed |
| **Spark feature gate** | MLflow `035752581af5484189f162a88787a43f`; job `819028526298241`; CSV `112a589e…4cb0` | SUCCESS in 641.554s (<1800s); `silver_features` 260 rows/50 cols (130+130), unique full-context keys, all 43 model features present; repeated export still valid |
| Tejas acceptance harness on that gate | `acceptance_report.json` in the same local dir | `remote_acceptance_complete=true`: no refit; 260 inference rows match saved forecasts at 1e-12; training 11,120 rows targets 27–208; Spark↔pandas parity true; job below limit |
| Phase 2 rehearsal | job run `644753599999402`; MLflow `290fbf06c7f549ffab6748340e9d2b89` | SUCCESS; cutoff 208 rehearsal (labeled, **not** real week 221); 130 archived public rows byte-identical to archive `a289e8d2b57240fe8dfd7955f9bfb89b` |
| Demo output | submit run `282966950685740` (SUCCESS); demo MLflow `4567c43718154782ab288e84a1a3bb6c` | live Delta `DESCRIBE HISTORY` + pinned Spark cutoff join + gold 260/260 + MLflow readback persisted to `/Volumes/workspace/halcyon/artifacts/demo/74752ffecc3449e29dfd7494ed47ad80/` |
| Methodology video | local + shared `…/demo/74752ffecc3449e29dfd7494ed47ad80/video/Bay-Area-Builders-methodology.mp4`; SHA `74bf5a020ac5a458e11f3cb7fdee3ffacc01e37282679138cfa395358d31d0bc` | 185.05s, 1920×1080 H.264/AAC; slides + synthetic voiceover; remote hash readback matched; **not uploaded to organizers** |
| Combined 2×2 interop (local) | `outputs/acceptance/local-9928c74f1880`, SHA `c5c6615b…1e191e6` | one-off smoke joining `historical_risk_pooled_price_v1` + `inventory_milp`; module interop only, not promotion |
| Not-yet-on-Delta smoke | `local-01b33ade57ef` (Tejas) SHA `b84b276d…90f3` | price-only + inventory; local only |

## 4. What is still open (MVP stop gate = these close)

1. ~~AV week-key fix~~ — merged (#38). One residual note: run `pytest -q` on
   `main` yourself once after any further merges.
2. **Andrew: selected + runner-up real Delta runs** on clean `main`, using
   `configs/phase1_selected_delta.json` / `phase1_runner_up_delta.json` (see
   PR #34), then post both run IDs. Acceptance for each: exact-byte validation
   (`python -m halcyon.submission <csv>`), manifest/gold check (130 unique keys
   per window per gold table), MLflow readback, `dirty=false` manifest. If a
   forecaster/policy config changes even slightly, re-freeze before reuse.
3. **Tejas: merge the acceptance harness** (branch above) once he confirms;
   it has already executed green on the Spark-gate run.
4. **Phase 2 on genuine data** (external prerequisite): organizer week-221
   release → `tools/databricks/bootstrap.py` new immutable release →
   `python -m halcyon.phase2 --release <id> --archive-run <phase1_run>` →
   `python -m halcyon.deploy --config configs/phase2_<id>.json --run` →
   validate bytes; archived public rows must stay byte-identical, private 222–234
   regenerated at cutoff 221. Rehearsal path is proven only for the mechanics.
5. **Human-only delivery** (never claim these): Kaggle team merge before first
   submission; ≤5 submissions/team/day; Databricks opt-in by Sat 18:00 CT;
   up to 2 final selections; ~3-minute video upload by Sun 12:00 CT. AV (human)
   asked that any final-CSV announcement start with **"NEW SUBMISSION CSV"**.

## 5. Known gotchas (save yourself an hour)

- **Python env**: use `/Users/jaseer/.venvs/dsdg-hackathon/bin/python` (3.12).
  `pytest 9.2.0` was installed into it by this role. The eval kernel is Python
  3.14 — pandas/numpy do **not** import in-kernel from this venv; run
  `subprocess` with the venv python for pandas work.
- **Databricks auth**: CLI/SDK profile `halcyon` (identity `jaseer@jaseer.com`).
  No new key needed. Warehouse id above. SDK pattern used everywhere:
  `w.files.download('/Volumes/…').contents.read()`.
- **ACLs**: training job `793929914775702` — `ak173@illinois.edu` is `IS_OWNER`;
  `tejasb3@illinois.edu` and `aryavratmishra0@gmail.com` were granted
  `CAN_MANAGE_RUN` and read back. Do not add the owner as a run-manager
  (API rejects "exactly one owner"). Jaseer has explicit schema `SELECT` on
  `workspace.halcyon` (ownership alone did not grant it — inherited grants were
  checked). Teammates inherit SELECT/MODIFY.
- **Demo notebook** is deployed at `/Workspace/Shared/halcyon/demo/run_demo`
  (source SHA `69903806…e709`, post-PR#33). The successful live run
  `282966950685740` predates PR #31/#33; those changed paths were exercised
  locally only (rehearsal labeling, stale-output cleanup with tamper guard,
  canonical comparison-manifest consumption). Re-run the live notebook if you
  want a live artifact newer than that.
- **Video refresh policy**: current video narrates the *policy candidate with
  provisional forecast*, not the frozen selection. If the final choice is used
  for submission, either refresh narration/slides from the final artifacts or
  keep the video as an explicitly labeled fallback and note the difference.
- **Board tool**: `tools/board unread|read|post|wait`; posts must start with
  `[<human>'s <agent>]` and mention logins (`@andrewkwon0804-web`, `@tbhojo`,
  `@AV-01`, `@JA-01`, `@all`). Read before commits and after merges.
- **Comparison artifacts**: new runs emit canonical `manifest.json`
  (embedded config, source hashes, code state, assumptions); older runs have
  `config.json` without lineage. The demo consumer in `notebooks/demo/run_demo.py`
  handles both and discloses gaps.

## 6. Do-not-claim list (keep the release honest)

Not established by any artifact seen this session: official/leaderboard score,
simulator parity with the organizer, LLM/news improvement, Phase 2 on genuine
data, final Kaggle selections, opt-in, or any external upload. Proxy comparison
economics must stay labeled `proxy`. The `not_evaluated` demo runs measure only
export feasibility. The holdout was evaluated once (per rule) and the selection
stays dev-frozen; do not re-tune against it.

## 7. Quick commands used for acceptance

```bash
VENV=/Users/jaseer/.venvs/dsdg-hackathon/bin/python
$VENV -m halcyon.submission <submission.csv>            # exact-byte validation
$VENV -m pytest -q                                     # full suite
# read-only forecast-artifact acceptance (branch 36):
git show origin/36-forecast-artifact-acceptance:notebooks/forecasting/validate_run.py > /tmp/validate_run_36.py
PYTHONPATH=$PWD $VENV /tmp/validate_run_36.py \
  --run-dir outputs/final-evidence/035752581af5484189f162a88787a43f \
  --data-dir data \
  --features outputs/final-evidence/035752581af5484189f162a88787a43f/silver_features.csv \
  --job-report outputs/final-evidence/035752581af5484189f162a88787a43f/job_run.json \
  --output  outputs/final-evidence/035752581af5484189f162a88787a43f/acceptance_report.json
```

Acceptance notes live next to the downloaded artifacts as
`acceptance_review.json` / `acceptance_report.json` under
`outputs/final-evidence/<run_id>/`.
