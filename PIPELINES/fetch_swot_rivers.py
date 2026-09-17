#!/usr/bin/env python3
"""Fetch SWOT-observed river reach level/width data for every named river in
the Aral Sea drainage basin (Syr Darya + Amu Darya + the closed Zeravshan
basin), extending the lake/reservoir monitoring case study
(fetch_swot_reservoirs.py) to the rivers themselves -- Panj, Vakhsh, Naryn
and the rest are wide enough for SWOT's KaRIn radar to resolve as distinct
reaches.

Data sources (both public, no authentication required -- verified live,
same two endpoints already used for lakes):
- Hydroweb GeoServer (CNES/Theia), WFS: reach geometry and prior (SWORD)
  attributes for every reach in the SWOT Prior River Database.
  https://hydroweb.next.theia-land.fr/geoserver/REF_DATA/ows
- PO.DAAC Hydrocron API: per-overpass time series (water surface elevation,
  width, slope) for any SWORD reach_id.
  https://soto.podaac.earthdatacloud.nasa.gov/hydrocron/v1/timeseries

Study-area scope: reaches are kept only if their geometry intersects the
real Aral Sea drainage outline (the same dissolved HydroBASINS level-10
outline the lake fetch uses) AND SWORD assigns them a river_name -- an
unnamed reach is typically a short headwater or braid strand not
informative to monitor on its own. Unlike lakes (kept by area), rivers have
no comparable size field in the prior database that is reliable across the
whole reach network, so "has a name" is the inclusion criterion instead.

Several rivers appear under multiple SWORD spellings or reach roles
(Amu Darya / Amudarya / Amudaryo; Panj / Panj river / anabranch Panj; Naryn
/ Naryn River) -- these are merged into one canonical river group in
`river_group`, and each group is tagged with the sub-basin it drains
(Syr Darya, Amu Darya, or the Zeravshan closed basin, which no longer
reaches either river after upstream diversion).

Quality: the reach quality flag is `reach_q` here, not `quality_f` (that
name is valid for lakes only and Hydrocron 400s on it for the River
collection). Verified live against a spread of reaches across every major
named river before building this pipeline: reach_q of 0/1/2 carry real
wse/width readings, reach_q==3 is fill-valued and dropped, matching the
lake pipeline's quality_f==3 treatment.

Usage:
    python PIPELINES/fetch_swot_rivers.py
"""
from __future__ import annotations

import io
import json
import re
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
OUT_DIR = ROOT / "PUBLISHED/data/case-studies/rivers"
OUT_DIR.mkdir(parents=True, exist_ok=True)
BASIN_FILE = ROOT / "PUBLISHED/data/hydroclimate/basins-level10.geojson"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
WFS_URL = "https://hydroweb.next.theia-land.fr/geoserver/REF_DATA/ows"
HYDROCRON_URL = "https://soto.podaac.earthdatacloud.nasa.gov/hydrocron/v1/timeseries"
START_TIME = "2023-01-01T00:00:00Z"
FILL_VALUE = -999999999999.0
REQUEST_PAUSE_S = 0.3

# Canonical river group <- every SWORD spelling/role seen inside the basin
# outline. Anything not listed keeps its own SWORD name as its group.
RIVER_GROUP_ALIASES = {
    "amudaryo": "Amu Darya", "amudarya": "Amu Darya", "amu darya": "Amu Darya",
    "panj": "Panj", "panj river": "Panj", "anabranch panj": "Panj",
    "naryn": "Naryn", "naryn river": "Naryn",
    "vakhsh river": "Vakhsh", "vakhsh": "Vakhsh",
    "kofarnihon river": "Kofarnihon", "kofarnihon": "Kofarnihon",
    "chirciq": "Chirchik", "chirchik": "Chirchik",
    "kara darya": "Kara Darya",
    "zeravshan": "Zeravshan", "zarafshan": "Zeravshan",
    "qaradarya (zarafshan)": "Qaradarya (Zeravshan tributary)",
}

# Sub-basin each river group drains. Zeravshan is its own closed basin: it
# was historically an Amu Darya tributary but has not reached it since
# upstream irrigation diversion, so it is not grouped under Amu Darya here.
BASIN_OF_RIVER = {
    "Syr Darya": "Syr Darya", "Naryn": "Syr Darya", "Kara Darya": "Syr Darya",
    "Chirchik": "Syr Darya", "Chatkal": "Syr Darya", "Ohangaron": "Syr Darya",
    "Sokh": "Syr Darya", "Qaradarya": "Syr Darya",
    "Amu Darya": "Amu Darya", "Panj": "Amu Darya", "Vakhsh": "Amu Darya",
    "Kofarnihon": "Amu Darya", "Surxondaryo": "Amu Darya",
    "Kunduz River": "Amu Darya", "Kokcha River": "Amu Darya",
    "Obikhingou": "Amu Darya",
    "Zeravshan": "Zeravshan (closed basin)",
    "Qaradarya (Zeravshan tributary)": "Zeravshan (closed basin)",
}


