# Campaign 128 postmortem and restart handoff

**Status: HUMAN-CANCELLED — ALL AGENTS SIGNED OFF.** Updated 2026-11-08 05:09 UTC.

This is a state report, not an instruction to resume. It applies to the next orchestrator **or** worker. Nobody is waiting for an ACK, a merge, a model fix, a Kaggle result, or a Databricks run. A new human directive must designate the next orchestrator and assign new work.

## 1. Verdict in one minute

- **Best official public remains 70.76. No public improvement was achieved.** The human uploaded our new scope/state CSV and reported **70.76 again**. Do not rerun a check to confirm that report or describe a local estimate as an official gain.
- All three actual teammates completed three substantial experiments each. Three challenger modules survived, but **none is wired into the live submission defaults**. Historical gains are promising, not private-score proof.
- Independent review caught two FX parser/lifecycle defects and an optimistic scenario-fill relaxation. The policy defect was fixed in PR #137; the FX defects remain unresolved. Cancellation stopped further integration, not a completed release.
- Tejas's uncommitted scope-model default cutover was **reverted exactly**. The incumbent, original artifacts, and human's existing selections were not replaced. No agent uploaded to Kaggle or ran a new Databricks job.
- **Start next with the corrected scenario-policy candidate and the unresolved FX correctness issue, not more release machinery or repeated warning multipliers.** Decide what to adopt only after reading the evidence below.

## 2. Exact code and workspace state

