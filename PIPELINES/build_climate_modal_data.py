"""Make compact per-basin JSON for the versioned climate modal and downloads."""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "PUBLISHED/data/atlas/climate-continuation"
DEST = BASE / "basins"
UNITS = {
    "ppt": "mm/month", "precipitation": "mm/month", "tmin": "°C", "tmax": "°C",
    "aet": "mm/month", "def": "mm/month", "pet": "mm/month", "q": "mm/month",
    "soil": "mm", "srad": "W/m²", "swe": "mm", "vap": "kPa", "ws": "m/s",
    "vpd": "kPa", "PDSI": "index",
}
LABELS = {
    "ppt": "Precipitation", "precipitation": "Precipitation", "tmin": "Minimum temperature",
    "tmax": "Maximum temperature", "aet": "Actual evapotranspiration",
    "def": "Climate water deficit", "pet": "Potential evapotranspiration",
    "q": "Modelled runoff generation", "soil": "Soil moisture", "srad": "Solar radiation",
    "swe": "Snow water equivalent", "vap": "Vapour pressure", "ws": "Wind speed",
    "vpd": "Vapour pressure deficit", "PDSI": "Palmer drought severity index",
}


def build():
    import sys
    sys.path.insert(0, str(ROOT))
    from PIPELINES.model_regional_climate_continuation import TEST_END, VERSION
    DEST.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    estimated = f"estimated_{VERSION}"
    # A producer year the record already holds is the record, not a second product.
    direct = [path for path in (BASE / "terraclimate-v1.1").glob("year=*.parquet")
              if int(path.stem.split("=")[1]) > TEST_END]
    direct_part = f"""
      SELECT basin_id, 'direct_v1.1' product, 'local' support, variable,
             year, month, value, coverage, NULL::DOUBLE integral, NULL::DOUBLE err
      FROM read_parquet({[str(path) for path in direct]})
      UNION ALL""" if direct else ""
    query = f"""{direct_part}
      SELECT basin_id, '{estimated}' product, 'local' support, variable,
             year, month, estimate AS value, 1::DOUBLE coverage, NULL::DOUBLE integral, holdout_abs_error_p90 err
      FROM read_parquet('{BASE / f'{VERSION}*continuation.parquet'}')
      UNION ALL
      SELECT basin_id,
             CASE WHEN product='terraclimate_v1.1_direct' THEN 'direct_v1.1' ELSE '{estimated}' END,
             'upstream', variable, year, month, upstream_mean,
             coverage_fraction, upstream_integral_mcm, NULL::DOUBLE
      FROM read_parquet('{BASE / 'upstream.parquet'}')
      ORDER BY basin_id, product, support, variable, year, month
    """
    rows = con.execute(query)
    current_id, series, count = None, {}, 0

    def flush():
        nonlocal count
        if current_id is None:
            return
        document = {
            "basin_id": current_id,
            "record_type": "versioned_basin_climate",
            "row_fields": ["year", "month", "value", "coverage_fraction", "water_equivalent_mcm", "holdout_abs_error_p90"],
            "series": series,
            "source_index": "/data/atlas/climate-continuation/index.json",
            "note": f"The atlas record is TerraClimate {VERSION} through {TEST_END}-12; later months are ERA-based estimates of it until the producer releases the year. Upstream runoff is modelled generation, not observed flow.",
        }
        (DEST / f"{current_id}.json").write_text(json.dumps(document, separators=(",", ":"), allow_nan=False) + "\n")
        count += 1

    while batch := rows.fetchmany(5000):
        for basin_id, product, support, variable, year, month, value, coverage, integral, error in batch:
            if basin_id != current_id:
                flush()
                current_id, series = basin_id, {}
            key = f"{product}:{support}:{variable}"
            if key not in series:
                series[key] = {"product": product, "support": support, "variable": variable,
                               "label": LABELS[variable], "unit": UNITS[variable], "rows": []}
            series[key]["rows"].append([year, month, value, coverage, integral, error])
    flush()
    if count != 7445:
        raise ValueError(f"Expected 7,445 basins; generated {count}")
    direct_years = sorted(int(path.stem.split("=")[1]) for path in direct)
    continuation_latest = con.execute(f"SELECT max(year*100+month) FROM read_parquet('{BASE / f'{VERSION}*continuation.parquet'}')").fetchone()[0]
    (BASE / "basins-index.json").write_text(json.dumps({
        "basins": count, "base_url": "/data/atlas/climate-continuation/basins/",
        "schema": "Each series row follows row_fields in the basin JSON.",
        "products": {"direct_v1.1": {"meaning": "Producer TerraClimate v1.1", "years": direct_years},
                     estimated: {"meaning": f"ERA-based provisional TerraClimate {VERSION} after {TEST_END}-12",
                                        "through": f"{continuation_latest // 100}-{continuation_latest % 100:02d}"}},
    }, indent=2) + "\n")
    print(f"Built climate modal JSON for {count} basins")


if __name__ == "__main__":
    build()
