import hashlib
from pathlib import Path

import pandas as pd
import pytest

from halcyon.accept import check_export, check_gold

DATA = Path(__file__).resolve().parents[2] / "data"
RAW = (DATA / "sample_submission.csv").read_bytes()
SHA = hashlib.sha256(RAW).hexdigest()
SUPPLIERS = pd.read_csv(DATA / "suppliers.csv")
MANIFEST = {"export": {"sha256": SHA}, "dirty": False, "git_sha": "abc", "fallback_reason": None}


def failed(checks):
    return [name for name, passed, _ in checks if not passed]


def test_good_run_passes():
    assert failed(check_export(RAW, MANIFEST, SHA, SUPPLIERS)) == []


@pytest.mark.parametrize("manifest,sha,expected", [
    ({**MANIFEST, "dirty": True}, SHA, "built from clean code"),
    ({**MANIFEST, "dirty": None}, SHA, "built from clean code"),
    ({**MANIFEST, "fallback_reason": "boom"}, SHA, "no fallback used"),
    ({**MANIFEST, "export": {"sha256": "0"}}, SHA, "csv hash matches manifest"),
    (MANIFEST, "0", "csv hash matches MLflow"),
])
def test_each_record_mismatch_fails(manifest, sha, expected):
    assert failed(check_export(RAW, manifest, sha, SUPPLIERS)) == [expected]


def test_invalid_bytes_fail_validation():
    bad = RAW.replace(b"w209_lithium,0.2067", b"w209_lithium,1.2067")
    digest = hashlib.sha256(bad).hexdigest()
    manifest = {**MANIFEST, "export": {"sha256": digest}}
    assert failed(check_export(bad, manifest, digest, SUPPLIERS)) == ["csv passes the validator"]


def test_retained_public_rows_are_compared():
    assert failed(check_export(RAW, MANIFEST, SHA, SUPPLIERS, retained=RAW)) == []
    changed_public = RAW.replace(b"w209_lithium,0.2067", b"w209_lithium,0.3067")
    assert failed(check_export(RAW, MANIFEST, SHA, SUPPLIERS, retained=changed_public)) == [
        "public rows match the archived run"]
    changed_private = RAW.replace(b"w234_natural_gas,", b"w234_natural_gas,0")
    assert failed(check_export(RAW, MANIFEST, SHA, SUPPLIERS, retained=changed_private)) == []


def test_gold_needs_130_unique_rows_per_window():
    good = {(t, w): (130, 130) for t in ("gold_forecasts", "gold_decisions") for w in ("public", "private")}
    assert failed(check_gold(good, ["public", "private"])) == []
    assert len(failed(check_gold({**good, ("gold_decisions", "public"): (131, 130)}, ["public", "private"]))) == 1
    assert len(failed(check_gold({}, ["public"]))) == 2
