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

Each published record carries the raw per-pass observations (so a reader
can see the actual scatter, not just a monthly summary), a LOESS-smoothed
trend, and an explicit outlier/partial-pass flag per point — the three
things a chart needs to show the data honestly rather than just prettily.
LOESS for area is fit on the monthly-max series, not the raw one: a raw
per-pass fit would be dragged around by the partial-swath low cluster
described in fetch_swot_reservoirs.py, which is a coverage artefact, not
real week-to-week variability. WSE does not have that problem (a partial
view of a lake surface still reads a true elevation), so its LOESS fits
the raw, outlier-filtered per-pass series directly.

Usage:
    python PIPELINES/build_swot_lake_crosswalk.py
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
from statsmodels.nonparametric.smoothers_lowess import lowess

ROOT = Path(__file__).resolve().parents[1]
CS = ROOT / "PUBLISHED/data/case-studies/reservoirs"
WATER_BODIES = ROOT / "PUBLISHED/data/hydroclimate/water-bodies-reviewed.geojson"
OUT_CROSSWALK = CS / "swot_hydrolakes_crosswalk.csv"
OUT_SWOT_DIR = CS / "swot"


def loess_fit(dates: pd.Series, values: pd.Series, frac: float) -> list[float | None]:
    """LOESS at each of `dates`' own positions, so the smoothed line can be
    paired point-for-point with the series it summarises. Returns None
    (rather than a number) for degenerate/matching-only inputs."""
    valid = values.notna()
    if valid.sum() < 5:
        return [None] * len(values)
    x = dates.astype("int64").to_numpy(dtype=float)
    y = values.to_numpy(dtype=float)
    smoothed = lowess(y[valid.to_numpy()], x[valid.to_numpy()], frac=frac, return_sorted=False)
    out = np.full(len(values), np.nan)
    out[valid.to_numpy()] = smoothed
    return [None if np.isnan(v) else round(float(v), 3) for v in out]


