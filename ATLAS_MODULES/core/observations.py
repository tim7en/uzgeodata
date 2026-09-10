"""Append-only basin observation store: the contract both atlas programmes write through.

`REPRODUCIBILITY.md` specifies the long observation table, its identity and its
rules. This module is the executable form of that specification. Nothing may
enter the store except through `build`, so the confusions the contract names
fail loudly here instead of becoming published numbers:

* a land-cover class code read as a calendar month (`glc_pc_s01` is class 1, not January),
* a climatology read as a dated observation (monthly climatology 07 is not July 2026),
* a missing value read as a zero,
* a changed unit, geometry or period hidden inside an unversioned series,
* a correction that overwrites the value it replaces instead of superseding it.

The store is written as partitioned CSV. That is a staging format, not the
production decision: the physical design stays open until it is benchmarked.
"""
from __future__ import annotations
import csv
from datetime import date
import hashlib
from pathlib import Path

# Column order of the long table, as specified in REPRODUCIBILITY.md. Resolution,
# licence and code provenance belong to the source-release and recipe tables, not
# repeated on every row.
FIELDS = (
    "observation_id", "revision", "supersedes",
    "basin_id", "geometry_version", "basin_level",
    "attribute_id", "recipe_version", "mode", "spatial_support",
    "time_kind", "temporal_statistic", "valid_start", "valid_end", "year", "month",
    "value", "unit", "coverage_fraction", "valid_count", "expected_count",
    "quality_flag", "missing_reason",
    "source_release_id", "run_id", "retrieved_at", "recorded_at", "provisional",
)

# Identity of an observation. Deliberately excludes run_id and revision: a
# correction from a later run is a new revision of the same observation, not a
# second observation. It also excludes value, unit and coverage, so a changed
# unit cannot quietly present itself as a different observation.
IDENTITY = (
    "basin_id", "geometry_version", "basin_level", "attribute_id", "recipe_version",
    "mode", "spatial_support", "time_kind", "valid_start", "valid_end", "year", "month",
    "source_release_id",
)

# The scope over which a unit, a time kind and a period definition must agree:
# one attribute, under one mode and support, across every basin. Keeping basins
# inside the scope is deliberate — two basins reported in different units are
# exactly the mixed-unit series the contract rejects. Any of it may still change,
# but only when the recipe or the geometry release changes with it.
SERIES = ("attribute_id", "mode", "spatial_support")

TIME_KINDS = ("static", "source_epoch", "climatology", "observation")
MODES = ("reference_import", "baseline_reproduction", "baseline_reproduction_candidate",
         "annual_extension")
SUPPORTS = ("s", "u", "p")
INTEGERS = ("basin_level", "revision", "year", "month", "valid_count", "expected_count")
NUMBERS = ("value", "coverage_fraction")


class ContractError(ValueError):
    """A record that would break the published observation contract."""


def observation_id(record):
    """Stable identity: the same observation from a later run keeps this id."""
    material = "|".join(f"{field}={_text(record.get(field))}" for field in IDENTITY)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def row_key(record):
    return f"{record['observation_id']}@{record['revision']}"


def build(**record):
    """Normalise and validate one observation. The only way into the store."""
    record.setdefault("revision", 1)
    record.setdefault("supersedes", None)
    record.setdefault("provisional", False)
    for field in FIELDS:
        record.setdefault(field, None)
    unknown = set(record) - set(FIELDS)
    if unknown:
        raise ContractError(f"Fields outside the contract: {sorted(unknown)}")
    record["basin_id"] = _text(record["basin_id"])  # HYBAS_ID is a string, never an int
    for field in INTEGERS:
        record[field] = _integer(field, record[field])
    for field in NUMBERS:
        record[field] = _number(field, record[field])
    record["provisional"] = bool(record["provisional"])
    record["observation_id"] = observation_id(record)
    return validate(record)


def validate(record):
    """Every rule the contract states, applied to a single record."""
    if not record["basin_id"]:
        raise ContractError("basin_id is required and is stored as a string")
    if record["basin_level"] is None:
        raise ContractError("basin_level is required; a value without its level is unjoinable")
    for field, allowed in (("time_kind", TIME_KINDS), ("mode", MODES), ("spatial_support", SUPPORTS)):
        if record[field] not in allowed:
            raise ContractError(f"{field} must be one of {allowed}, not {record[field]!r}")
    for field in ("attribute_id", "geometry_version", "recipe_version", "source_release_id", "run_id"):
        if not record[field]:
            raise ContractError(f"{field} is required; an unattributed value is not evidence")

    _validate_time(record)
    _validate_value(record)
    _validate_counts(record)
    _validate_revision(record)
    return record


