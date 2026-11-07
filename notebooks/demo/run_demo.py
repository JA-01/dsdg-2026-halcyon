# Databricks notebook source
# MAGIC %md
# MAGIC # Halcyon: released observations → forecasts → supplier orders
# MAGIC A three-minute, artifact-backed walkthrough, not a training run. All checks run before
# MAGIC evidence is displayed. No market observations after the recorded cutoff are used.
# MAGIC **0:00–0:30:** release and exact export; **0:30–1:00:** independent windows;
# MAGIC **1:00–2:10:** one material's observed signals, forecasts and supplier orders;
# MAGIC **2:10–3:00:** real evaluation evidence, Databricks lineage and limitations.
# MAGIC Local: `python notebooks/demo/run_demo.py --run-dir outputs/demo-source/<run_id> --data-dir data --offline --output-dir outputs/demo/<run_id>`.
# MAGIC Add `--comparison-dir outputs/demo-source/<comparison_run_id>` to show a separate
# MAGIC real historical comparison, including per-window cost/fill regressions and lineage gaps.
# MAGIC Databricks: import this file as a Python SOURCE notebook; set `source_root` to the
# MAGIC deployed repository/package root and `run_dir` to the actual run Volume directory.
# MAGIC Live mode reads pinned Delta sources, gold outputs and MLflow. Leave `data_dir`
# MAGIC blank to use `/Volumes/<catalog>/<schema>/raw/<release_id>` for the organizer sample.
# MAGIC Offline mode requires the released CSV directory and never imports Spark or MLflow.

# COMMAND ----------
import argparse
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

IN_NOTEBOOK = "dbutils" in globals()
if IN_NOTEBOOK:
    for name, default in {
        "source_root": "/Workspace/Shared/halcyon/pipeline/src",
        "run_dir": "/Volumes/workspace/halcyon/artifacts/runs/c0001ec0e4c847b3821ad74c3bf422b2",
        "data_dir": "", "output_dir": "", "material": "", "offline": "false",
        "evaluation_artifacts": "[]", "comparison_dir": "",
    }.items():
        dbutils.widgets.text(name, default)
    sys.path.insert(0, dbutils.widgets.get("source_root"))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from halcyon.constants import SHARE_COLUMNS
from halcyon.contracts import eligibility, validate_decisions, validate_forecasts
from halcyon.data import Dataset, SCHEMAS
from halcyon.submission import build_submission, load_reference, validate_bytes


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    result = json.loads(path.read_bytes())
    require(isinstance(result, dict), f"{path}: expected a JSON object")
    return result


def same_values(actual, expected, columns, name):
    require(len(actual) == len(expected), f"{name}: row counts differ")
    for column in columns:
        left, right = actual[column], expected[column]
        if pd.api.types.is_numeric_dtype(right):
            require(np.allclose(left.to_numpy(dtype=float), right.to_numpy(dtype=float),
                                rtol=1e-12, atol=1e-12, equal_nan=False),
                    f"{name}: {column} differs")
        else:
            require(left.astype(str).tolist() == right.astype(str).tolist(),
                    f"{name}: {column} differs")


def check_context(frame, manifest, name):
    keys = ["run_id", "window_id", "target_week", "material"]
    required = keys + ["cutoff_week"]
    require(set(required) <= set(frame), f"{name}: missing identity/cutoff columns")
    require(not frame[required].isna().any().any(), f"{name}: null identity/cutoff")
    require(set(frame.run_id) == {manifest["run_id"]}, f"{name}: wrong run_id")
    require(not frame.duplicated(keys).any(), f"{name}: duplicate gold identity")
    for column in ("target_week", "cutoff_week"):
        require((frame[column] == frame[column].astype(int)).all(), f"{name}: noninteger {column}")
    windows = {w["window_id"]: w for w in manifest["windows"]}
    require(len(windows) == len(manifest["windows"]), "manifest: duplicate windows")
    archived = manifest.get("archived_public")
    if archived:
        require("public" not in windows, "manifest: archived public also regenerated")
        windows["public"] = {"cutoff": archived["origin_cutoff"], "target_weeks": list(range(209, 222))}
    require(set(frame.window_id) == set(windows), f"{name}: window identities differ")
    seen_weeks = set()
    for window_id, window in windows.items():
        block = frame[frame.window_id == window_id]
        weeks = set(window["target_weeks"])
        require(not (seen_weeks & weeks), "manifest: overlapping windows")
        seen_weeks |= weeks
        require(set(block.target_week) == weeks, f"{name}: wrong weeks in {window_id}")
        require(set(block.cutoff_week) == {window["cutoff"]}, f"{name}: wrong cutoff in {window_id}")
        require(min(weeks) > window["cutoff"], f"{name}: target not after cutoff")
        if archived and window_id == "public":
            require("origin_run_id" in block and set(block.origin_run_id) == {archived["origin_run_id"]},
                    f"{name}: archived origin_run_id differs")
    expected_targets = {"public": set(range(209, 222)), "private": set(range(222, 235))}
    require(set(windows) == set(expected_targets), f"{name}: expected public/private windows")
    for window_id, window in windows.items():
        require(set(window["target_weeks"]) == expected_targets[window_id],
                f"{name}: {window_id} does not match competition window")
        if not (archived and window_id == "public"):
            require(window["cutoff"] == manifest["cutoff"], f"{name}: manifest/window cutoff differs")
    return windows


