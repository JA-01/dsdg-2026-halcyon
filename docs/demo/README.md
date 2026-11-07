# Halcyon demo runbook

A recorded, artifact-backed walkthrough for Bay Area Builders. Use the
[three-minute script](video-script.md) and [release checklist](../release-checklist.md).
Competition [rules](../../kaggle_instructions.md), [cheat sheet](<../../Participant Cheat Sheet (share with teams).md>)
and [contracts](../contracts.md) take precedence over older planning status.

## Evidence boundary

The baseline reference is **provisional**, not a selected final candidate:

| Resource | Actual reference |
| --- | --- |
| Workspace | [Halcyon Databricks](https://dbc-7e1d4af4-7a60.cloud.databricks.com) |
| Pipeline job | [793929914775702](https://dbc-7e1d4af4-7a60.cloud.databricks.com/jobs/793929914775702) |
| Baseline job run | [352305866720915](https://dbc-7e1d4af4-7a60.cloud.databricks.com/?o=7474644438221407#job/793929914775702/run/352305866720915) |
| MLflow | Experiment `/Shared/halcyon/runs`; run `c0001ec0e4c847b3821ad74c3bf422b2` (open **Experiments** in the workspace) |
| Source release | `weeks-1-208-18caf03f890c`; configured source Delta versions **1** |
| Run files | `/Volumes/workspace/halcyon/artifacts/runs/c0001ec0e4c847b3821ad74c3bf422b2/` |
| Gold Delta | `workspace.halcyon.gold_forecasts`, `workspace.halcyon.gold_decisions` |

Read `manifest.json` and `validation_report.json` from that directory, alongside
`submission.csv`, `forecasts.csv`, and `decisions.csv`. The manifest, not this
page, determines the selected run's model/policy, cutoffs, hash and status.
A job-run ID is **not** the MLflow/run-directory ID.

The downloaded manifest and validation report both record **260** rows and
SHA-256 `3f5a17f3d2b774938c6b13e7cf6fb4c19138831782fa4db702118a830a8d486c`;
the report says `valid: true`, while `score_status` is `not_evaluated`.
Jaseer's acceptance review independently downloaded and validated these bytes,
read MLflow `FINISHED`, and checked 130 unique keys per window in both gold tables.

The provisional model uses historical disruption rates and last observed
benchmark prices; its policy orders known weekly demand with supplier shares
proportional to normal capacity. It is **not** the organizer sample policy and
**does not adjust orders in response to forecast risk**. A material/week join
shows the forecast and decision together, not evidence of such a response.
There are no forecast backtests, candidate comparisons or policy evaluation
artifacts in this reference run. Export success is not forecasting improvement.
AV's separately exercised inventory-cover/proxy evidence is documented in
[simulator assumptions](../simulator-assumptions.md); do not present it as already
logged in this MLflow run. No official score, news/LLM improvement, external
submission, opt-in or upload is established by these artifacts.

### Connected inventory-policy candidate

The real Delta policy candidate is MLflow run
`74752ffecc3449e29dfd7494ed47ad80`, successful job run `1098642218506545`.
Its forecast remains `provisional_origin_naive`; policy is `inventory_cover`.
The downloaded export has 260 rows and SHA-256
`734c30db0566c6968a43bc527958d264533fb22adf248f29f3d22bf825641247`.
Unlike the provisional capacity-split policy, inventory cover uses forecast
risk/price growth, cutoff-safe supply estimates and lane-aware allocation.
This is a policy candidate, not a demonstrated forecasting improvement or a
human-selected final submission.

Separate MLflow comparison `16a09a7f38e4484fa6c51e678bbee2cd` is `FINISHED`.
Its downloaded `config.json`, `backtests.csv` and `summary.csv` compare the
same provisional forecaster with naive versus inventory policies at origins
130/156. Inventory cover lowers proxy cost in three windows and raises it
0.96% in 157–169; forecast skills are zero by construction. These comparisons
ran on local CSVs, not inside the Delta export job. They do not include source
hashes or a complete code/assumptions manifest; the recorded Git SHA predates
the comparison implementation. Keep that reproducibility gap visible until
the integration owner publishes a fully traced final comparison.

Use the candidate directory with the same demo command below. Add
`--comparison-dir outputs/demo-source/16a09a7f38e4484fa6c51e678bbee2cd`
to include the separately recorded comparison. Keep the actual MLflow API
readback as `comparison_readback.json` beside its downloaded files when
available; it identifies the comparison run without inventing missing lineage.


## Prepare the recording

1. Download all five run files into
   `outputs/demo-source/c0001ec0e4c847b3821ad74c3bf422b2/`, keeping their bytes
   unchanged. Use the authenticated Databricks CLI/SDK; do not record credentials.
2. Open the demo entrypoint below. Supply the **run directory**, not its parent
   or a submission CSV alone, and competition historical inputs under `data/`.
   Use only market observations at or before each row's recorded cutoff. The
   known demand plan may extend beyond cutoff; future realized prices, shocks
   and supply must not enter the demonstration's model/policy inputs.
3. Keep the generated report open for offline playback. Identify it as a
   recorded view of this run, not a newly executed Databricks candidate.
4. In Databricks, open the linked job run, its MLflow run and the SQL cells
   below. Capture their actual outputs once; use screenshots if compute is
   unavailable. An offline report alone does not prove a live Spark execution.
5. Before recording, reconcile the run ID, model/policy IDs, cutoff, checksum,
   validation and evidence-status panel. Stop if they disagree. A future
   candidate may replace `--run-dir`, but its comparisons and provenance must
   exist before changing the narration from provisional to selected.

## Notebook and local entrypoint

Entrypoint: [`notebooks/demo/run_demo.py`](../../notebooks/demo/run_demo.py).
From the repository root, in the project's Python environment:

```bash
python notebooks/demo/run_demo.py \
  --run-dir outputs/demo-source/c0001ec0e4c847b3821ad74c3bf422b2 \
  --data-dir data \
  --offline \
  --output-dir outputs/demo/c0001ec0e4c847b3821ad74c3bf422b2
```

Add `--material lithium` to focus the trace; omit it for the notebook's default
material selection. The local command is offline and must not be described as
executing Spark or reading live MLflow.

Outputs under `--output-dir`:

| File | Recording use |
| --- | --- |
| `demo_report.json` | Run identity, validation and honest evidence status |
| `provenance.csv` | Source/run lineage |
| `windows.csv` | Public/private cutoffs and independent windows |
| `source_signals.csv` | Historical market observations at cutoff |
| `material_forecasts_decisions.csv` | Same-material forecast/order trace |
| `supplier_allocations.csv` | Eligible supplier allocation detail |
| `comparison_summary.csv` | Optional separate comparison's aggregate results |
| `comparison_backtests.csv` | Optional separate comparison's recorded backtests |
| `comparison_deltas.csv` | Optional per-window changes, including regressions |

The three comparison files are emitted when `--comparison-dir` is provided.
`demo_report.json` keeps their run identity, readback and lineage limitations
under `comparison`; they are not evaluation artifacts of the export run itself.

For Databricks, import the Python file as a source notebook into the owned
`/Workspace/Shared/halcyon/demo/` namespace. Set widgets `source_root` to the
workspace directory containing `halcyon/` (the pipeline's deployed source is
`/Workspace/Shared/halcyon/pipeline/src`), `run_dir` to the actual Volume run
directory, `output_dir` to a writable demo-results directory, and `offline` to
`false` for pinned Delta source reads and MLflow readback. `data_dir` supplies
CSV history in offline mode; `material` is optional. The notebook is deployed at
`/Workspace/Shared/halcyon/demo/run_demo` and its live execution is recorded below.
Retain a copy of the generated outputs for recording without live compute.
Set the optional `comparison_dir` widget to the downloaded comparison directory
to include the same separate evidence in Databricks.

## Databricks evidence to capture

Run these in a SQL notebook attached to the project workspace. They are recording
instructions, not a claim that this documentation change executed them.

```sql
DESCRIBE HISTORY workspace.halcyon.bronze_prices;

-- Explicit pinned source read and a real Spark aggregation, not future truth.
SELECT week, material, AVG(spot_price) AS mean_supplier_spot,
       AVG(futures_4w) AS mean_futures_quote
FROM workspace.halcyon.bronze_prices VERSION AS OF 1
WHERE release_id = 'weeks-1-208-18caf03f890c' AND week <= 208
GROUP BY week, material
ORDER BY week DESC, material
LIMIT 10;

-- Full context keys prevent cross-run/window fanout.
SELECT f.run_id, f.window_id, f.cutoff_week, f.target_week, f.material,
       f.disruption_prob, f.price_forecast, d.order_units,
       d.share_KES, d.share_VAL, d.share_SUN,
       d.share_ORI, d.share_HAL, d.share_AUR
FROM workspace.halcyon.gold_forecasts f
JOIN workspace.halcyon.gold_decisions d
  ON f.run_id = d.run_id AND f.window_id = d.window_id
 AND f.target_week = d.target_week AND f.material = d.material
WHERE f.run_id = 'c0001ec0e4c847b3821ad74c3bf422b2'
ORDER BY f.window_id, f.target_week, f.material;
```

The first query exposes Delta history; the second demonstrates the Spark
supplier-to-material market aggregation. It does **not** prove this aggregation
was a feature used by the provisional model: that model carries forward the
released `outcomes.benchmark_price`. In the offline trace compare this benchmark
with the corresponding historical supplier spot mean (allow source rounding),
then show the actual forecast and eligible supplier allocation for the same
material. Futures quotes are observed market context, not realized future prices
or a proven forecasting contribution.

In MLflow show the run's parameters, source/version lineage, `submission_rows`
and actual artifacts. The setup experiment `/Shared/halcyon/setup` is separate
infrastructure evidence, not a trained model or candidate comparison. If a real
baseline/candidate comparison is absent, show that absence and the release gate
rather than inventing a comparison chart.

## Evaluation and Phase 2 narration

- Develop/tune on origins **130/156**. Each origin forecasts 26 weeks without
  revealing the first half to the second; simulate the two 13-week windows
  independently. Reserve origin **182** (targets 183–208) until settings are
  selected; evaluate once and disclose regressions. Report horizons 1–13
  separately for the Phase 2 task. Do not call an untouched holdout evaluated.
- Phase 1 uses cutoff **208** for public 209–221 and private 222–234. Every
  window starts with five weeks of stock and no transit; no state crosses it.
- **Pending prerequisite:** obtain the genuine Phase 2 competition release
  through week **221** after Saturday noon Central. Ingest a new immutable
  release, pin versions, retain validated archived public rows with original
  run/cutoff/hash, and regenerate private 222–234 at cutoff 221 with fresh stock
  and zero transit. Still export all 260 IDs. Do not fabricate Phase 2 data or
  describe newly revealed public weeks as fresh out-of-sample validation.
- Simulator cost/fill/diversification are **proxy** until organizer parity and
  normalizers are established. One concrete limitation: material-level risk
  does not identify the failed supplier; shared-lane shocks can hit several
  suppliers together, and unannounced reversals remain difficult to predict.

## Exercised demo and recording

Jaseer's acceptance review ran the local entrypoint against policy candidate
`74752ffecc3449e29dfd7494ed47ad80` with the separate comparison directory above.
It produced the report and all trace/comparison tables. Negative smoke cases
rejected a tampered manifest checksum and a persisted decision that disagreed
with the CSV; temporary inputs were removed.

The deployed notebook ran with `offline=false` in Databricks submit run
`282966950685740` and terminated `SUCCESS`. Its downloaded report confirms
actual Delta histories, the pinned Spark cutoff join, MLflow `FINISHED`,
260 matching gold forecasts/decisions, and exact export validation. Live output:
`/Volumes/workspace/halcyon/artifacts/demo/74752ffecc3449e29dfd7494ed47ad80/`.
Local copies: `outputs/demo-live/74752ffecc3449e29dfd7494ed47ad80/`.

A narrated, artifact-backed MP4 was generated at
`outputs/demo-video/Bay-Area-Builders-methodology.mp4`: **185.05 seconds**,
1920×1080, H.264 video/AAC audio, SHA-256
`74bf5a020ac5a458e11f3cb7fdee3ffacc01e37282679138cfa395358d31d0bc`.
Frames were visually inspected; FFmpeg decoded the file and measured a
non-silent narration track. This is a generated slide walkthrough with synthetic
voiceover, not a screen recording or an organizer upload confirmation.
It describes the named policy candidate and provisional forecast; replace it
if the final selected methodology changes.
