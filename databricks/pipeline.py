# Databricks notebook source
"""Current halcyon submission, using Delta sources and MLflow artifacts."""
import json
import re
import sys
from pathlib import Path

import mlflow

for name, default in [("catalog", "workspace"), ("schema", "halcyon"),
                      ("input_path", ""), ("source_revision", "")]:
    dbutils.widgets.text(name, default)
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x) for x in [catalog, schema]):
    raise ValueError("Invalid catalog/schema")
root = Path(dbutils.widgets.get("input_path"))
if not str(root).startswith(f"/Volumes/{catalog}/{schema}/raw/phase2/"):
    raise ValueError("input_path must be under the project's raw/phase2 Volume")
sys.path.insert(0, str(root / "halcyon.zip"))
from halcyon.data import release_cutoff
from halcyon.submit import build, validate

# COMMAND ----------
# These explicit CSV schemas come from the working Phase 1 Databricks importer.
# Dedicated c2_ tables leave the archived bronze/silver tables untouched.
schemas = json.loads((root / "schemas.json").read_text())
tables = {}
for name, csv_schema in schemas.items():
    table = f"`{catalog}`.`{schema}`.c2_{name}"
    source = (spark.read.schema(csv_schema).option("header", True)
              .option("mode", "FAILFAST").option("multiLine", True)
              .option("escape", '"').csv(str(root / f"{name}.csv")))
    source.write.format("delta").mode("overwrite").option("overwriteSchema", True).saveAsTable(table)
    tables[name] = spark.table(table).toPandas()
    print(f"{table}: {len(tables[name])} rows")

# COMMAND ----------
mlflow.set_tracking_uri("databricks")
# The parent path is a workspace directory containing the deployed notebook.
mlflow.set_experiment("/Shared/halcyon/phase2/runs")
with mlflow.start_run(run_name="current-main-submission") as run:
    cutoff = release_cutoff(tables)
    mlflow.log_params({"source_revision": dbutils.widgets.get("source_revision"),
                       "release_cutoff": cutoff, "public_cutoff": min(cutoff, 208),
                       "private_cutoff": min(cutoff, 221), "input_path": str(root)})
    frame = build(tables)
    validate(frame, tables)
    output_dir = Path(f"/Volumes/{catalog}/{schema}/artifacts/phase2/{run.info.run_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "submission.csv"
    frame.to_csv(output, index=False)
    # Volume files are copied locally for MLflow clients that reject FUSE artifacts.
    local = Path("/tmp") / f"halcyon-{run.info.run_id}.csv"
    local.write_bytes(output.read_bytes())
    mlflow.log_artifact(str(local), artifact_path="submission")
    mlflow.log_metrics({"validated_rows": len(frame), "mean_price_forecast": float(frame.price_forecast.mean()),
                        "mean_disruption_prob": float(frame.disruption_prob.mean()),
                        "total_order_units": float(frame.order_units.sum())})
    mlflow.log_metrics({f"rows_{name}": len(table) for name, table in tables.items()})
    mlflow.set_tag("score_status", "unscored; no Kaggle upload")
    report = {"csv": str(output), "validated_rows": len(frame), "release_cutoff": cutoff,
              "source_revision": dbutils.widgets.get("source_revision"),
              "mlflow_run_id": run.info.run_id, "experiment_id": run.info.experiment_id}
    mlflow.log_dict(report, "result.json")
    (output_dir / "result.json").write_text(json.dumps(report, indent=2) + "\n")
dbutils.notebook.exit(json.dumps(report))
