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
# Structured news events for this run's release, with each article's own week and its evidence.
from halcyon.news import extract_events
from halcyon.pipeline import load_source

events = extract_events(load_source(config.source, spark)["news"])
write_gold(spark, catalog, schema, "silver_news_events", events.assign(run_id=result.run_id, **release))

# COMMAND ----------
# Native Spark features from the same pinned tables, persisted per window and checked against pandas.
from halcyon.contracts import phase1_windows, phase2_windows
from halcyon.delta import check_feature_parity, pinned_tables
from halcyon.forecasting.features import build_features
from halcyon.forecasting.spark import build_spark_features

tables = pinned_tables(spark, catalog, schema, config.source["release_id"], config.source["versions"])
dataset = load_source(config.source, spark)
windows = phase1_windows(result.manifest["cutoff"]) if config.mode == "phase1" else phase2_windows(result.manifest["cutoff"])
feature_report = {}
for window in windows:
    weeks = list(window.target_weeks)
    features = build_spark_features(tables, window.cutoff, weeks, run_id=result.run_id,
                                    release_id=config.source["release_id"], window_id=window.window_id)
    local = features.toPandas()
    compared = check_feature_parity(local, build_features(dataset, window.cutoff, weeks))
    features.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(
        f"`{catalog}`.`{schema}`.`silver_features`")
    feature_report[window.window_id] = {"rows": len(local), "numeric_columns_matching_pandas": compared}

# COMMAND ----------
report = {key: result.manifest.get(key) for key in (
    "status", "run_id", "git_sha", "dirty", "release_id", "delta_versions", "model_ids", "policy_ids",
    "fallback_reason", "export", "score_status")}
report["artifacts"] = f"{config.publish_dir}/{result.run_id}"
report["news_events"] = len(events)
report["spark_features"] = feature_report
print(json.dumps(report, indent=2))
dbutils.notebook.exit(json.dumps(report))
