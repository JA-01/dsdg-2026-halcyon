"""Build, export and validate the competition CSV. Rejects invalid values; never repairs them.

CLI: python -m halcyon.submission path/to/submission.csv [--data-dir data]
Exit code 0 = valid, 1 = invalid, 2 = usage/IO error.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .constants import COUNTRIES, SHARE_COLUMNS, SHARE_SUM_TOLERANCE, SUBMISSION_COLUMNS
from .contracts import eligibility

MAX_ERRORS = 50


class SubmissionError(ValueError):
    """The submission violates the competition contract. The message names the first bad row."""


@dataclass(frozen=True)
class ExportResult:
    path: Path
    sha256: str
    rows: int


def _finite(text: str) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def validate_bytes(raw: bytes, expected_ids: list[str], allowed: dict[str, set[str]]) -> list[str]:
    """Return problems in file order (empty when valid). The first one is the first bad row."""
    errors: list[str] = []
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append("file starts with a UTF-8 BOM")
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        return [f"file is not UTF-8: {exc}"]
    reader = csv.reader(lines)
    header = next(reader, None)
    if header is None:
        return ["file is empty"]
    if header != list(SUBMISSION_COLUMNS):
        return [*errors, f"header must be {list(SUBMISSION_COLUMNS)}, got {header}"]

    seen: list[str] = []
    for line, row in enumerate(reader, start=2):
        if len(row) != len(SUBMISSION_COLUMNS):
            errors.append(f"line {line}: expected {len(SUBMISSION_COLUMNS)} fields, got {len(row)}")
            continue
        rid, cells = row[0], row[1:]
        where = f"line {line} ({rid})"
        if rid in seen:
            errors.append(f"{where}: duplicate id")
        seen.append(rid)
        values = dict(zip(SUBMISSION_COLUMNS[1:], map(_finite, cells)))
        blanks = [c for c, v in values.items() if v is None]
        if blanks:
            errors.append(f"{where}: blank, non-numeric or non-finite {blanks}")
            continue
        if not 0 <= values["disruption_prob"] <= 1:
            errors.append(f"{where}: disruption_prob {values['disruption_prob']} outside [0, 1]")
        if values["price_forecast"] <= 0:
            errors.append(f"{where}: price_forecast {values['price_forecast']} must be above 0")
        if values["order_units"] < 0:
            errors.append(f"{where}: order_units {values['order_units']} is negative")
        shares = [values[c] for c in SHARE_COLUMNS]
        if any(not 0 <= s <= 1 for s in shares):
            errors.append(f"{where}: share outside [0, 1]")
        if abs(sum(shares) - 1) > SHARE_SUM_TOLERANCE:
            errors.append(f"{where}: shares sum to {sum(shares)!r}, not 1")
        material = rid.split("_", 1)[1] if "_" in rid else ""
        if material not in allowed:
            errors.append(f"{where}: unknown material {material!r}")
        else:
            bad = [c for c, s in zip(COUNTRIES, shares) if s != 0 and c not in allowed[material]]
            if bad:
                errors.append(f"{where}: positive share on ineligible supplier {bad}")

    missing = sorted(set(expected_ids) - set(seen))
    extra = sorted(set(seen) - set(expected_ids))
    if missing:
        errors.append(f"{len(missing)} missing id(s), first {missing[0]}")
    if extra:
        errors.append(f"{len(extra)} unexpected id(s), first {extra[0]}")
    if not errors and seen != expected_ids:
        errors.append("rows are not in sample_submission id order")
    return errors


def build_submission(forecasts: pd.DataFrame, decisions: pd.DataFrame,
                     expected_ids: list[str]) -> pd.DataFrame:
    """One-to-one join of forecasts and decisions, in sample id order. Values pass through as is."""
    keys = ["target_week", "material"]
    columns = list(SUBMISSION_COLUMNS[1:3])
    try:
        joined = forecasts[keys + columns].merge(
            decisions[keys + list(SUBMISSION_COLUMNS[3:])], on=keys, how="outer",
            validate="one_to_one", indicator=True)
    except pd.errors.MergeError as exc:
        raise SubmissionError(f"forecast/decision join is not one-to-one: {exc}") from exc
    unmatched = joined[joined["_merge"] != "both"]
    if len(unmatched):
        first = unmatched.iloc[0]
        raise SubmissionError(
            f"forecast/decision keys differ at week {first['target_week']} {first['material']}")
    joined["id"] = "w" + joined["target_week"].astype(int).astype(str) + "_" + joined["material"]
    frame = joined.set_index("id", drop=False)
    unknown = sorted(set(frame.index) - set(expected_ids))
    missing = sorted(set(expected_ids) - set(frame.index))
    if unknown or missing:
        raise SubmissionError(f"ids differ from sample: missing {missing[:3]}, unexpected {unknown[:3]}")
    return frame.loc[expected_ids, list(SUBMISSION_COLUMNS)].reset_index(drop=True)


def write_submission(frame: pd.DataFrame, path: str | Path, expected_ids: list[str],
                     allowed: dict[str, set[str]]) -> ExportResult:
    """Validate the serialized bytes, write one real CSV atomically, then reread and revalidate."""
    path = Path(path)
    raw = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    errors = validate_bytes(raw, expected_ids, allowed)
    if errors:
        raise SubmissionError(f"refusing to write {path}: {errors[0]} ({len(errors)} problem(s))")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(raw)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    written = path.read_bytes()
    errors = validate_bytes(written, expected_ids, allowed)
    if written != raw or errors:
        raise SubmissionError(f"{path} failed validation after writing: {errors[:1]}")
    return ExportResult(path, hashlib.sha256(written).hexdigest(), len(expected_ids))


def load_reference(data_dir: str | Path) -> tuple[list[str], dict[str, set[str]]]:
    """Expected ids (in order) and eligibility, from the organizer's files."""
    data_dir = Path(data_dir)
    ids = pd.read_csv(data_dir / "sample_submission.csv", usecols=["id"])["id"].tolist()
    return ids, eligibility(pd.read_csv(data_dir / "suppliers.csv"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a competition submission CSV.")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    try:
        raw = args.csv.read_bytes()
        expected_ids, allowed = load_reference(args.data_dir)
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    errors = validate_bytes(raw, expected_ids, allowed)
    if errors:
        print(f"INVALID: {args.csv} ({len(errors)} problem(s), showing up to {MAX_ERRORS})")
        for error in errors[:MAX_ERRORS]:
            print(f"  - {error}")
        return 1
    print(f"VALID: {args.csv} rows={len(expected_ids)} sha256={hashlib.sha256(raw).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
