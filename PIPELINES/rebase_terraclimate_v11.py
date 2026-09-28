"""Rebase the atlas's TerraClimate series on the producer's v1.1 release.

python PIPELINES/rebase_terraclimate_v11.py [--dry-run]

Why this exists. The monthly record was built from TerraClimate v1.0 as Earth Engine
hosts it (IDAHO_EPSCOR/TERRACLIMATE). That collection stops at 2024-12: TerraClimate
is released once a year, and from the 2025 release the producer moved to v1.1, which
Earth Engine has not ingested. The producer publishes v1.1 for every year from 1958
and advises against joining v1.0 and v1.1 in one series, so a record continued past
2024 has to be v1.1 throughout - not v1.0 with a v1.1 year stapled on.

What it does. Every year the producer lists, from the first year of the record, is
read by `extract_regional_climate_grids.py terraclimate-v11 --family
terraclimate-v1.1-history` (fractional cell overlap on the 1/24 degree grid, the
same reduction as the continuation package). This replaces the eleven TerraClimate
series in the per-basin history files and in the query cube with those values,
end to end, and relabels them. The ERA5-Land series (runoff, mean temperature) and
snow are untouched. Nothing is written unless every variable is complete for every
basin and month.

The earlier v1.0 values remain in Git history. Months after the last producer year
are not written here: they are the provisional product of
`model_regional_climate_continuation.py`, labelled as such.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now, write_json
from PIPELINES.build_basin_history import write_compact
from PIPELINES.update_published_record import CUBE, EXPECTED_GEOMETRY, HISTORY, index_cube, month_index

SOURCE = ROOT / "PUBLISHED/data/atlas/climate-continuation/terraclimate-v1.1-history"
PREFIX = "uzgeodata.dated.v1."
# Producer variable -> atlas series. srad, vap and ws have no atlas series.
SERIES = {
    "ppt": "pre_mm_s", "tmax": "tmx_dc_s", "tmin": "tmn_dc_s", "aet": "aet_mm_s",
    "pet": "pet_mm_s", "soil": "soil_mm_s", "def": "cwd_mm_s", "q": "rtc_mm_s",
    "swe": "swe_mm_s", "vpd": "vpd_kp_s", "PDSI": "pds_ix_s",
}
RELEASE = {
    "source": "terraclimate_v1.1",
    "asset": "TerraClimate v1.1, Climatology Lab yearly NetCDF (climate.northwestknowledge.net)",
    "source_release": "terraclimate-v1.1@climatologylab",
    "product_version": "v1.1",
    "reduction": "fractional 1/24 degree cell overlap with basin polygons",
}
METHOD = "terraclimate_v11_rebase@1"


def years_available(first):
    found = sorted(int(path.stem.split("=")[1]) for path in SOURCE.glob("year=*.parquet"))
    if not found or found[0] > first:
        raise FileNotFoundError(f"No TerraClimate v1.1 history from {first} under {SOURCE}. Run "
                                "extract_regional_climate_grids.py terraclimate-v11 --years "
                                f"{first}-<last> --family terraclimate-v1.1-history first.")
    years = [year for year in found if year >= first]
    gaps = sorted(set(range(years[0], years[-1] + 1)) - set(years))
    if gaps:
        raise FileNotFoundError(f"TerraClimate v1.1 history is missing years {gaps}")
    return years


def load(years, start, width):
    """One matrix a series, basins by months of the history frame, NaN where empty.

    Twenty million values held as Python tuples cost gigabytes; as float matrices
    they are a few hundred megabytes, and the history files are written from them.
    """
    import numpy as np
    pattern = [str(SOURCE / f"year={year}.parquet") for year in years]
    connection = duckdb.connect()
    basins = [row[0] for row in connection.execute(
        f"SELECT DISTINCT basin_id FROM read_parquet({pattern}) ORDER BY 1").fetchall()]
    position = {basin: i for i, basin in enumerate(basins)}
    matrices, counts = {}, {}
    for variable, name in SERIES.items():
        data = connection.execute(f"""
            SELECT basin_id, year, month, value FROM read_parquet({pattern})
            WHERE variable = ?""", [variable]).fetchnumpy()
        matrix = np.full((len(basins), width), np.nan)
        rows = np.fromiter((position[b] for b in data["basin_id"]), dtype=np.int64, count=len(data["basin_id"]))
        slots = (data["year"].astype(np.int64) - start) * 12 + data["month"].astype(np.int64) - 1
        values = np.asarray(data["value"], dtype=np.float64)
        matrix[rows, slots] = values
        matrices[name] = matrix
        counts[name] = len(values)
    connection.close()
    return basins, matrices, counts


def check(basins, matrices, counts, first_slot, last_slot):
    months = last_slot - first_slot + 1
    expected = len(basins) * months
    import numpy as np
    empty = 0
    for name, matrix in matrices.items():
        if counts[name] != expected:
            raise RuntimeError(f"{name}: expected {expected:,} values ({len(basins)} basins x {months} "
                               f"months) but the v1.1 history holds {counts[name]:,}. Nothing was written.")
        empty += int(np.isnan(matrix[:, first_slot:last_slot + 1]).sum())
    # The producer grid covers every basin; a handful of empty values would be a lake
    # or coastline cell, a lot of them a broken read.
    if empty > 0.001 * expected * len(matrices):
        raise RuntimeError(f"{empty:,} v1.1 values are empty. Nothing was written.")
    return empty


def rebase_history(basins, matrices, first_slot, last_slot, through, run_id, history=HISTORY):
    """Replace the eleven series in every basin file, end to end."""
    import numpy as np
    index = json.loads((history / "index.json").read_text(encoding="utf-8"))
    updated = 0
    for row, basin in enumerate(basins):
        path = history / f"{basin}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, matrix in matrices.items():
            series = payload["series"].get(name)
            if series is None:
                continue
            line = matrix[row]
            values = [None if np.isnan(value) or slot < first_slot or slot > last_slot else round(float(value), 4)
                      for slot, value in enumerate(line[:payload["months"]])]
            observed = sum(1 for value in values[:last_slot + 1] if value is not None)
            series.update(RELEASE)
            series.update({"values": values, "extracted_through": through, "run_ids": [run_id],
                           "methods": [METHOD], "observed_months": observed,
                           "missing_months": last_slot + 1 - observed,
                           "geometry_version": EXPECTED_GEOMETRY})
        write_compact(path, payload)
        index["observed_months"].setdefault(basin, {}).update(
            {name: payload["series"][name]["observed_months"] for name in matrices if name in payload["series"]})
        updated += 1
    for name in matrices:
        if name in index["series"]:
            index["series"][name].update(RELEASE)
            index["series"][name].update({"extracted_through": through, "run_ids": [run_id], "methods": [METHOD]})
    index["generated_at"] = utc_now()
    index.setdefault("appended", []).append({
        "at": utc_now(), "source": "terraclimate_v1.1", "through": through, "run_id": run_id,
        "mode": "rebased: the eleven TerraClimate series replaced end to end by the producer's v1.1",
        "replaced": "TerraClimate v1.0 from Earth Engine (IDAHO_EPSCOR/TERRACLIMATE), through 2024-12"})
    write_json(history / "index.json", index)
    return updated


def rebase_cube(years, units, cube=CUBE):
    """Each variable file rewritten from the v1.1 history, in the cube's own layout."""
    pattern = [str(SOURCE / f"year={year}.parquet") for year in years]
    connection = duckdb.connect()
    for variable, name in SERIES.items():
        path = cube / f"variable={name}" / "data_0.parquet"
        temporary = path.with_name("data_0.parquet.tmp")
        connection.execute(f"""
            COPY (SELECT basin_id, '{PREFIX}{name}' AS attribute_id, CAST(year AS BIGINT) AS year,
                         CAST(month AS BIGINT) AS month, CAST(value AS DOUBLE) AS value,
                         '{units[name]}' AS unit
                  FROM read_parquet({pattern}) WHERE variable = '{variable}'
                  ORDER BY basin_id, year, month)
            TO '{temporary.as_posix()}' (FORMAT PARQUET, COMPRESSION zstd, ROW_GROUP_SIZE 100000)""")
        temporary.replace(path)
    connection.close()


