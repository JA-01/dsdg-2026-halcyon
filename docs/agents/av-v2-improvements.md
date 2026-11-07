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
| P0 | Candidate record / Andrew | `docs/candidates.md:3-5` still says neither candidate is scored. Record human-reported 54.10 with exact run/hash; record later scores separately, not as locally reproduced facts. | Every scored upload maps to CSV hash/run/release; preserve V1 bytes and submission quota. |
| P0 | Selection / Andrew + Tejas + AV | V1 cost/simplicity tie-break ignores the 30% prediction component (`docs/candidates.md:18-36`). Existing price+optimized runner-up already exists; Andrew reports no record of its upload, so its score is unknown. | Declare V2 rule before comparisons: consider Brier/MAPE, per-window shock fill, diversification and cost jointly; no fabricated weighted official total. Select Pareto candidates, disclose regressions; at most two final selections. |
| P0 | Phase 2 / Andrew | Existing `halcyon/phase2.py`, runbook and archive path already implement refresh mechanics. Run against genuine release through221 when available; do not rebuild them. | Pinned new release/version/checksums; cutoff221;130 private rows222–234 with fresh stock/transit; unchanged130 archived public rows; validate all260 serialized rows and remote provenance. Public replay after release is not fresh validation. |
| P1 | Zero-order allocation / AV | `policy.py` previously used lane-balanced fallback shares even when order quantity was exactly zero. Equal eligible shares minimize country HHI and maximize diversification without shipping units. | Accepted by Tejas on board comment6702112819 and implemented: exactly-zero optimizer rows only; active quantities/sourcing unchanged. Real-data replay covers all20 dev-window/scenario combinations. Official benefit remains unknown if zero-order rows are excluded/quantity-weighted. |
| P1 | Forecast quality / Tejas | Both deployed candidates keep historical disruption rates (`docs/candidates.md:49-50`); selected also uses carry-forward price. Tejas's saved-dev analysis reports price-only MAPE improves over26 weeks but regresses h1–13 from0.064654 to0.066085. News evidence is mixed (`docs/news-events.md:25-35`). | Keep historical Phase2 default. Existing price runner-up is a bounded Phase1 experiment, not an automatic cutoff221 promotion. Compare Brier/MAPE separately on130/156 h1–13/h14–26 and disclose per-fold regressions. No new estimator/dependency justified. |
| P1 | Policy diagnostics / AV | Current MILP uses static trailing capacity/lead estimates and material-level risk, not supplier-specific disruption forecasts (`policy.py:350-366,438-447`). Residual shortages remain; this is a limitation, not proof another model is needed. | Inspect existing weekly/material/projection artifacts; prioritize by shortage COST, not raw cross-material units. Any later estimate change needs named causal rationale and fixed dev comparison, not a broad parameter search. No new production change currently justified. |
| P1 | Organizer parity / Andrew with human clarification | `simulator.py:131-135,306-322` explicitly labels average-cost, initial-stock, timing and aggregation assumptions. A single54.10 total cannot identify those rules. | Use authoritative organizer code/clarification if supplied; otherwise retain proxy labels and existing sensitivity scenarios. Do not calibrate fake official normalizers to one score. |
| P1 | Release evidence / Andrew | Existing acceptance, exporter, Spark/model harness and MLflow manifests already exist. Reuse them on actual new artifacts rather than add a second release framework. | Clean source/config lineage, explicit fallback state, exact bytes/hash readback,130 unique gold keys/window, model reload/feature parity when changed; actual public score receipt. |
| P1 | Phase2 acceptance / Andrew | `accept.py:79` checks public retention only when `--retained-from` is supplied; manifest already names the archive. `phase2.py:57-58` reuses one default output per release. | Peer review routed both risks to Andrew: derive/require the archive check, and use explicit distinct output paths for multiple candidates. Reuse existing mechanisms; no new release framework. |

The shared necessary-only list is acknowledged by AV and Tejas on the board:
incumbent/receipt records, Pareto+horizon-specific evidence, genuine221 refresh,
archived public/fresh private, bounded Phase1 runner-up, and zero-order shares.
Andrew's conditional-state experiment remains Tejas's owned evaluation decision,
not blanket approval for a new forecaster. Full team list and release decisions
remain on the board; no cross-owner changes were made by AV.

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

AV signs off only after the final board list is acknowledged, any accepted
owned change has regression+real-path smoke evidence and a merged PR, and Andrew
has the exact handoff. Andrew owns new remote CSV generation and external score
receipts. Genuine221 release, teammate acknowledgments and human Kaggle actions
must remain explicitly pending when not observed; never claim V2 beat54.10
without the score.

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