def source_data(manifest, data_dir, offline, spark_session):
    source = manifest.get("config", {}).get("source", {})
    if source.get("kind") == "delta":
        require(source.get("release_id") == manifest.get("release_id"), "release lineage differs")
        require(source.get("versions") == manifest.get("delta_versions"), "Delta pins differ")
    if offline:
        require(bool(data_dir), "offline mode needs --data-dir with released CSVs")
        data = Dataset.from_csv_dir(data_dir)
    else:
        from halcyon.delta import load_release
        require(spark_session is not None, "live mode requires a Databricks Spark session")
        require(source.get("kind") == "delta", "live mode requires recorded Delta source config")
        data = load_release(spark_session, source["catalog"], source["schema"],
                            source["release_id"], source["versions"])
        if not data_dir:
            data_dir = f"/Volumes/{source['catalog']}/{source['schema']}/raw/{source['release_id']}"
    require(set(SCHEMAS) <= set(manifest["source_sha256"]), "manifest: incomplete source checksums")
    for name in SCHEMAS:
        require(data.source_sha256[name] == manifest["source_sha256"][name],
                f"{name}: supplied source differs from the run's released snapshot")
    ids, allowed = load_reference(data_dir)
    require(allowed == eligibility(data["suppliers"]), "reference supplier eligibility differs")
    return data, ids, allowed, Path(data_dir)


def material_tables(data, joined, material):
    signal_blocks = []
    for cutoff in sorted(joined.cutoff_week.unique()):
        visible = data.as_of(int(cutoff))
        prices = visible["prices"].query("material == @material")
        supply = visible["supply_history"].query("material == @material")
        prices = prices.sort_values("week").groupby("country").tail(1)
        supply = supply.sort_values("week").groupby("country").tail(1)
        require(not prices.empty and not supply.empty, f"no observed signals for {material} at {cutoff}")
        prices = prices.rename(columns={"week": "price_observed_week"})
        supply = supply.rename(columns={"week": "supply_observed_week"})
        signals = prices[["material", "country", "price_observed_week", "spot_price", "futures_4w"]].merge(
            supply[["material", "country", "supply_observed_week", "capacity_units", "lead_time_weeks", "landed_cost"]],
            on=["material", "country"], validate="one_to_one")
        suppliers = visible["suppliers"].query("material == @material")
        require(set(signals.country) == set(suppliers.country), "observed supplier coverage differs")
        signals = signals.merge(suppliers[["material", "country", "lane", "normal_capacity_units"]],
                                on=["material", "country"], validate="one_to_one")
        outcomes = visible["outcomes"].query("material == @material").sort_values("week")
        signals["cutoff_week"] = int(cutoff)
        signals["historical_disruption_rate"] = outcomes.disrupted.mean()
        signals["last_benchmark_price"] = outcomes.benchmark_price.iloc[-1]
        signals["benchmark_observed_week"] = int(outcomes.week.iloc[-1])
        signal_blocks.append(signals)
    signals = pd.concat(signal_blocks, ignore_index=True)
    trace = joined[joined.material == material].copy()
    trace["horizon"] = trace.target_week - trace.cutoff_week
    trace = trace.merge(data["demand"][["week", "material", "demand_units"]].rename(columns={"week": "target_week"}),
                        on=["target_week", "material"], validate="one_to_one")
    require(trace.demand_units.notna().all(), "missing known future demand")
    allocations = trace.melt(id_vars=["run_id", "window_id", "target_week", "cutoff_week", "material", "order_units"],
                             value_vars=list(SHARE_COLUMNS), var_name="share_column", value_name="supplier_share")
    allocations["country"] = allocations.share_column.str.removeprefix("share_")
    allocations["requested_supplier_units"] = allocations.order_units * allocations.supplier_share
    # These are requested orders, not realized fills, arrivals, or inventory trajectories.
    allocations = allocations.drop(columns="share_column").merge(
        signals, on=["cutoff_week", "material", "country"], how="left", validate="many_to_one")
    allocations["eligible"] = allocations.country.isin(data["suppliers"].query("material == @material").country)
    return signals, trace, allocations


