"""Jaseer's V2 evidence: throwaway estimator of the published score formula.

NOT organizer parity and not calibrated to any Kaggle score. Compare candidates only.
  naive      = halcyon.policy.NaivePolicy (sample-shaped: demand, largest normal-capacity supplier)
  hindsight  = per-material LP on realized capacity/lead/landed cost inside the window
  F          = clip((naive - ours) / (naive - hindsight), 0, 1), costs from halcyon.simulator
  fill skill = clip((ours - naive) / (1 - naive), 0, 1) on shock+4 recovery weeks; 0 if naive fill is 1
  R          = 0.7 fill skill + 0.3 mean row diversification; P = 0 (policy-only comparison)
Windows: h1-13 from origins 52..169 step 13 (set A) and 58..162 step 13 (set B); no target past 182.

Run from the repository root:  python docs/agents/jaseer-v2-evidence/estimate.py
Writes per-window raw outcomes to docs/agents/jaseer-v2-evidence/windows.csv.

Comparison evidence (no parameter sweep):
  python docs/agents/jaseer-v2-evidence/estimate.py --comparison-evidence --output-dir outputs/v2-evidence
Add --mlflow to publish a real run; --tracking-uri, --experiment and --run-name are optional.
The comparison writes unrounded windows.csv, horizons.csv and reproducibility.json. Prediction errors
are raw estimator diagnostics, not an organizer score; the historical invocation is unchanged.
Comparison mode reports raw metrics only and verifies the local CSV release against config release IDs;
it does not read Delta or verify the configs' declared Delta table versions.
"""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog

import halcyon.policy as P
from halcyon.data import Dataset
from halcyon.forecasting.baseline import HistoricalForecaster
from halcyon.simulator import SimulatorConfig, simulate_window

DATA = Dataset.from_csv_dir("data")
SET_A = list(range(52, 170, 13))
SET_B = list(range(58, 163, 13))
OUT = Path(__file__).with_name("windows.csv")


def hindsight_cost(start, end):
    supply, demand = DATA["supply_history"], DATA["demand"].set_index(["week", "material"]).demand_units
    total = 0.0
    for material, rows in supply[supply.week.between(start, end)].groupby("material"):
        ref = rows.landed_cost.mean()
        weeks = list(range(start, end + 1)); T = len(weeks)
        countries = sorted(rows.country.unique()); C = len(countries)
        rows = rows.set_index(["week", "country"])
        d = np.array([demand[(w, material)] for w in weeks], float)
        nx = T * C; n = nx + 2 * T  # orders x[t,c], served s[t], ending stock I[t]
        cost = np.zeros(n); upper = np.full(n, np.inf); A = np.zeros((T, n)); b = np.zeros(T)
        for t, week in enumerate(weeks):
            for c, country in enumerate(countries):
                cap, lead, landed = rows.loc[(week, country), ["capacity_units", "lead_time_weeks", "landed_cost"]]
                k = t * C + c; cost[k] = landed; upper[k] = cap
                if t + int(lead) < T:
                    A[t + int(lead), k] -= 1.0
                else:
                    cost[k] -= 0.7 * ref  # arrives after the window: salvaged in transit
            cost[nx + t] = -5.0 * ref; upper[nx + t] = d[t]
            cost[nx + T + t] = 0.02 * ref
            A[t, nx + t] += 1.0; A[t, nx + T + t] += 1.0  # I_t = I_{t-1} + arrivals_t - s_t
            if t:
                A[t, nx + T + t - 1] -= 1.0
        b[0] = 5.0 * d[0]
        cost[nx + 2 * T - 1] -= 0.7 * ref
        result = linprog(cost, A_eq=A, b_eq=b, bounds=list(zip(np.zeros(n), upper)), method="highs")
        assert result.success, result.message
        total += result.fun + 5.0 * ref * d.sum()
    return total


