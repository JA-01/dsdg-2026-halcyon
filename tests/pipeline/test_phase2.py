import pytest

from halcyon.data import SCHEMAS
from halcyon.phase2 import build_config
from halcyon.pipeline import RunConfig

TEMPLATE = {
    "mode": "phase1", "source": {"kind": "delta", "catalog": "workspace", "schema": "halcyon"},
    "forecaster": {"class": "a:B"}, "policy": {"class": "c:D"}, "output_dir": "/tmp/x", "publish_dir": "/v",
    "mlflow": {"experiment": "/e", "run_name": "phase1"},
}


def report(cutoff, version=4):
    return {"release_id": f"weeks-1-{cutoff}-abc", "cutoff_week": cutoff,
            "tables": {f"bronze_{name}": {"rows": 1, "version": version} for name in SCHEMAS}}


def test_builds_a_valid_phase2_config_pinned_to_the_new_release():
    config = RunConfig.parse(build_config(TEMPLATE, report(221), "run1", "abc"))
    assert config.mode == "phase2" and config.source["release_id"] == "weeks-1-221-abc"
    assert set(config.source["versions"].values()) == {4} and "cutoff" not in config.source
    assert config.archived_public["origin_run_id"] == "run1" and config.archived_public["sha256"] == "abc"
    assert config.mlflow["run_name"] == "phase2-private"


def test_refuses_a_release_that_is_not_phase2():
    with pytest.raises(ValueError, match="not 221"):
        build_config(TEMPLATE, report(208), "run1", "abc")


def test_rehearsal_on_phase1_data_is_labeled():
    config = build_config(TEMPLATE, report(208), "run1", "abc", dry_run_cutoff=208)
    assert config["source"]["cutoff"] == 208 and "dry-run" in config["mlflow"]["run_name"]


def test_template_is_not_mutated_and_keeps_fallback():
    template = {**TEMPLATE, "fallback": {"forecaster": {"class": "a:B"}, "policy": {"class": "c:D"}}}
    config = build_config(template, report(221), "run1", "abc")
    assert config["fallback"] == template["fallback"] and template["mlflow"]["run_name"] == "phase1"
