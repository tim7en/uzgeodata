"""Project every already-measured basin time series into one shared browser contract.

`build_landcover_web.py` proved the pattern: one relationship table, one compact
JSON pair, one cinematic map. This is the same projection made generic, because
the graph already holds seven more basin-level tables that never needed a new
Earth Engine run — CFSv2 (climate state and anomaly), CHIRPS, CHIRTS, CPC, CAMS
and GHM are all measured, all keyed to a canonical BasinATLAS level, and all
declared in `ONTOLOGY/vocab/relationship-tables.json`. What was missing was not
data, it was a viewer.

Each entry in LAYERS names a CSV the graph already declares, the basin level it
was measured at (6, 7 or 12 — the reference geometry is read straight from the
review extraction, `PUBLISHED/data/review/basinatlas/basinatlas_uz_levNN.geojson`),
and how to fold its rows into `{basin: {period: {variable: {v, [z], [c]}}}}`.
`kind: "anomaly"` additionally carries the z-score and classification CFSv2's
anomaly table already computed, which is what lets the map colour a basin by how
far it sits from its own climatological normal rather than by raw magnitude.

    python PIPELINES/build_basin_layers_web.py
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "PUBLISHED/data/basin-layers"
INDEX = OUTPUT / "index.json"

# Source pipelines use a small controlled vocabulary for row-level quality.
# Preserve the counts for auditability, but also publish a weighted score the
# portal can encode as node health. Unknown states stay conservative rather
# than being treated as invalid.
QUALITY_WEIGHTS = {
    "ok": 1.0,
    "ok-centroid": 0.92,
    "ok-interpolated": 0.65,
    "ok-reanalysis": 0.9,
    "ok-reanalysis-centroid": 0.85,
    "ok-reanalysis-anomaly": 0.9,
    "ok-reanalysis-anomaly-centroid": 0.85,
    "review-extreme-reanalysis-anomaly": 0.5,
    "ok-satellite": 0.9,
    "limited-clear-sky": 0.5,
    "insufficient-clear-sky": 0.1,
    "implausible": 0.0,
}


def geometry_for(level: int) -> str:
    return f"/data/review/basinatlas/basinatlas_uz_lev{level:02d}.geojson"


# Friendly label and a stable colour per variable code, so switching variables
# changes hue meaningfully instead of assigning colour by draw order. Anything
# not named here still renders — falls back to a rotated palette and a
# title-cased label built from the code.
VARIABLES = {
    "precipitation": {"label": "Precipitation", "color": "#4cc9f0"},
    "precipitation_total": {"label": "Precipitation", "color": "#4cc9f0"},
    "air_temperature_mean": {"label": "Air temperature (mean)", "color": "#ff6b4a"},
    "snowfall_water_equivalent_total": {"label": "Snowfall water equivalent", "color": "#a7d8ff"},
    "snow_water_equivalent_mean": {"label": "Snow water equivalent", "color": "#e8f7ff"},
    "soil_moisture_layer_1_mean": {"label": "Soil moisture (layer 1)", "color": "#2dd4bf"},
    "modelled_runoff_total": {"label": "Modelled runoff", "color": "#1677ff"},
    "temperature_mean": {"label": "Temperature (mean)", "color": "#ff6b4a"},
    "temperature_max": {"label": "Temperature (max)", "color": "#ff3d3d"},
    "temperature_min": {"label": "Temperature (min)", "color": "#7fa8ff"},
    "tmax_mean": {"label": "Max temperature (mean)", "color": "#ff6b4a"},
    "tmax_absolute": {"label": "Max temperature (absolute)", "color": "#ff3d3d"},
    "tmin_mean": {"label": "Min temperature (mean)", "color": "#7fa8ff"},
    "tmin_absolute": {"label": "Min temperature (absolute)", "color": "#3aa0ff"},
    "soil_moisture_5cm": {"label": "Soil moisture 5 cm", "color": "#2dd4bf"},
    "soil_moisture_25cm": {"label": "Soil moisture 25 cm", "color": "#22bfae"},
    "soil_moisture_70cm": {"label": "Soil moisture 70 cm", "color": "#189c8d"},
    "soil_moisture_150cm": {"label": "Soil moisture 150 cm", "color": "#0f766e"},
    "potential_evaporation": {"label": "Potential evaporation", "color": "#f4a340"},
    "shortwave_down": {"label": "Shortwave radiation", "color": "#f4d35e"},
    "specific_humidity": {"label": "Specific humidity", "color": "#a78bfa"},
    "snow_cover_percent": {"label": "Snow cover", "color": "#e8f7ff"},
    "rh_mean": {"label": "Relative humidity", "color": "#a78bfa"},
    "vpd_mean": {"label": "Vapour pressure deficit", "color": "#c084fc"},
    "heat_index_max": {"label": "Heat index (max)", "color": "#ff5d5d"},
    "days_tmax_ge_35": {"label": "Days \u2265 35\u00b0C", "color": "#ff8a5c"},
    "days_tmax_ge_40": {"label": "Days \u2265 40\u00b0C", "color": "#ff3d3d"},
    "days_frost": {"label": "Frost days", "color": "#7fd4ff"},
    "stations_max_mean": {"label": "Stations informing max", "color": "#8aa0ad"},
    "stations_min_mean": {"label": "Stations informing min", "color": "#8aa0ad"},
    "aod_550nm": {"label": "Aerosol optical depth", "color": "#c9a06a"},
    "pm2p5": {"label": "PM2.5", "color": "#b0793f"},
    "ghm_mean": {"label": "Human modification (mean)", "color": "#e0507a"},
    "share_low": {"label": "Share: low modification", "color": "#4cc9f0"},
    "share_moderate": {"label": "Share: moderate modification", "color": "#f4a340"},
    "share_high": {"label": "Share: high modification", "color": "#e0507a"},
}
PALETTE = ["#4cc9f0", "#f4a340", "#a78bfa", "#2dd4bf", "#ff6b4a", "#e0507a"]


def variable_meta(code: str, position: int) -> dict:
    known = VARIABLES.get(code)
    if known:
        return dict(known)
    return {"label": code.replace("_", " ").title(), "color": PALETTE[position % len(PALETTE)]}


LAYERS = [
    {
        "id": "era5-land-full-basin-anomaly", "label": "ERA5-Land anomalies — Amu + Syr",
        "domain": "ATMOSPHERE", "dataset": "uz:ds/era5-land",
        "predicate": "uz:hasBasinAnomaly", "kind": "anomaly",
        "previewVariable": "precipitation_total", "previewMetric": "z_score",
        "source": "PUBLISHED/data/hydroclimate/era5-land-full-basin-anomaly.csv",
        "basinLevel": 7, "geometry": "/data/hydroclimate/basins-level07.geojson",
        "idColumn": "basin_id", "variableColumn": "variable",
        "valueColumn": "value", "unitColumn": "unit", "periodColumns": ["year", "month"],
        "periodGrain": "month", "spatialScope": "full_basin",
        "spatialUnit": "HydroATLAS level-7 subbasin", "baseline": "1991-2020",
        "what": ("Monthly ERA5-Land departures from a fixed 1991-2020 normal across every "
                 "level-7 unit in the complete Amu Darya and Syr Darya natural systems. "
                 "Formation, transit and terminal reaches resolve through the same layer."),
    },
    {
        "id": "era5-land-headwater-anomaly", "label": "ERA5-Land anomalies — headwaters",
        "domain": "ATMOSPHERE", "dataset": "uz:ds/era5-land",
        "predicate": "uz:hasBasinAnomaly", "kind": "anomaly",
        "previewVariable": "precipitation_total", "previewMetric": "z_score",
        "source": "PUBLISHED/data/hydroclimate/era5-land-headwater-anomaly.csv",
        "basinLevel": 7, "geometry": "/data/hydroclimate/headwater-units.geojson",
        "idColumn": "basin_id", "variableColumn": "variable",
        "valueColumn": "value", "unitColumn": "unit", "periodColumns": ["year", "month"],
        "periodGrain": "month", "spatialScope": "headwater_formation",
        "spatialUnit": "HydroATLAS level-7 subbasin", "baseline": "1991-2020",
        "what": ("Monthly ERA5-Land departures from a fixed 1991-2020 normal across every "
                 "level-7 subbasin upstream of the Panj-Vakhsh and Naryn-Karadarya controls."),
    },
    {
        "id": "cfsv2-basin-anomaly", "label": "CFSv2 anomalies — Uzbekistan", "domain": "ATMOSPHERE",
        "dataset": "uz:ds/cfsv2-noaa", "predicate": "uz:hasBasinAnomaly", "kind": "anomaly",
        "previewVariable": "precipitation", "previewMetric": "z_score",
        "source": "PUBLISHED/data/ontology/1_ATMOSPHERE/1.4_CFSV2_BASIN_ANOMALY/cfsv2-basin-anomaly.csv",
        "spatialScope": "national_intersection", "legacyScope": True,
        "basinLevel": 7, "idColumn": "basin_id", "variableColumn": "variable",
        "valueColumn": "value", "unitColumn": "unit", "periodColumns": ["year", "month"],
        "periodGrain": "month",
        "what": ("Observations expressed as z-scores against each basin's own climatological "
                 "normal \u2014 how far this month sits from what that basin usually sees, not "
                 "what the number is in absolute terms."),
    },
    {
        "id": "cfsv2-basin-monthly", "label": "CFSv2 monthly state — Uzbekistan", "domain": "ATMOSPHERE",
        "dataset": "uz:ds/cfsv2-noaa", "predicate": "uz:hasBasinStatistic", "kind": "value",
        "previewVariable": "precipitation",
        "source": "PUBLISHED/data/ontology/1_ATMOSPHERE/1.6_CFSV2_BASIN_MONTHLY/cfsv2-basin-monthly.csv",
        "spatialScope": "national_intersection", "legacyScope": True,
        "basinLevel": 7, "idColumn": "basin_id", "variableColumn": "variable",
        "valueColumn": "value", "unitColumn": "unit", "periodColumns": ["year", "month"],
        "periodGrain": "month",
        "what": "Monthly mean of the 6-hourly CFSv2 field: precipitation, temperature, four "
                "soil-moisture depths, evaporative demand, radiation and humidity.",
    },
    {
        "id": "chirps-v3-basin-pentad", "label": "CHIRPS pentad rainfall — Uzbekistan", "domain": "ATMOSPHERE",
        "dataset": "uz:ds/chirps-v3", "predicate": "uz:hasBasinStatistic", "kind": "value",
        "previewVariable": "precipitation_total",
        "source": "PUBLISHED/data/ontology/1_ATMOSPHERE/1.7_CHIRPS_V3_BASIN_PENTAD/chirps-v3-basin-pentad.csv",
        "spatialScope": "national_intersection", "legacyScope": True,
        "basinLevel": 12, "idColumn": "basin_id", "variableColumn": "variable",
        "valueColumn": "value", "unitColumn": "unit", "periodColumns": ["year", "month", "pentad"],
        "periodGrain": "pentad",
        "what": "Accumulated rainfall per level-12 basin per pentad at 5.6 km \u2014 six "
                "measurements a month.",
    },
    {
        "id": "chirts-basin-monthly", "label": "Temperature & humidity (CHIRTS)", "domain": "ATMOSPHERE",
        "dataset": "uz:ds/chirts", "predicate": "uz:hasBasinStatistic", "kind": "value",
        "previewVariable": "tmax_mean",
        "source": "PUBLISHED/data/ontology/1_ATMOSPHERE/1.8_CHIRTS_BASIN_MONTHLY/chirts-basin-monthly.csv",
        "spatialScope": "national_intersection", "legacyScope": True,
        "basinLevel": 12, "idColumn": "basin_id", "variableColumn": "variable",
        "valueColumn": "value", "unitColumn": "unit", "periodColumns": ["year", "month"],
        "periodGrain": "month",
        "what": "Station-blended temperature and humidity at 5.6 km, 1983\u20132016, including "
                "day counts above 35\u00b0 and 40\u00b0C a monthly mean cannot give.",
    },
    {
        "id": "cpc-basin-monthly", "label": "Temperature (CPC)", "domain": "ATMOSPHERE",
        "dataset": "uz:ds/cpc-temperature", "predicate": "uz:hasBasinStatistic", "kind": "value",
        "previewVariable": "tmax_mean",
        "source": "PUBLISHED/data/ontology/1_ATMOSPHERE/1.9_CPC_BASIN_MONTHLY/cpc-basin-monthly.csv",
        "spatialScope": "national_intersection", "legacyScope": True,
        "basinLevel": 6, "idColumn": "basin_id", "variableColumn": "variable",
        "valueColumn": "value", "unitColumn": "unit", "periodColumns": ["year", "month"],
        "periodGrain": "month",
        "what": "Gauge-based half-degree temperature, 1979\u2013present, with the station count "
                "that informed each cell.",
    },
    {
        "id": "cams-basin-monthly", "label": "Air quality (CAMS)", "domain": "ATMOSPHERE",
        "dataset": "uz:ds/cams-nrt", "predicate": "uz:hasBasinStatistic", "kind": "value",
        "previewVariable": "pm2p5",
        "source": "PUBLISHED/data/ontology/1_ATMOSPHERE/1.1_CAMS_BASIN_MONTHLY/cams-basin-monthly.csv",
        "spatialScope": "national_intersection", "legacyScope": True,
        "basinLevel": 6, "idColumn": "basin_id", "variableColumn": "variable",
        "valueColumn": "value", "unitColumn": "unit", "periodColumns": ["year", "month"],
        "periodGrain": "month",
        "what": "Monthly mean of the CAMS +0h analysis: aerosol optical depth and PM2.5, the "
                "assimilated estimate of what the atmosphere was, not a forecast.",
    },
    {
        "id": "era5-land-full-basins-monthly", "label": "ERA5-Land monthly state — Amu + Syr",
        "domain": "ATMOSPHERE", "dataset": "uz:ds/era5-land",
        "predicate": "uz:hasBasinStatistic", "kind": "value",
        "previewVariable": "precipitation_total",
        "source": "PUBLISHED/data/hydroclimate/era5-land-full-basins-monthly.csv",
        "spatialScope": "full_basin", "spatialUnit": "HydroATLAS level-7 subbasin",
        "basinLevel": 7, "geometry": "/data/hydroclimate/basins-level07.geojson",
        "idColumn": "basin_id", "variableColumn": "variable",
        "valueColumn": "value", "unitColumn": "unit", "periodColumns": ["year", "month"],
        "periodGrain": "month",
        "what": ("Monthly temperature, precipitation, snowfall, snow water equivalent, soil "
                 "moisture and modelled runoff for every level-7 unit in both complete river "
                 "systems. ERA5-Land runoff is modelled and is not gauge discharge."),
    },
    {
        "id": "era5-land-headwaters-monthly", "label": "ERA5-Land monthly state — headwaters",
        "domain": "ATMOSPHERE", "dataset": "uz:ds/era5-land",
        "predicate": "uz:hasBasinStatistic", "kind": "value",
        "previewVariable": "precipitation_total",
        "source": "PUBLISHED/data/hydroclimate/era5-land-headwaters-monthly.csv",
        "spatialScope": "headwater_formation", "spatialUnit": "HydroATLAS level-7 subbasin",
        "basinLevel": 7, "geometry": "/data/hydroclimate/headwater-units.geojson",
        "idColumn": "basin_id", "variableColumn": "variable",
        "valueColumn": "value", "unitColumn": "unit", "periodColumns": ["year", "month"],
        "periodGrain": "month",
        "what": ("Monthly temperature, precipitation, snowfall, snow water equivalent, soil "
                 "moisture and modelled runoff across the transboundary Upper Amu and Upper Syr "
                 "formation zones. ERA5-Land is reanalysis; runoff here is not gauge discharge."),
    },
    {
        "id": "modis-snow-headwater-daily", "label": "MODIS daily snow — headwaters",
        "domain": "ATMOSPHERE", "dataset": "uz:ds/modis-terra-snow",
        "predicate": "uz:hasFormationStatistic", "kind": "value",
        "previewVariable": "snow_cover_percent",
        "source": "PUBLISHED/data/hydroclimate/modis-snow-headwater-systems-daily.csv",
        "basinLevel": 10, "geometry": "/data/hydroclimate/headwater-systems.geojson",
        "geometryIdColumn": "system_id",
        "idColumn": "system_id", "variableColumn": "variable",
        "valueColumn": "value", "unitColumn": "unit", "periodColumns": ["year", "month", "day"],
        "periodGrain": "day", "spatialScope": "headwater_formation",
        "spatialUnit": "headwater formation system",
        "what": ("Daily MODIS Terra snow cover for the Upper Amu and Upper Syr formation zones, "
                 "aggregated from elevation bands using valid-observation area."),
    },
    {
        "id": "ghm-basin-modification", "label": "Human modification", "domain": "LAND",
        "dataset": "uz:ds/csp-ghm", "predicate": "uz:hasBasinStatistic", "kind": "value",
        "previewVariable": "ghm_mean",
        "source": "PUBLISHED/data/ontology/2_LAND/2.1_GHM_UNIT_MODIFICATION/ghm-unit-modification.csv",
        "spatialScope": "national_intersection", "legacyScope": True,
        "basinLevel": 12, "idColumn": "unit_id", "variableColumn": "variable",
        "valueColumn": "value", "unitColumn": "unit", "periodColumns": ["epoch"],
        "periodGrain": "year", "filterColumn": "frame", "filterValue": "basin",
        "what": "Cumulative human modification for 2016 \u2014 settlement, agriculture, "
                "transport, mining and energy \u2014 as a 0 to 1 index at 1 km. One image, no "
                "timestamp: the single period is the whole record.",
    },
]


def period_key(row: dict, layer: dict) -> str:
    parts = [int(row[column]) for column in layer["periodColumns"]]
    if layer["periodGrain"] == "pentad":
        year, month, pentad = parts
        return f"{year:04d}-{month:02d}-p{pentad}"
    if layer["periodGrain"] == "month":
        year, month = parts
        return f"{year:04d}-{month:02d}"
    if layer["periodGrain"] == "day":
        year, month, day = parts
        return f"{year:04d}-{month:02d}-{day:02d}"
    return str(parts[0])


def write_json(path: Path, payload: dict, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False,
                  separators=(",", ":") if compact else None,
                  indent=None if compact else 2)
        handle.write("\n")
    temporary.replace(path)


def sample_preview(points: list[dict], limit: int = 48) -> list[dict]:
    """Keep a small, representative sparkline payload in the layer index."""
    if len(points) <= limit:
        return points
    positions = {round(index * (len(points) - 1) / (limit - 1)) for index in range(limit)}
    return [point for index, point in enumerate(points) if index in positions]


def build_layer(layer: dict) -> tuple[dict, dict]:
    # Absolute already (a test handing in a tmp_path) passes through; the
    # registry's own entries are repo-relative and resolve against ROOT.
    source = Path(layer["source"])
    if not source.is_absolute():
        source = ROOT / source
    values: dict[str, dict[str, dict[str, dict]]] = defaultdict(lambda: defaultdict(dict))
    variables: dict[str, dict] = {}
    periods: set[str] = set()
    rows_read = 0
    rows_seen = 0
    quality_counts: dict[str, int] = defaultdict(int)
    preview_totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])

    with source.open(encoding="utf8", newline="") as handle:
        for row in csv.DictReader(handle):
            if layer.get("filterColumn") and row.get(layer["filterColumn"]) != layer["filterValue"]:
                continue
            rows_seen += 1
            quality_counts[row.get("quality") or "ok"] += 1
            try:
                value = float(row[layer["valueColumn"]])
            except (KeyError, TypeError, ValueError):
                continue
            variable = row[layer["variableColumn"]]
            basin = str(row[layer["idColumn"]])
            period = period_key(row, layer)
            cell = {"v": round(value, 5)}
            if layer["kind"] == "anomaly":
                z = row.get("z_score")
                classification = row.get("classification")
                if z not in (None, ""):
                    cell["z"] = round(float(z), 3)
                if classification:
                    cell["c"] = classification
            values[basin][period][variable] = cell
            if variable not in variables:
                variables[variable] = {"code": variable, "unit": row.get(layer["unitColumn"]) or None,
                                       **variable_meta(variable, len(variables))}
            periods.add(period)
            rows_read += 1
            if variable == layer.get("previewVariable"):
                preview_value = value
                if layer.get("previewMetric") == "z_score" and row.get("z_score") not in (None, ""):
                    preview_value = float(row["z_score"])
                preview_totals[period][0] += preview_value
                preview_totals[period][1] += 1

    sorted_periods = sorted(periods)
    preview_variable = layer.get("previewVariable")
    preview_meta = variables.get(preview_variable, {})
    preview_points = sample_preview([
        {"period": period, "value": round(preview_totals[period][0] / preview_totals[period][1], 4)}
        for period in sorted(preview_totals)
        if preview_totals[period][1]
    ])
    valid_percent = round(rows_read / rows_seen * 100, 1) if rows_seen else 0.0
    quality_score = round(
        sum(count * QUALITY_WEIGHTS.get(state, 0.75)
            for state, count in quality_counts.items()) / rows_seen * 100,
        1,
    ) if rows_seen else 0.0
    series = {
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": layer["dataset"], "predicate": layer["predicate"],
        "spatialScope": layer.get("spatialScope", "national_intersection"),
        "spatialUnit": layer.get("spatialUnit", f"HydroATLAS level-{layer['basinLevel']} basin"),
        "basins": {basin: {period: cells for period, cells in sorted(annual.items())}
                  for basin, annual in sorted(values.items())},
    }
    entry = {
        "id": layer["id"], "label": layer["label"], "domain": layer["domain"],
        "kind": layer["kind"], "dataset": layer["dataset"], "predicate": layer["predicate"],
        "basinLevel": layer["basinLevel"],
        "spatialScope": layer.get("spatialScope", "national_intersection"),
        "spatialUnit": layer.get("spatialUnit", f"HydroATLAS level-{layer['basinLevel']} basin"),
        "legacyScope": layer.get("legacyScope", False),
        "baseline": layer.get("baseline"),
        "geometryIdColumn": layer.get("geometryIdColumn", "HYBAS_ID"),
        "geometry": layer.get("geometry") or geometry_for(layer["basinLevel"]),
        "periodGrain": layer["periodGrain"], "periods": sorted_periods,
        "variables": sorted(variables.values(), key=lambda item: item["code"]),
        "what": layer["what"],
        "series": f"/data/basin-layers/{layer['id']}.json",
        "coverage": {"rows": rows_read, "basins": len(values), "periods": len(sorted_periods)},
        "quality": {
            "validPercent": valid_percent,
            "scorePercent": quality_score,
            "states": dict(sorted(quality_counts.items())),
        },
        "preview": {
            "variable": preview_variable,
            "label": preview_meta.get("label", preview_variable),
            "unit": "z-score" if layer.get("previewMetric") == "z_score" else preview_meta.get("unit"),
            "aggregation": "mean across published basins",
            "points": preview_points,
        },
    }
    return entry, series


def build() -> list[dict]:
    entries = []
    for layer in LAYERS:
        entry, series = build_layer(layer)
        write_json(OUTPUT / f"{layer['id']}.json", series, compact=True)
        entries.append(entry)
        print(f"  {layer['id']:28} {entry['coverage']['rows']:>7,} rows · "
              f"{entry['coverage']['basins']:>5,} basins · {entry['coverage']['periods']:>5,} periods")
    return entries


def main() -> None:
    entries = build()
    write_json(INDEX, {
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": "Basin climate & land observatory",
        "description": ("Complete Amu Darya and Syr Darya observations are the primary scope; "
                        "the headwater formation layer remains available as a nested view. "
                        "Earlier Uzbekistan-intersection products remain marked as legacy comparisons."),
        "layers": entries,
    })
    print(f"\n  {len(entries)} layers -> {INDEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