def simulate(decisions, start, end):
    weekly = simulate_window(decisions, DATA["demand"], DATA["supply_history"], DATA["suppliers"],
                             DATA["outcomes"], start, end).weekly
    shock = weekly[weekly.shock_recovery]
    fill = shock.fulfilled_units.sum() / shock.demand_units.sum() if len(shock) else np.nan
    return weekly.total_cost.sum(), fill, weekly.diversification.mean()


def optimized(**config):
    return lambda: P.OptimizedPolicy(config=config)


CANDIDATES = {
    "current": optimized(),
    "tilt_k3": optimized(cost_tilt=3.0),
    "tilt_k3_risk_buffer_4": optimized(cost_tilt=3.0, risk_buffer_weeks=4.0),
    "tilt_k5": optimized(cost_tilt=5.0),
    "div_penalty_0.10": optimized(diversification_penalty=0.10),
    "div_penalty_0.05": optimized(diversification_penalty=0.05),
    "base_buffer_3": optimized(base_buffer_weeks=3.0),
    "risk_buffer_4": optimized(risk_buffer_weeks=4.0),
}


def main():
    rows = []
    for origin in SET_A + SET_B:
        weeks = list(range(origin + 1, origin + 14)); start, end = weeks[0], weeks[-1]
        forecasts = HistoricalForecaster().predict(DATA, origin, weeks)
        naive = simulate(P.NaivePolicy().decide(DATA, forecasts, origin, weeks), start, end)
        hindsight = hindsight_cost(start, end)
        for name, make in CANDIDATES.items():
            cost, fill, diversification = simulate(make().decide(DATA, forecasts, origin, weeks), start, end)
            F = float(np.clip((naive[0] - cost) / (naive[0] - hindsight), 0, 1))
            tie = np.isnan(naive[1]) or naive[1] >= 1 - 1e-12
            fill_skill = 0.0 if tie else float(np.clip((fill - naive[1]) / (1 - naive[1]), 0, 1))
            score = 100 * (0.4 * F + 0.3 * (0.7 * fill_skill + 0.3 * diversification))
            rows.append(dict(candidate=name, set="A" if origin in SET_A else "B", origin=origin,
                             window=f"{start}-{end}", score=score, F=F, fill_skill=fill_skill,
                             shock_fill=fill, diversification=diversification, total_cost=cost,
                             naive_cost=naive[0], naive_shock_fill=naive[1], hindsight_cost=hindsight))
    frame = pd.DataFrame(rows)
    frame.round(6).to_csv(OUT, index=False)
    current = frame[frame.candidate == "current"].set_index("origin").score
    summary = []
    for name, group in frame.groupby("candidate", sort=False):
        delta = group.set_index("origin").score - current
        shock = current > 50  # windows where naive misses shock demand and current scores high
        summary.append(dict(candidate=name, set_A=group[group.set == "A"].score.mean(),
                            set_B=group[group.set == "B"].score.mean(), delta_mean=delta.mean(),
                            delta_worst=delta.min(), wins=int((delta > 0.01).sum()),
                            delta_shock=delta[shock].mean(), delta_calm=delta[~shock].mean(),
                            hedged_gain=np.maximum(delta, 0).mean(),
                            diversification=group.diversification.mean()))
    print(pd.DataFrame(summary).round(2).to_string(index=False))


COMPARISON_CONFIGS = {
    "incumbent": "configs/phase1_selected_delta.json",
    "U1": "configs/phase1_v2_news_delta.json",
    "U2": "configs/phase1_v2_tilt_delta.json",
}
STATUS = "Estimator output only; NOT organizer parity; NOT an official competition score."