def main() -> None:
    OUT_SWOT_DIR.mkdir(parents=True, exist_ok=True)

    water_bodies = gpd.read_file(WATER_BODIES)
    inventory = pd.read_csv(CS / "lake_inventory.csv", dtype={"pld_id": str})
    summary = pd.read_csv(CS / "reservoir_summary.csv", dtype={"pld_id": str})
    monthly = pd.read_csv(CS / "reservoir_timeseries_monthly.csv", dtype={"pld_id": str}, parse_dates=["time"])
    monthly_by_lake = {pld_id: g for pld_id, g in monthly.groupby("pld_id")}
    raw = pd.read_csv(CS / "reservoir_observations_raw.csv", dtype={"pld_id": str}, parse_dates=["time"])
    raw["wse_outlier"] = raw["wse_outlier"].astype(bool)
    raw_by_lake = {pld_id: g.sort_values("time") for pld_id, g in raw.groupby("pld_id")}

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

    # A HydroLAKES polygon can legitimately contain several SWOT lakes: e.g.
    # the "Aydar" catalogue entry's boundary is drawn at Aydarkul's maximum
    # historical extent, which also encloses a few much smaller nearby ponds
    # whose SWOT centroids fall inside the same polygon. Publishing one JSON
    # per water_body_id means picking one; every duplicate lost the map's own
    # per-lake area comparison anyway, since the map only has one figure
    # (the catalogue area) to compare against a single SWOT record. Keep the
    # SWOT lake whose own area is closest, in log scale, to the catalogue
    # figure the map already shows -- for Aydar that is the 2,938 km2 match,
    # not the 2.7 km2 or 12 km2 ponds sharing its polygon.
    before = len(crosswalk)
    log_gap = (np.log(crosswalk["swot_area_km2"].clip(lower=0.01))
               - np.log(pd.to_numeric(crosswalk["hydrolakes_area_km2"], errors="coerce").clip(lower=0.01))).abs()
    crosswalk = (crosswalk.assign(_gap=log_gap)
                 .sort_values("_gap")
                 .drop_duplicates("water_body_id", keep="first")
                 .drop(columns="_gap")
                 .sort_index())
    if before != len(crosswalk):
        print(f"  Resolved {before - len(crosswalk)} SWOT lakes sharing a HydroLAKES polygon with a better-matched sibling")

    crosswalk.to_csv(OUT_CROSSWALK, index=False)
    print(f"Matched {len(crosswalk)} of {len(inventory)} SWOT lakes to a HydroLAKES water body")

    named_lookup = {r.pld_id: r for r in summary.itertuples() if pd.notna(r.name)}
    n_written = 0
    for row in crosswalk.itertuples():
        pld_id = row.pld_id
        monthly_series = monthly_by_lake.get(pld_id)
        raw_series = raw_by_lake.get(pld_id)
        if monthly_series is None or monthly_series["area_total"].notna().sum() == 0 or raw_series is None:
            continue
        monthly_series = monthly_series.dropna(subset=["area_total"], how="all").sort_values("time")
        meta = named_lookup.get(pld_id)

        area_loess = loess_fit(monthly_series["time"], monthly_series["area_total"], frac=0.35)
        clean_wse = raw_series["wse"].where(~raw_series["wse_outlier"])
        wse_loess_raw = loess_fit(raw_series["time"], clean_wse, frac=0.2)

        payload = {
            "pld_id": pld_id,
            "water_body_id": row.water_body_id,
            "name": meta.name if meta is not None else None,
            "source": "NASA/CNES SWOT mission, SWOT_L2_HR_LakeSP_2.0 via PO.DAAC Hydrocron",
            "case_study": "/reservoir-monitoring.html",
            # Raw per-pass observations, exactly as SWOT reported them (after
            # dropping quality_f==3 "bad" passes upstream). partial_f marks a
            # pass that only imaged part of the lake -- expect area_km2 to
            # read low on those, not because the lake shrank. wse_outlier
            # marks a statistically implausible elevation reading; the value
            # is kept, not hidden, so a chart can show it struck through
            # rather than pretend it was never measured.
            "observations": [
                {
                    "time": t.strftime("%Y-%m-%d"),
                    "area_km2": None if pd.isna(a) else round(float(a), 2),
                    "partial": bool(p),
                    "wse_m": None if pd.isna(w) else round(float(w), 2),
                    "wse_outlier": bool(o),
                }
                for t, a, p, w, o in zip(
                    raw_series["time"], raw_series["area_total"], raw_series["partial_f"],
                    raw_series["wse"], raw_series["wse_outlier"],
                )
            ],
            # LOESS trend, paired point-for-point with the series it
            # summarises -- area against the monthly-max points (partial-pass
            # resistant), water level against the raw, outlier-filtered
            # per-pass points (finer-grained; a level reading is not biased
            # by partial coverage the way area is).
            "area_loess": [
                {"time": t.strftime("%Y-%m-%d"), "value": v}
                for t, v in zip(monthly_series["time"], area_loess)
            ],
            "wse_loess": [
                {"time": t.strftime("%Y-%m-%d"), "value": v}
                for t, v in zip(raw_series["time"], wse_loess_raw)
            ],
            "months": [
                {
                    "time": t.strftime("%Y-%m-%d"),
                    "area_km2": None if pd.isna(a) else round(float(a), 2),
                    "wse_m": None if pd.isna(w) else round(float(w), 2),
                    "n_overpasses": int(n),
                }
                for t, a, w, n in zip(monthly_series["time"], monthly_series["area_total"],
                                       monthly_series["wse"], monthly_series["n_overpasses"])
            ],
        }
        (OUT_SWOT_DIR / f"{row.water_body_id}.json").write_text(json.dumps(payload), encoding="utf-8")
        n_written += 1

    print(f"Wrote {n_written} per-lake SWOT time series JSON files to {OUT_SWOT_DIR}")


if __name__ == "__main__":
    main()