def _validate_time(record):
    kind = record["time_kind"]
    # A dated observation is the only kind that carries a year. Static values,
    # source epochs and climatologies have none, so no year can be invented for them.
    if kind == "observation":
        if record["year"] is None:
            raise ContractError("a dated observation requires its year")
        if not (record["valid_start"] and record["valid_end"]):
            raise ContractError("a dated observation requires its valid period")
    elif record["year"] is not None:
        raise ContractError(f"time_kind {kind!r} carries no year; {record['year']} would be invented")

    # A month is a calendar month. Only a climatology or a dated observation has
    # one; elsewhere a two-digit dimension is a class code and must not be stored
    # as a month.
    if record["month"] is not None:
        if kind not in ("climatology", "observation"):
            raise ContractError(f"time_kind {kind!r} has no calendar month; {record['month']} is a dimension code")
        if not 1 <= record["month"] <= 12:
            raise ContractError(f"month {record['month']} is not a calendar month")

    if record["valid_start"] and record["valid_end"]:
        start, end = _date(record["valid_start"]), _date(record["valid_end"])
        if end <= start:
            raise ContractError(f"valid_end {record['valid_end']} must lie after valid_start {record['valid_start']}; the end is exclusive")


def _validate_value(record):
    # A missing value states why it is missing, and never arrives as a zero.
    if record["value"] is None:
        if not record["missing_reason"]:
            raise ContractError("a null value requires a missing_reason")
    elif record["missing_reason"]:
        raise ContractError(f"value {record['value']} carries missing_reason {record['missing_reason']!r}; a measured value is not missing")
    if not record["unit"] and record["value"] is not None:
        raise ContractError("a value requires its unit")


def _validate_counts(record):
    valid, expected = record["valid_count"], record["expected_count"]
    for field in ("valid_count", "expected_count"):
        if record[field] is not None and record[field] < 0:
            raise ContractError(f"{field} cannot be negative")
    if valid is not None and expected is not None:
        if valid > expected:
            raise ContractError(f"valid_count {valid} exceeds expected_count {expected}")
        if expected and record["coverage_fraction"] is not None:
            if abs(record["coverage_fraction"] - valid / expected) > 1e-6:
                raise ContractError("coverage_fraction disagrees with its own QA denominators")
    if record["coverage_fraction"] is not None and not 0 <= record["coverage_fraction"] <= 1:
        raise ContractError(f"coverage_fraction {record['coverage_fraction']} lies outside 0..1")


def _validate_revision(record):
    if record["revision"] is None or record["revision"] < 1:
        raise ContractError("revision starts at 1 and increases")
    if record["revision"] == 1:
        if record["supersedes"]:
            raise ContractError("a first revision supersedes nothing")
        return
    if not record["supersedes"]:
        raise ContractError(f"revision {record['revision']} must name the row it supersedes")
    superseded_id, _, superseded_revision = record["supersedes"].partition("@")
    if superseded_id != record["observation_id"]:
        raise ContractError("a revision supersedes an earlier revision of the same observation, not another one")
    if not superseded_revision.isdigit() or int(superseded_revision) >= record["revision"]:
        raise ContractError(f"revision {record['revision']} cannot supersede {record['supersedes']}")


def series_conflicts(rows):
    """Unit, time kind and period definition hold steady unless a version moves.

    A dated series varies its period by design, one row per month, so only the
    period *definition* of an undated kind is held constant here: a climatology
    that quietly changes its window is a different measurement wearing the same
    name, while January 2003 and February 2003 are simply two observations.
    """
    problems, seen = set(), {}
    for record in rows:
        series = tuple(record[field] for field in SERIES)
        version = (record["recipe_version"], record["geometry_version"])
        watched = ["unit", "time_kind"]
        if record["time_kind"] != "observation":
            watched += ["valid_start", "valid_end"]
        for field in watched:
            slot = (series, version, field)
            if slot in seen and seen[slot] != record[field]:
                problems.add(f"{series[0]} ({series[1]}): {field} changes from {seen[slot]!r} "
                             f"to {record[field]!r} without a new recipe or geometry version")
            seen.setdefault(slot, record[field])
    return sorted(problems)