def comparison_errors(forecasts, weeks):
    """Match by week/material, never by incidental dataframe row ordering."""
    from halcyon.contracts import validate_forecasts

    validate_forecasts(forecasts, weeks)
    truth = DATA["outcomes"].loc[
        lambda frame: frame.week.isin(weeks),
        ["week", "material", "disrupted", "benchmark_price"],
    ].rename(columns={"week": "target_week"})
    aligned = truth.merge(forecasts, on=["target_week", "material"], how="outer",
                          validate="one_to_one", indicator=True)
    if not aligned["_merge"].eq("both").all():
        raise ValueError("Forecast and truth week/material keys differ")
    for column in ["disrupted", "benchmark_price", "disruption_prob", "price_forecast"]:
        aligned[column] = pd.to_numeric(aligned[column], errors="coerce").astype(float)
    invalid_labels = ~np.isfinite(aligned.disrupted) | ~aligned.disrupted.isin([0, 1])
    invalid_prices = ~np.isfinite(aligned.benchmark_price) | (aligned.benchmark_price <= 0)
    for label, invalid in [("disrupted", invalid_labels), ("benchmark_price", invalid_prices)]:
        if invalid.any():
            key = tuple(aligned.loc[invalid, ["target_week", "material"]].iloc[0])
            raise ValueError(f"Truth {label} invalid at {key}")
    aligned["brier"] = (aligned.disruption_prob - aligned.disrupted) ** 2
    aligned["price_mape_fraction"] = (
        (aligned.price_forecast - aligned.benchmark_price).abs() / aligned.benchmark_price
    )
    if not np.isfinite(aligned[["brier", "price_mape_fraction"]].to_numpy()).all():
        raise ValueError("Prediction error calculation produced nonfinite values")
    return aligned


def comparison_manifest(configs, args):
    root = Path(__file__).resolve().parents[3]
    bootstrap_path = root / "tools/databricks/bootstrap.py"
    spec = importlib.util.spec_from_file_location("halcyon_evidence_bootstrap", bootstrap_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load release manifest builder: {bootstrap_path}")
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    release = bootstrap.build_manifest(Path("data").resolve())
    for name, config in configs.items():
        configured_release = config["source"].get("release_id")
        if configured_release != release["release_id"]:
            raise ValueError(
                f"{name} config release_id {configured_release!r} differs from "
                f"verified local CSV release {release['release_id']!r}"
            )
    for name, digest in DATA.source_sha256.items():
        if release["files"][name]["sha256"] != digest:
            raise ValueError(f"Local CSV {name} changed after DATA was loaded")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                         capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True,
                           capture_output=True, text=True).stdout.strip()
    return {
        "status": STATUS, "git_sha": sha, "dirty": bool(dirty),
        "script": str(Path(__file__).resolve().relative_to(root)),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "invocation": sys.argv, "source_kind": "local CSV (not a Delta read)",
        "source_directory": str(Path("data").resolve()),
        "source_csv_sha256": {f"{name}.csv": digest for name, digest in DATA.source_sha256.items()},
        "verified_local_release_manifest": release,
        "release_manifest_builder": str(bootstrap_path.relative_to(root)),
        "release_manifest_builder_sha256": hashlib.sha256(bootstrap_path.read_bytes()).hexdigest(),
        "source_release_identity_from_configs": {
            name: config["source"] for name, config in configs.items()
        },
        "release_identity_note": (
            "Config release IDs match the manifest derived from the complete local CSV release, "
            "including sample_submission.csv. Delta was not consumed; declared Delta versions "
            "are not verified by this local evaluation."
        ),
        "source_config_sha256": {
            path: hashlib.sha256((root / path).read_bytes()).hexdigest()
            for path in COMPARISON_CONFIGS.values()
        },
        "candidates": {
            name: {"source_config": COMPARISON_CONFIGS[name],
                   "forecaster": {**config["forecaster"],
                                  "kwargs": config["forecaster"].get("kwargs", {})},
                   "policy": {**config["policy"], "kwargs": config["policy"].get("kwargs", {})}}
            for name, config in configs.items()
        },
        "origins": {"A": SET_A, "B": SET_B}, "horizons": list(range(1, 14)),
        "holdout_origin_182_used": False, "observed_through": DATA.observed_through,
        "visibility": "Forecaster and policy both receive DATA.as_of(origin); evaluator alone receives full truth.",
        "simulator_assumptions": asdict(SimulatorConfig()),
        "metrics_semantics": {
            "brier": "Mean (disruption_prob - realized disrupted)^2 over keyed material/week rows.",
            "price_mape_fraction": "Mean abs(price_forecast - benchmark_price)/benchmark_price; fraction, not percent.",
            "total_cost": "Sum of simulator weekly total_cost; raw cost, lower is better.",
            "naive_cost": "Same simulator with NaivePolicy and the incumbent forecasts.",
            "hindsight_cost": "Existing per-material realized capacity/lead/landed-cost LP for this window.",
            "shock_fill": "Sum fulfilled / sum demand in simulator shock+4 recovery rows; NaN if no rows.",
            "diversification": "Unweighted mean of simulator weekly/material diversification rows.",
            "aggregation": "Per-window errors weight material/week rows equally; per-horizon errors weight materials equally. Aggregates are unweighted means of window or horizon rows, separately overall/A/B.",
            "undefined": "Undefined values remain NaN in CSV and are omitted from MLflow metrics.",
        },
        "mlflow_requested": args.mlflow,
        "mlflow_settings": {"tracking_uri": args.tracking_uri, "experiment": args.experiment,
                            "run_name": args.run_name},
    }


