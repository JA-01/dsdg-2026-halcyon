# Implementation contracts — v1

Canonical interface agreement adopts Andrew's #7 and AV's #8 board proposals,
using a root `halcyon/` package. This supersedes the unmerged src-layout draft.
Andrew owns shared definitions; Tejas owns forecasting; AV owns policy/simulator.
All agents review this document. Incompatible changes require a board proposal
and affected owners' acknowledgment before consumers switch.

## Run, release and window identity

`run_id` is the root MLflow run ID. Select one `release_id`, pin source Delta
versions and copy the selected setup manifest/report into the run artifacts.
Record source checksums, Git SHA, config/package/feature versions and seeds.
Do not read a global “latest” table during a run.

| Mode | Window | Forecast cutoff | Targets | Inventory |
| --- | --- | ---: | --- | --- |
| Phase 1 | public | 208 | 209–221 | Fresh five-week stock, no transit |
| Phase 1 | private | 208 | 222–234 | Fresh five-week stock, no transit |
| Phase 2 | public | Archived Phase 1 | 209–221 | Retain validated archived rows |
| Phase 2 | private | 221 | 222–234 | Fresh five-week stock, no transit |

Andrew's runner calls `Policy.decide` **separately for each window**, passing
only that window's target weeks/forecasts and fresh predicted inventory state.
Phase 1 private targets are horizons 14–26 from cutoff 208. Phase 2 private is
horizons 1–13 from 221. Never reveal the first window to plan the second.

Historical origin C mirrors this with independent `C+1..C+13` and
`C+14..C+26` windows, both forecast from C. Report horizons 1–13 separately.
Development origins: 130/156; locked final holdout: 182 (183–208).

Phase 2 retains the validated Phase 1 public block by default, recording its
originating run/cutoff/checksum, and generates new private rows. Retrospective
public optimization is optional and cannot count as fresh validation. Every
export has 260 IDs. No public inventory/transit carries into private.

## Dataset boundary and public interfaces

`Dataset` wraps typed pandas DataFrames from local fixtures or pinned Delta
snapshots. `Dataset.as_of(cutoff)` returns a filtered copy: observed tables only
through cutoff, static suppliers unchanged, and known demand through all 234
weeks. It must not mutate the original evaluator data.

Shared table keys: `news`, `prices`, `tariffs`, `shipping`, `macro`, `suppliers`,
`demand`, `outcomes`, `supply_history`; optional `silver_supplier_week`,
`silver_material_week`, `news_events`. Raw schemas follow the existing bootstrap.
Andrew publishes the concrete table-access accessor and constants import path
with the #7 scaffold before consumers integrate; use that one accessor, not
inconsistent attributes invented independently by each agent.

Accepted prediction/policy protocol:

```python
Forecaster.predict(data: Dataset, cutoff: int, target_weeks: list[int]) -> pandas.DataFrame
Policy.decide(data: Dataset, forecasts: pandas.DataFrame,
              cutoff: int, target_weeks: list[int]) -> pandas.DataFrame
run_pipeline(cutoff: int, forecaster: Forecaster, policy: Policy)  # Andrew's core runner
```

The runner supplies `data.as_of(cutoff)` to forecaster and policy and calls the
policy independently per window. Config-driven CLI/job wrappers can extend the
runner without breaking these accepted core protocols. Model/policy parameters,
seed and artifacts directory belong in the implementations' explicit config.
Pure forecasting, policy, simulator and validator APIs have no implicit Spark
session or external network dependency. Spark feature builders are separate.

Tejas additionally filters each **inner training origin**; outer filtering alone
does not prevent leakage. Never use future realized markets/news/labels/supply
as features. Metadata/checksums are not model features. Existing silver tables
contain observed same-week data and need historical feature transformations.
Realized future truth is kept separately and passed only to the evaluator.

Forecast output has exactly one row per target week/material, with
`target_week`, `material`, finite `disruption_prob` in [0,1] and finite positive
`price_forecast`. Optional `model_id`/diagnostics are retained as provenance.
The target material set is the 10 static supplier materials. Missing/duplicate
keys or wrong coverage are errors. A complete Phase 1 forecast has 260 rows;
a Phase 2 private forecast has 130.

