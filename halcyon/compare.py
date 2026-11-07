"""Compare forecaster/policy pairs on historical origins, with the final holdout locked.

CLI: python -m halcyon.compare --config configs/compare_dev.json

Every origin forecasts both 13-week windows from the same cutoff and simulates each with fresh
inventory. Economics come from AV's proxy simulator, so results are comparisons between candidates
and never an official competition score.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .constants import DEVELOPMENT_ORIGINS, FINAL_HOLDOUT_ORIGIN
from .contracts import ContractError, historical_windows
from .data import Dataset
from .pipeline import build_component, code_lineage, load_source, package_versions, plan_windows
from .simulator import SimulatorConfig, simulate_window

SCORE_STATUS = "proxy"


def forecast_metrics(forecasts: pd.DataFrame, data: Dataset, cutoff: int) -> dict[str, float]:
    """Raw Brier/MAPE, and the same errors for the competition's reference forecasts."""
    outcomes = data["outcomes"]
    truth = forecasts.merge(outcomes, left_on=["target_week", "material"], right_on=["week", "material"],
                            validate="one_to_one")
    if len(truth) != len(forecasts):
        raise ContractError("forecast weeks have no released outcomes to score against")
    history = outcomes[outcomes["week"] <= cutoff].sort_values("week").groupby("material")
    rate = truth["material"].map(history["disrupted"].mean())
    last_price = truth["material"].map(history["benchmark_price"].last())
    actual, price = truth["disrupted"], truth["benchmark_price"]
    brier = float(((truth["disruption_prob"] - actual) ** 2).mean())
    mape = float(((truth["price_forecast"] - price).abs() / price).mean())
    reference_brier = float(((rate - actual) ** 2).mean())
    reference_mape = float(((last_price - price).abs() / price).mean())
    return {
        "brier": brier, "mape": mape, "reference_brier": reference_brier, "reference_mape": reference_mape,
        # Undefined when the reference is perfect; kept NaN rather than reported as a perfect score.
        "brier_skill": 1 - brier / reference_brier if reference_brier else float("nan"),
        "mape_skill": 1 - mape / reference_mape if reference_mape else float("nan"),
    }


def backtest_pair(data: Dataset, name: str, forecaster, policy, origin: int) -> list[dict]:
    """Long-format rows keyed by candidate/origin/window/material/metric."""
    rows: list[dict] = []
    windows = historical_windows(origin)
    forecasts, decisions = plan_windows(data, windows, forecaster, policy)

    def add(window_id: str, material: str, metrics: Mapping[str, float]) -> None:
        for metric, value in metrics.items():
            rows.append({"candidate": name, "origin": origin, "window_id": window_id, "material": material,
                         "metric": metric, "value": float(value), "score_status": SCORE_STATUS})

    for window in windows:
        scoped = forecasts[forecasts["window_id"] == window.window_id]
        add(window.window_id, "__all__", forecast_metrics(scoped, data, origin))
        result = simulate_window(
            decisions[decisions["window_id"] == window.window_id], data["demand"], data["supply_history"],
            data["suppliers"], data["outcomes"], window.target_weeks[0], window.target_weeks[-1])
        by_material = {row["material"]: row for row in result.material_metrics.to_dict("records")}
        for material, row in by_material.items():
            add(window.window_id, material, {k: v for k, v in row.items()
                                             if isinstance(v, (int, float, np.number)) and k != "window_id"})
        add(window.window_id, "__all__", {k: v for k, v in result.metrics.iloc[0].to_dict().items()
                                          if isinstance(v, (int, float, np.number))})
    return rows


def compare(data: Dataset, candidates: Mapping[str, Mapping], origins: Sequence[int] = DEVELOPMENT_ORIGINS,
            allow_holdout: bool = False) -> pd.DataFrame:
    """Run every candidate on every origin. Building fresh components keeps each fold independent."""
    if FINAL_HOLDOUT_ORIGIN in origins and not allow_holdout:
        raise ContractError(f"origin {FINAL_HOLDOUT_ORIGIN} is the locked holdout; set allow_holdout once, at the end")
    rows = []
    for name, spec in candidates.items():
        for origin in origins:
            rows += backtest_pair(data, name, build_component(spec["forecaster"]), build_component(spec["policy"]), origin)
    return pd.DataFrame(rows)


SUMMARY_METRICS = ("brier", "mape", "brier_skill", "mape_skill", "total_cost", "fill_rate",
                   "shock_fill_rate", "mean_diversification")


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    """One row per candidate/origin/window of aggregate metrics, for side-by-side reading."""
    overall = results[(results["material"] == "__all__") & results["metric"].isin(SUMMARY_METRICS)]
    return (overall.pivot_table(index=["origin", "window_id", "candidate"], columns="metric", values="value")
            .reindex(columns=list(SUMMARY_METRICS)).reset_index())


def comparison_manifest(config: dict, data: Dataset, origins: Sequence[int]) -> dict:
    """Everything needed to reconstruct a comparison, beyond the numbers themselves."""
    return {**code_lineage(), "config": config, "origins": list(origins), "score_status": SCORE_STATUS,
            "holdout_used": FINAL_HOLDOUT_ORIGIN in origins, "source_sha256": data.source_sha256,
            "observed_through": data.observed_through, "package_versions": package_versions(),
            "simulator_assumptions": asdict(SimulatorConfig())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare candidates on historical origins.")
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text())
    data = load_source(config["source"])
    origins = config.get("origins", list(DEVELOPMENT_ORIGINS))
    results = compare(data, config["candidates"], origins, bool(config.get("allow_holdout", False)))
    summary = summarize(results)
    print(summary.round(4).to_string(index=False))

    output = Path(config.get("output_dir", "outputs/comparisons"))
    output.mkdir(parents=True, exist_ok=True)
    results.to_csv(output / "backtests.csv", index=False)
    summary.to_csv(output / "summary.csv", index=False)
    manifest = comparison_manifest(config, data, origins)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    if config.get("mlflow"):
        _log(config, results, summary, manifest)
    return 0


def _log(config: dict, results: pd.DataFrame, summary: pd.DataFrame, manifest: dict) -> None:
    import mlflow

    if config["mlflow"].get("tracking_uri"):
        mlflow.set_tracking_uri(config["mlflow"]["tracking_uri"])
    mlflow.set_experiment(config["mlflow"]["experiment"])
    with mlflow.start_run(run_name=config["mlflow"].get("run_name", "comparison")) as run, tempfile.TemporaryDirectory() as scratch:
        mlflow.log_params({"git_sha": manifest["git_sha"], "dirty": manifest["dirty"], "origins": str(config.get("origins", list(DEVELOPMENT_ORIGINS))),
                           "candidates": ",".join(config["candidates"]), "score_status": SCORE_STATUS})
        means = summary.groupby("candidate")[list(SUMMARY_METRICS)].mean()
        for candidate, row in means.iterrows():
            mlflow.log_metrics({f"{candidate}.{metric}": float(value) for metric, value in row.items() if np.isfinite(value)})
        directory = Path(scratch)
        results.to_csv(directory / "backtests.csv", index=False)
        summary.to_csv(directory / "summary.csv", index=False)
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        mlflow.log_artifacts(scratch)
        print(f"MLflow comparison run: {run.info.run_id}")


if __name__ == "__main__":
    sys.exit(main())