COMPARISON = ROOT / "PUBLISHED/data/atlas/climate-continuation/v1.1-vs-v1.0.json"
FRAME = ROOT / "GEODATA/transboundary_basins_v2/hydroatlas-level12-full-basins.geojson"


def compare_versions(years):
    """What the rebase changes, measured before the v1.0 values are overwritten.

    Per series and river system over the years both releases hold: the mean
    difference, its RMSE and the correlation, month by month and basin by basin; and
    the annual regional means of each, so a changed level or trend is visible.
    """
    import geopandas as gpd
    systems = gpd.read_file(FRAME, columns=["HYBAS_ID", "system_id", "SUB_AREA"], ignore_geometry=True)
    systems["basin_id"] = systems.HYBAS_ID.astype("int64").astype(str)
    connection = duckdb.connect()
    connection.register("systems", systems[["basin_id", "system_id", "SUB_AREA"]])
    pattern = [str(SOURCE / f"year={year}.parquet") for year in years]
    report = {"generated_at": utc_now(), "note": "v1.0 is TerraClimate from Earth Engine as the atlas held it; v1.1 "
              "is the producer's release reduced the same way here. The difference includes the product change "
              "(v1.1 builds on ERA5 anomalies) and is why the two are not joined in one series.",
              "series": {}}
    for variable, name in SERIES.items():
        cube = CUBE / f"variable={name}" / "data_0.parquet"
        rows = connection.execute(f"""
            WITH paired AS (
              SELECT s.system_id, v.year, s.SUB_AREA area, v.value v11, c.value v10
              FROM read_parquet({pattern}) v
              JOIN read_parquet('{cube.as_posix()}') c USING (basin_id, year, month)
              JOIN systems s USING (basin_id)
              WHERE v.variable = '{variable}' AND v.value IS NOT NULL AND c.value IS NOT NULL)
            SELECT system_id, count(*), min(year), max(year), avg(v11 - v10), sqrt(avg(power(v11 - v10, 2))),
                   corr(v11, v10), sum(v10 * area) / sum(area), sum(v11 * area) / sum(area)
            FROM paired GROUP BY 1 ORDER BY 1""").fetchall()
        annual = connection.execute(f"""
            SELECT s.system_id, v.year, sum(c.value * s.SUB_AREA) / sum(s.SUB_AREA),
                   sum(v.value * s.SUB_AREA) / sum(s.SUB_AREA)
            FROM read_parquet({pattern}) v
            JOIN read_parquet('{cube.as_posix()}') c USING (basin_id, year, month)
            JOIN systems s USING (basin_id)
            WHERE v.variable = '{variable}' AND v.value IS NOT NULL AND c.value IS NOT NULL
            GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
        report["series"][name] = {system: {
            "pairs": n, "years": [first, last], "bias": round(bias, 4), "rmse": round(rmse, 4),
            "correlation": round(correlation, 4) if correlation is not None else None,
            "mean_v1_0": round(old, 4), "mean_v1_1": round(new, 4),
            "annual_mean": [[year, round(a, 4), round(b, 4)] for s_, year, a, b in annual if s_ == system],
        } for system, n, first, last, bias, rmse, correlation, old, new in rows}
    connection.close()
    COMPARISON.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return report


def run(dry_run=False):
    index = json.loads((HISTORY / "index.json").read_text(encoding="utf-8"))
    start, end = index["years"]
    years = years_available(start)
    first, through = f"{years[0]:04d}-01", f"{years[-1]:04d}-12"
    if years[-1] > end:
        raise RuntimeError(f"The history frame ends in {end}; v1.1 reaches {through}. "
                           "Widen the frame before rebasing.")
    first_slot, last_slot = month_index(first) - start * 12, month_index(through) - start * 12
    units = {name: index["series"][name]["unit"] for name in SERIES.values()}
    run_id = f"terraclimate-v11-rebase-{utc_now().replace(':', '').replace('-', '')}"
    basins, matrices, counts = load(years, start, index["months"])
    empty = check(basins, matrices, counts, first_slot, last_slot)
    summary = {"years": [years[0], years[-1]], "series": sorted(SERIES.values()), "basins": len(basins),
               "values": sum(counts.values()), "empty_values": empty, "run_id": run_id}
    if dry_run:
        return {"dry_run": True, **summary}
    # Measured while the cube still holds the release being replaced. A second run
    # finds v1.1 in the cube and keeps the first comparison.
    if json.loads((HISTORY / "index.json").read_text(encoding="utf-8"))["series"]["pre_mm_s"].get("product_version") != "v1.1":
        compare_versions(years)
    updated = rebase_history(basins, matrices, first_slot, last_slot, through, run_id)
    rebase_cube(years, units)
    note = {"at": utc_now(), "source": "terraclimate_v1.1", "months": [first, through], "run_id": run_id,
            "mode": "rebased on TerraClimate v1.1 producer release"}
    cube_rows = index_cube(note, CUBE)
    return {**summary, "history_basins": updated, "cube_rows": cube_rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    print(json.dumps(run(parser.parse_args().dry_run), indent=2), flush=True)


if __name__ == "__main__":
    main()