def river_group(raw_name: str) -> str | None:
    if not raw_name or not isinstance(raw_name, str):
        return None
    name = raw_name.strip()
    if not name or name.upper() == "NODATA":
        return None
    return RIVER_GROUP_ALIASES.get(name.lower(), name)


def basin_of(group: str) -> str:
    return BASIN_OF_RIVER.get(group, "Aral Sea drainage (unclassified tributary)")


class NotFound(Exception):
    """Hydrocron's deterministic response for a real feature_id with no
    passing observations in the time window -- reported as an HTTP 400, not
    a 404, and indistinguishable from a transient error by status code
    alone. Retrying it wastes the backoff schedule on every reach that
    genuinely just has no data (common: short/unnamed-adjacent SWORD
    reaches), so it is raised as its own exception and never retried."""


def http_get_json(url: str, retries: int = 4, timeout: int = 90) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", "replace")
            if error.code == 400 and "were not found" in body:
                raise NotFound(body) from None
            last_error = error
            time.sleep(3 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            time.sleep(3 * (attempt + 1))
    raise last_error


def load_basin_polygon():
    gdf = gpd.read_file(BASIN_FILE)
    return gdf.union_all()


def fetch_named_reaches(basin_poly) -> gpd.GeoDataFrame:
    """Every SWORD reach with a river_name whose geometry intersects the
    real basin outline (not its bounding rectangle)."""
    west, south, east, north = basin_poly.bounds
    rows = []
    start_index = 0
    page = 500
    while True:
        params = {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": "swot_prior_river_db",
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
            props = f["properties"]
            group = river_group(props.get("river_name"))
            if group is None:
                continue
            try:
                geom = shape(f["geometry"])
            except Exception:
                continue
            if not geom.intersects(basin_poly):
                continue
            c = geom.centroid
            rows.append({
                "reach_id": str(props.get("reach_id")),
                "river_name_raw": props.get("river_name"),
                "river_group": group,
                "basin": basin_of(group),
                "p_length_m": props.get("p_length"),
                "p_wse_m": props.get("p_wse"),
                "p_width_m": props.get("p_width"),
                "p_slope": props.get("p_slope"),
                "p_dist_out_m": props.get("p_dist_out"),
                "lon": c.x, "lat": c.y,
                "geometry": geom,
            })
        start_index += page
        print(f"  WFS page at startIndex={start_index}: {len(rows)} named reaches matched so far", flush=True)
        if len(feats) < page:
            break
        time.sleep(REQUEST_PAUSE_S)
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def fetch_reach_timeseries(reach_id: str) -> pd.DataFrame:
    params = {
        "feature": "Reach",
        "feature_id": reach_id,
        "start_time": START_TIME,
        "end_time": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "output": "csv",
        "collection_name": "SWOT_L2_HR_RiverSP_2.0",
        "fields": "reach_id,time_str,wse,width,slope,reach_q,partial_f",
    }
    url = HYDROCRON_URL + "?" + urllib.parse.urlencode(params)
    try:
        data = http_get_json(url)
    except NotFound:
        # A real reach with zero passing observations in the window -- not a
        # fetch failure, just an empty record (see NotFound's docstring).
        return pd.DataFrame()
    csv_text = data.get("results", {}).get("csv", "")
    if not csv_text.strip():
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(csv_text))
    df = df[df["time_str"] != "no_data"].copy()
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time_str"], utc=True, errors="coerce")
    for col in ("wse", "width", "slope"):
        df.loc[df[col] <= FILL_VALUE / 2, col] = pd.NA
    df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)

    # reach_q: 0 good, 1 suspect, 2 degraded, 3 bad (verified live: 3 carries
    # only fill values across every reach sampled). Drop 3, keep the rest,
    # same threshold as the lake pipeline's quality_f==3 exclusion.
    df = df[df["reach_q"] != 3].copy()
    df["wse_outlier"] = False
    if df["wse"].notna().sum() > 4:
        median = df["wse"].median()
        mad = (df["wse"] - median).abs().median()
        threshold = max(5.0, 6 * 1.4826 * mad)
        df["wse_outlier"] = (df["wse"] - median).abs() > threshold
    return df.reset_index(drop=True)


def monthly_median(series: pd.DataFrame, reach_id: str) -> pd.DataFrame:
    if series.empty:
        return series
    clean_wse = series["wse"].where(~series["wse_outlier"])
    monthly = series.assign(wse=clean_wse).set_index("time").resample("MS").agg(
        wse=("wse", "median"),
        width=("width", "median"),
        n_overpasses=("wse", "size"),
    ).dropna(subset=["wse", "width"], how="all").reset_index()
    monthly["reach_id"] = reach_id
    return monthly


