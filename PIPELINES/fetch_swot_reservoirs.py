#!/usr/bin/env python3
"""Fetch SWOT-observed lake/reservoir level and area data for the entire
Aral Sea drainage basin (Syr Darya + Amu Darya), for the reservoir/lake
monitoring case study.

Data sources (both public, no authentication required — verified live):
- Hydroweb GeoServer (CNES/Theia), WFS: polygon geometry for every lake in
  the SWOT Prior Lake Database (PLD).
  https://hydroweb.next.theia-land.fr/geoserver/REF_DATA/ows
- PO.DAAC Hydrocron API: per-overpass time series (water surface elevation,
  area) for any PLD lake_id.
  https://soto.podaac.earthdatacloud.nasa.gov/hydrocron/v1/timeseries

Both endpoints reject requests with no User-Agent (or a bot-like one) —
this is a WAF rule on the CNES side, not an API key requirement.

Study-area scope: lakes are kept only if their polygon intersects the real
Aral Sea drainage outline (a dissolve of every HydroBASINS level-10 unit in
PUBLISHED/data/hydroclimate/basins-level10.geojson — the same basin
delineation the discharge case study's maps already use), not a bounding
rectangle. A rectangle around this basin runs from 34 to 44 degrees N and
silently excludes the Aral Sea itself, which sits at 45-46.5 degrees N.

Five named reservoirs (Toktogul, Kayrakkum, Charvak, Nurek, Aydarkul/
Arnasay) are identified by matching each one's known approximate
coordinates and full-pool surface area (public knowledge) against the
nearest large PLD polygon inside the basin outline — PLD itself carries no
names, so this is a best-match, not an authoritative crosswalk. Every
other lake/reservoir >= 1 km2 inside the basin is fetched too, without a
name, identified only by its PLD id and location.

Usage:
    python PIPELINES/fetch_swot_reservoirs.py
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "PUBLISHED/data/case-studies/reservoirs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
BASIN_FILE = ROOT / "PUBLISHED/data/hydroclimate/basins-level10.geojson"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
WFS_URL = "https://hydroweb.next.theia-land.fr/geoserver/REF_DATA/ows"
HYDROCRON_URL = "https://soto.podaac.earthdatacloud.nasa.gov/hydrocron/v1/timeseries"
MIN_LAKE_AREA_KM2 = 1.0
START_TIME = "2023-01-01T00:00:00Z"  # before SWOT's science orbit (2023-07-21); harmless, returns nothing early on
FILL_VALUE = -999999999999.0
REQUEST_PAUSE_S = 0.3  # be a polite, infrequent caller of someone else's public API

NAMED_RESERVOIRS = {
    "4620019453": {"name": "Toktogul", "river": "Naryn / Syr Darya", "country": "Kyrgyzstan", "known_area_km2": 284},
    "4620036363": {"name": "Kayrakkum", "river": "Syr Darya", "country": "Tajikistan", "known_area_km2": 520},
    "4620025973": {"name": "Charvak", "river": "Chirchik", "country": "Uzbekistan", "known_area_km2": 40},
    "4610049903": {"name": "Nurek", "river": "Vakhsh / Amu Darya", "country": "Tajikistan", "known_area_km2": 98},
    "4620005313": {"name": "Aydarkul / Arnasay", "river": "Syr Darya overflow", "country": "Uzbekistan", "known_area_km2": 2000},
    # The three largest lakes in the whole basin turn out to be what is left
    # of the Aral Sea itself, only found once lakes were clipped against the
    # real basin polygon instead of a rectangle that stopped at 44N.
    "4610055043": {"name": "North Aral Sea", "river": "Syr Darya terminus", "country": "Kazakhstan", "known_area_km2": 3300},
    "4610055052": {"name": "South Aral Sea (western basin)", "river": "Amu Darya terminus", "country": "Uzbekistan", "known_area_km2": 3000},
    "4620094823": {"name": "South Aral Sea (eastern basin)", "river": "Amu Darya terminus", "country": "Uzbekistan/Kazakhstan", "known_area_km2": 3500},
}


def http_get_json(url: str, retries: int = 5, timeout: int = 90) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            time.sleep(3 * (attempt + 1))
    raise last_error


def load_basin_polygon():
    gdf = gpd.read_file(BASIN_FILE)
    return gdf.union_all()


def fetch_all_lakes_clipped(basin_poly) -> pd.DataFrame:
    """Every PLD lake >= MIN_LAKE_AREA_KM2 whose polygon intersects the real
    basin outline (not its bounding rectangle)."""
    west, south, east, north = basin_poly.bounds
    rows = []
    start_index = 0
    page = 300
    while True:
        params = {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": "swot_prior_lake_db",
            "bbox": f"{west},{south},{east},{north},EPSG:4326",
            "outputFormat": "application/json",
            "count": page, "startIndex": start_index,
        }
        url = WFS_URL + "?" + urllib.parse.urlencode(params)
        data = http_get_json(url)
        feats = data.get("features", [])
        if not feats:
            break
        for f in feats:
            area = f["properties"].get("p_ref_area")
            if not area or area < MIN_LAKE_AREA_KM2:
                continue
            try:
                geom = shape(f["geometry"])
            except Exception:
                continue
            if geom.intersects(basin_poly):
                c = geom.centroid
                rows.append({"pld_id": f["properties"]["fid"], "area_km2": area, "lon": c.x, "lat": c.y})
        start_index += page
        print(f"  WFS page at startIndex={start_index}: {len(rows)} matched so far", flush=True)
        if len(feats) < page:
            break
        time.sleep(REQUEST_PAUSE_S)
    return pd.DataFrame(rows)


def fetch_lake_timeseries(pld_id: str) -> pd.DataFrame:
    params = {
        "feature": "PriorLake",
        "feature_id": pld_id,
        "start_time": START_TIME,
        "end_time": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "output": "csv",
        "collection_name": "SWOT_L2_HR_LakeSP_2.0",
        "fields": "lake_id,time_str,wse,area_total,quality_f,partial_f",
    }
    url = HYDROCRON_URL + "?" + urllib.parse.urlencode(params)
    data = http_get_json(url)
    csv_text = data.get("results", {}).get("csv", "")
    if not csv_text.strip():
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(csv_text))
    df = df[df["time_str"] != "no_data"].copy()
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time_str"], utc=True, errors="coerce")
    for col in ("wse", "area_total"):
        df.loc[df[col] <= FILL_VALUE / 2, col] = pd.NA
    df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)

    # SWOT's summary quality flag (0 good, 1 suspect, 2 degraded, 3 bad):
    # drop only 3, since even flag 1 still contains most of the usable record.
    # quality_f alone does not catch everything: some datasets have passes
    # reporting elevations physically impossible for the lake (thousands of
    # metres off), still flagged "suspect" like most of the good passes
    # around them. A robust per-lake outlier filter on WSE catches what the
    # quality flag misses.
    df = df[df["quality_f"] != 3].copy()
    df["wse_outlier"] = False
    if df["wse"].notna().sum() > 4:
        median = df["wse"].median()
        mad = (df["wse"] - median).abs().median()
        threshold = max(20.0, 6 * 1.4826 * mad)
        # Flagged, not discarded: a chart showing raw observations needs to
        # display these points as excluded, not silently omit them.
        df["wse_outlier"] = (df["wse"] - median).abs() > threshold

    # area_total is what SWOT's ~50 km swath saw of the lake in that one
    # pass, not a scaled whole-lake estimate. A large or elongated lake is
    # often only partly crossed, so area_total clusters at a low value (a
    # sliver of the lake) and a much higher one (nearly all of it) across
    # different passes. A partial pass can only under-count true extent,
    # never over-count it, so downstream aggregation uses monthly MAX, not
    # mean, as the extent estimate.
    return df.reset_index(drop=True)


def monthly_max_extent(series: pd.DataFrame, name: str) -> pd.DataFrame:
    if series.empty:
        return series
    clean_wse = series["wse"].where(~series["wse_outlier"])
    monthly = series.assign(wse=clean_wse).set_index("time").resample("MS").agg(
        area_total=("area_total", "max"),
        wse=("wse", "median"),
        n_overpasses=("area_total", "size"),
    ).dropna(subset=["area_total"], how="all").reset_index()
    monthly["pld_id"] = name
    return monthly


def main() -> None:
    print("Loading the real Aral Sea drainage basin outline...")
    basin_poly = load_basin_polygon()
    print(f"  basin bounds: {basin_poly.bounds}")

    print("\nFetching and clipping the lake inventory against the real basin polygon...")
    inventory = fetch_all_lakes_clipped(basin_poly)
    inventory.to_csv(OUT_DIR / "lake_inventory.csv", index=False)
    print(f"  {len(inventory)} lakes >= {MIN_LAKE_AREA_KM2} km2 inside the basin "
          f"(total area {inventory.area_km2.sum():,.0f} km2)")

    print(f"\nFetching SWOT time series for all {len(inventory)} lakes "
          f"(this is a long-running batch call to a public API; progress is saved incrementally)...")
    monthly_path = OUT_DIR / "reservoir_timeseries_monthly.csv"
    summary_path = OUT_DIR / "reservoir_summary.csv"
    raw_path = OUT_DIR / "reservoir_observations_raw.csv"
    monthly_rows = []
    summary_rows = []
    raw_rows = []
    named_raw_rows = []
    failed = []

    for i, row in enumerate(inventory.itertuples(), 1):
        pld_id = row.pld_id
        meta = NAMED_RESERVOIRS.get(pld_id, {})
        try:
            series = fetch_lake_timeseries(pld_id)
        except Exception as error:
            failed.append({"pld_id": pld_id, "error": str(error)})
            print(f"  [{i}/{len(inventory)}] {pld_id}: FAILED ({error})", flush=True)
            time.sleep(REQUEST_PAUSE_S)
            continue

        n_valid_area = series["area_total"].notna().sum() if len(series) else 0
        monthly = monthly_max_extent(series, pld_id) if len(series) else pd.DataFrame()
        m_area = monthly["area_total"].dropna() if len(monthly) else pd.Series(dtype=float)

        summary_rows.append({
            "pld_id": pld_id,
            "name": meta.get("name"),
            "river": meta.get("river"),
            "country": meta.get("country"),
            "known_area_km2": meta.get("known_area_km2"),
            "lon": row.lon, "lat": row.lat, "pld_ref_area_km2": row.area_km2,
            "n_overpasses": len(series),
            "n_valid_area": int(n_valid_area),
            "n_months": len(monthly),
            "first_obs": series["time"].min().isoformat() if len(series) else None,
            "last_obs": series["time"].max().isoformat() if len(series) else None,
            "first_area_km2": float(m_area.iloc[0]) if len(m_area) else None,
            # Max over the last 3 available months, not just the single most
            # recent one: a month can close out with only one overpass, and
            # if that one pass happened to be a partial-swath sliver, the
            # literal last value understates a reservoir that was actually
            # near full a few weeks earlier (seen on Toktogul: 238 km2 in
            # April, then a single 1-overpass May reading of 21 km2).
            "latest_area_km2": float(m_area.tail(3).max()) if len(m_area) else None,
            "min_area_km2": float(m_area.min()) if len(m_area) else None,
            "max_area_km2": float(m_area.max()) if len(m_area) else None,
        })
        if len(monthly):
            monthly_rows.append(monthly)
        if len(series):
            raw = series[["time", "area_total", "wse", "partial_f", "wse_outlier"]].copy()
            raw.insert(0, "pld_id", pld_id)
            raw_rows.append(raw)
        if pld_id in NAMED_RESERVOIRS and len(series):
            series = series.copy()
            series["name"] = meta.get("name")
            named_raw_rows.append(series)

        label = meta.get("name", pld_id)
        print(f"  [{i}/{len(inventory)}] {label}: {len(series)} overpasses, {len(monthly)} months", flush=True)

        # Incremental save every 25 lakes so a crash partway through a ~30
        # minute run against someone else's API does not lose earlier work.
        if i % 25 == 0 or i == len(inventory):
            pd.concat(monthly_rows, ignore_index=True).to_csv(monthly_path, index=False) if monthly_rows else None
            pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
            pd.concat(raw_rows, ignore_index=True).to_csv(raw_path, index=False) if raw_rows else None

        time.sleep(REQUEST_PAUSE_S)

    if named_raw_rows:
        pd.concat(named_raw_rows, ignore_index=True).to_csv(OUT_DIR / "named_reservoirs_raw_timeseries.csv", index=False)

    if failed:
        pd.DataFrame(failed).to_csv(OUT_DIR / "fetch_failures.csv", index=False)
        print(f"\n{len(failed)} lakes failed after retries; see fetch_failures.csv")

    manifest = {
        "generated": pd.Timestamp.now("UTC").isoformat() + "Z",
        "sources": {
            "geometry": WFS_URL,
            "timeseries": HYDROCRON_URL,
            "collection_name": "SWOT_L2_HR_LakeSP_2.0",
            "basin_outline": "PUBLISHED/data/hydroclimate/basins-level10.geojson (dissolved)",
        },
        "min_lake_area_km2": MIN_LAKE_AREA_KM2,
        "n_lakes_total": len(inventory),
        "n_lakes_with_data": int((pd.DataFrame(summary_rows)["n_overpasses"] > 0).sum()) if summary_rows else 0,
        "n_named_reservoirs_attempted": len(NAMED_RESERVOIRS),
        "n_named_reservoirs": sum(
            1 for r in summary_rows if r["name"] and r["n_overpasses"] > 0
        ),
        "named_reservoirs_without_data": [
            meta["name"] for pid, meta in NAMED_RESERVOIRS.items()
            if pid in {f["pld_id"] for f in failed}
            or not any(r["pld_id"] == pid and r["n_overpasses"] > 0 for r in summary_rows)
        ],
        "n_fetch_failures": len(failed),
        "identification_method": "named reservoirs matched by nearest PLD polygon to known coordinates "
                                  "and full-pool area; not an authoritative name crosswalk (PLD has no names). "
                                  "Every other lake is unnamed, identified by PLD id and location only.",
        "dropped_candidates": ["Andijan", "Tuyamuyun"],
        "dropped_reason": "no PLD polygon matched both position and plausible area with enough confidence to publish as named",
        "quality_filtering": "dropped quality_f==3 (bad); WSE outliers beyond median +/- max(20m, 6*MAD) dropped "
                              "per lake; area_total aggregated to monthly MAX (not mean) because a single SWOT "
                              "pass frequently images only part of a large lake — a partial pass can only "
                              "under-count true extent, never over-count it.",
    }
    (OUT_DIR / "reservoir_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nDone. {len(inventory)} lakes processed, {len(failed)} failures. Outputs in {OUT_DIR}")


if __name__ == "__main__":
    sys.exit(main())
