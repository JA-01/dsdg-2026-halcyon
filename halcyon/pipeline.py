"""Run forecasts and policy per window, then export and record one validated submission.

CLI: python -m halcyon.pipeline --config configs/phase1_baseline_local.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from .constants import MATERIALS, PUBLIC_WEEKS, SHARE_COLUMNS, SUBMISSION_COLUMNS, SUBMISSION_WEEKS
from .contracts import (
    ContractError, Forecaster, Policy, Window, eligibility, phase1_windows, phase2_windows,
    validate_decisions, validate_forecasts,
)
from .data import Dataset
from .submission import ExportResult, SubmissionError, build_submission, validate_bytes, write_submission

MODES = {"phase1": (208, phase1_windows), "phase2": (221, phase2_windows)}
PACKAGES = ("pandas", "numpy", "scikit-learn", "scipy", "mlflow", "databricks-sdk")


def submission_ids() -> list[str]:
    """The 260 ids in organizer sample order (tests pin this to sample_submission.csv)."""
    return [f"w{week}_{material}" for week in SUBMISSION_WEEKS for material in MATERIALS]


@dataclass(frozen=True)
class ArchivedPublic:
    """A validated earlier export whose public rows are retained in a Phase 2 submission."""

    csv_path: str
    sha256: str
    origin_run_id: str
    origin_cutoff: int = 208


@dataclass
class RunResult:
    run_id: str
    forecasts: pd.DataFrame
    decisions: pd.DataFrame
    export: ExportResult
    manifest: dict
    run_dir: Path


def _archived_frames(archived: ArchivedPublic, allowed: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = Path(archived.csv_path).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != archived.sha256:
        raise SubmissionError(f"archived submission checksum {actual} != expected {archived.sha256}")
    errors = validate_bytes(raw, submission_ids(), allowed)
    if errors:
        raise SubmissionError(f"archived submission is invalid: {errors[0]}")
    frame = pd.read_csv(Path(archived.csv_path))
    parts = frame["id"].str.extract(r"^w(?P<target_week>\d+)_(?P<material>.+)$")
    frame = frame.assign(target_week=parts["target_week"].astype(int), material=parts["material"])
    frame = frame[frame["target_week"].isin(PUBLIC_WEEKS)]
    context = {"window_id": "public", "cutoff_week": archived.origin_cutoff,
               "origin_run_id": archived.origin_run_id}
    keys = ["target_week", "material"]
    forecasts = frame[keys + list(SUBMISSION_COLUMNS[1:3])].assign(**context)
    decisions = frame[keys + ["order_units", *SHARE_COLUMNS]].assign(**context)
    return forecasts, decisions


def _with_identity(frame: pd.DataFrame, column: str, component: Any) -> pd.DataFrame:
    """Keep provenance when a module declares its identity on the class, not in the frame."""
    if column in frame.columns:
        return frame
    return frame.assign(**{column: getattr(component, column, type(component).__name__)})


def plan_windows(data: Dataset, windows: Sequence[Window], forecaster: Forecaster,
                 policy: Policy) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Forecast once per cutoff, then plan each window independently from its own forecasts."""
    suppliers = data["suppliers"]
    forecast_blocks, decision_blocks = [], []
    for cutoff in sorted({window.cutoff for window in windows}):
        members = [window for window in windows if window.cutoff == cutoff]
        targets = sorted(week for window in members for week in window.target_weeks)
        forecasts = validate_forecasts(forecaster.predict(data.as_of(cutoff), cutoff, targets), targets)
        forecasts = _with_identity(forecasts, "model_id", forecaster)
        for window in members:
            weeks = list(window.target_weeks)
            scoped = forecasts[forecasts["target_week"].isin(weeks)].reset_index(drop=True)
            decisions = validate_decisions(
                policy.decide(data.as_of(cutoff), scoped.copy(), cutoff, weeks), weeks, suppliers)
            decisions = _with_identity(decisions, "policy_id", policy)
            context = {"window_id": window.window_id, "cutoff_week": cutoff}
            forecast_blocks.append(scoped.assign(**context))
            decision_blocks.append(decisions.assign(**context))
    return pd.concat(forecast_blocks, ignore_index=True), pd.concat(decision_blocks, ignore_index=True)


