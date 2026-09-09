"""The published tables must import cleanly, or they are not usable evidence.

A CSV carrying the literal `nan` reads into R as a character vector, silently:
no warning, no error, just a column of text where numbers were expected. That is
the failure these tests exist to prevent, along with its quieter relatives -
mixed types in one column, a BOM, CRLF, an undescribed column, or precision that
implies an accuracy the measurement does not have.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TIDY = ROOT / "PUBLISHED/data/case-studies/tidy"
MANIFEST = ROOT / "PUBLISHED/data/case-studies/tidy-downloads.manifest.json"

NUMERIC = re.compile(r"-?\d+(\.\d+)?([eE][+-]?\d+)?")
# Anything a reader could mistake for data, or that breaks a numeric column.
SENTINELS = re.compile(
    r"(?<![A-Za-z0-9_.-])(nan|NaN|NAN|None|inf|-inf|Infinity|null|-9999|-999)(?![A-Za-z0-9_.-])")


def tables():
    if not TIDY.exists():
        pytest.skip("tidy tables are not published")
    return sorted(TIDY.glob("*.csv"))


@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST.exists():
        pytest.skip("tidy-downloads.manifest.json is not published")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_no_table_carries_a_missing_value_sentinel():
    """Empty is the only missing value; `nan` would retype the whole column."""
    for path in tables():
        found = sorted(set(SENTINELS.findall(path.read_text(encoding="utf-8"))))
        assert not found, f"{path.name} contains {found}"


def test_encoding_is_plain_utf8_with_unix_line_endings():
    """A BOM lands in the first column name; CRLF trips naive readers."""
    for path in tables():
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{path.name} has a BOM"
        assert b"\r\n" not in raw, f"{path.name} has CRLF line endings"
        assert raw.endswith(b"\n"), f"{path.name} has no trailing newline"


def test_every_column_holds_one_type():
    """A column that is numeric except for a few strings imports as strings."""
    for path in tables():
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            continue
        for column in rows[0]:
            values = [row[column] for row in rows if row[column] != ""]
            if not values:
                continue
            text = [value for value in values if not NUMERIC.fullmatch(value)]
            assert not text or len(text) == len(values), (
                f"{path.name}:{column} mixes {len(text)} text values into {len(values)}")


def test_numbers_are_rounded_to_something_a_measurement_supports():
    """Full float64 precision is noise presented as information."""
    for path in tables():
        excessive = re.findall(r"-?\d+\.\d{7,}", path.read_text(encoding="utf-8"))
        assert not excessive, f"{path.name} carries {excessive[:2]}"


def test_headers_are_snake_case():
    """One naming convention, so a reader can guess the next column name."""
    for path in tables():
        with path.open(encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle))
        for column in header:
            assert re.fullmatch(r"[a-z][a-z0-9_]*", column), f"{path.name}: {column!r}"


def test_every_column_is_described_with_a_unit():
    """A number without a unit is not a measurement."""
    dictionary = TIDY / "data_dictionary.csv"
    if not dictionary.exists():
        pytest.skip("data dictionary is not published")
    with dictionary.open(encoding="utf-8", newline="") as handle:
        described = {(row["file"], row["column"]): row for row in csv.DictReader(handle)}
    for path in tables():
        if path.name == "data_dictionary.csv":
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle))
        for column in header:
            entry = described.get((path.name, column))
            assert entry, f"{path.name}:{column} is undescribed"
            assert entry["unit"] and entry["description"], f"{path.name}:{column}"


def test_the_two_evaluations_stay_distinguishable(manifest):
    """Stratified and chronological are different experiments, not one series."""
    for name in ("pskem_monthly.csv", "pskem_seasonal.csv"):
        path = TIDY / name
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        labels = {row["evaluation"] for row in rows}
        assert labels == {"stratified", "chronological"}, f"{name}: {labels}"

    with (TIDY / "model_scores.csv").open(encoding="utf-8", newline="") as handle:
        scores = list(csv.DictReader(handle))
    assert {row["evaluation"] for row in scores} == {"stratified", "chronological"}
    assert {row["source"] for row in scores} >= {"model", "benchmark"}


def test_manifest_row_counts_match_the_files(manifest):
    """A manifest that drifts from the bundle is worse than no manifest."""
    counts = {table["file"]: table["rows"] for table in manifest["tables"]}
    for path in tables():
        assert path.name in counts, f"{path.name} is not in the manifest"
        with path.open(encoding="utf-8", newline="") as handle:
            actual = sum(1 for _ in handle) - 1
        assert counts[path.name] == actual, path.name


def test_the_bundle_stays_small_enough_to_download():
    """'Light' is a requirement, not a hope: this is meant to be one click."""
    total = sum(path.stat().st_size for path in TIDY.iterdir() if path.is_file())
    assert total < 5_000_000, f"{total/1e6:.1f} MB is no longer a light bundle"