def live_readback(manifest, forecasts, decisions, material, signals, spark_session):
    from mlflow.tracking import MlflowClient
    from pyspark.sql import Window, functions as F
    source = manifest["config"]["source"]
    for identifier in (source["catalog"], source["schema"]):
        require(re.fullmatch(r"[A-Za-z0-9_]+", identifier), "unsafe SQL identifier")
    namespace = f"`{source['catalog']}`.`{source['schema']}`"
    histories = []
    for name in ("prices", "supply_history", "outcomes"):
        table = f"bronze_{name}"
        history = spark_session.sql(f"DESCRIBE HISTORY {namespace}.{table}").toPandas()
        require(source["versions"][table] in set(history.version), f"{table}: pinned history unavailable")
        history["source_table"] = f"{source['catalog']}.{source['schema']}.{table}"
        history["pinned_version"] = source["versions"][table]
        histories.append(history)
    transformed = []
    for cutoff in sorted(signals.cutoff_week.unique()):
        latest = {}
        for name in ("prices", "supply_history"):
            table = f"bronze_{name}"
            frame = spark_session.sql(
                f"SELECT * FROM {namespace}.{table} VERSION AS OF {int(source['versions'][table])} "
                "WHERE release_id = :release_id AND week <= :cutoff AND material = :material",
                args={"release_id": source["release_id"], "cutoff": int(cutoff), "material": material})
            frame = frame.withColumn("_rank", F.row_number().over(
                Window.partitionBy("material", "country").orderBy(F.col("week").desc())))
            latest[name] = frame.filter(F.col("_rank") == 1)
        price = latest["prices"].select("material", "country", F.col("week").alias("price_observed_week"), "spot_price", "futures_4w")
        supply = latest["supply_history"].select("material", "country", F.col("week").alias("supply_observed_week"),
                                                       "capacity_units", "lead_time_weeks", "landed_cost")
        transformed.append(price.join(supply, ["material", "country"], "inner")
                           .withColumn("cutoff_week", F.lit(int(cutoff))).toPandas())
    spark_signals = pd.concat(transformed, ignore_index=True)
    order = ["cutoff_week", "material", "country"]
    same_values(spark_signals.sort_values(order).reset_index(drop=True),
                signals.sort_values(order).reset_index(drop=True), list(spark_signals.columns), "Spark cutoff transformation")
    gold_counts = {}
    for name, expected in (("forecasts", forecasts), ("decisions", decisions)):
        actual = spark_session.sql(
            f"SELECT * FROM {namespace}.gold_{name} WHERE run_id = :run_id AND release_id = :release_id",
            args={"run_id": manifest["run_id"], "release_id": manifest["release_id"]}).toPandas()
        keys = ["run_id", "window_id", "target_week", "material"]
        require(not actual.duplicated(keys).any(), f"gold_{name}: duplicate identity")
        same_values(actual.sort_values(keys).reset_index(drop=True),
                    expected.sort_values(keys).reset_index(drop=True),
                    [c for c in expected if c != "origin_run_id"], f"gold_{name}")
        gold_counts[name] = len(actual)
    settings = manifest["config"].get("mlflow", {})
    client = MlflowClient(tracking_uri=settings.get("tracking_uri", "databricks"))
    run = client.get_run(manifest["run_id"])
    params, metrics = dict(run.data.params), dict(run.data.metrics)
    for key, expected in {"submission_sha256": manifest["export"]["sha256"],
                          "release_id": manifest["release_id"], "git_sha": manifest["git_sha"]}.items():
        require(params.get(key) == expected, f"MLflow {key} differs")
    require(metrics.get("submission_rows") == manifest["export"]["rows"], "MLflow row metric differs")
    experiment = client.get_experiment(run.info.experiment_id)
    require(experiment.name == settings["experiment"], "MLflow experiment differs")
    readback = {"run_id": run.info.run_id, "status": run.info.status,
                "experiment_id": run.info.experiment_id, "experiment_name": experiment.name,
                "artifact_uri": run.info.artifact_uri, "params": params, "metrics": metrics,
                "gold_rows": gold_counts}
    return pd.concat(histories, ignore_index=True), spark_signals, readback


