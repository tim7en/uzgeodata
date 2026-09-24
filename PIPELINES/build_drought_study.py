"""Basin drought study: water-year precipitation, SPI and PDSI against 10/20/30-year norms.

Source is one product version end to end: producer TerraClimate v1.1, 1960-2025,
reduced to all 7,445 level-12 basins (extract_regional_climate_grids.py
terraclimate-v11 --family terraclimate-v1.1-history). Nothing here splices v1.0,
v1.1 and ERA estimates into one series.

Water year N runs October N-1 to September N, the convention of Central Asian
water management; precipitation falls mostly October-May and feeds the
following irrigation season.

Norms per unit and water year:
  wmo_1991_2020   fixed WMO climatological standard normal
  early_1961_1990 the previous standard normal, to show the shift between them
  trailing_10/20/30  mean of the 10/20/30 water years before the year in question

SPI-12 is a gamma distribution fitted to 1991-2020 water-year totals, converted
to a standard normal deviate (McKee et al. 1993). It is fitted on each unit's own
totals, so a level-7 SPI comes from the level-7 total, not an average of SPIs.

Upstream supply: runoff generation q and precipitation are accumulated over each
basin's whole upstream area. TerraClimate q is a one-bucket water balance with no
glacier melt and no reservoir regulation, so the upstream q anomaly is a supply
signal from rain and snow only, not a flow forecast.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIPELINES.model_regional_climate_continuation import accumulate_one  # noqa: E402

HISTORY = ROOT / "PUBLISHED/data/atlas/climate-continuation/terraclimate-v1.1-history"
GEO = ROOT / "GEODATA/transboundary_basins_v2"
ADMIN = ROOT / "GEODATA/uzb_admbnda_adm1_2018b/uzb_admbnda_adm1_2018b.shp"
OUT = ROOT / "PUBLISHED/data/atlas/drought-study"
WMO = (1991, 2020)
EARLY = (1961, 1990)
TRAILING = (10, 20, 30)
# Documented events, with the source that names them. The study reports where each
# lands in the data; it does not use them to fit anything.
DOCUMENTED = [
    {"water_year": 2000, "kind": "dry", "source": "CAWater PEER Amu Darya key findings",
     "url": "https://www.cawater-info.net/projects/peer-amudarya/key_findings_e.htm"},
    {"water_year": 2001, "kind": "dry", "source": "CAWater PEER Amu Darya key findings; FAO drought characteristics in Central Asia",
     "url": "https://www.cawater-info.net/projects/peer-amudarya/key_findings_e.htm"},
    {"water_year": 2008, "kind": "dry", "source": "CAWater PEER Amu Darya key findings",
     "url": "https://www.cawater-info.net/projects/peer-amudarya/key_findings_e.htm"},
    {"water_year": 2021, "kind": "dry", "source": "2021 Central Asia drought (Kazakhstan, Kyrgyzstan, Turkmenistan, Uzbekistan)",
     "url": "https://en.wikipedia.org/wiki/2021_Central_Asia_drought"},
    {"water_year": 1969, "kind": "wet", "source": "1969 Amu Darya flood (Karataw dam failure, Beruni flooded)",
     "url": "https://rsaa.org.uk/blog/remembering-the-amu-darya/"},
    {"water_year": 1998, "kind": "wet", "source": "Lower Amu Darya high-water year (water-quality record)",
     "url": "https://www.researchgate.net/publication/352087422_Assessment_of_water_quality_in_the_downstream_of_the_Amu_Darya_basin"},
]


def monthly_to_water_years():
    """Water-year sums (ppt, q, pet) and mean PDSI per level-12 basin; complete years only."""
    con = duckdb.connect()
    frame = con.execute(f"""
      WITH m AS (
        SELECT basin_id, variable, value,
               CASE WHEN month >= 10 THEN year + 1 ELSE year END AS water_year
        FROM read_parquet('{HISTORY / 'year=*.parquet'}')
      )
      SELECT basin_id, water_year,
        sum(value) FILTER (WHERE variable='ppt') ppt,
        sum(value) FILTER (WHERE variable='q') q,
        sum(value) FILTER (WHERE variable='pet') pet,
        avg(value) FILTER (WHERE variable='PDSI') pdsi,
        count(*) FILTER (WHERE variable='ppt') AS n_months
      FROM m GROUP BY 1, 2
    """).df()
    frame = frame[frame.n_months == 12].drop(columns="n_months")
    first, last = int(frame.water_year.min()), int(frame.water_year.max())
    if last < 2025 or first > EARLY[0]:
        raise ValueError(f"History covers water years {first}-{last}; need {EARLY[0]}-2025")
    return frame


def spi(totals, years):
    """SPI of each total against a gamma fit on the WMO-period totals (zeros handled as a point mass)."""
    reference = totals[(years >= WMO[0]) & (years <= WMO[1])]
    reference = reference[np.isfinite(reference)]
    if len(reference) < 25 or reference.max() <= 0:
        return np.full(len(totals), np.nan)
    zero = np.mean(reference <= 0)
    positive = reference[reference > 0]
    shape, _, scale = stats.gamma.fit(positive, floc=0)
    cdf = zero + (1 - zero) * stats.gamma.cdf(np.maximum(totals, 0), shape, scale=scale)
    return stats.norm.ppf(np.clip(cdf, 1e-6, 1 - 1e-6))


def metrics(frame, unit):
    """Norms, anomalies and SPI for every (unit, water_year) row of frame."""
    parts = []
    for _, group in frame.sort_values([unit, "water_year"]).groupby(unit, sort=False):
        group = group.copy()
        years = group.water_year.to_numpy()
        for column in ("ppt", "q", "pdsi"):
            values = group[column].to_numpy(dtype=float)
            wmo = values[(years >= WMO[0]) & (years <= WMO[1])].mean()
            early = values[(years >= EARLY[0]) & (years <= EARLY[1])].mean()
            group[f"{column}_wmo"] = wmo
            group[f"{column}_early"] = early
            for window in TRAILING:
                group[f"{column}_trailing_{window}"] = (
                    pd.Series(values).shift(1).rolling(window, min_periods=window).mean().to_numpy())
        group["spi12"] = spi(group.ppt.to_numpy(dtype=float), years)
        parts.append(group)
    result = pd.concat(parts, ignore_index=True)
    for column in ("ppt", "q"):
        for norm in ("wmo", "early", *(f"trailing_{w}" for w in TRAILING)):
            base = result[f"{column}_{norm}"]
            result[f"{column}_anom_pct_{norm}"] = np.where(base > 0, (result[column] - base) / base * 100, np.nan)
    for norm in ("wmo", *(f"trailing_{w}" for w in TRAILING)):
        result[f"pdsi_diff_{norm}"] = result.pdsi - result[f"pdsi_{norm}"]
    return result


def area_weighted(frame, keys, lookup):
    """Aggregate level-12 depths to larger units by SUB_AREA weight; lookup maps basin_id to the unit keys."""
    joined = frame.merge(lookup[["basin_id", "area_km2", *[k for k in keys if k != "water_year"]]], on="basin_id")
    for column in ("ppt", "q", "pet", "pdsi"):
        joined[column] = joined[column] * joined.area_km2
    grouped = joined.groupby(keys)[["ppt", "q", "pet", "pdsi", "area_km2"]].sum().reset_index()
    for column in ("ppt", "q", "pet", "pdsi"):
        grouped[column] = grouped[column] / grouped.area_km2
    return grouped


def upstream(frame, basins):
    """Upstream-area mean of ppt and q for each basin and water year."""
    below = dict(zip(basins.basin_id, basins.next_down.where(basins.next_down != "0")))
    area = dict(zip(basins.basin_id, basins.area_km2))
    indegree = {b: 0 for b in basins.basin_id}
    for b, d in below.items():
        if d in indegree:
            indegree[d] += 1
        else:
            below[b] = None
    queue, order = deque(b for b, n in indegree.items() if n == 0), []
    while queue:
        b = queue.popleft()
        order.append(b)
        d = below[b]
        if d:
            indegree[d] -= 1
            if indegree[d] == 0:
                queue.append(d)
    rows = []
    for year, group in frame.groupby("water_year"):
        results = {c: accumulate_one(dict(zip(group.basin_id, group[c])), order, below, area)
                   for c in ("ppt", "q")}
        for b in order:
            rows.append({"basin_id": b, "water_year": int(year),
                         "up_ppt": results["ppt"][b]["mean"], "up_q": results["q"][b]["mean"],
                         "up_area_km2": results["ppt"][b]["area_km2"],
                         "up_q_mcm": results["q"][b]["integral_mcm"]})
    return pd.DataFrame(rows)


def simplified_paths(geo, key, tolerance):
    """SVG path strings in an equal-scale lon/lat projection shared by every map."""
    geo = geo.copy()
    geo["geometry"] = geo.geometry.simplify(tolerance, preserve_topology=True)
    paths = {}
    for ident, geometry in zip(geo[key], geo.geometry):
        polygons = geometry.geoms if geometry.geom_type == "MultiPolygon" else [geometry]
        parts = []
        for polygon in polygons:
            ring = polygon.exterior.coords
            parts.append("M" + "L".join(f"{x:.3f},{-y:.3f}" for x, y in ring) + "Z")
        paths[str(ident)] = "".join(parts)
    return paths


def records(frame, columns):
    return [[None if (isinstance(v, float) and not np.isfinite(v)) else
             (round(v, 3) if isinstance(v, float) else v) for v in row]
            for row in frame[columns].itertuples(index=False, name=None)]


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    geo12 = gpd.read_file(GEO / "hydroatlas-level12-full-basins.geojson")
    basins = pd.DataFrame({
        "basin_id": geo12.HYBAS_ID.astype("int64").astype(str),
        "next_down": geo12.NEXT_DOWN.astype("int64").astype(str),
        "area_km2": geo12.SUB_AREA, "up_area_hydroatlas": geo12.UP_AREA,
        "system_id": geo12.system_id, "headwater": geo12.in_headwater_formation.astype(bool),
        "level07": geo12.PFAF_ID.astype("int64").astype(str).str[:7],
    })
    wy = monthly_to_water_years()
    print(f"Water years {wy.water_year.min()}-{wy.water_year.max()}, {wy.basin_id.nunique()} basins", flush=True)

    # Level-12: local metrics plus upstream supply.
    local12 = metrics(wy, "basin_id")
    up = upstream(wy, basins)
    up = up.merge(metrics(up.rename(columns={"up_ppt": "ppt", "up_q": "q"}).assign(pdsi=np.nan),
                          "basin_id")[["basin_id", "water_year", "ppt_anom_pct_wmo", "q_anom_pct_wmo", "spi12"]]
                  .rename(columns={"ppt_anom_pct_wmo": "up_ppt_anom_pct_wmo",
                                   "q_anom_pct_wmo": "up_q_anom_pct_wmo", "spi12": "up_spi12"}),
                  on=["basin_id", "water_year"])
    level12 = local12.merge(up, on=["basin_id", "water_year"])
    level12.to_parquet(OUT / "basin-wateryear.parquet", compression="zstd", index=False)
    print(f"Level-12 table: {len(level12):,} rows", flush=True)

    # Level-7 units and whole systems, from area-weighted depths (SPI refitted on the aggregate).
    level07 = metrics(area_weighted(wy, ["level07", "water_year"], basins), "level07")
    systems = metrics(area_weighted(wy, ["system_id", "water_year"], basins), "system_id")
    zones = metrics(area_weighted(wy, ["system_id", "headwater", "water_year"], basins)
                    .assign(zone=lambda f: f.system_id + np.where(f.headwater, ":headwater", ":lowland")), "zone")

    # Uzbekistan regions: local conditions over the region, and the upstream supply of
    # the largest river reach that passes through it.
    admin = gpd.read_file(ADMIN).to_crs(4326)
    points = gpd.GeoDataFrame(basins, geometry=geo12.geometry.representative_point(), crs=geo12.crs).to_crs(4326)
    inside = gpd.sjoin(points, admin[["ADM1_EN", "ADM1_PCODE", "geometry"]], predicate="within")
    region_basins = inside[["basin_id", "ADM1_EN", "ADM1_PCODE"]]
    local_region = metrics(area_weighted(wy, ["ADM1_PCODE", "water_year"],
                                         region_basins.merge(basins[["basin_id", "area_km2"]])), "ADM1_PCODE")
    reach = (inside.sort_values("up_area_hydroatlas", ascending=False)
             .groupby("ADM1_PCODE").head(1)[["ADM1_PCODE", "ADM1_EN", "basin_id", "system_id", "up_area_hydroatlas"]])
    region = local_region.merge(reach, on="ADM1_PCODE").merge(
        level12[["basin_id", "water_year", "up_q_anom_pct_wmo", "up_ppt_anom_pct_wmo", "up_spi12", "up_q_mcm"]],
        on=["basin_id", "water_year"])

    # Where documented events land in the data.
    checks = []
    for event in DOCUMENTED:
        for system, group in systems.groupby("system_id"):
            ranked = group.sort_values("spi12").reset_index(drop=True)
            row = group[group.water_year == event["water_year"]]
            if row.empty:
                continue
            row = row.iloc[0]
            checks.append({**event, "system_id": system, "spi12": row.spi12,
                           "ppt_anom_pct_wmo": row.ppt_anom_pct_wmo, "pdsi": row.pdsi,
                           "q_anom_pct_wmo": row.q_anom_pct_wmo,
                           "dry_rank": int(ranked.index[ranked.water_year == event["water_year"]][0]) + 1,
                           "years": len(group)})

    # Severity over the WMO-and-after period, per level-7 unit.
    recent = level07[level07.water_year >= WMO[0]]
    severity = recent.groupby("level07").agg(
        severe_years=("spi12", lambda s: int((s <= -1.5).sum())),
        moderate_years=("spi12", lambda s: int((s <= -1.0).sum())),
        wet_years=("spi12", lambda s: int((s >= 1.0).sum())),
        worst_spi=("spi12", "min"),
        worst_year=("spi12", lambda s: int(recent.loc[s.idxmin(), "water_year"])),
    ).reset_index()
    shift = level07.groupby("level07").agg(ppt_wmo=("ppt_wmo", "first"), ppt_early=("ppt_early", "first"),
                                           pdsi_wmo=("pdsi_wmo", "first")).reset_index()
    shift["norm_shift_pct"] = (shift.ppt_wmo - shift.ppt_early) / shift.ppt_early * 100
    severity = severity.merge(shift, on="level07")

    geo07 = gpd.read_file(GEO / "hydroatlas-level07-full-basins.geojson")
    geo07["level07"] = geo07.PFAF_ID.astype("int64").astype(str)
    centre = gpd.GeoDataFrame(geo07[["level07"]], geometry=geo07.geometry.representative_point(), crs=geo07.crs)
    in_region = dict(gpd.sjoin(centre.to_crs(4326), admin[["ADM1_EN", "geometry"]], predicate="within")
                     [["level07", "ADM1_EN"]].itertuples(index=False, name=None))
    unit_info = {r.level07: {"system": r.system_id, "headwater": bool(r.in_headwater_formation),
                             "area_km2": r.SUB_AREA, "up_area_km2": r.UP_AREA,
                             "lon": round(c.x, 2), "lat": round(c.y, 2), "region": in_region.get(r.level07)}
                 for r, c in zip(geo07.itertuples(), centre.geometry)}
    level07_columns = ["level07", "water_year", "ppt", "spi12", "pdsi",
                       "ppt_anom_pct_wmo", "ppt_anom_pct_trailing_10", "ppt_anom_pct_trailing_20",
                       "ppt_anom_pct_trailing_30", "ppt_anom_pct_early",
                       "pdsi_diff_wmo", "pdsi_diff_trailing_10", "pdsi_diff_trailing_20", "pdsi_diff_trailing_30"]
    series_columns = ["water_year", "ppt", "ppt_wmo", "ppt_trailing_10", "ppt_trailing_20", "ppt_trailing_30",
                      "ppt_anom_pct_wmo", "spi12", "pdsi", "q", "q_anom_pct_wmo"]
    region_columns = ["ADM1_PCODE", "ADM1_EN", "system_id", "water_year", "ppt", "ppt_anom_pct_wmo", "spi12",
                      "pdsi", "up_q_anom_pct_wmo", "up_ppt_anom_pct_wmo", "up_spi12", "up_q_mcm"]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "TerraClimate v1.1 producer NetCDF, fractional-overlap basin means",
        "water_year": "October to September, labelled by the ending year",
        "water_years": [int(wy.water_year.min()), int(wy.water_year.max())],
        "norms": {"wmo": list(WMO), "early": list(EARLY), "trailing": list(TRAILING)},
        "spi": "gamma fit to 1991-2020 water-year totals per unit; SPI <= -1 moderate, <= -1.5 severe, <= -2 extreme drought",
        "caveats": [
            "TerraClimate is a gridded model product, not station observations.",
            "q is one-bucket runoff generation with no glacier melt or reservoir regulation; upstream q anomalies are rain-and-snow supply signals, not river flow.",
            "Trailing norms need 10/20/30 earlier water years, so they start in 1971/1981/1991.",
        ],
        "systems": {s: records(g, series_columns) for s, g in systems.groupby("system_id")},
        "zones": {s: records(g, series_columns) for s, g in zones.groupby("zone")},
        "series_columns": series_columns,
        "documented": checks,
        "level07_columns": level07_columns,
        "level07": records(level07, level07_columns),
        "severity_columns": list(severity.columns),
        "severity": records(severity, list(severity.columns)),
        "units": unit_info,
        "region_columns": region_columns,
        "regions": records(region.sort_values(["ADM1_EN", "water_year"]), region_columns),
        "reaches": {r.ADM1_PCODE: {"basin_id": r.basin_id, "up_area_km2": r.up_area_hydroatlas, "system": r.system_id}
                    for r in reach.itertuples()},
    }
    (OUT / "summary.json").write_text(json.dumps(report, separators=(",", ":"), allow_nan=False) + "\n")
    geometry = {
        "level07": simplified_paths(geo07, "level07", 0.03),
        "regions": simplified_paths(admin.assign(code=admin.ADM1_PCODE), "code", 0.03),
        "bounds": list(geo07.total_bounds),
    }
    (OUT / "geometry.json").write_text(json.dumps(geometry, separators=(",", ":")) + "\n")
    level07.to_parquet(OUT / "level07-wateryear.parquet", compression="zstd", index=False)
    region.to_parquet(OUT / "regions-wateryear.parquet", compression="zstd", index=False)
    print(f"Drought study written: {len(level07):,} level-7 rows, {len(region):,} region rows", flush=True)
    for check in checks:
        print(f"  {check['water_year']} {check['kind']:3} {check['system_id']:10} SPI {check['spi12']:+.2f} "
              f"P {check['ppt_anom_pct_wmo']:+.0f}% PDSI {check['pdsi']:+.2f} rank {check['dry_rank']}/{check['years']}")


if __name__ == "__main__":
    build()
