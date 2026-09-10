"""Run the dated monthly snow series across all 7,445 level-12 basins.

python PIPELINES/extract_regional_snow.py [--batch 250] [--years 2003-2022]

The pilot proved the method on 20 basins; the benchmark priced it on 250. This is
the regional run, and at that size the shape of the job matters as much as the
method: one call for 7,445 basins would exceed what Earth Engine will return, and a
run measured in hours cannot start from the beginning every time something fails.

So the work is cut into basin batches and taken a year at a time. Each finished
batch-year is written to a checkpoint before anything else is attempted, a failed
one is retried with backoff and then recorded rather than hidden, and a rerun skips
whatever is already complete. The ledger at the end says, per year, how many basins
were expected and how many arrived, so an incomplete run is visible as incomplete
instead of looking like a region with less snow in it.

Null months are carried through as nulls with their reason. A basin-month with no
cloud-free observation is not a basin-month without snow.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.runtime import sha256, utc_now, write_json
from ATLAS_MODULES.hydrosheds.functions import dated_snow
from PIPELINES.benchmark_regional_batch import BBOX, GDB, LAYER, SYSTEMS, CELL
from PIPELINES.extract_dated_snow import (
    ATTRIBUTE, PROJECT, SOURCE_RELEASE, UNIT, month_period, observation_rows)
from PIPELINES.stage_pilot_observations import BASIN_LEVEL, STORE

CHECKPOINTS = ROOT / "WORKSPACE/atlas_runs/regional_snow"
LEDGER = STORE / "regional-snow-ledger.json"
DEFAULT_YEARS = (2003, 2022)
RETRIES = 3


def load_frame():
    """The full level-12 frame of both systems, in a stable order."""
    import pyogrio
    frame = pyogrio.read_dataframe(GDB, layer=LAYER, bbox=BBOX)
    frame = frame[frame.MAIN_BAS.astype("int64").isin(SYSTEMS)]
    return frame.sort_values("HYBAS_ID").reset_index(drop=True)


def regional_grid(frame):
    """The shared 15 arc-second lattice, aligned exactly as the pilot's grid is."""
    west, south, east, north = frame.total_bounds
    west, south = [math.floor(v / CELL) * CELL for v in (west, south)]
    east, north = [math.ceil(v / CELL) * CELL for v in (east, north)]
    return [CELL, 0.0, west, 0.0, -CELL, north]


def geometry_version(frame):
    """Identity of this geometry selection: the release, the level and the basins in it."""
    material = f"{LAYER}|{BASIN_LEVEL}|" + ",".join(str(int(h)) for h in frame.HYBAS_ID)
    import hashlib
    return "reg-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def batches(frame, size):
    for start in range(0, len(frame), size):
        chunk = frame.iloc[start:start + size]
        yield start // size, [{"geometry": geometry.__geo_interface__,
                               "properties": {"HYBAS_ID": int(hybas)}}
                              for geometry, hybas in zip(chunk.geometry, chunk.HYBAS_ID)]


def checkpoint_path(batch, year):
    return CHECKPOINTS / f"batch-{batch:04d}" / f"year-{year}.json"


def summarise_year(rows, expected_basins, seconds):
    """What arrived for one year. `complete` is the claim the ledger has to earn."""
    basins = len({row["hybas_id"] for row in rows})
    return {"rows": len(rows), "basins": basins, "expected_basins": expected_basins,
            "complete": basins == expected_basins,
            "values": sum(1 for row in rows if row["value"] is not None),
            "null_months": sum(1 for row in rows if row["value"] is None),
            "seconds": seconds}


