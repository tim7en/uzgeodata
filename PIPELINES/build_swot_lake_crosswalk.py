#!/usr/bin/env python3
"""Cross-reference SWOT-tracked lakes with the map's existing HydroLAKES/GRanD
water-body layer, and publish a compact per-lake SWOT time series JSON for
every match so the landing map's LakeModal can fetch it on demand.

Match rule: a SWOT lake's centroid must fall inside a HydroLAKES polygon.
This is deliberately conservative — it will miss a HydroLAKES water body
whose mapped polygon does not actually reach the coordinate SWOT currently
observes water at (this happens for the Aral Sea's now-separated basins if
a HydroLAKES entry only covers one), but it will not silently pair two
unrelated water bodies the way a plain nearest-centroid match could in a
basin this dense with small lakes.

Usage:
    python PIPELINES/build_swot_lake_crosswalk.py
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
CS = ROOT / "PUBLISHED/data/case-studies/reservoirs"
WATER_BODIES = ROOT / "PUBLISHED/data/hydroclimate/water-bodies-reviewed.geojson"
OUT_CROSSWALK = CS / "swot_hydrolakes_crosswalk.csv"
OUT_SWOT_DIR = CS / "swot"


def main() -> None:
    OUT_SWOT_DIR.mkdir(parents=True, exist_ok=True)

    water_bodies = gpd.read_file(WATER_BODIES)
    inventory = pd.read_csv(CS / "lake_inventory.csv", dtype={"pld_id": str})
    summary = pd.read_csv(CS / "reservoir_summary.csv", dtype={"pld_id": str})
    monthly = pd.read_csv(CS / "reservoir_timeseries_monthly.csv", dtype={"pld_id": str}, parse_dates=["time"])
    monthly_by_lake = {pld_id: g for pld_id, g in monthly.groupby("pld_id")}

    # Equal-area projection for the fallback distance check below.
    water_bodies_proj = water_bodies.to_crs("ESRI:102025")

    matches = []
    for row in inventory.itertuples():
        point = Point(row.lon, row.lat)
        hits = water_bodies[water_bodies.geometry.contains(point)]
        if hits.empty:
            # Point-in-polygon fails for elongated reservoirs whose SWOT
            # centroid lands just outside a narrower HydroLAKES digitisation
            # of the same feature (this happened for Nurek). Fall back to
            # nearest polygon within 3 km, only when its catalogue area is
            # within a factor of 3 of SWOT's own estimate, so a near-miss on
            # a a real match is recovered without pairing unrelated lakes.
            point_proj = gpd.GeoSeries([point], crs="EPSG:4326").to_crs("ESRI:102025").iloc[0]
            dist_km = water_bodies_proj.geometry.distance(point_proj) / 1000
            nearby = water_bodies[(dist_km <= 3)].copy()
            if nearby.empty:
                continue
            areas = pd.to_numeric(nearby["area_km2"], errors="coerce")
            plausible = nearby[(areas >= row.area_km2 / 3) & (areas <= row.area_km2 * 3)]
            if plausible.empty:
                continue
            hits = plausible.loc[[dist_km.loc[plausible.index].idxmin()]]
        if len(hits) > 1:
            # Rare (nested/overlapping polygons); keep the one whose
            # catalogue area is closest in log-scale to SWOT's own estimate.
            import numpy as np
            areas = pd.to_numeric(hits["area_km2"], errors="coerce").fillna(1.0)
            hits = hits.iloc[[(np.log(areas) - np.log(max(row.area_km2, 0.1))).abs().argmin()]]
        match = hits.iloc[0]
        matches.append({
            "pld_id": row.pld_id,
            "water_body_id": match["water_body_id"],
            "hydrolakes_name": match["display_name"],
            "water_body_type": match["water_body_type"],
            "hydrolakes_area_km2": match["area_km2"],
            "swot_area_km2": row.area_km2,
        })

    crosswalk = pd.DataFrame(matches)
    crosswalk.to_csv(OUT_CROSSWALK, index=False)
    print(f"Matched {len(crosswalk)} of {len(inventory)} SWOT lakes to a HydroLAKES water body")

    named_lookup = {r.pld_id: r for r in summary.itertuples() if pd.notna(r.name)}
    n_written = 0
    for row in crosswalk.itertuples():
        pld_id = row.pld_id
        series = monthly_by_lake.get(pld_id)
        if series is None or series["area_total"].notna().sum() == 0:
            continue
        series = series.dropna(subset=["area_total"], how="all").sort_values("time")
        meta = named_lookup.get(pld_id)
        payload = {
            "pld_id": pld_id,
            "water_body_id": row.water_body_id,
            "name": meta.name if meta is not None else None,
            "source": "NASA/CNES SWOT mission, SWOT_L2_HR_LakeSP_2.0 via PO.DAAC Hydrocron",
            "case_study": "/reservoir-monitoring.html",
            "months": [
                {
                    "time": t.strftime("%Y-%m-%d"),
                    "area_km2": None if pd.isna(a) else round(float(a), 2),
                    "wse_m": None if pd.isna(w) else round(float(w), 2),
                    "n_overpasses": int(n),
                }
                for t, a, w, n in zip(series["time"], series["area_total"], series["wse"], series["n_overpasses"])
            ],
        }
        (OUT_SWOT_DIR / f"{row.water_body_id}.json").write_text(json.dumps(payload), encoding="utf-8")
        n_written += 1

    print(f"Wrote {n_written} per-lake SWOT time series JSON files to {OUT_SWOT_DIR}")


if __name__ == "__main__":
    main()
