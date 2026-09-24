"""Pskem level-12 TerraClimate v1.0 continuation from ERA5-Land.

The fitted field estimates what the frozen TerraClimate v1.0 basin series would
have reported. It is not a station-calibrated climate truth or reservoir inflow.
Run with --extract-era once to acquire ERA5-Land precipitation on the same 15
arc-second analysis grid as the atlas. Later runs reuse that cached extraction.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUN = ROOT / "PUBLISHED/data/atlas/runs/pskem-all281-20260909T184834061745Z"
CUBE = ROOT / "PUBLISHED/data/atlas/cube"
OUT = ROOT / "PUBLISHED/data/case-studies/pskem-climate-continuation"
ERA_PRECIP = OUT / "era5-precipitation-grid.csv"
STATION_SERIES = OUT / "pskem-station-product-grid.csv"
TRAIN_END = 2018
TEST_END = 2024
ASSET = "ECMWF/ERA5_LAND/MONTHLY_AGGR"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def pskem_frame():
    geo = json.loads((RUN / "pilot-basins.geojson").read_text())
    lock = json.loads((RUN / "source-lock.json").read_text())
    features = geo["features"]
    ids = {str(int(f["properties"]["HYBAS_ID"])) for f in features}
    return features, ids, lock["surrogate_grid"]["transform"]


def extract_era_precip(features, transform, through_year: int) -> None:
    """Annual stacks and zonal reduction use the atlas's exact analysis frame."""
    import ee
    from ATLAS_MODULES.hydrosheds.functions import dated_monthly

    ee.Initialize(project="ee-sabitovty")
    available = int(ee.ImageCollection(ASSET).sort("system:time_start", False)
                    .first().date().format("YYYY").getInfo())
    through_year = min(through_year, available)
    dated_monthly.SOURCES["pskem_era_precip"] = {
        "asset": ASSET,
        "bands": {"total_precipitation_sum": {"scale": 1000.0,
                 "unit": "millimetres per month", "attribute": "case.pskem.era_precip"}},
    }
    collection = dated_monthly.feature_collection(features)
    expected = dated_monthly.expected_cells(collection, transform)
    previous = {}
    if ERA_PRECIP.exists():
        with ERA_PRECIP.open(newline="") as handle:
            previous = {(r["basin_id"], int(r["year"]), int(r["month"])): r
                        for r in csv.DictReader(handle)}
    years = sorted({y for y in range(2003, through_year + 1)
                    if y == through_year or any(
                        (str(int(f["properties"]["HYBAS_ID"])), y, month) not in previous
                        for f in features for month in range(1, 13))})
    for year in years:
        extracted = dated_monthly.year_rows("pskem_era_precip", collection, transform,
                                            year, expected)
        for row in extracted:
            value = row["value"]
            if value is not None and value < -0.001:
                raise ValueError(f"Negative ERA precipitation: {row}")
            key = (row["hybas_id"], year, row["month"])
            previous[key] = {"basin_id": row["hybas_id"], "year": year,
                             "month": row["month"], "value": "" if value is None else max(0, value),
                             "valid_count": row["valid_count"],
                             "expected_count": row["expected_count"]}
        write_csv(ERA_PRECIP, [previous[k] for k in sorted(previous)],
                  ["basin_id", "year", "month", "value", "valid_count", "expected_count"])
        print(f"ERA precipitation: {year} complete", flush=True)
    (OUT / "era5-precipitation-grid.manifest.json").write_text(json.dumps({
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "asset": ASSET,
        "band": "total_precipitation_sum", "conversion": "metres times 1000 to millimetres",
        "spatial_frame": str((RUN / "pilot-basins.geojson").relative_to(ROOT)),
        "analysis_transform": transform, "reducer": "unweighted mean of valid 15 arc-second analysis cells",
        "rows": len(previous), "latest_available_year": available,
    }, indent=2) + "\n")


def cube_values(variable: str, ids: set[str]) -> dict[tuple[str, int, int], float]:
    path = CUBE / f"variable={variable}/data_0.parquet"
    con = duckdb.connect()
    try:
        rows = con.execute("SELECT basin_id, year, month, value FROM read_parquet(?) "
                           "WHERE basin_id IN (SELECT unnest(?)) AND value IS NOT NULL",
                           [str(path), sorted(ids)]).fetchall()
    finally:
        con.close()
    return {(str(b), int(y), int(m)): float(v) for b, y, m, v in rows}


