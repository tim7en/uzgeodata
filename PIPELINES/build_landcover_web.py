"""Project basin land-cover measurements into compact browser JSON.

The measurement CSV is the system of record. This projection keeps its ontology
identity and provenance in a small index, then pivots rows by basin and year so
the map can recolour thousands of polygons without scanning a CSV in-browser.
It is safe to run while the resumable Earth Engine job is appending: only
complete CSV records are accepted and both JSON outputs are replaced atomically.

    python PIPELINES/build_landcover_web.py
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "PUBLISHED/data/ontology/2_LAND/2.3_LANDCOVER_BASIN_YEAR"
          / "landcover-basin-year.csv")
REFERENCE = ROOT / "PUBLISHED/data/review/basinatlas/basinatlas_uz_lev12.geojson"
OUTPUT = ROOT / "PUBLISHED/data/landcover"
INDEX = OUTPUT / "index.json"
SERIES = OUTPUT / "basin-series.json"

CLASSES = [
    {"code": 1, "name": "Water", "color": "#3b82f6"},
    {"code": 2, "name": "Trees", "color": "#22c55e"},
    {"code": 4, "name": "Flooded vegetation", "color": "#2dd4bf"},
    {"code": 5, "name": "Crops", "color": "#f4d35e"},
    {"code": 7, "name": "Built area", "color": "#ff6b5d"},
    {"code": 8, "name": "Bare ground", "color": "#d6a76c"},
    {"code": 9, "name": "Snow / ice", "color": "#e6f5ff"},
    {"code": 10, "name": "Clouds", "color": "#cbd5e1"},
    {"code": 11, "name": "Rangeland", "color": "#a3c95b"},
]
CLASS_CODES = {item["code"] for item in CLASSES}
YEARS = list(range(2017, 2026))


def write_json(path: Path, payload: dict, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False,
                  separators=(",", ":") if compact else None,
                  indent=None if compact else 2)
        handle.write("\n")
    temporary.replace(path)


def reference_basins() -> tuple[dict[str, dict], int]:
    document = json.loads(REFERENCE.read_text(encoding="utf8"))
    basins = {}
    for feature in document["features"]:
        props = feature["properties"]
        basin_id = str(props["HYBAS_ID"])
        basins[basin_id] = {
            "pfaf": str(props.get("PFAF_ID") or ""),
            "areaKm2": props.get("SUB_AREA"),
            "uzbekistanKm2": props.get("UZ_AREA_KM2"),
        }
    return basins, len(document["features"])


def build() -> tuple[dict, dict]:
    if not SOURCE.exists():
        raise SystemExit(f"Land-cover basin table not found: {SOURCE.relative_to(ROOT)}")

    reference, reference_count = reference_basins()
    values: dict[str, dict[int, dict[int, float]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    totals: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    source_rows = 0

    with SOURCE.open(encoding="utf8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                basin = str(row["basin_id"])
                year = int(row["year"])
                code = int(row["class_code"])
                area = float(row["km2"])
            except (KeyError, TypeError, ValueError):
                continue
            if basin not in reference or code not in CLASS_CODES or year not in YEARS:
                continue
            values[basin][year][code] = area
            totals[year][code] += area
            source_rows += 1

    years = YEARS
    by_year = {
        str(year): len([1 for annual in values.values() if year in annual])
        for year in years
    }
    measured_basin_years = sum(len(annual) for annual in values.values())
    expected_basin_years = reference_count * len(years)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    series = {
        "version": "1.0",
        "generatedAt": generated_at,
        "basins": {
            basin: {
                "pfaf": reference[basin]["pfaf"],
                "areaKm2": reference[basin]["areaKm2"],
                "uzbekistanKm2": reference[basin]["uzbekistanKm2"],
                "years": {
                    str(year): {str(code): round(area, 4)
                                for code, area in sorted(classes.items())}
                    for year, classes in sorted(annual.items())
                },
            }
            for basin, annual in sorted(values.items())
        },
    }
    index = {
        "version": "1.0",
        "generatedAt": generated_at,
        "title": "Basin land-cover observatory",
        "description": ("Annual Impact Observatory / Esri land-cover area reduced over the "
                        "whole canonical BasinATLAS level-12 catchments that intersect "
                        "Uzbekistan."),
        "source": {
            "platform": "Google Earth Engine",
            "asset": "projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS",
            "nativeResolutionMetres": 10,
            "reductionScaleMetres": 30,
            "licence": "CC-BY-4.0",
        },
        "ontology": {
            "subject": "uz:ds/esri-io-landcover-10m",
            "predicate": "uz:hasBasinStatistic",
            "objectType": "Basin",
            "identifierScheme": "HYBAS_ID",
            "distribution": "uz:dist/landcover-basin-year",
        },
        "reference": {
            "dataset": "BasinATLAS v1.0 Uzbekistan extraction",
            "layer": "basinatlas_uz_lev12",
            "basins": reference_count,
            "geometry": "/data/hydrography/basins.geojson",
            "boundary": "/data/hydrography/boundary.geojson",
            "scope": "Whole level-12 catchments intersecting Uzbekistan",
        },
        "years": years,
        "classes": CLASSES,
        "coverage": {
            "sourceRows": source_rows,
            "measuredBasins": len(values),
            "measuredBasinYears": measured_basin_years,
            "expectedBasinYears": expected_basin_years,
            "percent": (round(measured_basin_years / expected_basin_years * 100, 2)
                        if expected_basin_years else 0),
            "byYear": by_year,
            "complete": bool(expected_basin_years and measured_basin_years == expected_basin_years),
        },
        "totalsKm2": {
            str(year): {str(code): round(area, 2) for code, area in sorted(classes.items())}
            for year, classes in sorted(totals.items())
        },
        "series": "/data/landcover/basin-series.json",
    }
    return index, series


def main() -> None:
    index, series = build()
    write_json(INDEX, index)
    write_json(SERIES, series, compact=True)
    coverage = index["coverage"]
    print(f"{coverage['sourceRows']:,} rows · {coverage['measuredBasins']:,} basins · "
          f"{coverage['percent']:.2f}% basin-years")
    print(f"  -> {INDEX.relative_to(ROOT)}")
    print(f"  -> {SERIES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
