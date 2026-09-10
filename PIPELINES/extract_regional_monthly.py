"""Run a dated monthly source across all 7,445 level-12 basins.

python PIPELINES/extract_regional_monthly.py terraclimate [--years 2003-2022]

The snow runner proved the shape of a regional dated extraction; this generalises it
to the sources that already publish monthly imagery. The batching, checkpointing,
retry and ledger machinery is the snow runner's, unchanged — a second copy of that
logic would be a second thing to get wrong.

What differs is that one pass carries several variables. Reducing over basin
geometry costs about the same for six bands as for one, measured at 14.1 s against
15.8 s on a 250-basin sample, so every band of a source travels together and each
becomes its own dated attribute.

Scale factors and units come from the reviewed climatology builders, and are checked
against the published climatology over its own window before a regional run.
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
from ATLAS_MODULES.hydrosheds.functions import dated_monthly
from PIPELINES.extract_dated_snow import PROJECT, month_period
from PIPELINES.extract_regional_snow import (
    RETRIES, batches, geometry_version, is_complete, load_frame, regional_grid,
    summarise_year, support_summary, with_retries)
from PIPELINES.stage_pilot_observations import BASIN_LEVEL, STORE

CHECKPOINTS = ROOT / "WORKSPACE/atlas_runs/regional_monthly"
DEFAULT_YEARS = (2003, 2022)


def ledger_path(source):
    return STORE / f"regional-{source}-ledger.json"


def release_id(source):
    """The collection is the release; a server-side reduction leaves no bytes to hash."""
    return f"{source}@{dated_monthly.SOURCES[source]['asset']}"


def observation_rows(source, rows, geometry, recipe, run_id, at):
    """Every extracted number, through the contract, with nothing filled in for it."""
    spec = dated_monthly.SOURCES[source]["bands"]
    built = []
    for row in rows:
        band = spec[row["band"]]
        start, end = month_period(row["year"], row["month"])
        built.append(observations.build(
            basin_id=row["hybas_id"], geometry_version=geometry, basin_level=BASIN_LEVEL,
            attribute_id=band["attribute"], recipe_version=recipe, mode="annual_extension",
            spatial_support="s", time_kind="observation", temporal_statistic="monthly_mean",
            valid_start=start, valid_end=end, year=row["year"], month=row["month"],
            value=row["value"], unit=band["unit"],
            coverage_fraction=row["valid_count"] / row["expected_count"] if row["expected_count"] else None,
            valid_count=row["valid_count"], expected_count=row["expected_count"],
            quality_flag="open_surrogate_dated_observation",
            missing_reason=None if row["value"] is not None else "no_value_in_source_for_month",
            source_release_id=release_id(source), run_id=run_id,
            retrieved_at=at, recorded_at=at))
    return built


def run(source, years=DEFAULT_YEARS, store=STORE, project=PROJECT, batch_size=250):
    import ee
    ee.Initialize(project=project)
    spec = dated_monthly.SOURCES[source]
    bands = list(spec["bands"])

    frame = load_frame()
    transform, version = regional_grid(frame), geometry_version(frame)
    span = list(range(years[0], years[1] + 1))
    identifier = f"regional-{source}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}Z"
    recipe = f"dated_monthly@{sha256(ROOT / 'ATLAS_MODULES/hydrosheds/functions/dated_monthly.py')[:12]}"
    started = time.perf_counter()
    checkpoints = CHECKPOINTS / source

    ledger = {"run_id": identifier, "started_at": utc_now(), "source": source,
              "asset": spec["asset"], "bands": bands,
              "attributes": [spec["bands"][b]["attribute"] for b in bands],
              "geometry_version": version, "basins": len(frame), "years": [span[0], span[-1]],
              "batch_size": batch_size,
              "expected_rows": len(frame) * len(span) * 12 * len(bands),
              "retries": [], "failures": [], "by_year": {}}
    print(f"{source}: {len(frame)} basins, {len(span)} years, {len(bands)} bands "
          f"-> {ledger['expected_rows']:,} rows", flush=True)

    plan, expected = list(batches(frame, batch_size)), {}
    for index, features in plan:
        cache = checkpoints / f"batch-{index:04d}" / "expected.json"
        if cache.exists():
            expected[index] = json.loads(cache.read_text(encoding="utf-8"))
            continue
        collection = dated_monthly.feature_collection(features)
        result, error = with_retries(
            lambda c=collection: dated_monthly.expected_cells(c, transform),
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
            path = checkpoints / f"batch-{index:04d}" / f"year-{year}.json"
            if path.exists():
                collected.extend(json.loads(path.read_text(encoding="utf-8")))
                continue
            collection = dated_monthly.feature_collection(features)
            rows, error = with_retries(
                lambda c=collection, y=year, i=index: dated_monthly.year_rows(
                    source, c, transform, y, expected[i], bands),
                f"year-{year}/batch-{index}", ledger)
            if error:
                continue
            write_json(path, rows)
            collected.extend(rows)

        observations.append_partitioned(
            store, observation_rows(source, collected, version, recipe, identifier, utc_now()))
        summary = summarise_year(collected, len(frame), time.perf_counter() - year_started)
        summary["rows_per_band"] = len(collected) // len(bands) if bands else 0
        ledger["by_year"][str(year)] = summary
        print(f"{year}: {summary['basins']}/{len(frame)} basins, {len(collected):,} rows, "
              f"{summary['seconds']:.0f}s [{time.perf_counter() - started:.0f}s total]", flush=True)

    ledger["finished_at"] = utc_now()
    ledger["wall_seconds"] = time.perf_counter() - started
    ledger["stored_rows"] = sum(y["rows"] for y in ledger["by_year"].values())
    ledger["complete"] = is_complete(ledger)
    ledger["basin_support"] = support_summary(expected)
    write_json(ledger_path(source), ledger)

    observations.merge_table(store / "run.csv", [{
        "run_id": identifier, "started_at": ledger["started_at"], "finished_at": ledger["finished_at"],
        "wall_seconds": ledger["wall_seconds"],
        "status": "complete" if ledger["complete"] else "incomplete",
        "scientific_release": "not_eligible"}], "run_id")
    observations.merge_table(store / "recipe.csv", [
        {"recipe_version": recipe, "mode": "annual_extension"}], "recipe_version")
    observations.merge_table(store / "source_release.csv", [{
        "source_release_id": release_id(source), "name": f"{source} monthly imagery",
        "asset": spec["asset"], "sha256": "", "epoch": "",
        "valid_start": f"{span[0]:04d}-01-01", "valid_end": f"{span[-1] + 1:04d}-01-01",
        "retrieved_at": ledger["finished_at"], "pinned": False}], "source_release_id")
    return ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=sorted(dated_monthly.SOURCES))
    parser.add_argument("--years", default=f"{DEFAULT_YEARS[0]}-{DEFAULT_YEARS[1]}")
    arguments = parser.parse_args()
    first, _, last = arguments.years.partition("-")
    ledger = run(arguments.source, (int(first), int(last or first)))
    print(json.dumps({k: v for k, v in ledger.items() if k != "retries"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
