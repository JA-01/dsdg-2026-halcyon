import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from halcyon.baselines import ProvisionalForecaster, ProvisionalPolicy
from halcyon.constants import PRIVATE_WEEKS, PUBLIC_WEEKS, SHARE_COLUMNS
from halcyon.contracts import ContractError, Window, phase1_windows
from halcyon.data import Dataset
from halcyon.pipeline import (
    ArchivedPublic, RunConfig, load_source, plan_windows, run_from_config, run_pipeline, submission_ids,
)
from halcyon.submission import SubmissionError, load_reference, validate_bytes

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


@pytest.fixture(scope="module")
def data():
    return Dataset.from_csv_dir(DATA)


class Recording:
    """Wraps real baselines and records exactly what each module was given."""

    def __init__(self):
        self.forecaster_calls, self.policy_calls = [], []
        self._forecaster, self._policy = ProvisionalForecaster(), ProvisionalPolicy()

    def predict(self, data, cutoff, target_weeks):
        self.forecaster_calls.append((data.cutoff, cutoff, list(target_weeks)))
        return self._forecaster.predict(data, cutoff, target_weeks)

    def decide(self, data, forecasts, cutoff, target_weeks):
        self.policy_calls.append((data.cutoff, cutoff, list(target_weeks), set(forecasts["target_week"])))
        return self._policy.decide(data, forecasts, cutoff, target_weeks)


def test_ids_match_organizer_sample_order():
    assert submission_ids() == pd.read_csv(DATA / "sample_submission.csv")["id"].tolist()


def test_policy_is_called_separately_per_window_with_only_its_forecasts(data):
    module = Recording()
    plan_windows(data, phase1_windows(), module, module)
    assert module.forecaster_calls == [(208, 208, list(PUBLIC_WEEKS + PRIVATE_WEEKS))]
    assert [call[2] for call in module.policy_calls] == [list(PUBLIC_WEEKS), list(PRIVATE_WEEKS)]
    assert module.policy_calls[0][3] == set(PUBLIC_WEEKS) and module.policy_calls[1][3] == set(PRIVATE_WEEKS)
    assert all(call[0] == 208 for call in module.policy_calls)


def test_forecasts_do_not_change_when_future_rows_change(data):
    """Mutating anything after the cutoff must not move a module's output."""
    tables = {name: data[name] for name in data}
    for name in ("outcomes", "prices", "supply_history"):
        numeric = tables[name].select_dtypes("number").columns.drop("week")
        tables[name].loc[tables[name]["week"] > 150, numeric] = 999.0
    mutated = Dataset(tables)
    weeks = list(range(151, 164))
    pd.testing.assert_frame_equal(
        ProvisionalForecaster().predict(data.as_of(150), 150, weeks),
        ProvisionalForecaster().predict(mutated.as_of(150), 150, weeks))


def test_phase1_end_to_end_exports_valid_bytes(data, tmp_path):
    result = run_pipeline(208, ProvisionalForecaster(), ProvisionalPolicy(), data=data, output_dir=tmp_path)
    raw = result.export.path.read_bytes()
    ids, allowed = load_reference(DATA)
    assert validate_bytes(raw, ids, allowed) == []
    assert result.export.sha256 == hashlib.sha256(raw).hexdigest()
    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    assert manifest["export"]["sha256"] == result.export.sha256
    assert manifest["model_ids"] == ["provisional_origin_naive"]
    assert manifest["score_status"] == "not_evaluated" and len(manifest["source_sha256"]) == 9
    assert set(result.forecasts["window_id"]) == {"public", "private"}
    assert not result.decisions.duplicated(["run_id", "window_id", "target_week", "material"]).any()


def _phase1(data, tmp_path):
    return run_pipeline(208, ProvisionalForecaster(), ProvisionalPolicy(), data=data, output_dir=tmp_path / "one")


class ShiftedForecaster(ProvisionalForecaster):
    def predict(self, data, cutoff, target_weeks):
        return super().predict(data, cutoff, target_weeks).assign(disruption_prob=0.5, model_id="phase2")


