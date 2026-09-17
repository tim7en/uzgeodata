#!/usr/bin/env python3
"""Trace real upstream/downstream relationships between CA-discharge gauges.

Earlier mass-balance checks in this project compared gauges by named
sub-basin + drainage area only ("same BASIN string, bigger area = more
downstream"). That is wrong wherever a basin name changes at a confluence
(Naryn joining the Syr Darya, tributaries joining the Vaksh) and it cannot
tell a genuinely nested catchment from two unrelated basins of similar size.

CA-discharge already ships an exact delineated catchment polygon per gauge
(the `basins` layer, matched 1:1 to `basin_attributes` / gauge CODE — this is
the same HydroSHEDS-derived delineation the case study's basin maps already
draw from). Whether gauge A is upstream of gauge B is then a geometry
question, not a naming one: A is upstream of B iff A's catchment polygon
sits (almost) entirely inside B's.

Output: gauge_topology.csv — every confirmed nested pair, plus, per
downstream gauge, its single largest immediate upstream gauge (used by the
mass-balance check in train_pooled_transfer_model.py).

Usage:
    python PIPELINES/build_gauge_topology.py
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GPKG = ROOT / "GEODATA/ca-discharge-2023/CA-discharge.gpkg"
CS = ROOT / "PUBLISHED/data/case-studies"
BASIN_LOOKUP = CS / "gauge_basin_lookup.csv"
OUT = CS / "gauge_topology.csv"

# Central Asia Lambert Conformal Conic: for correct area/overlap math, not for display.
EQUAL_AREA_CRS = "ESRI:102025"
CONTAINMENT_THRESHOLD = 0.85  # fraction of the smaller polygon's area inside the larger one


def main() -> None:
    lookup = pd.read_csv(BASIN_LOOKUP, dtype={"gauge_code": str})
    scope_codes = set(lookup[lookup.aral_drainage].gauge_code)

    gdf = gpd.read_file(GPKG, layer="basins")
    gdf = gdf[gdf.CODE.isin(scope_codes)].reset_index(drop=True)
    gdf["geometry"] = gdf.buffer(0)  # repair any self-intersecting rings
    gdf = gdf.to_crs(EQUAL_AREA_CRS)
    gdf["area_calc_km2"] = gdf.geometry.area / 1e6
    print(f"Loaded {len(gdf)} delineated catchments in scope")

    order = gdf.sort_values("area_calc_km2").reset_index(drop=True)
    pairs = []
    for i in range(len(order)):
        small = order.iloc[i]
        for j in range(i + 1, len(order)):
            big = order.iloc[j]
            inter_km2 = small.geometry.intersection(big.geometry).area / 1e6
            frac = inter_km2 / small.area_calc_km2 if small.area_calc_km2 > 0 else 0
            if frac >= CONTAINMENT_THRESHOLD:
                pairs.append({
                    "upstream_code": small.CODE, "downstream_code": big.CODE,
                    "overlap_frac": round(frac, 4),
                    "upstream_area_km2": round(small.area_calc_km2, 1),
                    "downstream_area_km2": round(big.area_calc_km2, 1),
                })

    topo = pd.DataFrame(pairs)
    topo.to_csv(OUT, index=False)
    print(f"Confirmed nested (upstream, downstream) pairs: {len(topo)}")

    # For each downstream gauge, its single largest confirmed upstream gauge —
    # the dominant measured tributary feeding it, used for a same-network,
    # confluence-level plausibility check (discharge should not drop right at
    # a confluence, even though it commonly drops much further downstream in
    # this basin due to irrigation withdrawal — that is real, not a model bug).
    dominant = (topo.sort_values("upstream_area_km2", ascending=False)
                     .drop_duplicates("downstream_code", keep="first")
                     .rename(columns={"upstream_code": "dominant_upstream_code"}))
    dominant[["downstream_code", "dominant_upstream_code", "upstream_area_km2", "downstream_area_km2"]] \
        .to_csv(CS / "gauge_topology_dominant_upstream.csv", index=False)
    print(f"Gauges with an identified dominant upstream gauge: {len(dominant)}")


if __name__ == "__main__":
    main()
