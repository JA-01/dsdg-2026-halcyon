# AV V2 review: leaderboard pipeline improvements (#41)

## Benchmark and scope

Human-reported public Kaggle score: **54.10**, MLflow
[`7d2271940a5744c3bd3756a7071c72c4`](https://dbc-7e1d4af4-7a60.cloud.databricks.com/ml/experiments/2562241450728952/runs/7d2271940a5744c3bd3756a7071c72c4?o=7474644438221407),
CSV SHA-256 `2240be824b0808a9e70c78573259894f48a17e356134babe0a5daac9617aead6`.
This supersedes the unscored wording in the V1 candidate document; it does not
reveal component scores, organizer simulator internals, or private performance.
V2's public target is strictly above 54.10. Only an actual Kaggle result can
establish that. Preserve the incumbent if the candidate fails that gate.

Review covers repository rules, competition instructions/cheat sheet, plans,
contracts, handoffs, source, configs, notebook entrypoints, tests and recorded
artifacts. Policy/simulator received direct detailed review and fresh real-data
execution; completed internal read-only reviews covered forecasting/news and integration.
No video, UI, infrastructure rebuild, unlimited tuning or new optimizer framework.
Agents agree the final board list as peers; Tejas owns forecasts; AV owns policy;
Andrew owns integration and release. Only Jaseer reassigns ownership.

## Necessary-only proposed list

| Priority | Area / owner | Evidence and bounded decision | Acceptance / stop gate |
| --- | --- | --- | --- |
| P0 | Candidate record / Andrew | The human-reported54.10 incumbent is now recorded in `docs/candidates.md` by PR#51. Later scores must be recorded separately, not as locally reproduced facts. | Every scored upload maps to CSV hash/run/release; preserve V1 bytes and submission quota. |
| P0 | Selection / Andrew + Tejas + AV | V1 cost/simplicity tie-break ignored prediction skill. New evidence rejects the pooled-price runner-up for a final slot; the lead selects the two bounded shapes below as a hedge. | Keep raw Brier/MAPE, cost, shock fill and diversification by fold/horizon; no pseudo-official total. Preserve separate hashes and actual score receipts for U1/U2. |
| P0 | Phase 2 / Andrew | Existing `halcyon/phase2.py`, runbook and archive path already implement refresh mechanics. Run against genuine release through221 when available; do not rebuild them. | Pinned new release/version/checksums; cutoff221;130 private rows222–234 with fresh stock/transit; unchanged130 archived public rows; validate all260 serialized rows and remote provenance. Public replay after release is not fresh validation. |
| P1 | Zero-order allocation / AV | `policy.py` previously used lane-balanced fallback shares even when order quantity was exactly zero. Equal eligible shares minimize country HHI and maximize diversification without shipping units. | Accepted by Tejas on board comment6702112819 and implemented: exactly-zero optimizer rows only; active quantities/sourcing unchanged. Real-data replay covers all20 dev-window/scenario combinations. Official benefit remains unknown if zero-order rows are excluded/quantity-weighted. |
| P1 | Forecast quality / Tejas | Initial review preferred historical private forecasts because pooled prices regress h1–13 MAPE (0.064654→0.066085). Later independently checked existing news-state forecasts and the fixed price blend support the lead's bounded two-shape plan. | Final lead decision below supersedes the early historical-forecast-only disposition. Policy risks remain historical; no new estimator/dependency or broader search. |
| P1 | Policy diagnostics / AV | Static trailing capacity/lead estimates and material-level risk remain limitations. Lead-approved PR#62 adds only the declared post-hoc tilt candidate, not supplier-specific forecasts or an optimizer rewrite. | Default0 compatibility, capacity/quantity/eligibility checks and explicit tail losses; no additional tuning. |
| P1 | Organizer parity / Andrew with human clarification | `simulator.py:131-135,306-322` explicitly labels average-cost, initial-stock, timing and aggregation assumptions. A single54.10 total cannot identify those rules. | Use authoritative organizer code/clarification if supplied; otherwise retain proxy labels and existing sensitivity scenarios. Do not calibrate fake official normalizers to one score. |
| P1 | Release evidence / Andrew | Existing acceptance, exporter, Spark/model harness and MLflow manifests already exist. Reuse them on actual new artifacts rather than add a second release framework. | Clean source/config lineage, explicit fallback state, exact bytes/hash readback,130 unique gold keys/window, model reload/feature parity when changed; actual public score receipt. |
| P1 | Phase2 acceptance / Andrew | PR#51 adds `retained_run(manifest, explicit)` and automatically loads archived public rows from manifest provenance. `phase2.py` still reuses one default output per release. | Verify archive checks on actual new artifacts; use explicit distinct `--output` paths for multiple candidates. No new release framework. |

Andrew explicitly acknowledged the original shared list on board comment
6702166956; Tejas and AV had already acknowledged it. Subsequent proposals
must receive their own decisions; the earlier list is not blanket approval for
cost tilts, price blends or an extra scoring framework. AV remains active through
those peer decisions and implementation handoffs, per the human's correction.

## Fresh execution evidence

Executed the existing `evaluate_policies` API with `HistoricalForecaster`,
`OptimizedPolicy` and `InventoryPolicy`, origins130/156 only, and all five
existing evaluator scenarios. Temporary output directories were removed after
inspection. No origin182 evaluation, new model fitting, or Phase2 truth used.

| Evaluator scenario | Optimized summed cost | Inventory-cover summed cost |
| --- | ---: | ---: |
| Default | 19,122,665.23 | 19,728,248.33 |
| Five-week-summed opening inventory | 19,449,473.77 | 20,050,415.98 |
| Per-supplier floor quantities | 19,209,882.71 | 19,878,700.37 |
| Historical reference cost | 18,860,982.08 | 19,337,636.60 |
| Pre-demand holding | 19,652,063.73 | 20,253,041.30 |

Summed cost is not the official competition score. Individual windows can
regress: optimizer default cost in144–156 exceeds inventory cover. Largest
observed development shortage expense among inspected material rows was copper
in131–143:488,379.46, despite shock-fill1.0; overall and shock metrics must both
remain visible. High raw-unit steel shortages are not automatically higher
financial priority than copper.

Executed real `run_pipeline(208, HistoricalForecaster(), OptimizedPolicy(), ...)`:
260 validated serialized rows,130 public+130 private; observed data ends208.
Local CSV SHA-256 `219ca02c36eca45a59ecd9ca0e0d9e58b6b87b9dff0bb16cfa5205c8aaab3821`.
This is a local smoke artifact, NOT the54.10 remote CSV, a new upload, or proof
of remote byte reproducibility. It had116 zero-order rows and136 fractional
order quantities. Rules allow nonnegative real quantities; do not round exports
without evidence of organizer requirements.

A throwaway counterfactual changed only exactly-zero-order shares to uniform
eligible shares. For every dev window, every weekly field other than
concentration/diversification was exactly identical, including all inventory,
fulfilled/cancelled units and decomposed costs.

| Dev origin / horizon | Zero-order rows | Diversification before | After |
| --- | ---: | ---: | ---: |
|130 / h1–13|53|0.972401|0.978170|
|130 / h14–26|54|0.974844|0.980613|
|156 / h1–13|58|0.974455|0.980224|
|156 / h14–26|58|0.974894|0.980663|

This supports a very small policy improvement under current aggregation, not
a guarantee of a measurable leaderboard change or of exceeding54.10 alone.

## Keep and defer

- Keep independent window resets, fixed cutoff views, sample-order exact260-ID
  validation, complete four-week recovery lookback and explicit solver failures.
- Keep current conservative MILP buffers, capacity/lead quantiles and prohibition
  on speculative terminal salvage buying. No robust/scenario optimizer rewrite.
- Do not rerun or tune on the already-consumed origin182 holdout.130/156 are
  development evidence, not a new unbiased holdout. Any new retrospective fold
  must be declared exploratory, with its role fixed before evaluation.
- Do not substitute quantity-weighted diversification for the unknown organizer
  aggregation, or optimize public truth and claim generalization after Phase2.
- Defer supplier-specific forecasting, larger feature/model sweeps, neural models,
  extra dependencies, external data/LLMs and broader news parsing unless a named
  dev failure makes the smallest change necessary.
- Do not add generic validation, compatibility shims, retry layers or tests for
  wiring. Keep tests at consumer-visible physics/eligibility/cutoff boundaries.

## Completion gate

AV signs off only after explicit peer agreement on the final lead list AND the
approved cross-owner implementation handoffs/reviews are complete, not when
AV's own PR finishes. Andrew owns new remote generation, genuine221 refresh,
calibration#9 and external score receipts. Unobserved releases/scores stay
pending; never claim V2 beat54.10 without an actual score receipt.

## Implemented AV handoff

PR[#47](https://github.com/JA-01/DSDG-Hackathon/pull/47) contains this review,
the bounded optimizer zero-order cutover, consumer-visible eligibility/HHI
regressions, and updated simulator assumptions. No new dependency, config
switch, alternate optimizer, or API change.

Post-change real-data smoke rebuilt all four development windows and checked
all five evaluator scenarios against saved pre-change decisions: quantities,
positive-order shares and economic/inventory outcomes match within numerical
serialization tolerance; diversification improves or ties. The actual cutoff208
pipeline produced260 validated rows,130 per window, SHA-256
`bcbded2371459959a6e591fe342974a594c18292bab3aa341d0312a573f2ae2f`.
Full repository suite:372 passed,1 optional native-Spark skip.
No origin182 evaluation, Phase2 release or external score was claimed.

## Continued peer review after the premature local sign-off

Read merged Andrew review (PR#49), news candidate/archive fix (PR#51), and
Tejas's independent check (PR#53), not merely the board summaries.

| Proposal | AV disposition | Required boundary |
| --- | --- | --- |
| #5 Existing news-state probability-only candidate | Accept isolated experiment after exact integration invariants pass; Tejas independently exercised it on58–162 step13, h1–13. | Same-code baseline and candidate must have identical prices, quantities, positive/zero-order shares and projected state. Phase1 h14–26 must retain EXACT historical probabilities; Phase2 must retain its archived public block. Preserve incumbent and both model/policy identities; no score promise. |
| #6 Active-order cost tilt, k=3 | Lead APPROVED and reassigned implementation to Jaseer's agent; PR#62 merged after AV runtime/source ACK. Final U2 also sets `risk_buffer_weeks=4`. | Default0 preserves prior bytes; exactly-zero shares stay uniform; positive totals match the SAME-rb4 untilted solve, not necessarily U1. Capacity spill and eligibility pass. Late slices are intentionally permitted and stale projection omitted. Fixed settings, no more tuning. |
| #7 Price blend | Lead APPROVED75% last benchmark +25% trailing52-week mean, flat at ALL horizons. Andrew's PR#60 merged; Tejas independently checked it. | Flat-by-material blend preserves pre-tilt MILP decisions with the same buffer. This is not the unchanged-price clipping argument. Preserve news-only U1 separately. |
| #8 Production pseudo-official scorer | REJECTED by final lead decision. | #9 is a later throwaway calibration check on released209–221 versus54.10, not official parity, fresh validation or retrospective tuning. |

### Actual merged-candidate smoke: mismatch found and corrected

At main`8d2d5cc`, directly executed two cutoff208 `run_pipeline` calls with
historical+optimized and news-state+`HistoricalRiskPolicy`. Both wrote valid260-row
CSVs; all non-probability columns were exactly identical. However, all130
Phase1 private h14–26 probabilities also changed (maximum absolute difference
0.017254273504273505): the neutral long-horizon lift still used a smoothed rate.

Baseline local SHA-256:
`bcbded2371459959a6e591fe342974a594c18292bab3aa341d0312a573f2ae2f`.
Out-of-scope candidate local SHA-256:
`2aa07565c6ca728630c17552a7d4d4f62bd2333328a61512d8804940a5b1ab51`.
These are temporary smoke artifacts, not remote candidates or upload receipts.
No scoring-window truth was evaluated. Reported on board comment6702241723
and issue#50. Andrew's correction landed at main`005310b`: h>13 explicitly
retains the base historical probability. Re-executed the actual two-run smoke:
all non-probability columns remain exactly identical,130 public probabilities
change and ZERO private probabilities differ (maximum difference0).
Corrected temporary candidate SHA-256:
`cbb463652c411e10ff3266ece2d36143012f70e5544329ad7d1985a35bb3d048`.
Focused news/acceptance/Phase2 regressions:31 passed.

Also exercised archive mechanics at cutoff208 using `ArchivedPublic`,
`phase2_windows(208)` and the real pipeline:260 rows validate, public rows are
exactly retained and `retained_run` automatically resolves the archive run from
the manifest. This is a Phase1-data rehearsal, not a genuine221 run. Pure local
acceptance helpers received the local hash as the expected MLflow hash; no
remote MLflow/gold/artifact readback is attributed to this smoke.

### Final consensus and remaining external gates

Canonical plan: [Jaseer's final V2 list](jaseer-v2-improvements.md), lead board
6702359200. HOLD explicitly released. Human6702375263 requested all agents
confirm the same final plan; AV confirmed6702391988, including the rb4 amendment.

- U1: news probabilities h1–13, exact historical beyond13, carry-forward price,
  current shares; `configs/phase1_v2_news_delta.json`.
- U2: U1 plus fixed price blend0.25 at ALL horizons, cost tilt3 and
  `risk_buffer_weeks=4`; `configs/phase1_v2_tilt_delta.json`.
- Genuine cutoff221: both shapes preserve their public archive and independently
  initialize private stock/transit. No public-score-only rule selects private.
- Keep exact-zero uniform shares, mandatory archive acceptance and raw fold/h1–13
  evidence. Reject production scorer/new sweeps/model stacks/UI/video.
- After Phase2, compare the throwaway estimator on incumbent209–221 against54.10.
  This is a calibration diagnostic, not independent validation or proof of parity.
- Post actual run/config/hash/score receipts. No observed score yet exceeds54.10.

### Independent PR#62 and stored U1 acceptance

Reviewed PR#62 at`bebfde37` in an isolated checkout.153 policy/simulator tests
pass. Real origins97/130/156/169 h1–13 confirm same-rb4 quantity conservation,
eligible normalized shares, estimated-capacity violations at most1.82e-12,
unchanged zero-order shares and no misleading `projection` on tilted outputs.
Default and explicitcost_tilt0 exports match the previous local baseline
BYTE-FOR-BYTE; tilted-historical260-row export validates. No182-origin or209+
realized truth evaluated. AV review ACK: board6702379452; Jaseer merged#62.

Tail risk is real even with rb4: at origin97 raw proxy cost rises5,559,364.41→
6,204,338.08 and shock fill falls0.92295→0.86298; origin169 improves cost and
shock fill. Acceptance is for the declared hedge, not dominance or guaranteed
leaderboard gain. Late-arriving reallocated slices are intentional and documented;
the untilted solver ledger is omitted rather than presented as final-plan state.

Read actual stored U1 and incumbent artifacts with authenticated CLI, plus
MLflow metadata and run-filtered SQL. U1 run`32244c21c3ed44da8eafda2ed2f4acae`
is FINISHED, clean`005310b`, no fallback, SHA-256
`59dc988ba37dce62c47a6eb4f18169e8d9ef69fdc14cbc2e191349c87a5f07e3`.
Hash matches manifest and MLflow. All four gold table/window combinations have
130 rows and130 unique keys. Against the54.10 file, prices, quantities, positive
shares and private probabilities are EXACTLY identical;130 public probabilities
and24 zero-order share rows change. This is real remote acceptance, not a score
or U2 acceptance claim. The initial full `halcyon.accept` invocation lacked local
MLflow/SDK dependencies; CLI readback provided the independent evidence without
changing project dependencies.
