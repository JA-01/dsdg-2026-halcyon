"""Write a Phase 2 run config from a release's setup report, so nothing is edited by hand.

python -m halcyon.phase2 --release <release_id> --archive-run <phase1_run_id> [--like configs/x.json]
python -m halcyon.phase2 ... --dry-run-cutoff 208   # rehearse on Phase 1 data, labeled as a rehearsal
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .data import SCHEMAS

ARTIFACTS = "/Volumes/workspace/halcyon/artifacts"


def build_config(template: dict, report: dict, archive_run: str, archive_sha256: str, *,
                 dry_run_cutoff: int | None = None) -> dict:
    """Inherit models and policy from a Phase 1 config; pin the release and the archived public rows."""
    versions = {f"bronze_{name}": report["tables"][f"bronze_{name}"]["version"] for name in SCHEMAS}
    source = {"kind": "delta", "catalog": template["source"]["catalog"], "schema": template["source"]["schema"],
              "release_id": report["release_id"], "versions": versions}
    run_name = "phase2-private"
    if dry_run_cutoff is not None:
        source["cutoff"] = dry_run_cutoff
        run_name = "phase2-dry-run-not-a-candidate"
    elif report["cutoff_week"] != 221:
        raise ValueError(f"{report['release_id']} covers week {report['cutoff_week']}, not 221; "
                         "pass --dry-run-cutoff only for a rehearsal")
    config = {key: template[key] for key in ("forecaster", "policy", "output_dir", "publish_dir", "mlflow") if key in template}
    if template.get("fallback"):
        config["fallback"] = template["fallback"]
    config["mlflow"] = {**config["mlflow"], "run_name": run_name}
    return {"mode": "phase2", "source": source, **config, "archived_public": {
        "csv_path": f"{ARTIFACTS}/runs/{archive_run}/submission.csv", "sha256": archive_sha256,
        "origin_run_id": archive_run, "origin_cutoff": 208}}


def main() -> None:
    from databricks.sdk import WorkspaceClient

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--release", required=True)
    parser.add_argument("--archive-run", required=True, help="Phase 1 run whose public rows are retained")
    parser.add_argument("--like", type=Path, default=Path("configs/phase1_inventory_delta.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run-cutoff", type=int)
    parser.add_argument("--profile", default="halcyon")
    args = parser.parse_args()
    w = WorkspaceClient(profile=args.profile)
    report = json.loads(w.files.download(f"{ARTIFACTS}/{args.release}/setup_report.json").contents.read())
    archived = w.files.download(f"{ARTIFACTS}/runs/{args.archive_run}/submission.csv").contents.read()
    config = build_config(json.loads(args.like.read_text()), report, args.archive_run,
                          hashlib.sha256(archived).hexdigest(), dry_run_cutoff=args.dry_run_cutoff)
    suffix = "dry_run" if args.dry_run_cutoff is not None else args.release
    output = args.output or Path(f"configs/phase2_{suffix}.json")
    output.write_text(json.dumps(config, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