def era_precip_values(ids: set[str]) -> dict[tuple[str, int, int], float]:
    if not ERA_PRECIP.exists():
        return {}
    with ERA_PRECIP.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {}
    for r in rows:
        if r["basin_id"] not in ids or not r["value"]:
            continue
        if int(r["valid_count"]) < int(r["expected_count"]):
            continue
        result[(r["basin_id"], int(r["year"]), int(r["month"]))] = float(r["value"])
    return result


def extract_station() -> None:
    """Sample native source cells at the Pskem meteorological station."""
    import ee
    from PIPELINES.extract_station_products import PRODUCTS, collection, year_rows

    ee.Initialize(project="ee-sabitovty")
    site = {"station_id": "uz:station/meteo-419704", "name": "Pskem",
            "longitude": 70.378123, "latitude": 41.940491}
    points = collection([site])
    rows = []
    for product in PRODUCTS:
        for year in range(2010, 2025):
            rows.extend(year_rows(product, points, year))
            print(f"Pskem station cell: {product} {year}", flush=True)
    write_csv(STATION_SERIES, rows,
              ["station_id", "product", "band", "measure", "year", "month",
               "value", "unit", "asset"])
    (OUT / "pskem-station-product-grid.manifest.json").write_text(json.dumps({
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "station_id": site["station_id"], "coordinates": [site["longitude"], site["latitude"]],
        "support": "native grid cell containing the station point", "years": [2010, 2024],
        "products": {name: spec["asset"] for name, spec in PRODUCTS.items()},
        "rows": len(rows),
    }, indent=2) + "\n")


def station_comparison() -> dict:
    if not STATION_SERIES.exists():
        return {"status": "station_grid_extraction_missing"}
    observations = {}
    source = ROOT / "PUBLISHED/data/hydroclimate/pskem-station-monthly.csv"
    with source.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["station_id"] == "uz:station/meteo-419704" and row["value"]:
                observations[row["variable"], int(row["year"]), int(row["month"])] = float(row["value"])
    products = {}
    with STATION_SERIES.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["value"]:
                products[row["product"], row["measure"], int(row["year"]), int(row["month"])] = float(row["value"])
    summary = {}
    for variable in ("air_temperature_mean", "precipitation_total"):
        summary[variable] = {}
        for product in ("era5_land", "terraclimate"):
            pairs = []
            for (measure, year, month), observed in observations.items():
                if measure != variable:
                    continue
                if variable == "air_temperature_mean" and product == "terraclimate":
                    high = products.get((product, "air_temperature_max", year, month))
                    low = products.get((product, "air_temperature_min", year, month))
                    estimated = (high + low) / 2 if high is not None and low is not None else None
                else:
                    estimated = products.get((product, variable, year, month))
                if estimated is not None:
                    pairs.append((year, estimated, observed))
            summary[variable][product] = {
                "all": metrics([(e, o) for _, e, o in pairs]),
                "2019_2024": metrics([(e, o) for y, e, o in pairs if 2019 <= y <= 2024]),
            }
    return {"status": "sampled_at_station_cell", "station_id": "uz:station/meteo-419704",
            "station_coordinates": [70.378123, 41.940491],
            "comparison": summary,
            "warning": "A single valley station is not a validation of high mountain basin means. "
                       "Source station coordinates and relocation history are unverified."}


