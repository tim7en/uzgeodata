"""Fit and validate ERA-based TerraClimate v1.0 continuation for 7,445 basins.

The 2025 producer TerraClimate v1.1 record stays separate. ERA-based estimates
continue the old v1.0 statistic for precipitation and temperature extrema; they
are never written into the original atlas cube or labeled as observations.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import duckdb
import geopandas as gpd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "PUBLISHED/data/atlas/climate-continuation"
CUBE = ROOT / "PUBLISHED/data/atlas/cube"
FRAME = ROOT / "GEODATA/transboundary_basins_v2/hydroatlas-level12-full-basins.geojson"
TRAIN_END = 2018
TEST_END = 2024
VARIABLES = ("precipitation", "tmin", "tmax")
ACCUMULATE_TC = ("ppt", "aet", "pet", "q", "tmin", "tmax")
FLUXES = {"ppt", "aet", "pet", "q", "precipitation"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frame():
    geo = gpd.read_file(FRAME)[["HYBAS_ID", "NEXT_DOWN", "SUB_AREA", "system_id"]]
    geo["basin_id"] = geo.HYBAS_ID.astype("int64").astype(str)
    geo["next_down"] = geo.NEXT_DOWN.astype("int64").astype(str)
    return geo[["basin_id", "next_down", "SUB_AREA", "system_id"]].rename(
        columns={"SUB_AREA": "area_km2"})


def connection(basins):
    era_files = sorted((OUT / "era5-land").glob("year=*.parquet"))
    if len(era_files) < 24 or not (OUT / "terraclimate-v1.1/year=2025.parquet").exists():
        raise FileNotFoundError("Regional ERA years 2003–2026 and TerraClimate v1.1 2025 are required")
    con = duckdb.connect()
    con.register("basins", basins)
    con.execute("PRAGMA memory_limit='3GB'")
    con.execute(f"""
        CREATE TEMP TABLE paired AS
        WITH target AS (
          SELECT basin_id,year,month,'precipitation' AS variable,
                 'precipitation_mm' AS era_variable,value AS reference
          FROM read_parquet('{CUBE / 'variable=pre_mm_s/data_0.parquet'}')
          UNION ALL
          SELECT basin_id,year,month,'tmin','temperature_c',value
          FROM read_parquet('{CUBE / 'variable=tmn_dc_s/data_0.parquet'}')
          UNION ALL
          SELECT basin_id,year,month,'tmax','temperature_c',value
          FROM read_parquet('{CUBE / 'variable=tmx_dc_s/data_0.parquet'}')
        )
        SELECT t.basin_id,b.system_id,t.year,t.month,t.variable,
               e.value AS era,t.reference
        FROM target t
        JOIN read_parquet('{OUT / 'era5-land/year=*.parquet'}') e
          ON e.basin_id=t.basin_id AND e.year=t.year AND e.month=t.month
          AND e.variable=t.era_variable
        JOIN basins b ON b.basin_id=t.basin_id
        WHERE t.year BETWEEN 2003 AND 2024
          AND e.value IS NOT NULL AND t.reference IS NOT NULL
          AND e.coverage > 0.999
    """)
    return con


def fit(con):
    region = con.execute(f"""
        SELECT system_id,variable,month,count(*) n,
               avg(reference-era) delta,
               sum(reference)/nullif(sum(era),0) ratio
        FROM paired WHERE year<= {TRAIN_END}
        GROUP BY 1,2,3
    """).fetchall()
    regional = {(system, variable, month): (delta, ratio)
                for system, variable, month, _, delta, ratio in region}
    local = con.execute(f"""
        SELECT basin_id,system_id,variable,month,count(*) n,
               avg(reference-era) delta,
               sum(reference)/nullif(sum(era),0) ratio
        FROM paired WHERE year<= {TRAIN_END}
        GROUP BY 1,2,3,4
    """).fetchall()
    rows = []
    for basin, system, variable, month, n, delta, ratio in local:
        if n < 8:
            continue
        global_delta, global_ratio = regional[system, variable, month]
        weight = n / (n + 8)
        if variable == "precipitation":
            if ratio is None or global_ratio is None:
                continue
            coefficient = min(4.0, max(0.25, weight * ratio + (1 - weight) * global_ratio))
            operation = "multiply"
        else:
            coefficient = weight * delta + (1 - weight) * global_delta
            operation = "add"
        rows.append({"basin_id": basin, "system_id": system, "variable": variable,
                     "month": month, "coefficient": coefficient,
                     "operation": operation, "training_months": n})
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, OUT / "coefficients.parquet", compression="zstd")
    con.register("coefficients", table)
    return len(rows)


def validate(con):
    rows = con.execute(f"""
        SELECT p.variable,p.system_id,count(*) n,
               avg(p.era-p.reference) raw_bias,
               sqrt(avg(power(p.era-p.reference,2))) raw_rmse,
               avg(abs(p.era-p.reference)) raw_mae,
               avg(CASE WHEN p.variable='precipitation' THEN p.era*c.coefficient
                        ELSE p.era+c.coefficient END-p.reference) adjusted_bias,
               sqrt(avg(power(CASE WHEN p.variable='precipitation' THEN p.era*c.coefficient
                                   ELSE p.era+c.coefficient END-p.reference,2))) adjusted_rmse,
               avg(abs(CASE WHEN p.variable='precipitation' THEN p.era*c.coefficient
                            ELSE p.era+c.coefficient END-p.reference)) adjusted_mae,
               quantile_cont(abs(CASE WHEN p.variable='precipitation' THEN p.era*c.coefficient
                                       ELSE p.era+c.coefficient END-p.reference),0.9) adjusted_abs_error_p90,
               count(DISTINCT p.basin_id) basins
        FROM paired p JOIN coefficients c
          ON p.basin_id=c.basin_id AND p.month=c.month AND p.variable=c.variable
        WHERE p.year BETWEEN {TRAIN_END + 1} AND {TEST_END}
        GROUP BY 1,2 ORDER BY 1,2
    """).fetchall()
    summary = {}
    for variable, system, n, raw_bias, raw_rmse, raw_mae, adjusted_bias, adjusted_rmse, adjusted_mae, error_p90, basins in rows:
        summary.setdefault(variable, {})[system] = {
            "pairs": n, "basins": basins,
            "raw": {"bias": raw_bias, "rmse": raw_rmse, "mae": raw_mae},
            "adjusted": {"bias": adjusted_bias, "rmse": adjusted_rmse, "mae": adjusted_mae,
                         "absolute_error_p90": error_p90},
            "improved": adjusted_rmse < raw_rmse and adjusted_mae < raw_mae}
    return summary


def continuation(con, scores):
    eligible = [v for v in VARIABLES if all(scores.get(v, {}).get(system, {}).get("improved")
                                         for system in ("amu_darya", "syr_darya"))]
    if not eligible:
        raise ValueError("No variable improved in both systems; continuation withheld")
    values = ",".join(f"'{v}'" for v in eligible)
    error_rows = [{"system_id": system, "variable": variable,
                   "holdout_abs_error_p90": result["adjusted"]["absolute_error_p90"]}
                  for variable, systems in scores.items() for system, result in systems.items()]
    con.register("error_scale", pa.Table.from_pylist(error_rows))
    table = con.execute(f"""
        SELECT e.basin_id,b.system_id,e.year,e.month,c.variable,
               e.value AS era_value,
               CASE WHEN c.variable='precipitation' THEN greatest(0,e.value*c.coefficient)
                    ELSE e.value+c.coefficient END AS estimate,
               s.holdout_abs_error_p90,
               'estimated_terraclimate_v1.0_continuation' AS status
        FROM read_parquet('{OUT / 'era5-land/year=*.parquet'}') e
        JOIN coefficients c ON e.basin_id=c.basin_id AND e.month=c.month
          AND e.variable=CASE WHEN c.variable='precipitation' THEN 'precipitation_mm'
                              ELSE 'temperature_c' END
        JOIN basins b ON e.basin_id=b.basin_id
        JOIN error_scale s ON b.system_id=s.system_id AND c.variable=s.variable
        WHERE e.year>2024 AND e.value IS NOT NULL AND e.coverage>0.999
          AND c.variable IN ({values})
        ORDER BY c.variable,e.basin_id,e.year,e.month
    """).to_arrow_table()
    pq.write_table(table, OUT / "v1.0-continuation.parquet", compression="zstd")
    return eligible, table.num_rows


def topological(basins):
    identifiers = list(basins.basin_id)
    included = set(identifiers)
    downstream = {r.basin_id: r.next_down if r.next_down in included else None
                  for r in basins.itertuples()}
    incoming = {basin: 0 for basin in identifiers}
    for below in downstream.values():
        if below:
            incoming[below] += 1
    ready = deque(sorted(basin for basin, count in incoming.items() if count == 0))
    order = []
    while ready:
        basin = ready.popleft()
        order.append(basin)
        below = downstream[basin]
        if below:
            incoming[below] -= 1
            if incoming[below] == 0:
                ready.append(below)
    if len(order) != len(identifiers):
        raise ValueError("Cycle in level-12 basin routing")
    return order, downstream


def accumulate_one(local, order, downstream, area):
    """Sum each local contribution once, then divide by covered upstream area."""
    total_area = {b: area[b] for b in order}
    covered = {b: area[b] if b in local and local[b] is not None else 0.0 for b in order}
    weighted = {b: local[b] * area[b] if b in local and local[b] is not None else 0.0
                for b in order}
    for basin in order:
        below = downstream[basin]
        if below:
            total_area[below] += total_area[basin]
            covered[below] += covered[basin]
            weighted[below] += weighted[basin]
    return {b: {"area_km2": total_area[b], "coverage": covered[b] / total_area[b],
                "mean": weighted[b] / covered[b] if covered[b] > 0 else None,
                "integral_mcm": weighted[b] * 0.001 if covered[b] > 0 else None}
            for b in order}


def upstream_products(basins):
    order, downstream = topological(basins)
    area = dict(zip(basins.basin_id, basins.area_km2))
    con = duckdb.connect()
    groups = defaultdict(dict)
    for basin, y, month, variable, value in con.execute(
        "SELECT basin_id,year,month,variable,value FROM read_parquet(?) WHERE variable IN "
        "('ppt','aet','pet','q','tmin','tmax')",
        [str(OUT / "terraclimate-v1.1/year=*.parquet")]).fetchall():
        groups[("terraclimate_v1.1_direct", y, month, variable)][basin] = value
    for basin, _, y, month, variable, _, value, _, _ in con.execute(
        "SELECT * FROM read_parquet(?) WHERE variable IN ('precipitation','tmin','tmax')",
        [str(OUT / "v1.0-continuation.parquet")]).fetchall():
        groups[("estimated_v1.0_continuation", y, month, variable)][basin] = value
    rows = []
    for (product, year, month, variable), local in sorted(groups.items()):
        result = accumulate_one(local, order, downstream, area)
        for basin, values in result.items():
            complete = values["coverage"] > 0.999999
            rows.append({"basin_id": basin, "year": year, "month": month,
                         "variable": variable, "product": product,
                         "upstream_area_km2": values["area_km2"],
                         "coverage_fraction": values["coverage"],
                         "upstream_mean": values["mean"] if complete else None,
                         "upstream_integral_mcm": values["integral_mcm"] if complete and variable in FLUXES else None,
                         "integral_meaning": "generated_water_equivalent_not_routed_flow"
                         if variable == "q" else "areal_water_equivalent" if variable in FLUXES else None})
    pq.write_table(pa.Table.from_pylist(rows), OUT / "upstream.parquet", compression="zstd")
    return len(rows)


def v11_agreement(con):
    """Agreement with 2025 v1.1; ERA is a parent, so this is not independent validation."""
    return con.execute(f"""
        SELECT c.variable,count(*) n,
               avg(c.estimate-v.value) bias,
               sqrt(avg(power(c.estimate-v.value,2))) rmse
        FROM read_parquet('{OUT / 'v1.0-continuation.parquet'}') c
        JOIN read_parquet('{OUT / 'terraclimate-v1.1/year=2025.parquet'}') v
          ON c.basin_id=v.basin_id AND c.year=v.year AND c.month=v.month
          AND v.variable=CASE c.variable WHEN 'precipitation' THEN 'ppt'
                                     WHEN 'tmin' THEN 'tmin' ELSE 'tmax' END
        WHERE c.year=2025 AND v.value IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """).fetchall()


def v11_version_overlap(con):
    """Same-year v1.1 vs v1.0 difference before deciding whether to splice."""
    source = OUT / "terraclimate-v1.1-primary/year=2024.parquet"
    if not source.exists():
        return {"status": "not_extracted"}
    rows = con.execute(f"""
        WITH reference AS (
          SELECT basin_id,year,month,'ppt' AS variable,value
          FROM read_parquet('{CUBE / 'variable=pre_mm_s/data_0.parquet'}')
          WHERE year=2024
          UNION ALL
          SELECT basin_id,year,month,'tmin',value
          FROM read_parquet('{CUBE / 'variable=tmn_dc_s/data_0.parquet'}')
          WHERE year=2024
          UNION ALL
          SELECT basin_id,year,month,'tmax',value
          FROM read_parquet('{CUBE / 'variable=tmx_dc_s/data_0.parquet'}')
          WHERE year=2024
        )
        SELECT v.variable,b.system_id,count(*) n,avg(v.value-r.value) bias,
               sqrt(avg(power(v.value-r.value,2))) rmse
        FROM read_parquet('{source}') v JOIN reference r
          ON v.basin_id=r.basin_id AND v.year=r.year AND v.month=r.month
          AND v.variable=r.variable
        JOIN basins b ON v.basin_id=b.basin_id
        WHERE v.value IS NOT NULL AND r.value IS NOT NULL
        GROUP BY 1,2 ORDER BY 1,2
    """).fetchall()
    return {variable: {system: {"pairs": n, "bias": bias, "rmse": rmse}
                       for v, system, n, bias, rmse in rows if v == variable}
            for variable in ("ppt", "tmin", "tmax")}


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    basins = frame()
    if len(basins) != 7445:
        raise ValueError("Regional frame is not 7,445 level-12 basins")
    con = connection(basins)
    coefficient_count = fit(con)
    scores = validate(con)
    eligible, continuation_rows = continuation(con, scores)
    latest_code = con.execute(f"SELECT max(year*100+month) FROM read_parquet('{OUT / 'v1.0-continuation.parquet'}')").fetchone()[0]
    latest_month = f"{latest_code // 100:04d}-{latest_code % 100:02d}"
    upstream_rows = upstream_products(basins)
    agreement = {v: {"pairs": n, "bias": bias, "rmse": rmse}
                 for v, n, bias, rmse in v11_agreement(con)}
    version_overlap = v11_version_overlap(con)
    direct_years = sorted(int(p.stem.split("=")[1]) for p in
                          (OUT / "terraclimate-v1.1").glob("year=*.parquet"))
    inputs = [FRAME, CUBE / "index.json"]
    inputs += [CUBE / f"variable={variable}/data_0.parquet"
               for variable in ("pre_mm_s", "tmn_dc_s", "tmx_dc_s")]
    inputs += sorted((OUT / "era5-land").glob("year=*.parquet"))
    inputs += sorted((OUT / "terraclimate-v1.1").glob("year=*.parquet"))
    inputs += sorted((OUT / "terraclimate-v1.1-primary").glob("year=*.parquet"))
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "basins": len(basins), "systems": {"amu_darya": 4917, "syr_darya": 2528},
              "training_years": [2003, TRAIN_END], "held_out_years": [TRAIN_END + 1, TEST_END],
              "method": "basin-calendar-month additive delta for temperature extrema and multiplicative factor for precipitation; 8 pseudo-year shrinkage toward system monthly coefficient",
              "source_versions": {"target": "TerraClimate v1.0 Earth Engine through 2024-12",
                                  "verification": f"TerraClimate v1.1 producer NetCDF through {direct_years[-1]}-12",
                                  "predictor": "ERA5-Land monthly native-grid fractional-overlap basin mean"},
              "coefficients": coefficient_count, "validation": scores,
              "input_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in inputs},
              "eligible_variables": eligible, "continuation_rows": continuation_rows,
              "continuation_through": latest_month,
              "v1.1_2025_agreement": agreement,
              "v1.1_vs_v1.0_2024_overlap": version_overlap,
              "upstream_rows": upstream_rows,
              "interpretation": "2025 TerraClimate v1.1 is a direct but version-changed source; it is not spliced into v1.0. Its ERA5 parent makes agreement with ERA-based estimates non-independent. 2026 continuation is modelled, and upstream runoff generation is not routed observed flow."}
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    index = {
        "generated_at": report["generated_at"], "basins": len(basins),
        "time_support": "calendar month", "spatial_support": "level-12 local basin and routed upstream set",
        "products": {
            "terraclimate_v1.1_direct": {
                "years": direct_years,
                "files": [f"/data/atlas/climate-continuation/terraclimate-v1.1/year={year}.parquet"
                          for year in direct_years],
                "meaning": "producer release reduced onto basin polygons; modelled climate and water balance",
            },
            "estimated_v1.0_continuation": {
                "file": "/data/atlas/climate-continuation/v1.0-continuation.parquet",
                "years": [2025, int(latest_month[:4])], "months_observed_in_era": f"through {latest_month}",
                "variables": eligible,
                "meaning": "ERA-derived estimate of the older v1.0 statistic; not a producer observation",
            },
            "upstream": {"file": "/data/atlas/climate-continuation/upstream.parquet",
                         "meaning": "area-weighted upstream mean; water equivalent integral only for fluxes"},
        },
        "validation": "/data/atlas/climate-continuation/report.json",
        "source_note": "v1.0 and v1.1 are not spliced into one source series",
    }
    (OUT / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(run(), indent=2))
