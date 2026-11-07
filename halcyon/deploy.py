"""Upload the pipeline to the shared workspace, manage its saved job, and optionally run it.

python -m halcyon.deploy --profile halcyon [--config configs/x.json] [--run]
Never edits the setup job. Team access is copied from that job's permissions, so no emails live here.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import compute, iam, jobs, workspace

ROOT = Path(__file__).resolve().parent.parent
FOLDER = "/Workspace/Shared/halcyon/pipeline"
NOTEBOOK = f"{FOLDER}/run_pipeline"
SOURCE_ROOT = f"{FOLDER}/src"
JOB_NAME = "halcyon-pipeline"
TAG = "halcyon-pipeline"
SETUP_JOB = "408041045566144"
DEPENDENCIES = ["databricks-sdk==0.162.0", "mlflow==3.18.0", "pandas==3.1.1",
                "scikit-learn==1.9.1", "scipy==1.18.1"]


def upload_sources(w: WorkspaceClient) -> None:
    files = [*ROOT.glob("halcyon/**/*.py"), *ROOT.glob("configs/*.json")]
    for path in files:
        target = f"{SOURCE_ROOT}/{path.relative_to(ROOT)}"
        w.workspace.mkdirs(target.rsplit("/", 1)[0])
        w.workspace.import_(path=target, format=workspace.ImportFormat.AUTO, overwrite=True,
                            content=base64.b64encode(path.read_bytes()).decode())
    w.workspace.import_(path=NOTEBOOK, format=workspace.ImportFormat.SOURCE,
                        language=workspace.Language.PYTHON, overwrite=True,
                        content=base64.b64encode((ROOT / "notebooks/pipeline/run_pipeline.py").read_bytes()).decode())
    print(f"Uploaded {len(files)} files to {SOURCE_ROOT}", flush=True)


def ensure_job(w: WorkspaceClient, config: str) -> int:
    task = jobs.Task(task_key="pipeline", environment_key="halcyon", timeout_seconds=1800, max_retries=0,
                     notebook_task=jobs.NotebookTask(notebook_path=NOTEBOOK))
    settings = jobs.JobSettings(
        name=JOB_NAME, max_concurrent_runs=1, timeout_seconds=1800, tasks=[task], tags={"project": "halcyon", "managed_by": TAG},
        parameters=[jobs.JobParameterDefinition(name="config", default=config),
                    jobs.JobParameterDefinition(name="git_sha", default="unknown"),
                    jobs.JobParameterDefinition(name="source_root", default=SOURCE_ROOT)],
        environments=[jobs.JobEnvironment(environment_key="halcyon", spec=compute.Environment(
            environment_version="3", dependencies=DEPENDENCIES))])
    matching = list(w.jobs.list(name=JOB_NAME, expand_tasks=True))
    owned = [job for job in matching if (job.settings.tags or {}).get("managed_by") == TAG]
    if matching and not owned:
        raise RuntimeError(f"A job named {JOB_NAME} exists but is not managed by this script")
    if owned:
        w.jobs.reset(owned[0].job_id, settings)
        return owned[0].job_id
    return w.jobs.create(**{k: getattr(settings, k) for k in (
        "name", "max_concurrent_runs", "timeout_seconds", "tasks", "tags", "parameters", "environments")}).job_id


def share_job(w: WorkspaceClient, job_id: int) -> list[str]:
    """Grant each user on the setup job CAN_MANAGE_RUN here, then read the grant back."""
    acl = w.jobs.get_permissions(SETUP_JOB).access_control_list or []
    users = sorted({item.user_name for item in acl if item.user_name})
    w.jobs.update_permissions(str(job_id), access_control_list=[
        jobs.JobAccessControlRequest(user_name=user, permission_level=jobs.JobPermissionLevel.CAN_MANAGE_RUN)
        for user in users])
    granted = {item.user_name for item in w.jobs.get_permissions(str(job_id)).access_control_list or []}
    missing = set(users) - granted
    if missing:
        raise RuntimeError(f"job ACL did not apply for {sorted(missing)}")
    return users


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--profile", default="halcyon")
    parser.add_argument("--config", default="configs/phase1_baseline_delta.json")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    w = WorkspaceClient(profile=args.profile)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "halcyon", "configs", "notebooks"],
                           capture_output=True, text=True, cwd=ROOT).stdout.strip()
    version = f"{sha}-dirty" if dirty else sha
    upload_sources(w)
    job_id = ensure_job(w, args.config)
    users = share_job(w, job_id)
    output = {"job_id": job_id, "git_sha": version, "shared_with": len(users), "job_url": f"{w.config.host}/jobs/{job_id}"}
    if args.run:
        waiter = w.jobs.run_now(job_id=job_id, job_parameters={"config": args.config, "git_sha": version})
        output["run_id"] = waiter.run_id
        print(f"Started run {waiter.run_id}", flush=True)
        run = waiter.result()
        output["state"] = str(run.state.result_state)
        output["task_output"] = w.jobs.get_run_output(run.tasks[0].run_id).notebook_output.result
    print(json.dumps(output, indent=2), flush=True)


if __name__ == "__main__":
    main()