def station_transfer(parameters: list[dict]) -> dict:
    """Apply the containing basin's fixed factors at the station point as a stress test."""
    if not STATION_SERIES.exists():
        return {"status": "station_grid_extraction_missing"}
    from shapely.geometry import Point, shape

    features, _, _ = pskem_frame()
    point = Point(70.378123, 41.940491)
    containing = [str(int(f["properties"]["HYBAS_ID"])) for f in features
                  if shape(f["geometry"]).covers(point)]
    if len(containing) != 1:
        return {"status": "station_not_in_unique_basin", "matches": containing}
    basin = containing[0]
    coefficients = {(r["variable"], r["basin_id"], r["month"]): r["coefficient"]
                    for r in parameters}
    observed = {}
    with (ROOT / "PUBLISHED/data/hydroclimate/pskem-station-monthly.csv").open(newline="") as handle:
        for r in csv.DictReader(handle):
            if r["station_id"] == "uz:station/meteo-419704" and r["value"]:
                observed[r["variable"], int(r["year"]), int(r["month"])] = float(r["value"])
    raw = {}
    with STATION_SERIES.open(newline="") as handle:
        for r in csv.DictReader(handle):
            if r["product"] == "era5_land" and r["value"]:
                raw[r["measure"], int(r["year"]), int(r["month"])] = float(r["value"])
    result = {"status": "tested", "containing_basin": basin}
    for name, measure, kind in (("temperature_midpoint", "air_temperature_mean", "temperature"),
                                ("precipitation", "precipitation_total", "precipitation")):
        baseline, adjusted = [], []
        for (variable, year, month), value in observed.items():
            key = (name, basin, month)
            estimate = raw.get((measure, year, month))
            if variable != measure or not 2019 <= year <= 2024 or estimate is None or key not in coefficients:
                continue
            baseline.append((estimate, value))
            adjusted.append((adjust(estimate, coefficients[key], kind), value))
        result[name] = {"era5": metrics(baseline), "basin_adjustment_at_station": metrics(adjusted)}
    result["interpretation"] = ("This probes transfer from a basin mean correction to one station cell. "
                                "It is a stress test, not a spatially independent validation.")
    return result


def metrics(pairs: list[tuple[float, float]]) -> dict:
    if not pairs:
        return {"n": 0, "bias": None, "mae": None, "rmse": None}
    errors = [estimate - reference for estimate, reference in pairs]
    return {"n": len(errors), "bias": sum(errors) / len(errors),
            "mae": sum(map(abs, errors)) / len(errors),
            "rmse": math.sqrt(sum(e * e for e in errors) / len(errors))}


def fit(raw: dict, target: dict, kind: str) -> dict:
    """Monthly factors at each spatial unit, shrunk toward the Pskem monthly mean.

    Train only through 2018. A factor/delta is constant after training, preserving
    interannual ERA variation. No post-2024 TerraClimate value enters a fit.
    """
    by_unit = defaultdict(list)
    by_month = defaultdict(list)
    for (basin, year, month), value in raw.items():
        if 2003 <= year <= TRAIN_END and (basin, year, month) in target:
            ref = target[basin, year, month]
            by_unit[basin, month].append((value, ref))
            by_month[month].append((value, ref))

    def coefficient(pairs):
        if kind == "temperature":
            return sum(t - r for r, t in pairs) / len(pairs)
        # Ratio of totals avoids the unstable mean of wet/dry month ratios.
        return sum(t for _, t in pairs) / max(sum(r for r, _ in pairs), 1.0)

    regional = {m: coefficient(pairs) for m, pairs in by_month.items() if len(pairs) >= 8}
    coefficients = {}
    for key, pairs in by_unit.items():
        if len(pairs) < 8 or key[1] not in regional:
            continue
        # Eight pseudo-years keep a short local record from dominating the field.
        weight = len(pairs) / (len(pairs) + 8)
        local = coefficient(pairs)
        value = weight * local + (1 - weight) * regional[key[1]]
        if kind == "precipitation":
            value = min(4.0, max(0.25, value))
        coefficients[key] = value
    return coefficients


def adjust(raw: float, coefficient: float, kind: str) -> float:
    return raw + coefficient if kind == "temperature" else max(0.0, raw * coefficient)


