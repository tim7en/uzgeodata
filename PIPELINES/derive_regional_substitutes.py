"""Turn the dated regional observations into HydroATLAS-shaped substitute values.

python PIPELINES/derive_regional_substitutes.py [--years 2003-2022]

The regional extraction produced monthly observations; this computes the normals,
annual figures and indices that HydroATLAS defines, for every basin in the domain.
It reads only what is already in the store and fetches nothing.

The result is an independent open-data estimate over a stated period, published under
its own recipe version beside the original values, never in place of them. It moves
nothing toward reproduction: an estimate that agrees with a published attribute is
still an estimate.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.runtime import sha256, utc_now, write_json
from ATLAS_MODULES.hydrosheds.functions import derive_climatology as derive
from PIPELINES.stage_pilot_observations import BASIN_LEVEL, STORE, latest_run

BASE = "hydrosheds.basinatlas.v1."
DEFAULT_YEARS = (2003, 2022)
SUMMARY = STORE / "regional-substitutes-summary.json"

# Which source release stands behind each derived column family.
ORIGIN = {"aet": "terraclimate", "pet": "terraclimate", "swc": "terraclimate",
          "pre": "terraclimate", "cmi": "terraclimate", "ari": "terraclimate",
          "snw": "snow", "run": "era5_runoff"}


def units_by_family(batch):
    """The surrogate's own physical units, as the reviewed builders record them."""
    return {family: plan["units"]["surrogate"]
            for family, plan in batch["surrogate_families"].items()}


def family_of(column):
    return column.split("_")[0] if not column.startswith(("glc", "pnv", "wet")) else column[:6]


def releases(store):
    """Map each source to the release id its dated rows already point at."""
    found = {}
    for path in sorted((store / "time_kind=observation").glob("year=*/part.csv")):
        for row in observations.read_partitions(path.parent):
            variable = derive.INPUTS.get(row["attribute_id"])
            if variable:
                found[variable] = row["source_release_id"]
        if len(found) >= len(derive.INPUTS):
            break
    return found


def collect(store, years):
    """Accumulate every dated value in the window, one year partition at a time."""
    totals, geometry, runs = {}, None, set()
    for year in years:
        rows = observations.read_partitions(store / "time_kind=observation" / f"year={year}")
        regional = [r for r in rows if r["geometry_version"].startswith("reg-")]
        derive.accumulate(regional, totals)
        for row in regional[:1]:
            geometry = row["geometry_version"]
        runs.update(r["run_id"] for r in regional)
    return totals, geometry, runs


def build(store=STORE, years=DEFAULT_YEARS):
    batch, _ = latest_run()
    units = units_by_family(batch)
    span = list(range(years[0], years[1] + 1))
    identifier = f"regional-substitutes-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}Z"
    recipe = f"derive_climatology@{sha256(ROOT / 'ATLAS_MODULES/hydrosheds/functions/derive_climatology.py')[:12]}"
    started, at = time.perf_counter(), utc_now()

    totals, geometry, runs = collect(store, span)
    per_basin = derive.normals(totals)
    source_ids = releases(store)

    basins, columns = set(), set()
    rows, produced, empty = [], 0, 0
    grouped = {}
    for (basin, variable), monthly in per_basin.items():
        grouped.setdefault(basin, {})[variable] = monthly
    for basin, basin_normals in grouped.items():
        basins.add(basin)
        for column, (value, valid, expected) in derive.derive(basin_normals).items():
            family = family_of(column)
            columns.add(column)
            produced += value is not None
            empty += value is None
            month = int(column[-2:]) if column[-2:].isdigit() else None
            rows.append(observations.build(
                basin_id=basin, geometry_version=geometry, basin_level=BASIN_LEVEL,
                attribute_id=BASE + column, recipe_version=recipe, mode="annual_extension",
                spatial_support="s", time_kind="climatology",
                temporal_statistic="monthly_climatological_mean" if month
                                   else "annual_climatological_figure",
                valid_start=f"{span[0]:04d}-01-01", valid_end=f"{span[-1] + 1:04d}-01-01",
                month=month, value=value, unit=units.get(family, "unknown"),
                valid_count=valid, expected_count=expected,
                coverage_fraction=valid / expected if expected else None,
                quality_flag="derived_from_dated_observations",
                missing_reason=None if value is not None else "incomplete_dated_input_series",
                source_release_id=source_ids.get(
                    {"aet": "aet", "pet": "pet", "swc": "soil", "pre": "pre",
                     "cmi": "pre", "ari": "pre", "snw": "snw", "run": "run"}.get(family, "aet"),
                    "derived@unpinned"),
                run_id=identifier, retrieved_at=at, recorded_at=at))

    added, touched = observations.append_partitioned(store, rows)
    summary = {
        "run_id": identifier, "recipe_version": recipe, "generated_at": at,
        "period": [f"{span[0]:04d}-01-01", f"{span[-1] + 1:04d}-01-01"],
        "basins": len(basins), "columns": len(columns), "rows": len(rows), "new_rows": added,
        "values": produced, "without_value": empty,
        "derived_from_runs": sorted(runs), "partitions_touched": [str(p) for p in touched],
        "wall_seconds": time.perf_counter() - started,
        "meaning": "Independent open-data estimates over a stated period, published beside the "
                   "original HydroATLAS values and never in place of them. Agreement with a "
                   "published attribute would not make one a reproduction of the other.",
    }
    write_json(SUMMARY, summary)
    observations.merge_table(store / "run.csv", [{
        "run_id": identifier, "started_at": at, "finished_at": utc_now(),
        "wall_seconds": summary["wall_seconds"], "status": "complete",
        "scientific_release": "not_eligible"}], "run_id")
    observations.merge_table(store / "recipe.csv", [
        {"recipe_version": recipe, "mode": "annual_extension"}], "recipe_version")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", default=f"{DEFAULT_YEARS[0]}-{DEFAULT_YEARS[1]}")
    first, _, last = parser.parse_args().years.partition("-")
    summary = build(years=(int(first), int(last or first)))
    print(json.dumps({k: v for k, v in summary.items() if k != "partitions_touched"},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
