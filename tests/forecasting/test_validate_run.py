import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from halcyon.contracts import ContractError
from halcyon.data import Dataset
from halcyon.forecasting.models import PooledForecaster
from halcyon.pipeline import run_pipeline
from halcyon.policy import InventoryPolicy
from halcyon.submission import build_submission
from halcyon.pipeline import submission_ids
from notebooks.forecasting.validate_run import validate_run

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def saved_run(tmp_path_factory):
    data = Dataset.from_csv_dir(DATA)
    model = PooledForecaster(disruption_mode="historical", origin_stride=26, n_estimators=8)
    result = run_pipeline(208, model, InventoryPolicy(), data=data,
                          output_dir=tmp_path_factory.mktemp("frozen-run"),
                          lineage={"release_id": "test-release"})
    return result.run_dir


def test_serialized_model_detects_consistently_rewritten_forecasts(saved_run, tmp_path):
    directory = tmp_path / "changed"
    shutil.copytree(saved_run, directory)
    forecasts = pd.read_csv(directory / "forecasts.csv")
    forecasts.loc[0, "price_forecast"] *= 2
    forecasts.to_csv(directory / "forecasts.csv", index=False)
    decisions = pd.read_csv(directory / "decisions.csv")
    submission = build_submission(forecasts, decisions, submission_ids())
    submission.to_csv(directory / "submission.csv", index=False)
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["export"]["sha256"] = hashlib.sha256((directory / "submission.csv").read_bytes()).hexdigest()
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(AssertionError):
        validate_run(directory, DATA)


def test_persisted_features_cannot_skip_required_columns(saved_run, tmp_path):
    path = tmp_path / "features.csv"
    pd.DataFrame({"run_id": [saved_run.name], "target_week": [209], "material": ["lithium"]}).to_csv(path, index=False)
    with pytest.raises(ContractError, match="missing identity or feature"):
        validate_run(saved_run, DATA, features_path=path)


@pytest.mark.parametrize("state,start,end", [("FAILED", 1000, 2000), ("SUCCESS", 1000, 1801000),
                                            ("SUCCESS", 2000, 1000)])
def test_failed_or_overlong_job_cannot_close_acceptance(saved_run, tmp_path, state, start, end):
    path = tmp_path / "job.json"
    path.write_text(json.dumps({"run_id": 123, "state": {"result_state": state},
                                "start_time": start, "end_time": end}))
    with pytest.raises(ContractError, match="job did not finish|job duration"):
        validate_run(saved_run, DATA, job_report_path=path)
