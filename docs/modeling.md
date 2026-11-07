# Forecasting

## Historical reference

`halcyon.forecasting.baseline:HistoricalForecaster` implements
`predict(data, cutoff, target_weeks)`. Each material receives its own disruption
frequency over released history through the cutoff and its last observed
benchmark price. No organizer sample values are used. Requests must have unique
integer target weeks strictly after a positive integer cutoff. Missing material
history is an error, not an invented forecast. A one-week or single-class history
is supported.

The model narrows `Dataset.as_of(cutoff)` itself even when the caller provides
an unfiltered dataset. `save_artifacts(directory)` writes rates, last prices,
training bounds and model identity after prediction.

Baseline smoke: actual CSV data through208, `InventoryPolicy`, independent
public/private windows, exported260 valid rows with SHA256
`734c30db0566c6968a43bc527958d264533fb22adf248f29f3d22bf825641247`.
Eight baseline regression cases passed, including future-label mutation,
one-observation history and invalid request boundaries.

For config-driven execution use:

```json
{"class": "halcyon.forecasting.baseline:HistoricalForecaster", "kwargs": {}}
```

Development origins are130 and156. Origin182 stays locked until final selection.
Future demand is public; future realized outcomes, markets, supply and news are
not features. Phase1 private horizons are14–26 from208; Phase2 private is1–13
from221. Financial simulator metrics are proxies, not official competition scores.

## Pooled direct-horizon candidate

Config class: `halcyon.forecasting.models:PooledForecaster`, empty kwargs for
defaults. ExtraTrees classifier/regressor pool material one-hot identity and
numeric horizon with 42 observed/known-plan features. Prices use a log ratio to
the origin benchmark. Defaults: first origin26, stride4, horizons1–26,96 trees,
leaf8, depth12, seed10. Every inner origin gets its own narrowed Dataset; only
targets released by the outer cutoff enter training. Short/single-class or
insufficient training explicitly falls back to the historical model and records
the reason in output model IDs and metadata.

**Do not promote this candidate over the historical reference.** Development
Brier regresses in three of four blocks, severely at origin130; price MAPE
improves in three of four. These are raw errors, not an official score.

|Origin|Horizons|Historical Brier|Pooled Brier|Historical MAPE|Pooled MAPE|
|---|---|---:|---:|---:|---:|
|130|1–13|0.188864|0.529426|0.073022|0.071105|
|130|14–26|0.087680|0.704810|0.094111|0.092073|
|156|1–13|0.127638|0.093643|0.056286|0.061066|
|156|14–26|0.316593|0.343193|0.070443|0.065079|

Reproduce after `pip install -e '.[dev]'`:

```sh
python notebooks/forecasting/evaluate.py --output outputs/forecast-dev
```

The notebook writes predictions, Brier/MAPE by origin/horizon/material and
block/material, reliability bins, source/code checksums and package versions.
Per-fold model artifacts include metadata/config, numeric schema, training
features with their own origins, and fitted `model.pkl`. Only load pickle files
from trusted runs. `save_artifacts(directory)` is explicit: integration must call
it after prediction and package the directory in the run's MLflow artifacts.
No automatic model selection or holdout evaluation occurs.

## Feature entrypoints

`halcyon.forecasting.features.build_features(data,cutoff,target_weeks)` returns
`FEATURE_COLUMNS`, version `origin_numeric_v1`: target/material/cutoff/horizon/
version plus `NUMERIC_FEATURES`. Features cover lagged/rolling benchmark and
disruption history, observed spot/futures quotes, publication-safe announced
tariffs, supplier-linked shipping/macro/supply and known target demand. News is
intentionally not a dependency of this candidate.

`halcyon.forecasting.spark.build_spark_features(tables,cutoff,target_weeks,
run_id=...,release_id=...,window_id=...)` builds native Spark transformations
with the same numeric schema and adds complete persistence identity. `tables`
must contain one pinned release's raw DataFrames (or release-tagged frames);
the builder filters release and observation cutoff before window/join work.
It does not start a session, call pandas or use Python UDFs. Persist with keys
run/release/window/feature_version/cutoff_week/target_week/material.

Local native-Spark harness (requires optional PySpark and Java; not added to
production dependencies):

```sh
python notebooks/forecasting/spark_smoke.py --output outputs/spark-features
```

The harness reads actual source CSVs, executes native Spark at origin130 and
compares all shared numeric features to pandas. Databricks/Delta publication
remains with the integration owner. This workstation has no Databricks OAuth
profile; no remote forecast/feature run is claimed here.

## Conservative price-only ablation

Use `PooledForecaster(disruption_mode="historical")` to retain each material's
historical disruption rate while learning only relative prices. This skips
classifier fitting and uses model ID `historical_risk_pooled_price_v1`.
It isolates the price contribution without accepting the classifier regression;
the historical baseline remains the default until final selection. A single
class does not prevent price-model training in this mode.

Development mean over both origins: historical Brier0.180194/MAPE0.073466;
price-only Brier0.180194/MAPE0.072331. This is a small price-only improvement,
not proof of private-period performance. The evaluation notebook includes all
three variants with identical fold definitions. Final integrated suite:244
passed (including native Spark parity and future-mutation cases).

Actual cutoff208 + `InventoryPolicy` smoke exported260 valid rows, SHA256
`b84b276d873a7e0234b47c280309c4d24a24eb7d5b3d3bcdd305f566e9d990f3`.
The full classifier/regressor candidate separately exported260 valid rows,
SHA256 `267e375ce5b67d55a83750b1556847f8afcbd66bdc42552bb05b49eb4a4aa7c1`.
Both fits used training labels27–208; inner origins26–206.

Native Spark smoke passed on actual CSVs with PySpark4.3/Java23:40 requested
rows, all42 numeric features match pandas. Local harnesses pin Python workers to
the current interpreter; otherwise this workstation launches worker3.13 for the
driver3.12 environment. PySpark emits upstream pandas3 compatibility/deprecation
warnings; they are not suppressed.

## Frozen-run acceptance (no retraining)

`notebooks/forecasting/validate_run.py` audits downloaded trusted run artifacts.
It checks exact submission bytes against the manifest and saved forecasts/orders,
source CSV hashes, model/cutoff identity, serialized inference against saved
predictions, and training origins/targets. It supports the historical model and
pooled models without calling `predict` or refitting.

```sh
python notebooks/forecasting/validate_run.py \
  --run-dir outputs/frozen/<mlflow-run-id> --data-dir data \
  --features outputs/frozen/silver_features.csv \
  --job-report outputs/frozen/job.json \
  --output outputs/frozen/forecast-acceptance.json
```

Download the run directory's `manifest.json`, `submission.csv`, `forecasts.csv`,
`decisions.csv`, and complete `forecaster/` artifact folder. Only load trusted
team pickle artifacts. Export `workspace.halcyon.silver_features` filtered to the
exact run ID as CSV, with all identity and feature columns. `job.json` is the
Jobs get-run response, including run_id/state/start_time/end_time.
The audit requires successful terminal status and wall time below1800 seconds.
It compares every persisted window to the same source/cutoff pandas features.

For older explicitly downloaded local smoke artifacts, `--model-dir` identifies
their model directory. Without feature/job evidence, the report explicitly says
`not_checked` and `remote_acceptance_complete=false`; local checks cannot imply
remote acceptance. The checker never edits source run files or evaluates182.
