"""Re-derive the TerraClimate substitutes from the producer's v1.1 release.

python PIPELINES/derive_v11_substitutes.py [--years 2003-2025] [--dry-run]

Why. The independent estimates for precipitation, actual and potential
evapotranspiration, soil water, the moisture index and aridity were derived from
TerraClimate v1.0 as Earth Engine hosts it. The monthly record, catchment statistics,
drought study and reports moved to v1.1 on 2026-09-28 (rebase_terraclimate_v11.py),
and v1.1 is drier: recomputed normals differ by -9.6% for annual precipitation (median
basin). The two tabs then disagreed for the same basin and years
(qa/deep_dive/other_tabs/check_estimate_versions.py).

What. The same recipe as derive_regional_substitutes.py - calendar-month means, annual
totals, Willmott-Feddema moisture index - applied to the v1.1 monthly values already
published under climate-continuation/terraclimate-v1.1-history, for whole years only.
The rows go into the observation store as a new, complete run under the v1.1 release,
so publication takes them over the v1.0 rows by the store's ranking, while the v1.0
rows stay on record. Run accumulate_upstream_annuals.py and build_basin_api.py after.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.runtime import sha256, utc_now, write_json
from ATLAS_MODULES.hydrosheds.functions import derive_climatology as derive
from PIPELINES.derive_regional_substitutes import BASE, family_of, units_by_family
from PIPELINES.stage_pilot_observations import BASIN_LEVEL, STORE, latest_run
from PIPELINES.update_published_record import EXPECTED_GEOMETRY

SOURCE = ROOT / "PUBLISHED/data/atlas/climate-continuation/terraclimate-v1.1-history"
RELEASE = "terraclimate-v1.1@climatologylab"
SUPERSEDES = "terraclimate@IDAHO_EPSCOR/TERRACLIMATE"
# Producer variable -> the dated attribute the recipe reads.
VARIABLES = {"ppt": "uzgeodata.dated.v1.pre_mm_s", "aet": "uzgeodata.dated.v1.aet_mm_s",
             "pet": "uzgeodata.dated.v1.pet_mm_s", "soil": "uzgeodata.dated.v1.soil_mm_s"}
# The column families TerraClimate stands behind. Temperature is left to its own
# two-source derivation; snow and runoff come from other products.
FAMILIES = ("aet", "pet", "swc", "pre", "cmi", "ari")
SUMMARY = STORE / "regional-substitutes-v1.1-summary.json"


def dated_rows(years):
    pattern = [str(SOURCE / f"year={year}.parquet") for year in range(years[0], years[1] + 1)]
    missing = [p for p in pattern if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(f"v1.1 history is missing {missing[:3]}")
    connection = duckdb.connect()
    data = connection.execute(f"""
        SELECT basin_id, variable, month, value FROM read_parquet({pattern})
        WHERE variable IN ({', '.join('?' for _ in VARIABLES)})""", list(VARIABLES)).fetchall()
    connection.close()
    for basin, variable, month, value in data:
        yield {"basin_id": str(basin), "attribute_id": VARIABLES[variable], "month": int(month),
               "value": None if value is None else float(value)}


def record_in_store(years=(2003, 2025), at=None):
    """The store's own bookkeeping for this run: the source release it cites, and the
    whole-store counts in its manifest. Without them the store holds rows that point at
    an unregistered release, and a manifest that undercounts what it holds."""
    at = at or utc_now()
    observations.merge_table(STORE / "source_release.csv", [{
        "source_release_id": RELEASE, "name": "TerraClimate v1.1 (Climatology Lab producer release)",
        "asset": "https://climate.northwestknowledge.net/TERRACLIMATE/ yearly NetCDF, reduced in "
                 "PUBLISHED/data/atlas/climate-continuation/terraclimate-v1.1-history",
        "sha256": "", "epoch": "", "valid_start": f"{years[0]:04d}-01-01", "valid_end": f"{years[1] + 1:04d}-01-01",
        "retrieved_at": at, "pinned": False}], "source_release_id")
    path = STORE / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    totals = observations.summarise(STORE)
    manifest.update({
        "rows": totals["rows"], "current_rows": totals["current_rows"], "by_mode": totals["by_mode"],
        "by_time_kind": {kind: totals["by_time_kind"].get(kind, 0) for kind in observations.TIME_KINDS},
        "dated_observations": totals["dated_observations"], "attribute_count": len(totals["attributes"]),
        "dated_attributes": [a for a in totals["attributes"] if a.startswith("uzgeodata.dated.")],
        "missing_values": totals["missing_values"], "counts_refreshed_at": at,
    })
    write_json(path, manifest)
    return {"rows": totals["rows"]}


def build(years=(2003, 2025), dry_run=False):
    batch, _ = latest_run()
    units = units_by_family(batch)
    method = sha256(ROOT / "ATLAS_MODULES/hydrosheds/functions/derive_climatology.py")[:12]
    recipe = f"derive_climatology@{method}/{years[0]}-{years[1]}/v1.1"
    identifier = f"regional-substitutes-v11-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}Z"
    started, at = time.perf_counter(), utc_now()

    totals = derive.accumulate(dated_rows(years))
    grouped = {}
    for (basin, variable), monthly in derive.normals(totals).items():
        grouped.setdefault(basin, {})[variable] = monthly

    rows, produced, empty = [], 0, 0
    for basin, basin_normals in grouped.items():
        for column, (value, valid, expected) in derive.derive(basin_normals).items():
            if family_of(column) not in FAMILIES:
                continue
            produced += value is not None
            empty += value is None
            month = int(column[-2:]) if column[-2:].isdigit() else None
            rows.append(observations.build(
                basin_id=basin, geometry_version=EXPECTED_GEOMETRY, basin_level=BASIN_LEVEL,
                attribute_id=BASE + column, recipe_version=recipe, mode="annual_extension",
                spatial_support="s", time_kind="climatology",
                temporal_statistic="monthly_climatological_mean" if month else "annual_climatological_figure",
                valid_start=f"{years[0]:04d}-01-01", valid_end=f"{years[1] + 1:04d}-01-01",
                month=month, value=value, unit=units.get(family_of(column), "unknown"),
                valid_count=valid, expected_count=expected,
                coverage_fraction=valid / expected if expected else None,
                quality_flag="derived_from_dated_observations",
                missing_reason=None if value is not None else "incomplete_dated_input_series",
                source_release_id=RELEASE, run_id=identifier, retrieved_at=at, recorded_at=at))
    summary = {"run_id": identifier, "recipe_version": recipe, "source_release": RELEASE,
               "supersedes_release": SUPERSEDES, "period": [f"{years[0]:04d}-01-01", f"{years[1] + 1:04d}-01-01"],
               "basins": len(grouped), "columns": len({r["attribute_id"] for r in rows}), "rows": len(rows),
               "values": produced, "without_value": empty}
    if dry_run:
        return {"dry_run": True, **summary}
    added, _ = observations.append_partitioned(STORE, observations.as_revisions(STORE, rows))
    summary.update({"new_rows": added, "generated_at": at, "wall_seconds": time.perf_counter() - started,
                    "meaning": "Independent open-data estimates from TerraClimate v1.1, the release the "
                               "monthly record uses; they replace the v1.0-derived estimates in publication."})
    write_json(SUMMARY, summary)
    observations.merge_table(STORE / "run.csv", [{
        "run_id": identifier, "started_at": at, "finished_at": utc_now(),
        "wall_seconds": summary["wall_seconds"], "status": "complete",
        "scientific_release": "not_eligible"}], "run_id")
    observations.merge_table(STORE / "recipe.csv", [{"recipe_version": recipe, "mode": "annual_extension"}],
                             "recipe_version")
    summary["store"] = record_in_store(years, at)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", default="2003-2025")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--record-only", action="store_true",
                        help="register the release and refresh the manifest counts without re-deriving")
    arguments = parser.parse_args()
    first, _, last = arguments.years.partition("-")
    years = (int(first), int(last or first))
    print(json.dumps(record_in_store(years) if arguments.record_only else build(years, arguments.dry_run), indent=2))


if __name__ == "__main__":
    main()