def support_summary(expected, thresholds=(1, 5, 25, 100)):
    """How much grid each basin actually gets.

    A level-12 basin is not a fixed size. Most hold several hundred 15 arc-second
    cells, but the smallest hold a handful, and a monthly value there rests on those
    few cells: if they are all cloudy the month is null, and if they are not the
    value still carries far less support than a basin of median size. The counts are
    published so that a reader can filter on them rather than discover it later.
    """
    counts = sorted(cells for batch in expected.values() for cells in batch.values())
    if not counts:
        return {}
    middle = len(counts) // 2
    return {
        "basins": len(counts),
        "cells_min": counts[0], "cells_max": counts[-1],
        "cells_median": counts[middle] if len(counts) % 2 else (counts[middle - 1] + counts[middle]) // 2,
        "basins_at_or_below": {str(t): sum(1 for c in counts if c <= t) for t in thresholds},
        "basins_without_a_cell": sum(1 for c in counts if c == 0),
        "meaning": "Analysis cells per basin on the 15 arc-second grid. A value from a "
                   "basin with few cells is supported by few observations; every row "
                   "carries its own valid and expected counts so this can be filtered on. "
                   "A basin with no cell at all would yield no value rather than a zero.",
    }


def availability_by_year(store, years, version):
    """How the source's own availability moves over the record.

    A month is null when no cloud-free observation reached a basin at all. That is a
    property of the imagery, not of the snow, and it does not hold steady across a
    twenty-year record. Publishing it per year, with the size of the basins affected,
    is what stops a change in what the sensor delivered from being read later as a
    change in what the snow did. No cause is asserted here; the numbers are the
    finding, and explaining them is separate work.
    """
    report = {}
    for year in years:
        rows = [row for row in observations.read_partitions(
            store / "time_kind=observation" / f"year={year}")
            if row["geometry_version"] == version]
        if not rows:
            continue
        cells = {row["basin_id"]: row["expected_count"] for row in rows}
        nulls = [row for row in rows if row["value"] is None]
        sizes = sorted(cells[row["basin_id"]] for row in nulls)
        report[str(year)] = {
            "null_months": len(nulls),
            "basins_affected": len({row["basin_id"] for row in nulls}),
            "median_affected_basin_cells": sizes[len(sizes) // 2] if sizes else 0,
            "nulls_in_basins_over_100_cells": sum(1 for size in sizes if size > 100),
            "summer_share": round(sum(1 for row in nulls if 6 <= row["month"] <= 9) / len(nulls), 3)
            if nulls else 0.0,
        }
    return report


def is_complete(ledger):
    """A run is complete only if nothing failed, every year has every basin, and the
    rows written match the rows expected. Any one of those failing makes it partial."""
    return (not ledger["failures"]
            and bool(ledger["by_year"])
            and all(year["complete"] for year in ledger["by_year"].values())
            and ledger["stored_rows"] == ledger["expected_rows"])


def with_retries(work, label, ledger):
    """A transient Earth Engine failure is retried; a persistent one is recorded."""
    for attempt in range(1, RETRIES + 1):
        try:
            return work(), None
        except Exception as error:
            message = f"{type(error).__name__}: {str(error)[:300]}"
            ledger["retries"].append({"at": utc_now(), "target": label,
                                      "attempt": attempt, "error": message})
            if attempt == RETRIES:
                ledger["failures"].append({"at": utc_now(), "target": label, "error": message})
                return None, message
            time.sleep(min(60, 5 * 2 ** (attempt - 1)))
    return None, "unreachable"


def run(batch_size=250, years=DEFAULT_YEARS, store=STORE, project=PROJECT):
    import ee
    ee.Initialize(project=project)

    frame = load_frame()
    transform, version = regional_grid(frame), geometry_version(frame)
    span = list(range(years[0], years[1] + 1))
    identifier = f"regional-snow-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}Z"
    recipe = f"dated_snow@{sha256(ROOT / 'ATLAS_MODULES/hydrosheds/functions/dated_snow.py')[:12]}"
    started = time.perf_counter()

    ledger = {"run_id": identifier, "started_at": utc_now(), "attribute_id": ATTRIBUTE,
              "geometry_version": version, "basins": len(frame), "years": [span[0], span[-1]],
              "batch_size": batch_size, "expected_rows": len(frame) * len(span) * 12,
              "retries": [], "failures": [], "by_year": {}}
    print(f"{len(frame)} basins, {len(span)} years, batches of {batch_size} "
          f"-> {ledger['expected_rows']:,} rows", flush=True)

    # The QA denominators do not change with the year, so each batch pays for them once.
    plan, expected = list(batches(frame, batch_size)), {}
    for index, features in plan:
        cache = CHECKPOINTS / f"batch-{index:04d}" / "expected.json"
        if cache.exists():
            expected[index] = json.loads(cache.read_text(encoding="utf-8"))
            continue
        collection = dated_snow.feature_collection(features)
        result, error = with_retries(lambda c=collection: dated_snow.expected_cells(c, transform),
                                     f"expected/batch-{index}", ledger)
        if error:
            continue
        expected[index] = result
        write_json(cache, result)
    print(f"denominators ready for {len(expected)}/{len(plan)} batches "
          f"({time.perf_counter() - started:.0f}s)", flush=True)

    for year in span:
        year_started, collected = time.perf_counter(), []
        for index, features in plan:
            if index not in expected:
                continue
            path = checkpoint_path(index, year)
            if path.exists():
                collected.extend(json.loads(path.read_text(encoding="utf-8")))
                continue
            collection = dated_snow.feature_collection(features)
            rows, error = with_retries(
                lambda c=collection, y=year, i=index: dated_snow.year_rows(c, transform, y, expected[i]),
                f"year-{year}/batch-{index}", ledger)
            if error:
                continue
            write_json(path, rows)
            collected.extend(rows)

        built = observation_rows(collected, version, recipe, identifier, utc_now(), utc_now())
        observations.append_partitioned(store, built)

        ledger["by_year"][str(year)] = summarise_year(collected, len(frame),
                                                      time.perf_counter() - year_started)
        basins_seen = ledger["by_year"][str(year)]["basins"]
        print(f"{year}: {basins_seen}/{len(frame)} basins, {len(collected):,} rows, "
              f"{ledger['by_year'][str(year)]['seconds']:.0f}s "
              f"[{time.perf_counter() - started:.0f}s total]", flush=True)

    ledger["finished_at"] = utc_now()
    ledger["wall_seconds"] = time.perf_counter() - started
    ledger["stored_rows"] = sum(y["rows"] for y in ledger["by_year"].values())
    ledger["complete"] = is_complete(ledger)
    ledger["basin_support"] = support_summary(expected)
    ledger["availability"] = {
        "by_year": availability_by_year(store, span, version),
        "meaning": "A null month is a month in which no cloud-free observation reached the "
                   "basin. It is a property of the imagery, not of the snow. These counts are "
                   "not stable across the record, so a trend computed from this series without "
                   "accounting for them can mistake changing observation availability for "
                   "changing snow cover. No cause is asserted; the counts are the finding.",
        "source_images_are_not_the_explanation": "Daily source image counts are effectively "
                                                 "constant across the record; see source_images.",
    }
    ledger["source_images"] = {str(year): dated_snow.source_images(year) for year in span}
    write_json(LEDGER, ledger)

    observations.merge_table(store / "run.csv", [{
        "run_id": identifier, "started_at": ledger["started_at"], "finished_at": ledger["finished_at"],
        "wall_seconds": ledger["wall_seconds"],
        "status": "complete" if ledger["complete"] else "incomplete",
        "scientific_release": "not_eligible"}], "run_id")
    observations.merge_table(store / "recipe.csv", [
        {"recipe_version": recipe, "mode": "annual_extension"}], "recipe_version")
    observations.merge_table(store / "basin_geometry.csv", [{
        "geometry_version": version, "basin_level": BASIN_LEVEL, "basin_count": len(frame),
        "sha256": "", "scope": f"Amu Darya and Syr Darya level-12 frame from {LAYER}"}],
        "geometry_version")
    return ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, default=250)
    parser.add_argument("--years", default=f"{DEFAULT_YEARS[0]}-{DEFAULT_YEARS[1]}")
    arguments = parser.parse_args()
    first, _, last = arguments.years.partition("-")
    ledger = run(arguments.batch, (int(first), int(last or first)))
    print(json.dumps({k: v for k, v in ledger.items() if k not in ("retries", "source_images")},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