def build() -> dict:
    _, ids, transform = pskem_frame()
    era_t = cube_values("tmp_dc_s", ids)
    min_t = cube_values("tmn_dc_s", ids)
    max_t = cube_values("tmx_dc_s", ids)
    tc_t = {k: (v + max_t[k]) / 2 for k, v in min_t.items() if k in max_t}
    cases = {
        "temperature_midpoint": (era_t, tc_t, "temperature", "degrees Celsius"),
        "precipitation": (era_precip_values(ids), cube_values("pre_mm_s", ids),
                          "precipitation", "millimetres per month"),
    }
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "frame": "20 Pskem HydroATLAS level-12 units; 15 arc-second analysis grid",
              "grid_transform": transform, "train_years": [2003, TRAIN_END],
              "held_out_years": [TRAIN_END + 1, TEST_END],
              "variables": {}, "sources": {"era5": ASSET,
              "terraclimate": "IDAHO_EPSCOR/TERRACLIMATE v1.0"},
              "input_sha256": {"cube_index": digest(CUBE / "index.json"),
              "pskem_frame": digest(RUN / "pilot-basins.geojson")}}
    if ERA_PRECIP.exists():
        report["input_sha256"]["era_precipitation"] = digest(ERA_PRECIP)
    if STATION_SERIES.exists():
        report["input_sha256"]["station_products"] = digest(STATION_SERIES)
        report["input_sha256"]["station_observations"] = digest(
            ROOT / "PUBLISHED/data/hydroclimate/pskem-station-monthly.csv")
    report["station_comparison"] = station_comparison()
    continuation = []
    validation = []
    parameter_rows = []
    for name, (raw, target, kind, unit) in cases.items():
        if not raw:
            report["variables"][name] = {"status": "missing_era_grid_input"}
            continue
        coefficients = fit(raw, target, kind)
        test_keys = sorted(k for k in raw.keys() & target.keys()
                           if TRAIN_END < k[1] <= TEST_END and (k[0], k[2]) in coefficients)
        baseline = [(raw[k], target[k]) for k in test_keys]
        corrected = [(adjust(raw[k], coefficients[k[0], k[2]], kind), target[k])
                     for k in test_keys]
        base_score, new_score = metrics(baseline), metrics(corrected)
        eligible = bool(test_keys) and new_score["rmse"] < base_score["rmse"]
        report["variables"][name] = {"status": "held_out_improvement" if eligible else "no_held_out_improvement",
                                     "baseline": base_score, "adjusted": new_score,
                                     "basins": len({k[0] for k in test_keys}),
                                     "coefficient_count": len(coefficients), "unit": unit}
        for key in test_keys:
            basin, year, month = key
            validation.append({"variable": name, "basin_id": basin, "year": year,
                               "month": month, "era5": raw[key], "terraclimate_v1": target[key],
                               "adjusted": adjust(raw[key], coefficients[basin, month], kind)})
        for (basin, month), value in sorted(coefficients.items()):
            parameter_rows.append({"variable": name, "basin_id": basin,
                                   "month": month, "coefficient": value,
                                   "operation": "add" if kind == "temperature" else "multiply"})
        if eligible:
            for (basin, year, month), value in sorted(raw.items()):
                if year <= TEST_END or (basin, month) not in coefficients:
                    continue
                continuation.append({"variable": name, "basin_id": basin,
                                     "year": year, "month": month,
                                     "era5_value": value,
                                     "estimate": adjust(value, coefficients[basin, month], kind),
                                     "unit": unit, "status": "estimated_terraclimate_v1_continuation"})
    write_csv(OUT / "validation.csv", validation,
              ["variable", "basin_id", "year", "month", "era5", "terraclimate_v1", "adjusted"])
    write_csv(OUT / "coefficients.csv", parameter_rows,
              ["variable", "basin_id", "month", "coefficient", "operation"])
    write_csv(OUT / "continuation.csv", continuation,
              ["variable", "basin_id", "year", "month", "era5_value", "estimate", "unit", "status"])
    report["station_transfer"] = station_transfer(parameter_rows)
    report["continuation_rows"] = len(continuation)
    report["caveat"] = ("Target is a TerraClimate v1.0 basin statistic, not observed weather. "
                        "Temperature target is the midpoint of monthly extrema, not mean 2 m air temperature. "
                        "Precipitation factors retain ERA5 relative anomalies but cannot recover local orographic events. "
                        "Subbasins share coarse ERA5 cells; validation rows are spatially dependent. "
                        "No reservoir storage, level, inflow or post-2017 discharge is inferred.")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract-era", action="store_true", help="Refresh ERA precipitation grid from Earth Engine")
    parser.add_argument("--extract-station", action="store_true", help="Sample ERA and TerraClimate at the Pskem station")
    parser.add_argument("--through-year", type=int, default=2026)
    args = parser.parse_args()
    if args.extract_era:
        features, _, transform = pskem_frame()
        extract_era_precip(features, transform, args.through_year)
    if args.extract_station:
        extract_station()
    report = build()
    print(json.dumps({"variables": report["variables"],
                      "continuation_rows": report["continuation_rows"]}, indent=2))


if __name__ == "__main__":
    main()