def evaluation_artifacts(run_dir, requested, run_id):
    # Only actual files are shown; an absent metric is never replaced with a synthetic score.
    defaults = ["backtests.csv", "comparison.csv", "evaluation.json"]
    names = list(dict.fromkeys([name for name in defaults if (run_dir / name).exists()] + requested))
    evidence, tables, provenance = [], {}, []
    for index, name in enumerate(names):
        path = Path(name)
        if not path.is_absolute():
            path = run_dir / path
        raw = path.read_bytes()
        require(bool(raw.strip()), f"{path}: empty evaluation artifact")
        if path.suffix == ".csv":
            frame = pd.read_csv(io.BytesIO(raw))
            require(not frame.empty, f"{path}: empty evaluation table")
            owner_ids = sorted(frame.run_id.dropna().astype(str).unique()) if "run_id" in frame else []
        elif path.suffix == ".json":
            payload = read_json(path)
            owner_ids = [str(payload["run_id"])] if "run_id" in payload else []
            frame = pd.json_normalize(payload)
        else:
            raise ValueError(f"{path}: evaluation artifacts must be CSV or JSON")
        output_name = f"evaluation_{index}.csv"
        tables[output_name] = frame
        evidence.append({"path": str(path.resolve()), "sha256": sha(raw), "table": output_name,
                         "declared_run_ids": owner_ids,
                         "linkage": "same_run" if owner_ids == [run_id] else "external_or_unlinked",
                         "scope": "artifact-owned historical/proxy evidence; not target-week realized performance"})
        provenance.append({"kind": "evaluation", "path": str(path.resolve()), "sha256": sha(raw)})
    return evidence, tables, provenance