Model-source snapshot on `origin/main`: **`1314596b983a619ba4fbeb208c11299ad644cfa3`** (PR #137). The cancellation documentation adds no model changes.

Live `halcyon/submit.py` still defines:

```python
MODELS = (disruption_news.predict, price.predict, policy.plan)
HEDGE_MODELS = (partial(events.predict_shock, base=disruption_news.predict),
                price.predict, events.plan_shock)
```

The base/hedge public rows are currently identical. The hedge is the existing absolute-week-224 KES capacity×0.37/probability-floor0.6 hypothesis. General scenario-policy alternatives are **not** silently substituted.

Merged, **unwired** challenger sources:

| Module / owner | Source history | Current use |
|---|---|---|
| `halcyon/disruption_scope.py` / @JA-01 | PR #133, `515de8a` | Explicit scope upload only; not a default |
| `halcyon/disruption_fx.py` / @AV-01 | PR #135, `1b496b0` | Experimental; blocked by two unfixed defects |
| `halcyon/policy_scenarios.py` / @andrewkwon0804-web | PR #134 → #136 → **#137** | Corrected exact-fill challenger and combined KES overlay; not a default |

The original worktree remains on `128-score-campaign`. **User changes:** `orchestrator.md` and `worker.md` are deleted; `databricks-requirements.md`, `halcyon.egg-info/`, and `outputs/` are untracked. Do not restore, delete, stage, stash, or reset those changes without the human's instruction. No model-wiring change from this session remains there.

**Important local-code trap:** that original worktree last synchronized model code at `1b496b0`, before the corrected policy landed. Its local `policy_scenarios.py` is still the pre-fix LP. The exact-fill MILP is on `origin/main` and in the clean worktree above, not automatically in the original checkout. Do not run the old local challenger and mistake it for PR #137.

To publish only these documents without touching user changes, cancellation used clean worktree `/tmp/halcyon-cancel-128-20261108T050454Z`, branch `128-cancel-handoff-20261108t050454z`, based on `origin/main`. The abandoned draft PR #132 is superseded, not a model release. New agents should use a fresh main-based branch/worktree rather than assuming the original dirty checkout is safe to reset.

## 3. What was tried and what the numbers mean

All numbers in this section are **local estimates over all 11 historical selection origins**: 65, 78, 91, 104, 117, 130, 143, 156, 169, 182, 195; next 13 weeks. Incumbent mean/worst: **51.674722 / 34.452428**, mean P/F/R **0.259045 / 0.719879 / 0.503608**.

| Track | Experiment | Mean / worst | Decision and risk |
|---|---|---:|---|
| Andrew #129 | Scenario-coupled policy, **after exact-fill fix** | 50.573090 / 27.722064 | Reject as primary: 2 wins, 9 losses, largest loss10.905170. Retain as complementary candidate: best-of-two mean **53.735**, gain **+2.060**, at104/169. |
| Andrew #129 | Term-structured landed costs / terminal valuation | Best mean≈51.612; worst≈34.462 | Reject: mean−0.06 to−0.12; forecast/realized cost-drift correlation only0.18. |
| Andrew #129 | Score-normalized F/R frontier | Best mean≈51.647 / worst≈34.431 | Reject: mean−0.027; calm-window losses offset shock gains. Ban-share inflation also rejected. |
| Jaseer #130 | Typed physical survival | 51.379251 / 34.452428 | Reject: mean−0.295471, 3 regressions. |
| Jaseer #130 | Joint event states / scoped stories, final corrected version | **52.209609 / 34.452428** | Retain challenger: mean+0.534887, 5 wins/2 losses, max loss0.984929. Official public upload **ties70.76**. |
| Jaseer #130 | Supplier/country/lane graph | 51.776758 / 34.452428 | Reject: +0.102036 below complexity gate; 4 wins/1 loss, max loss0.623070. |
| AV #131 | Sanction-specific FX confirmation/persistence | **51.993367 / 34.452428** | Promising +0.318645, 2 wins/0 losses; **not release-ready until parser defects fixed**. |
| AV #131 | Supplier latent price factors | 50.735556 / 34.010354 | Reject: −0.939166, 9 regressions, max loss2.170866. |
| AV #131 | Physical price-regime decomposition | Mean51.536589 | Reject: −0.138133, 3 regressions; full origin evidence is on #131. |

### Follow-ups and concentration

- **#130 follow-up1/1 completed:** removing partial cancellation/recovery transitions while retaining the same learner gives52.170447. Transitions add only0.039162 mean score but improve raw Brier0.172774→0.161199. Most headline gain is origin195 (+6.719207); excluding195 gives **−0.083545** mean delta. Do not claim semantic scope handling alone explains the gain.
- **#129 follow-up1/1 completed, including required correctness repair:** scenario policy plus the existing KES overlay is identical to scenario-alone on all historical origins because week224 lies outside them. The absolute-date overlay has **no historical validation of its own**.
- **#131 targeted correctness round was interrupted:** AV's human had signed the worker out. The requested ownership handoff was never granted, and no parent edit was made. Issue #131 is OPEN/UNASSIGNED as a technical blocker, not an active worker assignment.
- One proposed integration, `partial(disruption_fx.predict, base=disruption_scope.predict)`, was exercised **before FX fixes**: mean52.528255/worst34.452428, +0.853533, 6 wins/1 loss, max loss0.984929; mean raw Brier0.151774. It passed11 composed future-tamper checks and a260-row build. **These are provisional numbers, not an adopted model; re-evaluate after real fixes.**

### Other negative results worth not repeating

Fixed existing state+LP mean50.892224 had no winning origins. Existing news+greedy had mean48.885424/worst26.808306 and +1.765226 best-of-two gain, but badly lost private basis-ban protection. A predeclared material-atomic LP/greedy gate then failed: mean49.453323/worst26.760723, 3 regressions/max loss14.340834, despite improving all six hand-authored private stress paths. It was rejected; no module/tests retained. **Synthetic scenario gains cannot override historical failure.**

Previously rejected #125/#126 remain rejected: first-basis-flag-age +0.012192 and warning-lift best+0.035475, each driven by156. Do not repeat without genuinely new evidence.

## 4. Correctness findings: fixed versus unresolved

**Fixed in PR #137:** the scenario LP allowed `fill <= request` and `fill <= capacity`, which permits refusing purchases that the simulator must fulfill. The corrected default uses binary saturation constraints and HiGHS MILP to enforce `fill = min(request, capacity)`. A failing-before/passing-after regression compares optimizer objective against realized cost. `Params.exact_min` defaults true; do not disable it to recover old results. Solver limits are900s plus one3600s retry; the worker reported typical0.4–5s solves. Review the fixed implementation/zero-capacity and timing boundaries before a new adoption decision; the parent did not complete a final integrated audit/run.

**Unresolved in `disruption_fx.py`:**
1. `_country_events` uses `events._reports`, reintroducing body-only lane expansion. A Kestria headline mentioning Merrow in its body can wrongly become a SUN event. Reuse the incumbent's headline-scoped parsing.
2. `Tensions ease after talks with Kestria` is not routed into the warning lifecycle. An FX-confirmed warning can survive cancellation and re-raise probabilities the incumbent canceled.

A newly authorized owner must reproduce both before fixing, retain consumer regressions, preserve thresholds/priors, and rerun isolated/composed11-origin inference. Do not hide these defects with a wrapper or simply call the candidate accepted.

**Scorer interpretation risk, not a proven official implementation:** local `score.py` clips Brier and price skill separately before combining P. Published wording explicitly clips combined P but does not settle subskill clipping. Baseline combined-only-clipping sensitivity is51.329470 versus standard51.674722. Inspect raw skills and that sensitivity; do not alter the calibrated shared scorer merely to create a gain. Perfect naive shock fill makes fill-skill unreachable at65/78/143/156/182/195; tiny denominators elsewhere can amplify small missed-unit changes.

## 5. Private strategies: evidence, not forecasts

Best-of-two final scoring is confirmed: only the higher private score of up to two selected submissions counts, not their average.

The corrected combined scenario/KES hedge is the most useful unintegrated policy lead:

| Synthetic path | Current KES hedge | Corrected combined hedge |
|---|---:|---:|
| S4 MERROW closure score | 64.35 | **80.32** |
| S4 unmet units | ≈90,300 | **≈26,600** |
| S5 KES-wide-ban score | **84.13** | 83.77 |
| S5 unmet units | 0 | 0 |

In S0–S3 the primary is the higher file of either pair. These scenarios have no assigned probabilities; their unweighted mean is not a private-performance estimate. Additional timing/severity checks showed that even the old KES hedge can leave188,714 unmet units under a5%-capacity KES-wide ban and231,683 when combined with a closure.

Future integration must deliberately choose **general policy in both honest windows** versus **private-only policy composition**. `policy_scenarios.plan_kes_overlay` and `compose(public_from, private_from)` exist. A general public policy must use cutoff208; it need not have the same orders as the primary. The old public-equality test is appropriate only for the existing private-only hedge. No new scenario-policy public CSV was uploaded or scored in this run.

## 6. Receipts, artifacts, and checks

### Official human-uploaded tie with known bytes

- File: `artifacts/uploads/scope_honest_20261107T234427Z.csv`.
- SHA256: **`5af90cd9a9e3baa6682a72ca7d23c59be1274f09d35663f763e340d90cf7c4a3`**.
- Models: `(disruption_scope.predict, price.predict, policy.plan)`.
- 260 rows validated; honest public cutoff208/private cutoff221; public block equals pure cutoff208 build.
- Human-reported official public **70.76**, equal to incumbent. No private score is known. The original70.76 file's recorded hash prefix remains `984a0b19`; its original bytes are outside this checkout, so preserve that original upload/receipt too.

### Preserved incumbent rebuilds, not original uploaded bytes

Files exist in `artifacts/` and fresh copies in `artifacts/campaign-128/`:

| File | Full local SHA256 |
|---|---|
| `basecase_honest-public.csv` | `0da997d7c1ba771af1d59a7c678f76e79b7b9f039ced1fd4765ab09468c2481d` |
| `KESban-hedge_honest-public.csv` | `2103b136ff02e34829ead57ec279a81eedd70adce6e72f8dd6d7aca3eb53856e` |
| `basecase_copied-public.csv` | `12e44e0c76a0189e11eb3a0c1696d237ad57ceffb0dc79d51fc06b63acbd97d3` |
| `KESban-hedge_copied-public.csv` | `d7b42a336f43730b167ee9c731718b4fd77b7782963a04ca7acb7f50cc03f34d` |

Three rebuilt hashes differ from original recorded prefixes; do not infer original numerical parity. Copied-public files use released truth/hindsight, are **not honest forecasts**, and still require human confirmation of organizer permission. Their private blocks equal the corresponding honest files.

### Verification limits

- Parent baseline at277d9a6: **80 tests passed**, all11-origin baseline remeasured, four valid260-row CLI builds, public/private invariants, post208 tamper isolation, old-artifact preservation, and exact committed-source Databricks preflight260+260/all10schemas passed.
- Scope explicit upload and the temporarily staged default CLI both produced the exact SHA above. The temporary default edit was reverted at cancellation.
- Worker-reported latest suite: **97 passed at1314596** after the exact-fill fix. This is worker evidence, not a completed parent final release check.
- Parent's later full suite at an intermediate revision **timed out at180s with partial output**; no all-pass result. No tests or experiments were restarted after cancellation.
- No final composed pair, final live-default switch, remote parity, Kaggle selections, or improved official score was completed. Do not describe this handoff as a verified new model release.

Evidence: `artifacts/campaign-128/` holds baseline, clipping sensitivity, portfolio decisions, composed-prediction, private robustness, official scope receipt, and snapshots of issues129/130/131. Full-precision corrected policy evidence and reproduction scripts are in [#129](https://github.com/JA-01/DSDG-Hackathon/issues/129#issuecomment-6714811950); scope/ablation in [#130](https://github.com/JA-01/DSDG-Hackathon/issues/130); FX/price experiments in [#131](https://github.com/JA-01/DSDG-Hackathon/issues/131). Issue #128 records integration decisions and exact reproduction commands.

Portable artifacts are retained in the **draft**, non-final [campaign128 release](https://github.com/JA-01/DSDG-Hackathon/releases/tag/untagged-3559c68f45c9f90a697b). The original baseline archive SHA is `9f49c8db81a48c012456a242f97cba705cbb778237c452eaeb40c80e49eecfbc`; the scope CSV is attached separately. A cancellation evidence archive is attached there as well; its asset name/hash are recorded on #128. Do not mistake the draft for an adopted final submission.

## 7. Databricks: no worker is still waiting

Existing job **838646686083545**, `workspace.halcyon`, original run-as identity. **Never create another job or change grants.** Last recorded successful run1000919729689519 / MLflow031a0c1acf834b40abb1d703bd5f76f7 is historical, not reverified this campaign.

This workstation's authentication was unavailable. Jaseer verified read-only CLI/SDK authentication on their workstation and could supply the final check, but **that assignment is now canceled and the worker released**. No new remote run/write occurred. A future run needs a newly authorized authenticated operator, accepted code committed/pushed first, and comparison of both downloaded CSVs with local values within1e-9. Local package preflight is not remote parity.

## 8. How any new agent starts — only after a human restarts work

1. Read this file, `AGENTS.md`, `summary.md` §§4/7/14, ADR0001 and `kaggle_instructions.md`; read board75 once. The board is history, not a queue of still-live commands.
2. Establish the human-designated orchestrator and current file handoffs. All old workers are released; do not assume AV is available or Jaseer still owns an active remote task. Issue #131 is an unassigned defect report.
3. Use fresh main-based work without disturbing the original worktree's user deletions/untracked files. Inspect actual source and evidence; do not infer defaults from old CSV names or module docstrings.
4. Highest-value reachable lead: review/reproduce corrected #129 complementary strategy, then consider the private pair. FX requires the two correctness fixes and an ownership handoff first. Scope's official public tie is already known; repeated uploads of tiny scope changes are not new evidence.
5. All selection remains the11 historical origins. Weekly inputs must be cut at each origin; only matured targets may fit. Public209–221 outcomes are released but **must not enter honest cutoff208 forecasts or selection**. Private222–234 can refit through221. No current-run tuning/scoring of released public outcomes occurred beyond the human's official receipt.
6. Before a real adoption: actual changed-path smoke, all affected/full tests with a sufficient solver deadline, valid260-row CSVs, mean/worst/regressions and raw/sensitivity metrics. Use explicit model tuples during experiments; Python default arguments bind old tuples at import, and changing only `MODELS` does not automatically compose the hedge planner.
7. Before release: update both intended model tuples/callers, select public-window behavior deliberately, commit/push, fresh output paths, existing Databricks job only, downloaded numerical parity, and human-authorized official uploads. Preserve incumbent until evidence justifies replacement.

No new-run experiment budget or authority is granted by this list. Prior budgets were three mechanisms per teammate plus one targeted round each; obtain a new mandate instead of silently extending them.

## 9. If no new run is started

Preserve the original70.76 submission and known-byte scope tie. The last validated incumbent private recommendation remains base plus the original KES hedge; the corrected combined hedge is a promising **unadopted alternative**, not an already validated new final pair. Humans alone choose/upload final submissions and finish the video. Instructions list Sunday Nov8,12:00PM Central; verify the live deadline and selected files. Final score uses the higher private result of the two selections.

**SIGN-OFF: Tejas's Codex SIGNED OFF. All teammate experiment, fix, and remote-run assignments are released by human cancellation. No watchers or ACK chains; resume only in a newly authorized run.**