def git_sha() -> str:
    if os.environ.get("HALCYON_GIT_SHA"):
        return os.environ["HALCYON_GIT_SHA"]
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True, cwd=Path(__file__).parent).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def code_lineage() -> dict[str, Any]:
    """The commit plus whether this checkout had uncommitted source, so a SHA is never overstated."""
    sha = git_sha()
    if os.environ.get("HALCYON_GIT_SHA"):
        return {"git_sha": sha, "dirty": sha.endswith("-dirty")}
    try:
        status = subprocess.run(["git", "status", "--porcelain", "halcyon", "configs", "notebooks"],
                                capture_output=True, text=True, check=True, cwd=Path(__file__).parent.parent)
        return {"git_sha": sha, "dirty": bool(status.stdout.strip())}
    except (OSError, subprocess.CalledProcessError):
        return {"git_sha": sha, "dirty": None}


def package_versions() -> dict[str, str]:
    found = {}
    for package in PACKAGES:
        try:
            found[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            found[package] = "absent"
    return found


def run_pipeline(cutoff: int, forecaster: Forecaster, policy: Policy, *, data: Dataset,
                 windows: Sequence[Window] | None = None, archived_public: ArchivedPublic | None = None,
                 output_dir: str | Path = "outputs", run_id: str | None = None,
                 lineage: dict | None = None) -> RunResult:
    """Core runner. `data` stays with the runner; modules only ever receive `as_of(cutoff)` views."""
    windows = tuple(windows) if windows is not None else phase1_windows(cutoff)
    run_id = run_id or f"local-{uuid.uuid4().hex[:12]}"
    allowed = eligibility(data["suppliers"])
    forecasts, decisions = plan_windows(data, windows, forecaster, policy)
    if archived_public is not None:
        old_forecasts, old_decisions = _archived_frames(archived_public, allowed)
        forecasts = pd.concat([old_forecasts, forecasts], ignore_index=True)
        decisions = pd.concat([old_decisions, decisions], ignore_index=True)
    forecasts, decisions = forecasts.assign(run_id=run_id), decisions.assign(run_id=run_id)

    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ids = submission_ids()
    export = write_submission(build_submission(forecasts, decisions, ids), run_dir / "submission.csv", ids, allowed)
    forecasts.to_csv(run_dir / "forecasts.csv", index=False)
    decisions.to_csv(run_dir / "decisions.csv", index=False)

    manifest = {
        "status": "exported", "run_id": run_id, **code_lineage(), "cutoff": cutoff,
        "windows": [asdict(window) for window in windows],
        "archived_public": asdict(archived_public) if archived_public else None,
        "model_ids": sorted(forecasts.get("model_id", pd.Series(dtype=str)).dropna().unique().tolist()),
        "policy_ids": sorted(decisions.get("policy_id", pd.Series(dtype=str)).dropna().unique().tolist()),
        "source_sha256": data.source_sha256, "package_versions": package_versions(),
        "export": {"file": export.path.name, "sha256": export.sha256, "rows": export.rows},
        "score_status": "not_evaluated", **(lineage or {}),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    (run_dir / "validation_report.json").write_text(json.dumps(
        {"valid": True, "errors": [], "rows": export.rows, "sha256": export.sha256}, indent=2) + "\n")
    return RunResult(run_id, forecasts, decisions, export, manifest, run_dir)


@dataclass
class RunConfig:
    """Parsed run file. See configs/ for examples. Unknown keys are errors."""

    mode: str
    source: dict
    forecaster: dict
    policy: dict
    fallback: dict | None = None
    archived_public: dict | None = None
    output_dir: str = "outputs"
    publish_dir: str | None = None
    mlflow: dict | None = None
    seed: int = 0
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, path: str | Path) -> "RunConfig":
        return cls.parse(json.loads(Path(path).read_text()))

    @classmethod
    def parse(cls, raw: dict) -> "RunConfig":
        allowed = set(cls.__dataclass_fields__) - {"raw"}
        unknown = set(raw) - allowed
        if unknown:
            raise ContractError(f"config: unknown keys {sorted(unknown)}")
        missing = {"mode", "source", "forecaster", "policy"} - set(raw)
        if missing:
            raise ContractError(f"config: missing keys {sorted(missing)}")
        config = cls(**raw, raw=raw)
        if config.mode not in MODES:
            raise ContractError(f"config: mode must be one of {sorted(MODES)}")
        if config.mode == "phase2" and not config.archived_public:
            raise ContractError("config: phase2 must name archived_public rows and their checksum")
        if config.mode == "phase1" and config.archived_public:
            raise ContractError("config: phase1 forecasts both windows; archived_public is phase2 only")
        kind = config.source.get("kind")
        if kind == "csv" and "path" not in config.source:
            raise ContractError("config: csv source needs path")
        if kind == "delta":
            needed = {"catalog", "schema", "release_id", "versions"} - set(config.source)
            if needed:
                raise ContractError(f"config: delta source needs {sorted(needed)}")
        if kind not in {"csv", "delta"}:
            raise ContractError("config: source.kind must be csv or delta")
        return config


def build_component(spec: dict) -> Any:
    """Instantiate {"class": "package.module:Name", "kwargs": {...}}."""
    module, _, name = spec["class"].partition(":")
    return getattr(importlib.import_module(module), name)(**spec.get("kwargs", {}))


def load_source(source: dict, spark=None) -> Dataset:
    if source["kind"] == "csv":
        return Dataset.from_csv_dir(source["path"])
    if spark is None:
        raise ContractError("a delta source needs a Spark session; run it in the Databricks job")
    from .delta import load_release
    return load_release(spark, source["catalog"], source["schema"], source["release_id"], source["versions"])


def run_from_config(config: RunConfig, spark=None) -> RunResult:
    default_cutoff, make_windows = MODES[config.mode]
    data = load_source(config.source, spark)
    cutoff = int(config.source.get("cutoff", default_cutoff))
    if data.observed_through != cutoff:
        raise ContractError(f"{config.mode} expects data through week {cutoff}, found {data.observed_through}")
    archived = ArchivedPublic(**config.archived_public) if config.archived_public else None
    lineage = {
        "mode": config.mode, "seed": config.seed, "config": config.raw,
        "release_id": config.source.get("release_id"), "delta_versions": config.source.get("versions"),
        "fallback_reason": None,
    }

    def execute(run_id: str | None, output_dir: str) -> RunResult:
        kwargs = dict(data=data, windows=make_windows(cutoff), archived_public=archived,
                      output_dir=output_dir, run_id=run_id, lineage=lineage)
        try:
            return run_pipeline(cutoff, build_component(config.forecaster), build_component(config.policy), **kwargs)
        except Exception as exc:
            if not config.fallback:
                raise
            lineage["fallback_reason"] = f"{type(exc).__name__}: {exc}"
            print(f"PRIMARY FAILED, using configured fallback: {lineage['fallback_reason']}", flush=True)
            return run_pipeline(cutoff, build_component(config.fallback["forecaster"]),
                                build_component(config.fallback["policy"]), **kwargs)

    if config.mlflow:
        result = _run_with_mlflow(config, execute)
    else:
        result = execute(None, config.output_dir)
    if config.publish_dir:
        shutil.copytree(result.run_dir, Path(config.publish_dir) / result.run_id, dirs_exist_ok=True)
    return result


def _run_with_mlflow(config: RunConfig, execute) -> RunResult:
    import mlflow

    if config.mlflow.get("tracking_uri"):
        mlflow.set_tracking_uri(config.mlflow["tracking_uri"])
    mlflow.set_experiment(config.mlflow["experiment"])
    with mlflow.start_run(run_name=config.mlflow.get("run_name")) as active, tempfile.TemporaryDirectory() as scratch:
        # Work on local disk: Volumes do not support every operation the atomic export uses.
        result = execute(active.info.run_id, scratch)
        manifest = result.manifest
        mlflow.log_params({
            "mode": config.mode, "seed": config.seed, "cutoff": manifest["cutoff"],
            "forecaster": config.forecaster["class"], "policy": config.policy["class"],
            "release_id": manifest.get("release_id"), "git_sha": manifest["git_sha"],
            "fallback_used": bool(manifest.get("fallback_reason")),
            "submission_sha256": manifest["export"]["sha256"],
        })
        mlflow.log_metric("submission_rows", manifest["export"]["rows"])
        mlflow.log_artifacts(str(result.run_dir))
        stable = Path(config.output_dir) / result.run_id
        shutil.copytree(result.run_dir, stable, dirs_exist_ok=True)
        result.run_dir = stable
        result.export = ExportResult(stable / result.export.path.name, result.export.sha256, result.export.rows)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Halcyon submission pipeline.")
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_from_config(RunConfig.load(args.config))
    print(json.dumps({"run_id": result.run_id, "submission": str(result.export.path),
                      "sha256": result.export.sha256, "rows": result.export.rows,
                      "fallback_reason": result.manifest.get("fallback_reason")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
