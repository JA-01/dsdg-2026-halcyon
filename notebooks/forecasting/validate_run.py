"""Read-only acceptance of trusted forecast artifacts; never refits a model.

python notebooks/forecasting/validate_run.py --run-dir <downloaded-run> --data-dir data \
  --features <silver_features.csv> --job-report <jobs-get-run.json> --output <report.json>

Only load model.pkl from a trusted team run: pickle is executable Python.
Missing remote evidence is reported as unchecked, not as acceptance success.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from halcyon.contracts import ContractError
from halcyon.data import Dataset
from halcyon.delta import check_feature_parity
from halcyon.forecasting.features import FEATURE_COLUMNS, FEATURE_VERSION, build_features
from halcyon.pipeline import submission_ids
from halcyon.submission import build_submission, validate_bytes
from halcyon.contracts import eligibility


def require(condition, message):
    if not condition:
        raise ContractError(message)


def validate_run(run_dir, data_dir, *, model_dir=None, features_path=None, job_report_path=None):
    run_dir = Path(run_dir)
    model_dir = Path(model_dir) if model_dir else run_dir / "forecaster"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    data = Dataset.from_csv_dir(data_dir)
    require(manifest["source_sha256"] == data.source_sha256, "source CSV hashes differ from run")
    raw = (run_dir / "submission.csv").read_bytes()
    require(hashlib.sha256(raw).hexdigest() == manifest["export"]["sha256"], "submission checksum differs")
    require(not validate_bytes(raw, submission_ids(), eligibility(data["suppliers"])), "submission bytes invalid")
    forecasts = pd.read_csv(run_dir / "forecasts.csv")
    decisions = pd.read_csv(run_dir / "decisions.csv")
    rebuilt = build_submission(forecasts, decisions, submission_ids())
    submitted = pd.read_csv(run_dir / "submission.csv")
    require(rebuilt.id.tolist() == submitted.id.tolist(), "submission IDs differ from forecasts/decisions")
    np.testing.assert_allclose(rebuilt.iloc[:, 1:].to_numpy(float), submitted.iloc[:, 1:].to_numpy(float),
                               rtol=1e-12, atol=1e-12)
    active = forecasts[forecasts.window_id.isin([w["window_id"] for w in manifest["windows"]])]
    cutoff = int(manifest["cutoff"])
    require(active.cutoff_week.eq(cutoff).all(), "active forecasts have wrong cutoff")
    features = build_features(data, cutoff, sorted(active.target_week.unique().tolist()))
    if (model_dir / "model.pkl").exists():
        with (model_dir / "model.pkl").open("rb") as stream:
            model = pickle.load(stream)
        metadata = json.loads((model_dir / "metadata.json").read_text())
        require(model.metadata_ == metadata, "serialized model metadata differs")
        require(metadata["cutoff_week"] == cutoff, "model cutoff differs")
        require(metadata["fallback"] is None, "candidate used fallback; validate fallback explicitly instead")
        require(model.model_id in manifest["model_ids"], "model ID differs from manifest")
        training = pd.read_csv(model_dir / "training_features.csv")
        require(len(training) == metadata["training_rows"], "training artifact row count differs")
        require((training.cutoff_week < training.target_week).all() and (training.target_week <= cutoff).all(),
                "training origin/target boundary violated")
        require(training.feature_version.eq(FEATURE_VERSION).all(), "training feature version differs")
        encoded = model.preprocessor_.transform(model._model_frame(features))
        price = np.exp(np.clip(np.log(features.latest_benchmark_price.to_numpy())
                              + model.price_model_.predict(encoded), -700, 700))
        if model.disruption_mode == "historical":
            risk = features.material.map(data.as_of(cutoff)["outcomes"].groupby("material").disrupted.mean()).to_numpy()
        else:
            class_index = list(model.disruption_model_.classes_).index(1)
            risk = model.disruption_model_.predict_proba(encoded)[:, class_index]
        expected = features[["target_week", "material"]].assign(expected_price=price, expected_risk=risk)
        training_rows = len(training)
    else:
        metadata = json.loads((model_dir / "model_metadata.json").read_text())
        require(metadata["cutoff_week"] == cutoff, "baseline cutoff differs")
        require(metadata["model_id"] in manifest["model_ids"], "baseline model ID differs")
        history = data.as_of(cutoff)["outcomes"].sort_values("week").groupby("material")
        rates, prices = history.disrupted.mean(), history.benchmark_price.last()
        require(metadata["rates"] == rates.to_dict() and metadata["last_prices"] == prices.to_dict(),
                "baseline saved rates/prices differ from released history")
        expected = features[["target_week", "material"]].assign(
            expected_price=features.material.map(prices), expected_risk=features.material.map(rates))
        training_rows = None
    joined = active.merge(expected, on=["target_week", "material"], validate="one_to_one")
    require(len(joined) == len(active) == len(expected), "saved model forecast key coverage differs")
    np.testing.assert_allclose(joined.price_forecast, joined.expected_price, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(joined.disruption_prob, joined.expected_risk, rtol=1e-12, atol=1e-12)
    report = {"run_id": manifest["run_id"], "model_inference_rows": len(joined), "refit": False,
              "training_rows": training_rows, "source_hashes_match": True, "saved_predictions_match": True,
              "submission_sha256": manifest["export"]["sha256"], "spark_features": "not_checked",
              "job_duration": "not_checked", "remote_acceptance_complete": False}
    if features_path:
        persisted = pd.read_csv(features_path)
        required = {"run_id", "release_id", "window_id", *FEATURE_COLUMNS}
        require(required <= set(persisted), "persisted features missing identity or feature columns")
        require(persisted.run_id.eq(manifest["run_id"]).all(), "features include another run")
        require(persisted.release_id.eq(manifest["release_id"]).all(), "feature release differs")
        require(persisted.feature_version.eq(FEATURE_VERSION).all(), "persisted feature version differs")
        require(set(persisted.window_id) == {w["window_id"] for w in manifest["windows"]}, "feature windows differ")
        for window in manifest["windows"]:
            block = persisted[persisted.window_id == window["window_id"]]
            require(not block.duplicated(["target_week", "material"]).any(), "duplicate persisted feature keys")
            check_feature_parity(block, build_features(data, window["cutoff"], window["target_weeks"]))
        report["spark_features"] = {"rows": len(persisted), "parity": True}
    if job_report_path:
        job = json.loads(Path(job_report_path).read_text())
        require(job["state"].get("result_state") == "SUCCESS", "job did not finish successfully")
        duration = (job["end_time"] - job["start_time"]) / 1000
        require(0 <= duration < 1800, "job duration exceeds 30-minute limit or timestamps invalid")
        report["job_duration"] = {"run_id": job["run_id"], "seconds": duration, "below_1800_seconds": True}
    report["remote_acceptance_complete"] = bool(features_path and job_report_path)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--model-dir")
    parser.add_argument("--features")
    parser.add_argument("--job-report")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = validate_run(args.run_dir, args.data_dir, model_dir=args.model_dir,
                          features_path=args.features, job_report_path=args.job_report)
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