def main() -> None:
    print("Loading the real Aral Sea drainage basin outline...")
    basin_poly = load_basin_polygon()

    print("\nFetching and clipping the named SWORD reach inventory against the real basin polygon...")
    inventory = fetch_named_reaches(basin_poly)
    inventory.drop(columns="geometry").to_csv(OUT_DIR / "reach_inventory.csv", index=False)
    inventory.to_file(OUT_DIR / "reaches_prior.geojson", driver="GeoJSON")
    group_counts = inventory["river_group"].value_counts()
    print(f"  {len(inventory)} named reaches across {inventory['river_group'].nunique()} rivers inside the basin")
    print(group_counts.to_string())

    print(f"\nFetching SWOT time series for all {len(inventory)} reaches "
          f"(long-running batch call to a public API; progress saved incrementally)...")
    monthly_path = OUT_DIR / "river_timeseries_monthly.csv"
    summary_path = OUT_DIR / "river_summary.csv"
    raw_path = OUT_DIR / "river_observations_raw.csv"
    monthly_rows, summary_rows, raw_rows, failed = [], [], [], []

    for i, row in enumerate(inventory.itertuples(), 1):
        reach_id = row.reach_id
        try:
            series = fetch_reach_timeseries(reach_id)
        except Exception as error:
            failed.append({"reach_id": reach_id, "error": str(error)})
            print(f"  [{i}/{len(inventory)}] {reach_id}: FAILED ({error})", flush=True)
            time.sleep(REQUEST_PAUSE_S)
            continue

        n_good = int((series["reach_q"] <= 1).sum()) if len(series) else 0
        monthly = monthly_median(series, reach_id) if len(series) else pd.DataFrame()

        summary_rows.append({
            "reach_id": reach_id,
            "river_group": row.river_group,
            "basin": row.basin,
            "river_name_raw": row.river_name_raw,
            "lon": row.lon, "lat": row.lat,
            "p_width_m": row.p_width_m, "p_wse_m": row.p_wse_m, "p_length_m": row.p_length_m,
            "n_overpasses": len(series),
            "n_good_or_suspect": n_good,
            "n_months": len(monthly),
            "first_obs": series["time"].min().isoformat() if len(series) else None,
            "last_obs": series["time"].max().isoformat() if len(series) else None,
            "latest_wse_m": float(monthly["wse"].dropna().iloc[-1]) if len(monthly) and monthly["wse"].notna().any() else None,
            "latest_width_m": float(monthly["width"].dropna().iloc[-1]) if len(monthly) and monthly["width"].notna().any() else None,
        })
        if len(monthly):
            monthly_rows.append(monthly)
        if len(series):
            raw = series[["time", "wse", "width", "slope", "partial_f", "wse_outlier", "reach_q"]].copy()
            raw.insert(0, "reach_id", reach_id)
            raw_rows.append(raw)

        print(f"  [{i}/{len(inventory)}] {row.river_group} ({reach_id}): {len(series)} overpasses, "
              f"{n_good} good/suspect, {len(monthly)} months", flush=True)

        if i % 50 == 0 or i == len(inventory):
            pd.concat(monthly_rows, ignore_index=True).to_csv(monthly_path, index=False) if monthly_rows else None
            pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
            pd.concat(raw_rows, ignore_index=True).to_csv(raw_path, index=False) if raw_rows else None

        time.sleep(REQUEST_PAUSE_S)

    if failed:
        pd.DataFrame(failed).to_csv(OUT_DIR / "fetch_failures.csv", index=False)
        print(f"\n{len(failed)} reaches failed after retries; see fetch_failures.csv")

    summary_df = pd.DataFrame(summary_rows)
    manifest = {
        "generated": pd.Timestamp.now("UTC").isoformat() + "Z",
        "sources": {
            "geometry": WFS_URL, "timeseries": HYDROCRON_URL,
            "collection_name": "SWOT_L2_HR_RiverSP_2.0",
            "basin_outline": "PUBLISHED/data/hydroclimate/basins-level10.geojson (dissolved)",
        },
        "n_reaches_total": len(inventory),
        "n_rivers": int(inventory["river_group"].nunique()),
        "n_reaches_with_data": int((summary_df["n_overpasses"] > 0).sum()) if len(summary_df) else 0,
        "n_reaches_with_good_data": int((summary_df["n_good_or_suspect"] >= 5).sum()) if len(summary_df) else 0,
        "n_fetch_failures": len(failed),
        "rivers": group_counts.to_dict(),
        "inclusion_rule": "reach intersects the real basin polygon AND SWORD assigns it a river_name "
                           "(no reliable size field exists for reaches across the whole network the way "
                           "p_ref_area does for lakes, so name presence is the filter instead).",
        "quality_filtering": "dropped reach_q==3 (fill-valued on every reach sampled); WSE outliers beyond "
                              "median +/- max(5m, 6*MAD) flagged (not dropped) per reach; monthly aggregation "
                              "uses the median of quality-passing overpasses.",
    }
    (OUT_DIR / "river_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nDone. {len(inventory)} reaches processed, {len(failed)} failures. Outputs in {OUT_DIR}")


if __name__ == "__main__":
    sys.exit(main())