def comparison_artifacts(directory):
    if not directory:
        return None, {}, []
    directory = Path(directory).resolve()
    config = read_json(directory / "config.json")
    backtests = pd.read_csv(directory / "backtests.csv")
    summary = pd.read_csv(directory / "summary.csv")
    keys = ["origin", "window_id", "candidate"]
    metric_columns = ["brier", "mape", "brier_skill", "mape_skill", "total_cost",
                      "fill_rate", "shock_fill_rate", "mean_diversification"]
    require(set(keys + ["material", "metric", "value", "score_status"]) <= set(backtests),
            "comparison: missing backtest columns")
    require(set(keys + metric_columns) <= set(summary), "comparison: missing summary columns")
    require(not backtests.empty and not summary.empty, "comparison: empty artifacts")
    require(not backtests.duplicated(keys + ["material", "metric"]).any(), "comparison: duplicate metric keys")
    require(not summary.duplicated(keys).any(), "comparison: duplicate summary keys")
    require(set(backtests.score_status) == {"proxy"}, "comparison: expected explicit proxy status")
    require(set(backtests.origin) == set(config["origins"]), "comparison: origins differ from config")
    require(set(backtests.candidate) == set(config["candidates"]), "comparison: candidates differ from config")
    for origin in config["origins"]:
        expected_windows = {f"origin{origin}_h01_13", f"origin{origin}_h14_26"}
        for candidate in config["candidates"]:
            require(set(summary[(summary.origin == origin) & (summary.candidate == candidate)].window_id)
                    == expected_windows, "comparison: independent-window coverage differs")
    overall = backtests[(backtests.material == "__all__") & backtests.metric.isin(metric_columns)]
    rebuilt = overall.pivot(index=keys, columns="metric", values="value").reset_index()
    left = summary.sort_values(keys).reset_index(drop=True)
    right = rebuilt.sort_values(keys).reset_index(drop=True)
    same_values(left, right, keys, "comparison summary identity")
    for column in metric_columns:
        require(np.allclose(left[column].to_numpy(dtype=float), right[column].to_numpy(dtype=float),
                            rtol=1e-12, atol=1e-12, equal_nan=True), f"comparison summary {column} differs")
    # Keep each origin/window visible: averages must not hide a regression.
    naive_names = [name for name, spec in config["candidates"].items()
                   if spec["policy"]["class"] == "halcyon.policy:NaivePolicy"]
    delta_tables = []
    if len(naive_names) == 1:
        naive = summary[summary.candidate == naive_names[0]]
        for candidate in sorted(set(summary.candidate) - set(naive_names)):
            delta = summary[summary.candidate == candidate].merge(
                naive, on=["origin", "window_id"], suffixes=("_candidate", "_naive"), validate="one_to_one")
            delta["cost_delta_candidate_minus_naive"] = delta.total_cost_candidate - delta.total_cost_naive
            delta["fill_delta_candidate_minus_naive"] = delta.fill_rate_candidate - delta.fill_rate_naive
            delta["cost_regression"] = delta.cost_delta_candidate_minus_naive > 0
            delta["fill_regression"] = delta.fill_delta_candidate_minus_naive < 0
            delta_tables.append(delta)
    provenance_names = ["config.json", "backtests.csv", "summary.csv"]
    readback_path = directory / "comparison_readback.json"
    readback = None
    run_id, git_sha = None, None
    if readback_path.exists():
        readback = read_json(readback_path)
        run = readback["run"]
        run_id = run["info"]["run_id"]
        params = {item["key"]: item["value"] for item in run["data"].get("params", [])}
        git_sha = params.get("git_sha")
        require(run["info"]["status"] == "FINISHED", "comparison MLflow run did not finish")
        require(params.get("score_status") == "proxy", "comparison MLflow status differs")
        require(json.loads(params["origins"]) == config["origins"], "comparison MLflow origins differ")
        require(set(params["candidates"].split(",")) == set(config["candidates"]),
                "comparison MLflow candidates differ")
        logged_metrics = {item["key"]: item["value"] for item in run["data"].get("metrics", [])}
        for candidate, group in summary.groupby("candidate"):
            for metric in metric_columns:
                value = group[metric].mean()
                if np.isfinite(value):
                    require(f"{candidate}.{metric}" in logged_metrics and
                            np.isclose(logged_metrics[f"{candidate}.{metric}"], value, rtol=1e-12, atol=1e-12),
                            f"comparison MLflow {candidate}.{metric} differs")
        provenance_names.append("comparison_readback.json")
    provenance = [{"kind": "separate_comparison", "path": str(directory / name),
                   "sha256": sha((directory / name).read_bytes())} for name in provenance_names]
    tables = {"comparison_summary.csv": summary, "comparison_backtests.csv": backtests}
    if delta_tables:
        tables["comparison_deltas.csv"] = pd.concat(delta_tables, ignore_index=True)
    report = {"directory": str(directory), "run_id": run_id, "recorded_git_sha": git_sha,
              "score_status": "proxy", "origins": config["origins"], "source": config["source"],
              "scope": "separate historical comparison; not the release run's realized evaluation",
              "holdout_182_present": 182 in config["origins"],
              "source_lineage_gap": "Comparison config records source location only; no source checksums/Delta pins are saved. Recorded Git SHA does not establish dirty-source identity.",
              "mlflow_readback": readback,
              "cost_regression_windows": int(sum(int(frame.cost_regression.sum()) for frame in delta_tables)),
              "fill_regression_windows": int(sum(int(frame.fill_regression.sum()) for frame in delta_tables))}
    return report, tables, provenance


