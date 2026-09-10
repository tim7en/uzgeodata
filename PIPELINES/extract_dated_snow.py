"""Extract dated monthly snow cover for the pilot basins and store it as observations.

python PIPELINES/extract_dated_snow.py [--years 2003-2022]

The first dated family in the atlas. Until now the store held static values, source
epochs and climatologies; this writes real observations, with the year and month
they were measured in and the period they cover.

It is a new variable, not a new vintage of an existing one. `snw_pc_s01` is defined
as a January climatology and keeps that meaning; a January 2003 measurement is
recorded under its own attribute id, so nothing claims equivalence because the
numbers look alike. The climatology and the dated series share a definition, mask
and analysis grid, which is what makes comparing them meaningful rather than a
coincidence — the comparison is reported, never used to adjust a value.

Every value carries its own QA denominators. A month in which no cloud-free day was
observed in a basin is stored as a null with that reason, not as zero snow.
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
from ATLAS_MODULES.hydrosheds.functions import dated_snow
from PIPELINES.stage_pilot_observations import PUBLISHED, STORE, BASIN_LEVEL, latest_run

ATTRIBUTE = "uzgeodata.dated.v1.snw_pc_s"
UNIT = "percent of cloud-free days with snow cover"
SOURCE_RELEASE = "modis_myd10a1@061"
CLIMATOLOGY_COLUMNS = {month: f"snw_pc_s{month:02d}" for month in dated_snow.MONTHS}
DEFAULT_YEARS = (2003, 2022)
PROJECT = "ee-sabitovty"


def run_id(now=None):
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%f")
    return f"pskem-datedsnow-{stamp}Z"


def month_period(year, month):
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year + 1:04d}-01-01" if month == 12 else f"{year:04d}-{month + 1:02d}-01"
    return start, end


def observation_rows(rows, geometry_version, recipe, identifier, recorded_at, retrieved_at):
    """Every extracted number, through the contract, with nothing filled in for it."""
    built = []
    for row in rows:
        start, end = month_period(row["year"], row["month"])
        has_value = row["value"] is not None
        built.append(observations.build(
            basin_id=row["hybas_id"], geometry_version=geometry_version, basin_level=BASIN_LEVEL,
            attribute_id=ATTRIBUTE, recipe_version=recipe, mode="annual_extension",
            spatial_support="s", time_kind="observation", temporal_statistic="monthly_mean",
            valid_start=start, valid_end=end, year=row["year"], month=row["month"],
            # A null month keeps its unit: the unit describes the series, not whether
            # this particular month happened to be observed.
            value=row["value"], unit=UNIT,
            coverage_fraction=row["valid_count"] / row["expected_count"] if row["expected_count"] else None,
            valid_count=row["valid_count"], expected_count=row["expected_count"],
            quality_flag="open_surrogate_dated_observation",
            missing_reason=None if has_value else "no_cloud_free_observation_in_month",
            source_release_id=SOURCE_RELEASE, run_id=identifier,
            retrieved_at=retrieved_at, recorded_at=recorded_at))
    return built


def compare_to_climatology(rows, batch, years):
    """Report how the dated series sits against the published climatology.

    A pooled daily climatology and a mean of monthly means are not the same average,
    so a small difference is expected even over the full window. Over a shorter span
    the difference is mostly the missing years and says little. This is a sanity
    report on the definition matching, never a calibration: no dated value is
    adjusted by it, and `years_averaged` says how much weight it can carry.
    """
    attributes = {a["column"]: a for a in batch["attributes"]}
    totals, differences = {}, []
    for row in rows:
        if row["value"] is not None:
            totals.setdefault((row["hybas_id"], row["month"]), []).append(row["value"])
    for (basin_id, month), values in totals.items():
        published = (attributes[CLIMATOLOGY_COLUMNS[month]]["surrogate_values"] or {}).get(basin_id)
        if published and published.get("raw_value") is not None:
            differences.append(abs(sum(values) / len(values) - published["raw_value"]))
    if not differences:
        return {"compared": 0}
    return {"compared": len(differences), "years_averaged": years,
            "max_absolute_difference_percentage_points": max(differences),
            "mean_absolute_difference_percentage_points": sum(differences) / len(differences),
            "meaning": "Mean of dated monthly means against the pooled daily climatology for the "
                       "same calendar month. Reported only; no dated value is adjusted by it."}


def extract(years=DEFAULT_YEARS, store=STORE, published=PUBLISHED, project=PROJECT):
    import ee
    ee.Initialize(project=project)
    batch, lock = latest_run(published)
    transform = lock["surrogate_grid"]["transform"]
    geometry = json.loads((published / "runs" / batch["run_id"] / "pilot-basins.geojson")
                          .read_text(encoding="utf-8"))
    identifier, started = run_id(), time.perf_counter()
    recipe = f"dated_snow@{sha256(ROOT / 'ATLAS_MODULES/hydrosheds/functions/dated_snow.py')[:12]}"

    span = list(range(years[0], years[1] + 1))
    extracted, provenance = dated_snow.extract(geometry["features"], transform, span, log=print)
    retrieved_at = utc_now()
    elapsed = time.perf_counter() - started

    rows = observation_rows(extracted, lock["selected_geometry_sha256"][:16], recipe,
                            identifier, retrieved_at, retrieved_at)
    existing = observations.read_partitions(store)
    stored = observations.append(existing, rows)
    observations.write_partitions(store, stored)

    observations.merge_table(store / "run.csv", [{
        "run_id": identifier, "started_at": retrieved_at, "finished_at": utc_now(),
        "wall_seconds": elapsed, "status": "complete", "scientific_release": "not_eligible"}], "run_id")
    observations.merge_table(store / "recipe.csv", [
        {"recipe_version": recipe, "mode": "annual_extension"}], "recipe_version")
    observations.merge_table(store / "source_release.csv", [{
        "source_release_id": SOURCE_RELEASE, "name": "MODIS MYD10A1 daily snow cover, collection 061",
        "asset": dated_snow.ASSET, "sha256": "", "epoch": "",
        "valid_start": f"{span[0]:04d}-01-01", "valid_end": f"{span[-1] + 1:04d}-01-01",
        "retrieved_at": retrieved_at, "pinned": False}], "source_release_id")

    dated = [r for r in observations.latest(stored) if r["time_kind"] == "observation"]
    summary = {
        "run_id": identifier, "attribute_id": ATTRIBUTE, "asset": dated_snow.ASSET,
        "years": [span[0], span[-1]], "basins": len({r["hybas_id"] for r in extracted}),
        "extracted_rows": len(extracted), "new_rows": len(stored) - len(existing),
        "dated_rows_in_store": len(dated),
        "missing_months": sum(1 for r in extracted if r["value"] is None),
        "wall_seconds": elapsed,
        "definition": {"snow_flag": f"{dated_snow.BAND} >= {dated_snow.SNOW_THRESHOLD}",
                       "masking": f"values above {dated_snow.VALID_MAX} excluded, not gap filled",
                       "reduction": "mean of cloud-free daily snow flags within the calendar month",
                       "grid": transform, "cell_arcsec": lock["surrogate_grid"]["cell_arcsec"]},
        "source_images": provenance,
        "climatology_comparison": compare_to_climatology(extracted, batch, len(span)),
        "release_note": "Server-side reduction returns no local artefact to hash; the collection "
                        "version and the per-month source image counts are the release fingerprint.",
    }
    write_json(store / "dated-snow-manifest.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", default=f"{DEFAULT_YEARS[0]}-{DEFAULT_YEARS[1]}",
                        help="inclusive year range, e.g. 2003-2022")
    first, _, last = parser.parse_args().years.partition("-")
    summary = extract((int(first), int(last or first)))
    print(json.dumps({k: v for k, v in summary.items() if k != "source_images"},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
