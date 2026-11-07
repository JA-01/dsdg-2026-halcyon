"""Provision the Halcyon workspace and start its serverless setup notebook.

Authenticate with `databricks auth login --profile halcyon` first. No secrets
are written to the repository. Resources are confined to the selected schema
and /Workspace/Shared/halcyon; existing unrelated resources are not modified.
"""

import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
from databricks.sdk.service import catalog, compute, jobs, workspace


ROOT = Path(__file__).resolve().parents[2]
DEPENDENCIES = (Path(__file__).parent / "requirements.txt").read_text().splitlines()
SPECS = {
    "demand": ("week INT,date DATE,material STRING,demand_units INT", ["week", "material"]),
    "macro": ("week INT,date DATE,country STRING,pmi DOUBLE,fx_rate DOUBLE,cpi_yoy DOUBLE,policy_rate DOUBLE,tension_index DOUBLE", ["week", "country"]),
    "news": ("article_id STRING,week INT,date DATE,source STRING,headline STRING,body STRING", ["article_id"]),
    "outcomes": ("week INT,date DATE,material STRING,benchmark_price DOUBLE,disrupted INT", ["week", "material"]),
    "prices": ("week INT,date DATE,material STRING,country STRING,spot_price DOUBLE,futures_4w DOUBLE", ["week", "material", "country"]),
    "shipping": ("week INT,date DATE,lane STRING,container_rate DOUBLE,transit_days INT,congestion_index DOUBLE", ["week", "lane"]),
    "suppliers": ("material STRING,country STRING,country_name STRING,lane STRING,base_lead_weeks INT,normal_capacity_units INT,base_tariff DOUBLE", ["material", "country"]),
    "supply_history": ("week INT,date DATE,material STRING,country STRING,capacity_units INT,lead_time_weeks INT,landed_cost DOUBLE", ["week", "material", "country"]),
    "tariffs": ("week INT,date DATE,material STRING,country STRING,tariff_rate DOUBLE,announced_rate DOUBLE,announced_effective_week INT", ["week", "material", "country"]),
    "sample_submission": ("id STRING,disruption_prob DOUBLE,price_forecast DOUBLE,order_units DOUBLE,share_KES DOUBLE,share_VAL DOUBLE,share_SUN DOUBLE,share_ORI DOUBLE,share_HAL DOUBLE,share_AUR DOUBLE", ["id"]),
}


def build_manifest(data_dir):
    """Validate source shapes and fingerprint the complete release before upload."""
    files = {}
    for name, (schema, keys) in SPECS.items():
        path = data_dir / f"{name}.csv"
        raw = path.read_bytes()
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        expected = [field.split()[0] for field in schema.split(",")]
        if reader.fieldnames != expected:
            raise ValueError(f"Unexpected columns in {path.name}: {reader.fieldnames}")
        rows = list(reader)
        if not rows:
            raise ValueError(f"Empty input: {path.name}")
        natural_keys = [tuple(row[key] for key in keys) for row in rows]
        if any(any(value in (None, "") for value in key) for key in natural_keys):
            raise ValueError(f"Null key in {path.name}")
        if len(set(natural_keys)) != len(rows):
            raise ValueError(f"Duplicate keys in {path.name}")
        weeks = [int(row["week"]) for row in rows] if "week" in expected else []
        files[name] = {
            "filename": path.name,
            "schema": schema,
            "keys": keys,
            "rows": len(rows),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "max_week": max(weeks) if weeks else None,
        }
    cutoff = files["outcomes"]["max_week"]
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:12]
    return {"release_id": f"weeks-1-{cutoff}-{digest}", "cutoff_week": cutoff, "files": files}