def build_demo(run_dir, data_dir, output_dir, material="", offline=True, spark_session=None,
               evaluation_paths=None, comparison_dir=""):
    run_dir = Path(run_dir).resolve()
    files = ["manifest.json", "validation_report.json", "submission.csv", "forecasts.csv", "decisions.csv"]
    raw = {name: (run_dir / name).read_bytes() for name in files}
    manifest, recorded = json.loads(raw["manifest.json"]), json.loads(raw["validation_report.json"])
    require(isinstance(manifest, dict) and isinstance(recorded, dict), "run JSON must contain objects")
    require(manifest["status"] == "exported", "run did not export successfully")
    data, ids, allowed, reference_dir = source_data(manifest, data_dir, offline, spark_session)
    errors = validate_bytes(raw["submission.csv"], ids, allowed)
    require(not errors, f"exact submission invalid: {errors[:1]}")
    digest = sha(raw["submission.csv"])
    require(manifest["export"]["file"] == "submission.csv", "manifest points to a different export")
    for name, report in (("manifest", manifest["export"]), ("validation_report", recorded)):
        require(report["sha256"] == digest, f"{name}: submission checksum differs")
        require(report["rows"] == len(ids), f"{name}: submission row count differs")
    require(recorded["valid"] is True and recorded["errors"] == [], "recorded validation did not pass")
    forecasts = pd.read_csv(io.BytesIO(raw["forecasts.csv"]))
    decisions = pd.read_csv(io.BytesIO(raw["decisions.csv"]))
    windows = check_context(forecasts, manifest, "forecasts")
    check_context(decisions, manifest, "decisions")
    weeks = sorted({int(re.match(r"w(\d+)_", value).group(1)) for value in ids})
    materials = sorted(allowed)
    validate_forecasts(forecasts, weeks, materials)
    validate_decisions(decisions, weeks, data["suppliers"], materials)
    for frame, column, manifest_key in ((forecasts, "model_id", "model_ids"),
                                        (decisions, "policy_id", "policy_ids")):
        observed_ids = sorted(frame[column].dropna().unique()) if column in frame else []
        require(observed_ids == sorted(manifest.get(manifest_key, [])), f"manifest {manifest_key} differs")
    keys = ["run_id", "window_id", "cutoff_week", "target_week", "material"]
    joined = forecasts.merge(decisions, on=keys, how="outer", validate="one_to_one", indicator=True)
    require((joined._merge == "both").all(), "forecast/decision full context keys differ")
    joined = joined.drop(columns="_merge")
    rebuilt = build_submission(forecasts, decisions, ids)
    exported = pd.read_csv(io.BytesIO(raw["submission.csv"]))
    same_values(exported, rebuilt, list(rebuilt.columns), "export versus persisted forecast/decision")
    material = material or materials[0]
    require(material in materials, f"unknown material {material!r}; choose {materials}")
    signals, trace, allocations = material_tables(data, joined, material)
    window_rows = []
    for window_id, window in windows.items():
        block = joined[joined.window_id == window_id]
        window_rows.append({"run_id": manifest["run_id"], "window_id": window_id,
                            "cutoff_week": window["cutoff"], "first_target_week": int(block.target_week.min()),
                            "last_target_week": int(block.target_week.max()), "rows": len(block),
                            "materials": block.material.nunique(), "horizon_min": int((block.target_week - block.cutoff_week).min()),
                            "horizon_max": int((block.target_week - block.cutoff_week).max()),
                            "total_order_units": float(block.order_units.sum()),
                            "initial_stock": "fresh five-week demand stock", "initial_transit_units": 0,
                            "carry_from_other_window": False,
                            "inventory_evidence": "planning contract; no realized inventory simulation implied"})
    provenance = [{"kind": "run_artifact", "path": str(run_dir / name), "sha256": sha(content)}
                  for name, content in raw.items()]
    for name in SCHEMAS:
        provenance.append({"kind": "source_snapshot", "path": str(reference_dir / f"{name}.csv") if offline else f"bronze_{name}",
                           "sha256": data.source_sha256[name],
                           "delta_version": (manifest.get("delta_versions") or {}).get(f"bronze_{name}")})
    provenance.append({"kind": "reference_sample", "path": str(reference_dir / "sample_submission.csv"),
                       "sha256": sha((reference_dir / "sample_submission.csv").read_bytes())})
    evaluations, extra_tables, extra_provenance = evaluation_artifacts(run_dir, evaluation_paths or [], manifest["run_id"])
    comparison, comparison_tables, comparison_provenance = comparison_artifacts(comparison_dir)
    extra_tables.update(comparison_tables)
    extra_provenance.extend(comparison_provenance)
    provisional = any("provisional" in str(value).lower() for value in
                      [*manifest.get("model_ids", []), *manifest.get("policy_ids", []),
                       manifest.get("config", {}).get("forecaster", {}).get("class", ""),
                       manifest.get("config", {}).get("policy", {}).get("class", "")])
    provisional_policy = "provisional_capacity_split" in manifest.get("policy_ids", [])
    classification = ("PROVISIONAL baseline" if provisional_policy else
                      "POLICY candidate with PROVISIONAL forecast" if provisional else
                      "configured model/policy; selection unconfirmed")
    score_status = manifest["score_status"]
    limitations = ["Validation proves export feasibility, not predictive skill or competition score.",
                   "Observed price/supply signals are cutoff-safe context, not proof of causal feature attribution.",
                   "Supplier quantities are requested orders, not realized fills, arrivals, or inventory states.",
                   "Public/private windows initialize inventory independently; private never inherits public stock or transit.",
                   "External submissions, opt-in, final selection and video upload are not confirmed by these artifacts."]
    if provisional_policy:
        limitations.append("PROVISIONAL baseline, not a selected candidate: historical disruption rate and last observed benchmark price. Capacity-split policy orders known weekly demand; forecast values do not change its allocations. Market/supply views explain context, not an optimized response.")
    elif provisional:
        limitations.append("POLICY candidate with PROVISIONAL historical-rate/carry-forward forecasts. InventoryPolicy may use forecast risk/price for cover; observed context is not causal attribution. No final selection is confirmed.")
    else:
        limitations.append("Configured model/policy run; candidate selection or improvement requires separate comparison evidence.")
    if score_status == "not_evaluated":
        limitations.append("not_evaluated: this release run has no measured target-window performance; optional historical artifacts do not change that status.")
    if score_status == "proxy":
        limitations.append("proxy: simulator assumptions/normalizers are not verified organizer parity; no official score claim.")
    if not evaluations and not comparison:
        limitations.append("No backtest/comparison artifact is available in this demo input.")
    if comparison:
        limitations.append("Separate historical comparison is proxy evidence, not release target performance. Cost/fill regressions remain visible; no official score or holdout success is inferred.")
    if manifest.get("archived_public"):
        limitations.append("Public rows retain archived run/cutoff/checksum lineage. Historical context shown here comes from the current pinned release, not an independently recovered archived source snapshot.")
    tables = {"windows.csv": pd.DataFrame(window_rows), "source_signals.csv": signals,
              "material_forecasts_decisions.csv": trace, "supplier_allocations.csv": allocations, **extra_tables}
    live = {"status": "not_requested_offline", "description": "No live Delta/MLflow readback claimed."}
    if not offline:
        history, spark_signals, readback = live_readback(manifest, forecasts, decisions, material, signals, spark_session)
        tables["delta_history.csv"] = history
        tables["spark_cutoff_signals.csv"] = spark_signals
        live = {"status": "read_back", **readback}
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "run_id": manifest["run_id"],
              "run_dir": str(run_dir), "release_id": manifest.get("release_id"), "git_sha": manifest["git_sha"],
              "delta_versions": manifest.get("delta_versions"), "mode": manifest.get("mode"),
              "model_ids": manifest.get("model_ids", []), "policy_ids": manifest.get("policy_ids", []),
              "fallback_reason": manifest.get("fallback_reason"),
              "classification": classification, "archived_public": manifest.get("archived_public"),
              "score_status": score_status, "material": material,
              "exact_export": {"valid": True, "sha256": digest, "rows": len(exported),
                               "reference_ids_and_eligibility": "passed", "persisted_outputs_match": True,
                               "manifest_and_report_match": True, "full_context_keys_match": True},
              "evaluation_artifacts": evaluations, "comparison": comparison, "live_evidence": live, "limitations": limitations,
              "presentation_flow": [{"seconds": "0–30", "view": "run identity and exact_export"},
                                    {"seconds": "30–60", "view": "windows.csv; independent inventory"},
                                    {"seconds": "60–130", "view": "source_signals.csv → material_forecasts_decisions.csv → supplier_allocations.csv"},
                                    {"seconds": "130–180", "view": "evaluation_artifacts, live_evidence, limitations"}]}
    tables["provenance.csv"] = pd.DataFrame(provenance + extra_provenance)
    output_dir = Path(output_dir) if output_dir else run_dir.parent / "demo" / manifest["run_id"]
    require(output_dir.resolve() != run_dir, "output directory must differ from input run directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name, frame in tables.items():
        path = output_dir / name
        frame.to_csv(path, index=False)
        outputs.append({"file": name, "rows": len(frame), "sha256": sha(path.read_bytes())})
    report["output_dir"] = str(output_dir.resolve())
    report["tables"] = outputs
    (output_dir / "demo_report.json").write_text(json.dumps(report, indent=2, default=str, allow_nan=False) + "\n")
    return report, tables

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Exact export and lineage (0:00–0:30)
# MAGIC The checksum below is recomputed from the actual submitted bytes, compared to both
# MAGIC recorded reports, and the decoded values are checked against persisted model/policy outputs.

# COMMAND ----------
if IN_NOTEBOOK:
    offline_text = dbutils.widgets.get("offline").lower()
    require(offline_text in {"true", "false"}, "offline must be true or false")
    requested_evaluation = json.loads(dbutils.widgets.get("evaluation_artifacts"))
    require(isinstance(requested_evaluation, list) and all(isinstance(p, str) for p in requested_evaluation),
            "evaluation_artifacts must be a JSON array of file paths")
    demo_report, demo_tables = build_demo(
        dbutils.widgets.get("run_dir"), dbutils.widgets.get("data_dir"), dbutils.widgets.get("output_dir"),
        material=dbutils.widgets.get("material"), offline=offline_text == "true",
        spark_session=globals().get("spark"), evaluation_paths=requested_evaluation,
        comparison_dir=dbutils.widgets.get("comparison_dir"))
    print(json.dumps({key: demo_report[key] for key in (
        "run_id", "classification", "release_id", "git_sha", "delta_versions", "model_ids", "policy_ids", "exact_export")}, indent=2))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Two independent windows (0:30–1:00)
# MAGIC Both windows start with fresh five-week stock and zero transit. In Phase 1, private
# MAGIC horizons are 14–26 from the same cutoff, not a second forecast using public outcomes.
# MAGIC The table describes the planning boundary, not an unexecuted inventory simulation.

# COMMAND ----------
if IN_NOTEBOOK:
    display(demo_tables["windows.csv"])

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Trace one material (1:00–2:10)
# MAGIC Read the observed-week columns first: every observation is at or before its cutoff.
# MAGIC Then follow the actual forecast and order rows into eligible supplier allocations.
# MAGIC For the provisional baseline, historical disruption/benchmark observations generate
# MAGIC forecasts; known demand and static normal capacities generate orders and shares.
# MAGIC It does **not** optimize orders in response to these market signals or forecast values.
# MAGIC Requested supplier units are order × share, not realized supplier fills.

# COMMAND ----------
if IN_NOTEBOOK:
    display(demo_tables["source_signals.csv"])
    display(demo_tables["material_forecasts_decisions.csv"])
    display(demo_tables["supplier_allocations.csv"].query("eligible"))

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Evidence and limitations (2:10–3:00)
# MAGIC `not_evaluated` is not zero performance. `proxy` is not an official score.
# MAGIC Historical comparisons appear only when real files exist; external/unlinked files
# MAGIC are explicitly identified. Live mode executes DESCRIBE HISTORY, pinned Spark cutoff
# MAGIC transformations, gold run-key checks and actual MLflow parameter/metric readback.
# MAGIC Offline mode makes no claim to have contacted Databricks.

# COMMAND ----------
if IN_NOTEBOOK:
    for name, frame in demo_tables.items():
        if name.startswith("evaluation_") or name in {"delta_history.csv", "spark_cutoff_signals.csv",
                                                     "comparison_summary.csv", "comparison_deltas.csv"}:
            print(name)
            display(frame)
    print(json.dumps({key: demo_report[key] for key in (
        "score_status", "evaluation_artifacts", "comparison", "live_evidence", "limitations", "output_dir")}, indent=2))
    display(demo_tables["provenance.csv"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate real Halcyon run artifacts and save offline demo evidence.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--material", default="")
    parser.add_argument("--comparison-dir", default="", help="Separate real config/backtests/summary directory.")
    parser.add_argument("--offline", action="store_true", help="Explicit offline mode (Python CLI is always offline).")
    parser.add_argument("--evaluation-artifact", action="append", default=[],
                        help="Real CSV/JSON path; relative paths are resolved inside run-dir. Repeatable.")
    args = parser.parse_args(argv)
    report, _ = build_demo(args.run_dir, args.data_dir, args.output_dir, material=args.material,
                           offline=True, evaluation_paths=args.evaluation_artifact,
                           comparison_dir=args.comparison_dir)
    print(json.dumps(report, indent=2, default=str, allow_nan=False))
    return 0


if __name__ == "__main__" and not IN_NOTEBOOK:
    raise SystemExit(main())
