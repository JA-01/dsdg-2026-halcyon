import csv
import hashlib
import io
from pathlib import Path

import pandas as pd
import pytest

from halcyon import submission as sub
from halcyon.constants import SUBMISSION_WEEKS
from halcyon.testing import example_decisions, example_forecasts

DATA = Path(__file__).resolve().parents[2] / "data"
SAMPLE = DATA / "sample_submission.csv"
IDS, ALLOWED = sub.load_reference(DATA)
SUPPLIERS = pd.read_csv(DATA / "suppliers.csv")


def rows():
    return list(csv.reader(io.StringIO(SAMPLE.read_text())))


def errors_after(mutate):
    table = rows()
    mutate(table)
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(table)
    return sub.validate_bytes(out.getvalue().encode(), IDS, ALLOWED)


def frames():
    weeks = list(SUBMISSION_WEEKS)
    return example_forecasts(weeks), example_decisions(weeks, SUPPLIERS)


def test_organizer_sample_is_valid():
    assert sub.validate_bytes(SAMPLE.read_bytes(), IDS, ALLOWED) == []
    assert len(IDS) == 260


@pytest.mark.parametrize("mutate,expected", [
    (lambda t: t.pop(), "missing id"),
    (lambda t: t.append(t[1]), "duplicate id"),
    (lambda t: t[1].__setitem__(0, "w999_lithium"), "unexpected id"),
    (lambda t: t[1].__setitem__(2, ""), "blank"),
    (lambda t: t[1].__setitem__(1, "nan"), "non-finite"),
    (lambda t: t[1].__setitem__(1, "inf"), "non-finite"),
    (lambda t: t[1].__setitem__(1, "1.2"), "disruption_prob"),
    (lambda t: t[1].__setitem__(2, "0"), "price_forecast"),
    (lambda t: t[1].__setitem__(3, "-1"), "order_units"),
    (lambda t: t[1].__setitem__(4, "0.5"), "sum to"),
    (lambda t: t[1].__setitem__(4, "-1"), "outside"),
    (lambda t: t[1].__setitem__(5, "x"), "non-numeric"),
    (lambda t: t[0].insert(0, "index"), "header"),
    (lambda t: t.__setitem__(1, t[1][:5]), "expected 10 fields"),
])
def test_invalid_rows_are_named(mutate, expected):
    assert any(expected in error for error in errors_after(mutate))


def test_first_error_names_the_first_bad_row():
    def mutate(table):
        table[3][1] = "2"
        table[7][1] = "3"
    assert "line 4 (" in errors_after(mutate)[0]


def test_ineligible_supplier_rejected_even_when_tiny():
    def mutate(table):  # w209_lithium is sold by KES, VAL, ORI, not AUR
        table[1][4], table[1][9] = "0.9999999", "0.0000001"
    assert any("ineligible" in error for error in errors_after(mutate))


def test_zero_order_still_needs_shares():
    def mutate(table):
        table[1][3] = "0"
        table[1][4:] = ["0"] * 6
    assert any("sum to" in error for error in errors_after(mutate))


def test_row_order_must_match_sample():
    def mutate(table):
        table[1], table[2] = table[2], table[1]
    assert any("order" in error for error in errors_after(mutate))


def test_empty_file():
    assert sub.validate_bytes(b"", IDS, ALLOWED) == ["file is empty"]


def test_build_uses_sample_order_and_passes_values_through():
    forecasts, decisions = frames()
    built = sub.build_submission(forecasts.sample(frac=1, random_state=1), decisions, IDS)
    assert built["id"].tolist() == IDS
    assert list(built.columns) == list(sub.SUBMISSION_COLUMNS)


def test_build_rejects_duplicate_and_mismatched_keys():
    forecasts, decisions = frames()
    with pytest.raises(sub.SubmissionError, match="one-to-one"):
        sub.build_submission(pd.concat([forecasts, forecasts.iloc[[0]]]), decisions, IDS)
    with pytest.raises(sub.SubmissionError, match="keys differ"):
        sub.build_submission(forecasts.iloc[1:], decisions, IDS)
    wrong = [w for w in SUBMISSION_WEEKS if w != 234]
    with pytest.raises(sub.SubmissionError, match="ids differ"):
        sub.build_submission(forecasts[forecasts.target_week.isin(wrong)],
                             decisions[decisions.target_week.isin(wrong)], IDS)


def test_export_writes_bytes_that_revalidate(tmp_path):
    built = sub.build_submission(*frames(), IDS)
    path = tmp_path / "nested" / "submission.csv"
    result = sub.write_submission(built, path, IDS, ALLOWED)
    raw = path.read_bytes()
    assert path.is_file() and result.rows == 260
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert sub.validate_bytes(raw, IDS, ALLOWED) == []
    assert raw.splitlines()[0].decode() == ",".join(sub.SUBMISSION_COLUMNS)
    assert [p.name for p in path.parent.iterdir()] == ["submission.csv"]


def test_export_refuses_invalid_shares_and_leaves_no_file(tmp_path):
    built = sub.build_submission(*frames(), IDS)
    built.loc[0, "share_KES"] = 0.9
    path = tmp_path / "submission.csv"
    with pytest.raises(sub.SubmissionError, match="refusing"):
        sub.write_submission(built, path, IDS, ALLOWED)
    assert not path.exists()


def test_export_refuses_nan(tmp_path):
    built = sub.build_submission(*frames(), IDS)
    built.loc[5, "price_forecast"] = float("nan")
    with pytest.raises(sub.SubmissionError, match="blank"):
        sub.write_submission(built, tmp_path / "s.csv", IDS, ALLOWED)


def test_cli_exit_codes(tmp_path, capsys):
    assert sub.main([str(SAMPLE), "--data-dir", str(DATA)]) == 0
    bad = tmp_path / "bad.csv"
    bad.write_text("nope\n")
    assert sub.main([str(bad), "--data-dir", str(DATA)]) == 1
    assert sub.main([str(tmp_path / "absent.csv"), "--data-dir", str(DATA)]) == 2
