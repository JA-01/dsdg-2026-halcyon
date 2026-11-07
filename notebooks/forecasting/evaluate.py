"""Run with python notebooks/forecasting/evaluate.py --output outputs/forecast-dev.

Only development origins130/156: never opens the locked182 holdout.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from halcyon.data import Dataset
from halcyon.forecasting.baseline import HistoricalForecaster
from halcyon.forecasting.models import PooledForecaster


def metric_rows(frame, origin, model):
    frame = frame.assign(horizon=frame.target_week - origin,
                         horizon_block=np.where(frame.target_week - origin <= 13, "h01_13", "h14_26"))
    rows = []
    def add(group, level, key):
        rows.append({"origin": origin, "model": model, "level": level, "key": str(key),
                     "rows": len(group), "brier": float(((group.disruption_prob-group.disrupted)**2).mean()),
                     "mape": float(((group.price_forecast-group.benchmark_price).abs()/group.benchmark_price).mean())})
    add(frame, "overall", "__all__")
    for column in ["horizon_block", "horizon", "material"]:
        for key, group in frame.groupby(column):
            add(group, column, key)
    for (block, material), group in frame.groupby(["horizon_block", "material"]):
        add(group, "block_material", f"{block}/{material}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data")
    parser.add_argument("--output", default="outputs/forecast-dev")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    data = Dataset.from_csv_dir(args.data)
    rows, predictions, calibration = [], [], []
    for origin in [130, 156]:
        weeks = list(range(origin+1, origin+27))
        for name, model in [("historical", HistoricalForecaster()), ("pooled", PooledForecaster()),
                            ("historical_risk_pooled_price", PooledForecaster(disruption_mode="historical"))]:
            forecasts = model.predict(data.as_of(origin), origin, weeks)
            directory = output / f"origin{origin}" / name
            model.save_artifacts(directory)
            if name != "historical":
                from halcyon.forecasting.features import build_features
                build_features(data.as_of(origin), origin, weeks).to_csv(directory/"prediction_features.csv", index=False)
            truth = forecasts.merge(data["outcomes"], left_on=["target_week", "material"],
                                    right_on=["week", "material"], validate="one_to_one")
            rows.extend(metric_rows(truth, origin, name))
            predictions.append(truth.assign(origin=origin, model=name))
            bins = pd.cut(truth.disruption_prob, [-0.001, .1, .25, .5, .75, 1.0])
            for interval, group in truth.groupby(bins, observed=True):
                calibration.append({"origin": origin, "model": name, "bin": str(interval), "rows": len(group),
                                    "mean_probability": float(group.disruption_prob.mean()),
                                    "observed_frequency": float(group.disrupted.mean())})
    metrics = pd.DataFrame(rows)
    metrics.to_csv(output/"metrics.csv", index=False)
    pd.concat(predictions, ignore_index=True).to_csv(output/"predictions.csv", index=False)
    pd.DataFrame(calibration).to_csv(output/"calibration.csv", index=False)
    source_paths = sorted(Path("halcyon/forecasting").glob("*.py")) + [Path(__file__)]
    metadata = {"origins": [130, 156], "holdout182": "locked_not_evaluated", "source_sha256": data.source_sha256,
                "code_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
                "git_sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip(),
                "packages": {p: importlib.metadata.version(p) for p in ["pandas", "numpy", "scikit-learn"]},
                "metric_status": "raw_forecast_errors_not_official_score"}
    (output/"manifest.json").write_text(json.dumps(metadata, indent=2)+"\n")
    print(metrics[metrics.level == "horizon_block"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
