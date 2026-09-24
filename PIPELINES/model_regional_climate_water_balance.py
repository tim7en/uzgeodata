"""Emulate the missing TerraClimate v1.0 water-balance variables from ERA5-Land.

Each basin/calendar-month has a training climatology. A predictor anomaly from
ERA5-Land is mapped with a slope shrunk toward its river-system/month slope.
2019–2024 is never used to fit coefficients. Predictions remain model estimates,
and TerraClimate runoff generation is not observed or routed river discharge.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from PIPELINES.model_regional_climate_continuation import CUBE, OUT, frame

TARGETS = {
    "aet": ("aet_mm_s", "aet_mm", "nonnegative"),
    "def": ("cwd_mm_s", "deficit_mm", "nonnegative"),
    "PDSI": ("pds_ix_s", "pds_balance_mm", "index"),
    "pet": ("pet_mm_s", "pet_mm", "nonnegative"),
    "q": ("rtc_mm_s", "runoff_mm", "nonnegative"),
    "soil": ("soil_mm_s", "soil_fraction", "nonnegative"),
    "swe": ("swe_mm_s", "swe_mm", "nonnegative"),
    "vpd": ("vpd_kp_s", "vpd_kpa", "nonnegative"),
}


def predictors(con):
    years = {int(path.stem.split("=")[1]) for path in (OUT / "era5-land-extended").glob("year=*.parquet")}
    if not years or set(range(2003, max(years) + 1)) - years or max(years) < 2025:
        raise FileNotFoundError("ERA5-Land extended predictors need every year from 2003 to the latest")
    con.execute(f"""
      CREATE TEMP TABLE era_wide AS
      SELECT basin_id,year,month,
        max(value) FILTER (WHERE variable='aet_mm') aet_mm,
        max(value) FILTER (WHERE variable='pet_mm') pet_mm,
        max(value) FILTER (WHERE variable='runoff_mm') runoff_mm,
        max(value) FILTER (WHERE variable='soil_fraction') soil_fraction,
        max(value) FILTER (WHERE variable='swe_mm') swe_mm,
        max(value) FILTER (WHERE variable='tmin_c') tmin_c,
        max(value) FILTER (WHERE variable='tmax_c') tmax_c,
        max(value) FILTER (WHERE variable='dewpoint_c') dewpoint_c
      FROM read_parquet('{OUT / 'era5-land-extended/year=*.parquet'}')
      WHERE coverage > 0.999
      GROUP BY 1,2,3
    """)
    con.execute(f"""
      CREATE TEMP TABLE era_ppt AS
      SELECT basin_id,year,month,max(value) precipitation_mm
      FROM read_parquet('{OUT / 'era5-land/year=*.parquet'}')
      WHERE variable='precipitation_mm' AND coverage>0.999
      GROUP BY 1,2,3
    """)
    con.execute("""
      CREATE TEMP TABLE predictors AS
      WITH physics AS (
        SELECT w.*,p.precipitation_mm,
          greatest(0,w.pet_mm-w.aet_mm) deficit_mm,
          greatest(0,0.6108*exp(17.27*((w.tmin_c+w.tmax_c)/2)/
                                (((w.tmin_c+w.tmax_c)/2)+237.3))
            -0.6108*exp(17.27*w.dewpoint_c/(w.dewpoint_c+237.3))) vpd_kpa
        FROM era_wide w JOIN era_ppt p USING (basin_id,year,month)
      )
      SELECT *,sum(precipitation_mm-pet_mm) OVER (
        PARTITION BY basin_id ORDER BY year,month ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
      ) pds_balance_mm
      FROM physics
    """)
    print("ERA water-balance predictor table ready", flush=True)


def fit_variable(con, variable, target_file, proxy, kind):
    con.execute("DROP TABLE IF EXISTS paired")
    con.execute(f"""
      CREATE TEMP TABLE paired AS
      SELECT p.basin_id,b.system_id,p.year,p.month,p.{proxy} AS x,t.value AS y
      FROM predictors p
      JOIN read_parquet('{CUBE / f'variable={target_file}/data_0.parquet'}') t
        USING (basin_id,year,month)
      JOIN basins b USING (basin_id)
      WHERE p.year BETWEEN 2003 AND 2024
        AND p.{proxy} IS NOT NULL AND isfinite(p.{proxy})
        AND t.value IS NOT NULL AND isfinite(t.value)
    """)
    con.execute("""
      CREATE OR REPLACE TEMP TABLE local_stats AS
      SELECT basin_id,system_id,month,count(*) n,avg(x) xmean,avg(y) ymean,
        covar_pop(x,y)/nullif(var_pop(x),0) local_slope
      FROM paired WHERE year<=2018 GROUP BY 1,2,3
    """)
    global_rows = con.execute("""
      SELECT p.system_id,p.month,
        sum((p.x-l.xmean)*(p.y-l.ymean))/nullif(sum(power(p.x-l.xmean,2)),0) slope
      FROM paired p JOIN local_stats l USING (basin_id,system_id,month)
      WHERE p.year<=2018 GROUP BY 1,2
    """).fetchall()
    global_slope = {(system, month): max(0.0, slope or 0.0)
                    for system, month, slope in global_rows}
    coefficients = []
    for basin, system, month, n, xmean, ymean, local_slope in con.execute(
        "SELECT * FROM local_stats ORDER BY basin_id,month").fetchall():
        if n < 8:
            continue
        regional = global_slope[(system, month)]
        local = max(0.0, min(local_slope or 0.0, 4 * regional)) if regional else 0.0
        weight = n / (n + 8)
        coefficients.append({"basin_id": basin, "system_id": system, "month": month,
                             "variable": variable, "predictor": proxy,
                             "target_mean": ymean, "predictor_mean": xmean,
                             "slope": weight * local + (1 - weight) * regional,
                             "training_months": n})
    con.register("coefficients", pa.Table.from_pylist(coefficients))
    expression = "c.target_mean+c.slope*(p.x-c.predictor_mean)"
    if kind == "nonnegative":
        expression = f"greatest(0,{expression})"
    scores = {}
    rows = con.execute(f"""
      SELECT p.system_id,count(*) pairs,count(DISTINCT p.basin_id) basins,
        avg(abs(p.y-c.target_mean)) baseline_mae,
        sqrt(avg(power(p.y-c.target_mean,2))) baseline_rmse,
        avg(abs(p.y-({expression}))) adjusted_mae,
        sqrt(avg(power(p.y-({expression}),2))) adjusted_rmse,
        avg(({expression})-p.y) adjusted_bias,
        quantile_cont(abs(p.y-({expression})),0.9) abs_error_p90
      FROM paired p JOIN coefficients c USING (basin_id,system_id,month)
      WHERE p.year BETWEEN 2019 AND 2024
      GROUP BY 1 ORDER BY 1
    """).fetchall()
    for system, pairs, basins, bmae, brmse, amae, armse, bias, p90 in rows:
        scores[system] = {"pairs": pairs, "basins": basins,
                          "seasonal_climatology": {"mae": bmae, "rmse": brmse},
                          "era_adjusted": {"mae": amae, "rmse": armse, "bias": bias,
                                           "absolute_error_p90": p90},
                          "improved": amae < bmae and armse < brmse}
    # Held-out RMSE per year: error rising with distance from 2018 is model drift;
    # both columns rising together is the target itself changing.
    for system, year, adjusted, baseline in con.execute(f"""
      SELECT p.system_id,p.year,sqrt(avg(power(p.y-({expression}),2))),
        sqrt(avg(power(p.y-c.target_mean,2)))
      FROM paired p JOIN coefficients c USING (basin_id,system_id,month)
      WHERE p.year BETWEEN 2019 AND 2024 GROUP BY 1,2 ORDER BY 1,2
    """).fetchall():
        scores[system].setdefault("rmse_by_year", {})[str(year)] = {
            "era_adjusted": adjusted, "seasonal_climatology": baseline}
    con.unregister("coefficients")
    return coefficients, scores


def run():
    basins = frame()
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")
    con.register("basins", basins)
    predictors(con)
    all_coefficients, validation = [], {}
    for variable, (target_file, proxy, kind) in TARGETS.items():
        coefficients, scores = fit_variable(con, variable, target_file, proxy, kind)
        all_coefficients.extend(coefficients)
        validation[variable] = scores
        print(variable, {system: round(result['era_adjusted']['rmse'], 3)
                         for system, result in scores.items()}, flush=True)
    pq.write_table(pa.Table.from_pylist(all_coefficients),
                   OUT / "water-balance-coefficients.parquet", compression="zstd")
    con.register("water_coefficients", pa.Table.from_pylist(all_coefficients))
    eligible = [variable for variable, systems in validation.items()
                if all(systems.get(system, {}).get("improved")
                       for system in ("amu_darya", "syr_darya"))]
    if not eligible:
        raise ValueError("No water-balance variables passed both held-out system checks")
    error_scale = pa.Table.from_pylist([
        {"system_id": system, "variable": variable,
         "holdout_abs_error_p90": scores["era_adjusted"]["absolute_error_p90"]}
        for variable, systems in validation.items() for system, scores in systems.items()
    ])
    con.register("error_scale", error_scale)
    rows = []
    for variable in eligible:
        _, proxy, kind = TARGETS[variable]
        expression = f"c.target_mean+c.slope*(p.{proxy}-c.predictor_mean)"
        if kind == "nonnegative":
            expression = f"greatest(0,{expression})"
        rows.extend(con.execute(f"""
          SELECT p.basin_id,b.system_id,p.year,p.month,'{variable}' AS variable,
            p.{proxy} AS era_value,{expression} AS estimate,
            e.holdout_abs_error_p90,
            'estimated_terraclimate_v1.0_water_balance' AS status
          FROM predictors p JOIN water_coefficients c
            ON p.basin_id=c.basin_id AND p.month=c.month AND c.variable='{variable}'
          JOIN basins b ON p.basin_id=b.basin_id
          JOIN error_scale e ON b.system_id=e.system_id AND e.variable='{variable}'
          WHERE p.year>2024 AND p.{proxy} IS NOT NULL
          ORDER BY p.basin_id,p.year,p.month
        """).fetchall())
    table = pa.Table.from_pylist([
        {"basin_id": basin, "system_id": system, "year": year, "month": month,
         "variable": variable, "era_value": raw, "estimate": estimate,
         "holdout_abs_error_p90": p90, "status": status}
        for basin, system, year, month, variable, raw, estimate, p90, status in rows
    ])
    pq.write_table(table, OUT / "v1.0-water-balance-continuation.parquet", compression="zstd")
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "method": "basin/month ERA predictor anomaly scaled to TerraClimate v1.0 using a basin slope shrunk toward river-system/month slope with eight pseudo-years",
              "training_years": [2003, 2018], "held_out_years": [2019, 2024],
              "validation": validation, "eligible_variables": eligible,
              "estimated_rows": table.num_rows,
              "warning": "TerraClimate product emulation; not independent station validation. q is modelled runoff generation, not observed discharge or routed river flow."}
    (OUT / "water-balance-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Published {table.num_rows:,} water-balance estimate rows for {eligible}", flush=True)
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
