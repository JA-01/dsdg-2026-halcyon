"""Check a finished run from what is actually stored remotely, not from the job's own report.

python -m halcyon.accept <mlflow_run_id> [--retained-from <run_id>] [--download-to dir]

Exit code 0 means every check passed. Files are read from the artifacts Volume, then compared with
the manifest, MLflow and the gold tables. This never starts a job or changes anything.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

import pandas as pd

from .constants import PUBLIC_WEEKS
from .contracts import eligibility
from .pipeline import submission_ids
from .submission import validate_bytes

ARTIFACTS = "/Volumes/workspace/halcyon/artifacts/runs"
WAREHOUSE = "ece93a7877e9e544"
GOLD_TABLES = ("gold_forecasts", "gold_decisions")


def public_rows(raw: bytes) -> pd.DataFrame:
    frame = pd.read_csv(io.BytesIO(raw))
    weeks = frame["id"].str.extract(r"^w(\d+)_")[0].astype(int)
    return frame[weeks.isin(PUBLIC_WEEKS)].reset_index(drop=True)


def retained_run(manifest: dict, explicit: str | None = None) -> str | None:
    """The run whose public rows must match: a Phase 2 manifest always names one, so never skip the check."""
    archived = manifest.get("archived_public")
    return explicit or (archived["origin_run_id"] if archived else None)


def check_export(raw: bytes, manifest: dict, mlflow_sha256: str | None, suppliers: pd.DataFrame,
                 retained: bytes | None = None) -> list[tuple[str, bool, str]]:
    """Pure checks on one run's bytes and records. Each result is (name, passed, detail)."""
    digest = hashlib.sha256(raw).hexdigest()
    errors = validate_bytes(raw, submission_ids(), eligibility(suppliers))
    checks = [
        ("csv passes the validator", not errors, errors[0] if errors else "260 rows"),
        ("csv hash matches manifest", digest == manifest["export"]["sha256"], digest),
        ("csv hash matches MLflow", digest == mlflow_sha256, str(mlflow_sha256)),
        ("built from clean code", manifest.get("dirty") is False, str(manifest.get("git_sha"))),
        ("no fallback used", not manifest.get("fallback_reason"), str(manifest.get("fallback_reason"))),
    ]
    if retained is not None:
        same = public_rows(raw).equals(public_rows(retained))
        checks.append(("public rows match the archived run", same, f"{len(public_rows(raw))} rows"))
    return checks


def check_gold(counts: dict[tuple[str, str], tuple[int, int]], windows: list[str]) -> list[tuple[str, bool, str]]:
    """counts maps (table, window) to (rows, unique target_week/material keys)."""
    return [(f"{table} {window} has 130 unique rows", counts.get((table, window)) == (130, 130),
             str(counts.get((table, window)))) for table in GOLD_TABLES for window in windows]


def main(argv: list[str] | None = None) -> int:
    import mlflow
    from databricks.sdk import WorkspaceClient

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run_id")
    parser.add_argument("--retained-from", help="run whose public rows this run must retain")
    parser.add_argument("--download-to", type=Path)
    parser.add_argument("--profile", default="halcyon")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    if not args.run_id.isalnum() or (args.retained_from and not args.retained_from.isalnum()):
        parser.error("run ids are alphanumeric")

    w = WorkspaceClient(profile=args.profile)
    read = lambda run, name: w.files.download(f"{ARTIFACTS}/{run}/{name}").contents.read()
    raw = read(args.run_id, "submission.csv")
    manifest = json.loads(read(args.run_id, "manifest.json"))
    mlflow.set_tracking_uri(f"databricks://{args.profile}")
    run = mlflow.tracking.MlflowClient().get_run(args.run_id)
    retained_from = retained_run(manifest, args.retained_from)
    retained = read(retained_from, "submission.csv") if retained_from else None
    checks = check_export(raw, manifest, run.data.params.get("submission_sha256"),
                          pd.read_csv(args.data_dir / "suppliers.csv"), retained)
    checks.append(("MLflow run finished", run.info.status == "FINISHED", run.info.status))

    counts = {}
    for table in GOLD_TABLES:
        result = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE, wait_timeout="30s",
            statement=f"SELECT window_id, count(*), count(DISTINCT target_week, material) "
                      f"FROM workspace.halcyon.{table} WHERE run_id = '{args.run_id}' GROUP BY 1")
        for window, rows, unique in result.result.data_array or []:
            counts[(table, window)] = (int(rows), int(unique))
    checks += check_gold(counts, ["public", "private"])

    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'}  {name}: {detail}")
    if args.download_to:
        args.download_to.mkdir(parents=True, exist_ok=True)
        (args.download_to / "submission.csv").write_bytes(raw)
    return 0 if all(passed for _, passed, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