Policy output has matching `target_week`, `material`, finite nonnegative
`order_units`, and `share_KES, share_VAL, share_SUN, share_ORI, share_HAL, share_AUR`.
Optional `policy_id`/diagnostics are retained. Plan the whole window using
predicted state; do not adapt submitted decisions using future realized arrivals.

AV implements the accepted pure helper in `halcyon/simulator.py`:

```python
simulate_window(decisions, demand, supply_history, suppliers, outcomes,
                start_week, end_week, *, reference_costs=None)
```

AV can publish additional keyword-only assumption settings with an adapter;
keep `Policy.decide` as the integration boundary. Andrew does not write AV's
`halcyon/policy.py` or `halcyon/simulator.py`. His provisional baseline adapters
remain isolated in `halcyon/baselines.py` until the owner modules land.

## Persistence and evaluator results

Andrew attaches `run_id`, `release_id`, `window_id`, `cutoff_week`, model/policy
IDs and archived `origin_run_id` when persisting gold outputs. Gold identity:
`(run_id, window_id, target_week, material)`. Write only current-run rows and
preserve other runs/releases. Every merge is one-to-one on full context keys.

Tejas's persisted features carry run/release/window/feature version, example
`cutoff_week`, target/material and horizon. Include those context columns in
keys to avoid fold/version collisions. For training rows cutoff is the example
origin, not the outer training cutoff. Publish dynamic feature schemas/version.

Simulator results expose `metrics`, `material_metrics`, and `weekly` DataFrames,
plus serialized `assumptions` and `score_status` in the integration artifact.
Weekly state is keyed by window/week/material, including demand, fulfilled
units, stockouts, ending stock/transit, purchase/holding/shortage/salvage costs
and shock/recovery flag. Metrics must retain raw costs/fill/concentration even
when an official total cannot be reproduced. Andrew can serialize AV's frames
into a common run manifest without changing AV's computation API.

Supplier slices fill independently up to capacity; cancelled units are unpaid
and not reassigned automatically. Reset each window. AV documents varying-
demand initial units, average-cost reference, arrival/holding timing, quantity
rounding and diversification/hindsight aggregation. Unknown exact normalizers
mean `score_status=proxy`; do not fabricate official scores. Expose undefined
skill denominators rather than silently replacing them with perfect results.

Historical naive baselines must use that origin's history/known demand. The
organizer sample contains values generated at week 208; using them at earlier
origins leaks information. Keep `organizer_sample` distinct from
`local_origin_naive` until organizer-policy equivalence is established.
Backtest keys: run/fold/window/material/metric name, with material `__all__`
for aggregates and explicit score status.

## Submission and run manifest

CSV column order, one header, no index/metadata:

```text
id,disruption_prob,price_forecast,order_units,share_KES,share_VAL,share_SUN,share_ORI,share_HAL,share_AUR
```

Exactly match the sample's 260 unique IDs, weeks 209–234. Reject missing/extra/
duplicate IDs, nonfinite values, out-of-range probabilities/shares, nonpositive
prices, negative orders, ineligible supplier shares and share sums outside
`1e-6`, including zero orders. **Do not silently renormalize/clip during export.**
The policy/model owner must produce valid outputs before the exporter accepts.

Build IDs after a one-to-one forecast/decision join and use sample ID order.
Andrew's validator identifies the first bad ID/rule; exporter validates, writes
one real CSV, rereads/validates serialized values and returns path/hash/row count.
Any baseline fallback must be explicit in config and logged.

Run manifest: status/run ID, release/checksums/Delta versions, Git SHA,
windows/cutoffs, configs/versions/seeds, model/policy IDs, raw/proxy metrics,
assumptions and artifact references. Store predictions, decisions, backtests,
manifest, validation report and CSV/hash under
`/Volumes/workspace/halcyon/artifacts/runs/<run_id>/` and in MLflow.
Andrew creates/shares `/Shared/halcyon/runs` and a separate training job.
Existing `/setup` is infrastructure evidence. No external LLM key/MCP/hosted
endpoint is a core dependency.