def notebook_content():
    """Render the source-format notebook into an importable Jupyter notebook."""
    source = (Path(__file__).parent / "workspace_setup.py").read_text()
    cells = []
    for block in source.replace("# Databricks notebook source\n", "", 1).split("# COMMAND ----------"):
        lines = [line.removeprefix("# MAGIC ") for line in block.strip().splitlines()]
        cells.append({"cell_type": "code", "metadata": {}, "execution_count": None,
                      "outputs": [], "source": [line + "\n" for line in lines]})
    return json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }, "cells": cells}).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="halcyon")
    parser.add_argument("--catalog", default="workspace")
    parser.add_argument("--schema", default="halcyon")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--prepare-only", action="store_true", help="Validate inputs without remote calls")
    args = parser.parse_args()
    if not all(name.replace("_", "").isalnum() for name in [args.catalog, args.schema]):
        raise ValueError("Catalog/schema must use letters, numbers, or underscores")
    manifest = build_manifest(args.data_dir)
    if args.prepare_only:
        print(json.dumps(manifest, indent=2))
        return
    w = WorkspaceClient(profile=args.profile)
    w.current_user.me()  # Fail early if authentication is missing.
    full_schema = f"{args.catalog}.{args.schema}"
    try:
        w.schemas.get(full_schema)
    except NotFound:
        w.schemas.create(args.schema, args.catalog, comment="Bay Area Builders supply-chain project")
    for name in ["raw", "artifacts"]:
        try:
            w.volumes.read(f"{full_schema}.{name}")
        except NotFound:
            w.volumes.create(args.catalog, args.schema, name, catalog.VolumeType.MANAGED)
    release_path = f"/Volumes/{args.catalog}/{args.schema}/raw/{manifest['release_id']}"
    w.files.create_directory(release_path)
    for spec in manifest["files"].values():
        with (args.data_dir / spec["filename"]).open("rb") as handle:
            w.files.upload(f"{release_path}/{spec['filename']}", handle, overwrite=True)
    w.files.upload(f"{release_path}/manifest.json", io.BytesIO(json.dumps(manifest, indent=2).encode()), overwrite=True)
    print(f"Uploaded {len(manifest['files'])} sources to {release_path}", flush=True)

    folder = "/Workspace/Shared/halcyon"
    w.workspace.mkdirs(folder)
    notebook_path = f"{folder}/Workspace Setup"
    w.workspace.import_(path=notebook_path, format=workspace.ImportFormat.JUPYTER,
                        content=base64.b64encode(notebook_content()).decode(), overwrite=True)
    task = jobs.Task(task_key="setup", timeout_seconds=1800, max_retries=0,
        environment_key="halcyon", notebook_task=jobs.NotebookTask(
            notebook_path=notebook_path,
            base_parameters={"catalog": args.catalog, "schema": args.schema, "release_path": release_path}))
    settings = jobs.JobSettings(name="halcyon-workspace-setup", max_concurrent_runs=1,
        timeout_seconds=1800, tasks=[task], tags={"project": "halcyon", "managed_by": "dsdg-bootstrap"},
        environments=[jobs.JobEnvironment(environment_key="halcyon",
            spec=compute.Environment(environment_version="3", dependencies=DEPENDENCIES))])
    matching = list(w.jobs.list(name=settings.name, expand_tasks=True))
    owned = [job for job in matching if (job.settings.tags or {}).get("managed_by") == "dsdg-bootstrap"]
    if matching and not owned:
        raise RuntimeError("A job with this name already exists but is not managed by this bootstrap")
    if len(owned) > 1:
        raise RuntimeError("Multiple managed setup jobs exist; select one before rerunning")
    if owned:
        job_id = owned[0].job_id
        w.jobs.reset(job_id, settings)
    else:
        job_id = w.jobs.create(**{k: getattr(settings, k) for k in [
            "name", "max_concurrent_runs", "timeout_seconds", "tasks", "tags", "environments"]}).job_id
    run_id = w.jobs.run_now(job_id=job_id).run_id
    result = {"host": w.config.host, "profile": args.profile, "catalog": args.catalog,
        "schema": args.schema, "release_id": manifest["release_id"], "release_path": release_path,
        "notebook_path": notebook_path, "job_id": job_id, "run_id": run_id,
        "job_url": f"{w.config.host}/jobs/{job_id}",
        "run_url": f"{w.config.host}/jobs/{job_id}/runs/{run_id}"}
    # This file deliberately contains identifiers only, never credentials.
    output = Path.home() / ".local/share/dsdg-databricks"
    output.mkdir(parents=True, exist_ok=True)
    (output / "workspace.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
