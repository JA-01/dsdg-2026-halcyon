"""Upload current main sources and CSVs, run the Phase 2 Databricks job.

Uses the archived bootstrap's SDK import, Volume and serverless job APIs.
Credentials stay in the user's external Databricks authentication profile.
"""
import argparse
import base64
import io
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def source_zip(ref):
    """Ship committed halcyon code, without dependencies or working-tree edits."""
    revision = subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True).strip()
    package = subprocess.check_output(["git", "archive", "--format=zip", revision, "halcyon"], cwd=ROOT)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        if "halcyon/submit.py" not in archive.namelist():
            raise ValueError("Source ref does not contain halcyon.submit")
    return revision, package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="halcyon")
    parser.add_argument("--job-id", type=int, help="Reuse an existing project job, preserving its run_as identity")
    parser.add_argument("--catalog", default="workspace")
    parser.add_argument("--schema", default="halcyon")
    parser.add_argument("--source-ref", default="origin/main", help="Committed code to run (default: origin/main; git fetch first)")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--upload-only", action="store_true", help="Upload inputs/package, print bundle variables; do not deploy or run")
    args = parser.parse_args()
    if args.prepare_only and args.upload_only:
        parser.error("--prepare-only and --upload-only are mutually exclusive")
    if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x) for x in [args.catalog, args.schema]):
        raise ValueError("Invalid catalog/schema")
    schemas = json.loads((ROOT / "databricks/schemas.json").read_text())
    revision, package = source_zip(args.source_ref)
    # Validate exactly the committed package being uploaded, in a clean process.
    with tempfile.TemporaryDirectory(prefix="halcyon-databricks-") as temporary:
        archive = Path(temporary) / "halcyon.zip"
        archive.write_bytes(package)
        script = """import json, sys
sys.path.insert(0, sys.argv[1])
from halcyon.data import read_all
from halcyon.submit import build, validate
tables = read_all(sys.argv[2])
frame = build(tables)
validate(frame, tables)
print(json.dumps({'rows': len(frame), 'columns': {k: list(v.columns) for k, v in tables.items()}}))
"""
        check = json.loads(subprocess.check_output(
            [sys.executable, "-c", script, str(archive), str(args.data_dir.resolve())],
            cwd=temporary, text=True))
    for name, spec in schemas.items():
        if check["columns"][name] != [field.split()[0] for field in spec.split(",")]:
            raise ValueError(f"Unexpected CSV columns: {name}")
    if args.prepare_only:
        print(json.dumps({"source_revision": revision, "validated_local_rows": check["rows"], "sources": len(schemas)}))
        return

    from databricks.sdk import WorkspaceClient
    from databricks.sdk.errors import NotFound
    from databricks.sdk.service import catalog, compute, jobs, workspace
    w = WorkspaceClient(profile=args.profile)
    w.current_user.me()
    namespace = f"{args.catalog}.{args.schema}"
    try:
        w.schemas.get(namespace)
    except NotFound:
        w.schemas.create(args.schema, args.catalog)
    for name in ["raw", "artifacts"]:
        try:
            w.volumes.read(f"{namespace}.{name}")
        except NotFound:
            w.volumes.create(args.catalog, args.schema, name, catalog.VolumeType.MANAGED)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = f"/Volumes/{args.catalog}/{args.schema}/raw/phase2/{stamp}"
    w.files.create_directory(destination)
    for name in schemas:
        with (args.data_dir / f"{name}.csv").open("rb") as handle:
            w.files.upload(f"{destination}/{name}.csv", handle, overwrite=False)
    for name, contents in [("halcyon.zip", package), ("schemas.json", json.dumps(schemas).encode())]:
        w.files.upload(f"{destination}/{name}", io.BytesIO(contents), overwrite=False)
    if args.upload_only:
        print(json.dumps({"input_path": destination, "source_revision": revision,
                          "catalog": args.catalog, "schema": args.schema,
                          "next": "cd databricks; databricks bundle deploy --profile halcyon --var input_path=<input_path>,source_revision=<source_revision>; databricks bundle run submission --profile halcyon"}, indent=2))
        return
    folder = "/Workspace/Shared/halcyon/phase2"
    notebook = f"{folder}/Submission"
    w.workspace.mkdirs(folder)
    w.workspace.import_(path=notebook, format=workspace.ImportFormat.SOURCE,
                        language=workspace.Language.PYTHON, overwrite=True,
                        content=base64.b64encode((ROOT / "databricks/pipeline.py").read_bytes()).decode())
    task = jobs.Task(task_key="submission", timeout_seconds=1800, max_retries=0,
        environment_key="halcyon", notebook_task=jobs.NotebookTask(notebook_path=notebook,
        base_parameters={"catalog": args.catalog, "schema": args.schema,
                         "input_path": destination, "source_revision": revision}))
    settings = jobs.JobSettings(name="halcyon-phase2-submission", max_concurrent_runs=1,
        timeout_seconds=1800, tasks=[task], tags={"managed_by": "halcyon-phase2"},
        environments=[jobs.JobEnvironment(environment_key="halcyon", spec=compute.Environment(
            environment_version="3", dependencies=["mlflow==3.18.0", "pandas==3.1.1",
            "scikit-learn==1.9.1", "scipy==1.18.1"]))])
    if args.job_id:
        current = w.jobs.get(args.job_id)
        if (current.settings.tags or {}).get("managed_by") != "halcyon-phase2":
            raise RuntimeError("Refusing to modify a job outside the Phase 2 project")
        # Partial update leaves the existing run_as and job ACLs unchanged.
        w.jobs.update(args.job_id, new_settings=jobs.JobSettings(
            tasks=[task], environments=settings.environments,
            max_concurrent_runs=1, timeout_seconds=1800))
        if w.jobs.get(args.job_id).run_as_user_name != current.run_as_user_name:
            raise RuntimeError("Existing job identity changed; refusing to start")
        job_id = args.job_id
        run_id = w.jobs.run_now(job_id=job_id).run_id
        print(json.dumps({"job_id": job_id, "run_id": run_id, "source_revision": revision,
                          "run_url": f"{w.config.host}/jobs/{job_id}/runs/{run_id}"}, indent=2))
        return
    matches = list(w.jobs.list(name=settings.name))
    if len(matches) > 1 or any((job.settings.tags or {}).get("managed_by") != "halcyon-phase2" for job in matches):
        raise RuntimeError("Refusing to modify an unowned or ambiguous job")
    if matches:
        job_id = matches[0].job_id
        w.jobs.reset(job_id, settings)
    else:
        job_id = w.jobs.create(**{key: getattr(settings, key) for key in
            ["name", "max_concurrent_runs", "timeout_seconds", "tasks", "tags", "environments"]}).job_id
    run_id = w.jobs.run_now(job_id=job_id).run_id
    print(json.dumps({"job_id": job_id, "run_id": run_id, "source_revision": revision,
                      "run_url": f"{w.config.host}/jobs/{job_id}/runs/{run_id}"}, indent=2))


if __name__ == "__main__":
    main()