def log_comparison(args, frame, horizons, manifest):
    import mlflow

    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)
    mlflow.set_experiment(args.experiment)
    metric_names = ["total_cost", "naive_cost", "hindsight_cost", "shock_fill",
                    "naive_shock_fill", "diversification", "naive_diversification",
                    "brier", "price_mape_fraction"]
    root = Path(__file__).resolve().parents[3]
    with mlflow.start_run(run_name=args.run_name) as run:
        mlflow.set_tags({"evidence_status": STATUS, "holdout_used": "false"})
        mlflow.log_params({
            "git_sha": manifest["git_sha"], "dirty": manifest["dirty"],
            "script_sha256": manifest["script_sha256"],
            "source_release_ids": ",".join(sorted({
                config["release_id"] for config in manifest["source_release_identity_from_configs"].values()
            })),
            "origins_A": json.dumps(SET_A), "origins_B": json.dumps(SET_B), "horizons": "1-13",
        })
        for row in frame.to_dict("records"):
            prefix = f"window/{row['candidate']}/set_{row['set']}/origin_{row['origin']}"
            mlflow.log_metrics({f"{prefix}/{key}": float(row[key])
                                for key in metric_names if np.isfinite(row[key])})
        for row in horizons.to_dict("records"):
            prefix = f"horizon/{row['candidate']}/set_{row['set']}/origin_{row['origin']}/h{row['horizon']}"
            mlflow.log_metrics({f"{prefix}/{key}": float(row[key])
                                for key in ["brier", "price_mape_fraction"] if np.isfinite(row[key])})
        for label, selected, selected_h in [
            ("overall", frame, horizons),
            ("set_A", frame[frame["set"] == "A"], horizons[horizons["set"] == "A"]),
            ("set_B", frame[frame["set"] == "B"], horizons[horizons["set"] == "B"]),
        ]:
            for candidate, group in selected.groupby("candidate"):
                means = group[metric_names].mean()
                mlflow.log_metrics({f"aggregate/{candidate}/{label}/mean_{key}": float(value)
                                    for key, value in means.items() if np.isfinite(value)})
            for (candidate, horizon), group in selected_h.groupby(["candidate", "horizon"]):
                means = group[["brier", "price_mape_fraction"]].mean()
                mlflow.log_metrics({f"aggregate/{candidate}/{label}/h{horizon}/mean_{key}": float(value)
                                    for key, value in means.items() if np.isfinite(value)})
        manifest["mlflow_run"] = {"run_id": run.info.run_id,
                                 "experiment_id": run.info.experiment_id,
                                 "tracking_uri": mlflow.get_tracking_uri()}
        (args.output_dir / "reproducibility.json").write_text(
            json.dumps(manifest, indent=2, allow_nan=False) + "\n")
        for name in ["windows.csv", "horizons.csv", "reproducibility.json"]:
            mlflow.log_artifact(str(args.output_dir / name))
        mlflow.log_artifact(str(Path(__file__).resolve()), artifact_path="script")
        for path in COMPARISON_CONFIGS.values():
            mlflow.log_artifact(str(root / path), artifact_path="source_configs")
        print(f"MLflow estimator evidence run: {run.info.run_id}")


