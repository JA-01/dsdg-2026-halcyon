# Databricks notebook source
# MAGIC %pip install mlflow==3.18.0 pandas==3.1.1 scikit-learn==1.9.1 scipy==1.18.1

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import hashlib
import json
import math
from functools import reduce
from pathlib import Path

import mlflow
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("schema", "halcyon")
dbutils.widgets.text("release_path", "")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
release_path = Path(dbutils.widgets.get("release_path"))
assert str(release_path).startswith(f"/Volumes/{catalog}/{schema}/raw/"), "Invalid release path"
namespace = f"`{catalog}`.`{schema}`"
manifest = json.loads((release_path / "manifest.json").read_text())
release_id = manifest["release_id"]
assert release_id.replace("-", "").isalnum(), "Invalid release ID"
report = {"release_id": release_id, "cutoff_week": manifest["cutoff_week"], "tables": {}}

# COMMAND ----------
# Ingest explicit schemas into versioned, release-scoped Delta snapshots.
for name, spec in manifest["files"].items():
    source = release_path / spec["filename"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == spec["sha256"], name
    df = (spark.read.schema(spec["schema"]).option("header", True)
          .option("mode", "FAILFAST").option("multiLine", True).option("escape", '"')
          .csv(str(source)))
    # Blank announced tariff fields are the only allowed null source values.
    required = [column for column in df.columns
                if column not in {"announced_rate", "announced_effective_week"}]
    nulls = reduce(lambda a, b: a | b, [F.col(column).isNull() for column in required])
    assert df.filter(nulls).limit(1).count() == 0, f"Required null in {name}"
    assert df.count() == spec["rows"], f"Row count mismatch: {name}"
    assert df.select(*spec["keys"]).distinct().count() == spec["rows"], f"Duplicate keys: {name}"
    snapshot = (df.withColumn("release_id", F.lit(release_id))
                .withColumn("source_sha256", F.lit(spec["sha256"]))
                .withColumn("ingested_at", F.current_timestamp()))
    table = f"{namespace}.bronze_{name}"
    (snapshot.write.format("delta").mode("overwrite")
        .option("replaceWhere", f"release_id = '{release_id}'").saveAsTable(table))
    count = spark.table(table).filter(F.col("release_id") == release_id).count()
    assert count == spec["rows"], table
    version = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"]
    report["tables"][f"bronze_{name}"] = {"rows": count, "version": version}
    print(f"{table}: {count} rows; Delta version {version}")

# COMMAND ----------
def released(name):
    return spark.table(f"{namespace}.bronze_{name}").filter(F.col("release_id") == release_id)


# A concrete Spark transformation: supplier-grain joins, then material aggregation.
supplier = released("suppliers").select("material", "country", "country_name", "lane",
    "base_lead_weeks", "normal_capacity_units", "base_tariff")
assert supplier.count() == 30
assert supplier.groupBy("material").count().filter("count != 3").count() == 0
market = released("prices").select("release_id", "week", "date", "material", "country", "spot_price", "futures_4w")
tariff = released("tariffs").select("week", "material", "country", "tariff_rate", "announced_rate", "announced_effective_week")
shipping = released("shipping").select("week", "lane", "container_rate", "transit_days", "congestion_index")
macro = released("macro").select("week", "country", "pmi", "fx_rate", "cpi_yoy", "policy_rate", "tension_index")
joined = (market.join(supplier, ["material", "country"], "left")
          .join(tariff, ["week", "material", "country"], "left")
          .join(shipping, ["week", "lane"], "left").join(macro, ["week", "country"], "left"))
assert joined.count() == manifest["files"]["prices"]["rows"], "Join multiplied supplier rows"
assert joined.filter("lane IS NULL OR congestion_index IS NULL OR pmi IS NULL OR tariff_rate IS NULL").count() == 0
aggregated = joined.groupBy("release_id", "week", "material").agg(
    F.avg("spot_price").alias("observed_mean_spot_price"),
    F.count("country").alias("supplier_count"),
    F.avg("congestion_index").alias("mean_lane_congestion"))
assert aggregated.filter("supplier_count != 3").count() == 0
for name, df in [("silver_supplier_week", joined), ("silver_material_week", aggregated)]:
    (df.write.format("delta").mode("overwrite")
       .option("replaceWhere", f"release_id = '{release_id}'").saveAsTable(f"{namespace}.{name}"))
    report["tables"][name] = {"rows": df.count(), "version":
        spark.sql(f"DESCRIBE HISTORY {namespace}.{name} LIMIT 1").first()["version"]}
labels = released("outcomes").select("week", "material", "benchmark_price")
check = aggregated.join(labels, ["week", "material"])
assert check.count() == manifest["files"]["outcomes"]["rows"]
assert check.filter(F.abs(F.col("observed_mean_spot_price") - F.col("benchmark_price")) > 0.01).count() == 0
report["benchmark_check"] = "passed"

# COMMAND ----------
# Verify the original sample contract and retain a downloadable known-good file.
# This is the organizer baseline, not a newly trained model or a Kaggle upload.
sample = released("sample_submission").drop("release_id", "source_sha256", "ingested_at").toPandas()
eligible = {}
for row in supplier.select("material", "country").collect():
    eligible.setdefault(row["material"], set()).add(row["country"])
expected_ids = {f"w{week}_{material}" for week in range(209, 235) for material in eligible}
assert len(sample) == 260 and sample["id"].is_unique and set(sample["id"]) == expected_ids
countries = ["KES", "VAL", "SUN", "ORI", "HAL", "AUR"]
for row in sample.to_dict("records"):
    material = row["id"].split("_", 1)[1]
    assert all(math.isfinite(row[column]) for column in sample.columns if column != "id")
    assert 0 <= row["disruption_prob"] <= 1 and row["price_forecast"] > 0 and row["order_units"] >= 0
    assert abs(sum(row[f"share_{country}"] for country in countries) - 1) <= 1e-6
    for country in countries:
        assert 0 <= row[f"share_{country}"] <= 1
        assert country in eligible[material] or row[f"share_{country}"] == 0
artifact_path = Path(f"/Volumes/{catalog}/{schema}/artifacts/{release_id}")
artifact_path.mkdir(parents=True, exist_ok=True)
baseline = artifact_path / "baseline_sample_submission.csv"
baseline.write_bytes((release_path / "sample_submission.csv").read_bytes())
report["baseline_sample_path"] = str(baseline)
report["baseline_sample_sha256"] = hashlib.sha256(baseline.read_bytes()).hexdigest()

# COMMAND ----------
mlflow.set_tracking_uri("databricks")
mlflow.set_experiment("/Shared/halcyon/setup")
with mlflow.start_run(run_name=f"workspace-setup-{release_id}") as run:
    mlflow.log_params({"release_id": release_id, "cutoff_week": manifest["cutoff_week"], "stage": "setup"})
    mlflow.set_tag("purpose", "workspace integration smoke test; not a model comparison")
    for name, info in report["tables"].items():
        mlflow.log_metric(f"rows_{name}", info["rows"])
    mlflow.log_metric("validated_sample_rows", len(sample))
    mlflow.log_dict(manifest, "source_manifest.json")
    mlflow.log_artifact(str(baseline), artifact_path="baseline")
    report["mlflow_run_id"] = run.info.run_id
    report["mlflow_experiment_id"] = run.info.experiment_id
    report["mlflow_version"] = mlflow.__version__
    mlflow.log_dict(report, "setup_report.json")
(artifact_path / "setup_report.json").write_text(json.dumps(report, indent=2) + "\n")
display(aggregated.orderBy("week", "material").limit(20))
dbutils.notebook.exit(json.dumps(report))