def test_phase2_retains_public_rows_and_replaces_private(data, tmp_path):
    first = _phase1(data, tmp_path)
    archived = ArchivedPublic(str(first.export.path), first.export.sha256, first.run_id)
    second = run_pipeline(
        208, ShiftedForecaster(), ProvisionalPolicy(), data=data, windows=(Window("private", 208, PRIVATE_WEEKS),),
        archived_public=archived, output_dir=tmp_path / "two")
    old, new = pd.read_csv(first.export.path), pd.read_csv(second.export.path)
    assert len(new) == 260
    public = old["id"].str.extract(r"w(\d+)_")[0].astype(int).isin(PUBLIC_WEEKS)
    pd.testing.assert_frame_equal(old[public], new[public])
    assert (new.loc[~public, "disruption_prob"] == 0.5).all()
    origin = second.decisions[second.decisions["window_id"] == "public"]["origin_run_id"]
    assert (origin == first.run_id).all()


def test_phase2_refuses_tampered_archive(data, tmp_path):
    first = _phase1(data, tmp_path)
    archived = ArchivedPublic(str(first.export.path), "0" * 64, first.run_id)
    with pytest.raises(SubmissionError, match="checksum"):
        run_pipeline(208, ProvisionalForecaster(), ProvisionalPolicy(), data=data,
                     windows=(Window("private", 208, PRIVATE_WEEKS),), archived_public=archived, output_dir=tmp_path)


class InvalidPolicy(ProvisionalPolicy):
    def decide(self, data, forecasts, cutoff, target_weeks):
        frame = super().decide(data, forecasts, cutoff, target_weeks)
        frame.loc[0, list(SHARE_COLUMNS)] = 0.0
        return frame


def test_invalid_policy_is_rejected_not_repaired(data, tmp_path):
    with pytest.raises(ContractError, match="sum to 1"):
        run_pipeline(208, ProvisionalForecaster(), InvalidPolicy(), data=data, output_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def _config(tmp_path, **extra):
    return {"mode": "phase1", "source": {"kind": "csv", "path": str(DATA)},
            "forecaster": {"class": "halcyon.baselines:ProvisionalForecaster"},
            "policy": {"class": "halcyon.baselines:ProvisionalPolicy"},
            "output_dir": str(tmp_path), **extra}


def test_config_run_and_publish(tmp_path):
    result = run_from_config(RunConfig.parse(_config(tmp_path / "out", publish_dir=str(tmp_path / "volume"))))
    assert (tmp_path / "volume" / result.run_id / "submission.csv").read_bytes() == result.export.path.read_bytes()
    assert result.manifest["fallback_reason"] is None and result.manifest["mode"] == "phase1"


def test_fallback_is_explicit_and_recorded(tmp_path):
    bad = {"policy": {"class": "tests_missing_module:Nope"}}
    good = {"forecaster": {"class": "halcyon.baselines:ProvisionalForecaster"},
            "policy": {"class": "halcyon.baselines:ProvisionalPolicy"}}
    result = run_from_config(RunConfig.parse(_config(tmp_path, **bad, fallback=good)))
    assert "tests_missing_module" in result.manifest["fallback_reason"]
    assert result.export.rows == 260
    with pytest.raises(ModuleNotFoundError):
        run_from_config(RunConfig.parse(_config(tmp_path, **bad)))


@pytest.mark.parametrize("change,match", [
    ({"surprise": 1}, "unknown keys"),
    ({"mode": "phase3"}, "mode"),
    ({"mode": "phase2"}, "archived_public"),
    ({"archived_public": {"csv_path": "x", "sha256": "y", "origin_run_id": "z"}}, "phase2 only"),
    ({"source": {"kind": "s3"}}, "source.kind"),
    ({"source": {"kind": "delta", "catalog": "c"}}, "delta source needs"),
])
def test_config_validation(tmp_path, change, match):
    with pytest.raises(ContractError, match=match):
        RunConfig.parse(_config(tmp_path, **change))


def test_config_refuses_a_release_that_does_not_match_the_mode(tmp_path):
    config = RunConfig.parse(_config(tmp_path, mode="phase2", archived_public={
        "csv_path": "x", "sha256": "y", "origin_run_id": "z"}))
    with pytest.raises(ContractError, match="through week 221"):
        run_from_config(config)


def test_delta_source_needs_spark():
    with pytest.raises(ContractError, match="Spark"):
        load_source({"kind": "delta", "catalog": "c", "schema": "s", "release_id": "r", "versions": {}})


@pytest.mark.parametrize("name", ["phase1_baseline_local.json", "phase1_baseline_delta.json"])
def test_committed_configs_parse(name):
    assert RunConfig.load(ROOT / "configs" / name).mode == "phase1"