def comparison_evidence(args):
    from halcyon.news.forecaster import DisruptionModel, HistoricalRiskPolicy

    root = Path(__file__).resolve().parents[3]
    configs = {name: json.loads((root / path).read_text())
               for name, path in COMPARISON_CONFIGS.items()}
    # Fixed candidate shapes from the shipping configs: this path never enters CANDIDATES.
    classes = {"halcyon.forecasting.baseline:HistoricalForecaster": HistoricalForecaster,
               "halcyon.news.forecaster:DisruptionModel": DisruptionModel,
               "halcyon.policy:OptimizedPolicy": P.OptimizedPolicy,
               "halcyon.news.forecaster:HistoricalRiskPolicy": HistoricalRiskPolicy}
    manifest = comparison_manifest(configs, args)
    rows, horizon_rows = [], []
    for origin in SET_A + SET_B:
        weeks = list(range(origin + 1, origin + 14))
        visible = DATA.as_of(origin)
        start, end = weeks[0], weeks[-1]
        incumbent_forecasts = HistoricalForecaster().predict(visible, origin, weeks)
        naive = simulate(P.NaivePolicy().decide(visible, incumbent_forecasts, origin, weeks), start, end)
        hindsight = hindsight_cost(start, end)
        for name, config in configs.items():
            model_spec, policy_spec = config["forecaster"], config["policy"]
            model = classes[model_spec["class"]](**model_spec.get("kwargs", {}))
            policy = classes[policy_spec["class"]](**policy_spec.get("kwargs", {}))
            forecasts = model.predict(visible, origin, weeks)
            errors = comparison_errors(forecasts, weeks)
            cost, fill, diversification = simulate(
                policy.decide(visible, forecasts.copy(), origin, weeks), start, end)
            identity = {"candidate": name, "set": "A" if origin in SET_A else "B", "origin": origin}
            rows.append({
                **identity, "window": f"{start}-{end}", "horizon_start": 1, "horizon_end": 13,
                "total_cost": cost, "naive_cost": naive[0], "hindsight_cost": hindsight,
                "shock_fill": fill, "naive_shock_fill": naive[1],
                "diversification": diversification, "naive_diversification": naive[2],
                "brier": float(errors.brier.mean()),
                "price_mape_fraction": float(errors.price_mape_fraction.mean()),
            })
            for week, group in errors.groupby("target_week"):
                horizon_rows.append({**identity, "horizon": int(week - origin), "target_week": int(week),
                                     "brier": float(group.brier.mean()),
                                     "price_mape_fraction": float(group.price_mape_fraction.mean())})
    frame, horizons = pd.DataFrame(rows), pd.DataFrame(horizon_rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output_dir / "windows.csv", index=False, float_format="%.17g")
    horizons.to_csv(args.output_dir / "horizons.csv", index=False, float_format="%.17g")
    (args.output_dir / "reproducibility.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    if args.mlflow:
        log_comparison(args, frame, horizons, manifest)
    print(f"{STATUS}\nEvidence files: {args.output_dir}")


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-evidence", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=OUT.parent / "comparison")
    parser.add_argument("--mlflow", action="store_true", help="Log one real MLflow run; failures propagate.")
    parser.add_argument("--tracking-uri", help="MLflow tracking URI; implies --mlflow.")
    parser.add_argument("--experiment", default="/Shared/halcyon/runs")
    parser.add_argument("--run-name", default="jaseer-v2-estimator-comparison")
    args = parser.parse_args()
    args.mlflow = args.mlflow or args.tracking_uri is not None
    if not args.comparison_evidence and (
        args.mlflow or args.output_dir != OUT.parent / "comparison"
        or args.experiment != "/Shared/halcyon/runs" or args.run_name != "jaseer-v2-estimator-comparison"
    ):
        parser.error("Evidence output/MLflow flags require --comparison-evidence")
    if args.comparison_evidence:
        comparison_evidence(args)
    else:
        main()


if __name__ == "__main__":
    cli()