def append(existing, incoming):
    """Add records without rewriting any that are already published."""
    by_key = {row_key(record): record for record in existing}
    result = list(existing)
    for record in incoming:
        key = row_key(record)
        if key in by_key:
            if _content(by_key[key]) != _content(record):
                raise ContractError(f"{key} is already published with different content; a correction is a new revision, not a rewrite")
            continue  # Staging the same frozen evidence twice is a no-op.
        if record["revision"] > 1 and record["supersedes"] not in by_key:
            raise ContractError(f"{key} supersedes {record['supersedes']}, which is not in the store")
        by_key[key] = record
        result.append(record)
    problems = series_conflicts(result)
    if problems:
        raise ContractError("; ".join(problems))
    return result


def latest(rows):
    """The current view: the newest revision of each observation, nothing dropped."""
    superseded = {record["supersedes"] for record in rows if record["supersedes"]}
    current = {}
    for record in rows:
        if row_key(record) in superseded:
            continue
        held = current.get(record["observation_id"])
        if held is None or record["revision"] > held["revision"]:
            current[record["observation_id"]] = record
    return sorted(current.values(), key=sort_key)


def sort_key(record):
    return (record["attribute_id"], record["mode"], record["basin_id"],
            _text(record["year"]), _text(record["month"]), record["revision"])


def partition(record):
    """Partitioned by time kind, and by year once observations are dated."""
    parts = [f"time_kind={record['time_kind']}"]
    if record["time_kind"] == "observation":
        parts.append(f"year={record['year']}")
    return Path(*parts)


def write_partitions(directory, rows):
    directory = Path(directory)
    groups = {}
    for record in rows:
        groups.setdefault(partition(record), []).append(record)
    written = []
    for name, group in sorted(groups.items()):
        path = directory / name / "part.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            for record in sorted(group, key=sort_key):
                writer.writerow({field: _text(record[field]) for field in FIELDS})
        written.append(path)
    return written


def merge_table(path, rows, key):
    """Side tables accumulate. Each pipeline contributes the rows it can vouch for,
    and never drops another pipeline's, so a run staged from one source does not
    erase the source releases of the next."""
    path = Path(path)
    existing, fields = {}, []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = list(reader.fieldnames or [])
            for row in reader:
                existing[row[key]] = row
    for row in rows:
        record = {name: _text(value) for name, value in row.items()}
        for name in record:
            if name not in fields:
                fields.append(name)
        existing[record[key]] = record
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for name in sorted(existing):
            writer.writerow({field: existing[name].get(field, "") for field in fields})
    return len(existing)


def read_partitions(directory):
    rows = []
    for path in sorted(Path(directory).glob("**/part.csv")):
        with path.open(encoding="utf-8", newline="") as stream:
            for raw in csv.DictReader(stream):
                rows.append(_decode(raw))
    return rows


def _decode(raw):
    record = {field: (raw.get(field) or None) for field in FIELDS}
    for field in INTEGERS:
        record[field] = _integer(field, record[field])
    for field in NUMBERS:
        record[field] = _number(field, record[field])
    record["provisional"] = record["provisional"] == "True"
    return record


# Who fetched a value and when is not the value. Re-fetching an immutable source
# yields the same observation, so these three fields identify the visit rather than
# the measurement and are left out of the comparison below.
VISIT = ("run_id", "retrieved_at", "recorded_at")


def _content(record):
    """What a re-run must reproduce exactly. The store keeps the run that first
    established a value, so a later run confirming the same number is a no-op and
    a later run disagreeing has to supersede it. If a source is mutable and gives a
    different number on re-fetch, that difference still surfaces as a conflict."""
    return {field: record[field] for field in FIELDS if field not in VISIT}


def _text(value):
    if value is None:
        return ""
    return str(value)


def _integer(field, value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ContractError(f"{field} must be a whole number, not {value!r}") from None


def _number(field, value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ContractError(f"{field} must be numeric, not {value!r}") from None


def _date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ContractError(f"{value!r} is not an ISO date") from None
