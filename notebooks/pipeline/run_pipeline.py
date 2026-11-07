# Databricks notebook source
# MAGIC %md
# MAGIC # Halcyon pipeline run
# MAGIC Loads a pinned Delta release, plans each scoring window independently, exports a validated
# MAGIC submission, and records it in MLflow, the artifacts Volume and the gold tables.

# COMMAND ----------
import json
import os
import sys

dbutils.widgets.text("source_root", "/Workspace/Shared/halcyon/pipeline/src")
dbutils.widgets.text("config", "configs/phase1_baseline_delta.json")
dbutils.widgets.text("git_sha", "unknown")
root = dbutils.widgets.get("source_root")
sys.path.insert(0, root)
os.environ["HALCYON_GIT_SHA"] = dbutils.widgets.get("git_sha")

from halcyon.delta import write_gold
from halcyon.pipeline import RunConfig, run_from_config

config = RunConfig.load(f"{root}/{dbutils.widgets.get('config')}")

# COMMAND ----------
result = run_from_config(config, spark=spark)
catalog, schema = config.source["catalog"], config.source["schema"]
release = {"release_id": config.source["release_id"]}
write_gold(spark, catalog, schema, "gold_forecasts", result.forecasts.assign(**release))
write_gold(spark, catalog, schema, "gold_decisions", result.decisions.assign(**release))

# COMMAND ----------
report = {key: result.manifest.get(key) for key in (
    "status", "run_id", "git_sha", "release_id", "delta_versions", "model_ids", "policy_ids",
    "fallback_reason", "export", "score_status")}
report["artifacts"] = f"{config.publish_dir}/{result.run_id}"
print(json.dumps(report, indent=2))
dbutils.notebook.exit(json.dumps(report))
