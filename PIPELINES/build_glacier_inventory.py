"""Build the transboundary glacier inventory for the runoff-formation layer.

GLIMS is a multi-temporal archive: one `glac_id` can carry several outlines from
different survey dates, and `intrnl_rock` polygons describe rock outcrops inside
those outlines. Summing the raw collection therefore double counts ice. This
pipeline keeps the latest `src_date` per glacier, subtracts the matching internal
rock, and publishes the relationships the formation layer needs:

* glacier -> level-10 / level-12 subbasin (exact vector intersection);
* glacier -> elevation band (SRTM raster mask, rescaled to the vector area);
* subbasin x elevation band -> glacier area (analysis-ready cross tabulation).

A glacier outline is an inventory of a fixed survey epoch, never a state
observation of the current water year.

    python PIPELINES/build_glacier_inventory.py
    python PIPELINES/build_glacier_inventory.py --systems upper_syr_darya
    python PIPELINES/build_glacier_inventory.py --refresh-geometry --refresh-stats
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Geod
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from build_headwater_pilot import sha256, write_json

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "ONTOLOGY/vocab/hydroclimate-system.json"
SYSTEMS = ROOT / "PUBLISHED/data/hydroclimate/headwater-systems.geojson"
SYSTEM_BANDS = ROOT / "PUBLISHED/data/hydroclimate/headwater-elevation-bands.csv"
BASIN_SOURCE = ROOT / "GEODATA/transboundary_basins_v2"
GEODATA_DIR = ROOT / "GEODATA/glaciers_headwaters_v1"
CACHE_DIR = ROOT / "WORKSPACE/glacier_inventory_cache"
PUBLISHED_DIR = ROOT / "PUBLISHED/data/hydroclimate"
PROJECT = "ee-sabitovty"
DEM_ASSET = "USGS/SRTMGL1_003"
GLACIER_SCALE = 30
BASIN_SCALE = 90
GLACIER_CHUNK = 750
UPLOAD_CHUNK = 200
BASIN_CHUNK = 150
SYSTEM_LEVEL = 10  # operational level that decides formation-zone membership
MINIMUM_PIECE_KM2 = 1e-6
DOWNLOAD_TIMEOUT = 1800
GEOD = Geod(ellps="WGS84")

OUTLINE_FIELDS = [
    "glac_id", "glac_name", "src_date", "anlys_time", "anlys_id", "subm_id", "rc_id",
    "db_area", "min_elev", "mean_elev", "max_elev", "glac_stat", "rec_status",
    "rgi_gl_typ", "gtng_o1reg", "gtng_o2reg", "primeclass", "surge_type", "term_type",
    "local_id", "wgms_id",
]
ROCK_FIELDS = ["glac_id", "src_date", "anlys_id"]
ATTRIBUTION_FIELDS = [
    "subm_id", "rc_id", "analysts", "submitters", "chief_affl", "geog_area",
    "release_dt", "proc_desc",
]
INVENTORY_FIELDS = [
    "glacier_id", "system_id", "river_system_id", "glacier_name", "survey_date",
    "analysis_date", "area_km2", "area_in_headwater_km2", "share_in_headwater_percent",
    "outline_area_km2", "internal_rock_area_km2",
    "reported_area_km2", "elevation_min_m", "elevation_mean_m", "elevation_max_m",
    "elevation_range_m", "dominant_elevation_band", "centroid_longitude",
    "centroid_latitude", "hybas_id_level10", "hybas_id_level12",
    "subbasin_count_level10", "glims_submission_id", "glims_analysis_id", "glims_rc_id",
    "rgi_region_o1", "rgi_region_o2", "glacier_status", "record_status", "source_asset",
    "dem_asset", "scale_m", "quality", "retrieved_at",
]
GLACIER_BAND_FIELDS = [
    "glacier_id", "system_id", "river_system_id", "elevation_band",
    "minimum_m_inclusive", "maximum_m_exclusive", "area_km2", "share_percent",
    "method", "scale_m", "retrieved_at",
]
LINK_FIELDS = [
    "glacier_id", "system_id", "river_system_id", "basin_level", "hybas_id",
    "in_headwater_formation", "area_km2", "share_of_glacier_percent",
    "is_primary_subbasin", "method", "retrieved_at",
]
BASIN_BAND_FIELDS = [
    "observation_unit_id", "basin_level", "system_id", "river_system_id", "hybas_id",
    "in_headwater_formation", "elevation_band", "minimum_m_inclusive",
    "maximum_m_exclusive", "basin_band_area_km2", "glacier_area_km2",
    "glacier_share_of_band_percent", "basin_area_km2", "basin_glacier_area_km2",
    "method", "basin_scale_m", "glacier_scale_m", "retrieved_at",
]
SYSTEM_BAND_FIELDS = [
    "observation_unit_id", "system_id", "river_system_id", "elevation_band",
    "minimum_m_inclusive", "maximum_m_exclusive", "glacier_count", "glacier_area_km2",
    "band_area_km2", "glacier_share_of_band_percent",
    "share_of_system_glacier_area_percent", "source_asset", "survey_date_min",
    "survey_date_max", "scale_m", "retrieved_at",
]
ATTRIBUTION_CSV_FIELDS = [
    "system_id", "glims_submission_id", "glims_rc_id", "analysts", "submitters",
    "chief_affiliation", "geographic_area", "release_date", "glacier_count",
    "glacier_area_km2", "survey_date_min", "survey_date_max", "processing_description",
]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def with_retry(label: str, call, attempts: int = 4):
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception as error:  # long Earth Engine runs hit transient failures
            if attempt == attempts:
                raise
            pause = 15 * attempt
            print(f"      retry {label}: {type(error).__name__} {str(error)[:110]} (sleep {pause}s)", flush=True)
            time.sleep(pause)


def geodesic_area_km2(geometry) -> float:
    if geometry.is_empty:
        return 0.0
    return abs(GEOD.geometry_area_perimeter(geometry)[0]) / 1e6


def repaired(geometry):
    return geometry if geometry.is_valid else geometry.buffer(0)


def text(value) -> str:
    """GLIMS writes the literal string "None" where an attribute is absent."""
    cleaned = str(value).strip() if value is not None else ""
    return "" if cleaned in {"", "None", "none", "NULL"} else cleaned


def number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def band_mask(dem, band: dict):
    import ee

    mask = ee.Image(1)
    if band["minimum"] is not None:
        mask = mask.And(dem.gte(band["minimum"]))
    if band["maximum"] is not None:
        mask = mask.And(dem.lt(band["maximum"]))
    return mask


def elevation_stack(bands: list[dict]):
    """Pixel area, elevation and per-band pixel area for polygon reductions."""
    import ee

    dem = ee.Image(DEM_ASSET).select("elevation")
    pixel_area = ee.Image.pixelArea()
    images = [
        pixel_area.rename("area_total"),
        dem.rename("dem"),
        dem.multiply(pixel_area).rename("dem_weighted"),
    ]
    for band in bands:
        images.append(pixel_area.updateMask(band_mask(dem, band)).rename(f"area__{band['id']}"))
    return ee.Image.cat(images)


def outline_selection(asset: str, geometry):
    """Latest GLIMS survey per glacier inside the system boundary."""
    import ee

    return (
        ee.FeatureCollection(asset)
        .filterBounds(geometry)
        .filter(ee.Filter.eq("line_type", "glac_bound"))
        .sort("src_date", False)
        .distinct(["glac_id"])
    )


def rock_selection(asset: str, geometry):
    """Internal rock outcrops of the retained outline of the same glacier and date."""
    import ee

    def keyed(feature):
        return feature.set(
            "join_key",
            ee.String(feature.get("glac_id")).cat("|").cat(ee.String(feature.get("src_date"))),
        )

    outlines = outline_selection(asset, geometry).map(keyed)
    rock = (
        ee.FeatureCollection(asset)
        .filterBounds(geometry)
        .filter(ee.Filter.eq("line_type", "intrnl_rock"))
        .map(keyed)
    )
    joined = ee.Join.inner().apply(
        rock, outlines, ee.Filter.equals(leftField="join_key", rightField="join_key")
    )
    return ee.FeatureCollection(joined.map(lambda feature: ee.Feature(feature.get("primary"))))


def reduce_polygons(collection, size: int, stack, bands: list[dict], label: str) -> list[dict]:
    """Chunked reduceRegions; the 5000-element getInfo ceiling forces slicing."""
    import ee

    reducer = ee.Reducer.sum().combine(ee.Reducer.minMax(), sharedInputs=True)
    selectors = [
        "glac_id", "area_total_sum", "dem_min", "dem_max", "dem_weighted_sum",
        *[f"area__{band['id']}_sum" for band in bands],
    ]
    listed = collection.toList(size)
    rows: list[dict] = []
    for start in range(0, size, GLACIER_CHUNK):
        count = min(GLACIER_CHUNK, size - start)
        subset = ee.FeatureCollection(listed.slice(start, start + count))
        reduced = stack.reduceRegions(
            collection=subset, reducer=reducer, scale=GLACIER_SCALE, tileScale=4
        ).select(selectors, retainGeometry=False)
        document = with_retry(f"{label}@{start}", lambda: reduced.getInfo())
        rows.extend(feature["properties"] for feature in document["features"])
        print(f"      {label} {min(start + count, size):,}/{size:,}", flush=True)
    return rows


def reduce_downloaded(features: list[dict], stack, bands: list[dict], label: str) -> list[dict]:
    """Reduce polygons that are already on disk.

    The internal-rock selection is an inner join, and Earth Engine re-runs that
    join inside every reduction it appears in — enough to exceed the user memory
    limit on the Amu Darya collection. Sending the downloaded geometry back keeps
    the reduction to what it actually measures.
    """
    import ee

    reducer = ee.Reducer.sum().combine(ee.Reducer.minMax(), sharedInputs=True)
    selectors = [
        "glac_id", "area_total_sum", "dem_min", "dem_max", "dem_weighted_sum",
        *[f"area__{band['id']}_sum" for band in bands],
    ]
    rows: list[dict] = []
    for start in range(0, len(features), UPLOAD_CHUNK):
        batch = features[start : start + UPLOAD_CHUNK]
        collection = ee.FeatureCollection([
            ee.Feature(ee.Geometry(feature["geometry"]), {"glac_id": feature["properties"]["glac_id"]})
            for feature in batch
        ])
        reduced = stack.reduceRegions(
            collection=collection, reducer=reducer, scale=GLACIER_SCALE, tileScale=8
        ).select(selectors, retainGeometry=False)
        document = with_retry(f"{label}@{start}", lambda: reduced.getInfo())
        rows.extend(feature["properties"] for feature in document["features"])
        print(f"      {label} {min(start + len(batch), len(features)):,}/{len(features):,}", flush=True)
    return rows


def reduce_basins(ids: list[int], asset: str, stack, bands: list[dict], label: str) -> list[dict]:
    """Elevation-band areas of whole subbasins; native geometry stays server side."""
    import ee

    source = ee.FeatureCollection(asset)
    band_names = ["area_total", *[f"area__{band['id']}" for band in bands]]
    rows: list[dict] = []
    for start in range(0, len(ids), BASIN_CHUNK):
        batch = ids[start : start + BASIN_CHUNK]
        subset = source.filter(ee.Filter.inList("HYBAS_ID", batch))
        reduced = stack.select(band_names).reduceRegions(
            collection=subset, reducer=ee.Reducer.sum(), scale=BASIN_SCALE, tileScale=4
        ).select(["HYBAS_ID", "SUB_AREA", *band_names], retainGeometry=False)
        document = with_retry(f"{label}@{start}", lambda: reduced.getInfo())
        rows.extend(feature["properties"] for feature in document["features"])
        print(f"      {label} {min(start + len(batch), len(ids)):,}/{len(ids):,}", flush=True)
    return rows


def load_or_fetch(path: Path, refresh: bool, fetch):
    if path.exists() and not refresh:
        print(f"    reuse {path.relative_to(ROOT)} ({path.stat().st_size / 1e6:.1f} MB)")
        return json.loads(path.read_text(encoding="utf-8"))
    payload = fetch()
    write_json(path, payload, compact=True)
    print(f"    wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1e6:.1f} MB)")
    return payload


def download_geojson(collection, fields: list[str]) -> dict:
    """Table download with a long read timeout.

    Earth Engine runs the query while the download URL is being read, and the
    internal-rock join over the whole Amu Darya collection needs far more than
    the five minutes the shared pilot helper allows.
    """
    import requests

    url = collection.getDownloadURL(filetype="GeoJSON", selectors=[".geo", *fields])
    response = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
    response.raise_for_status()
    document = response.json()
    if document.get("type") != "FeatureCollection":
        raise RuntimeError("Earth Engine did not return a GeoJSON FeatureCollection")
    return document


def download_or_empty(collection, fields: list[str], label: str) -> dict:
    document = with_retry(label, lambda: download_geojson(collection, fields))
    if not document["features"]:
        print(f"      {label}: no features returned")
    return document


def basin_index(level: int) -> dict[str, dict]:
    """Exact HydroATLAS geometry per river system, indexed for spatial queries."""
    path = BASIN_SOURCE / f"hydroatlas-level{level:02d}-full-basins.geojson"
    if not path.exists():
        raise SystemExit(f"Missing {path.relative_to(ROOT)}; run npm run basins:transboundary first")
    grouped: dict[str, dict] = {}
    for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
        props = feature["properties"]
        entry = grouped.setdefault(props["system_id"], {"geometries": [], "records": []})
        entry["geometries"].append(repaired(shape(feature["geometry"])))
        entry["records"].append({
            "hybas_id": int(props["HYBAS_ID"]),
            "in_headwater_formation": bool(props["in_headwater_formation"]),
            "sub_area_km2": number(props.get("SUB_AREA")),
        })
    for entry in grouped.values():
        entry["tree"] = STRtree(entry["geometries"])
    return grouped


def band_for_elevation(bands: list[dict], elevation: float | None) -> str:
    if elevation is None:
        return ""
    for band in bands:
        below = band["minimum"] is None or elevation >= band["minimum"]
        above = band["maximum"] is None or elevation < band["maximum"]
        if below and above:
            return band["id"]
    return ""


def read_system_band_areas() -> dict[tuple[str, str], float]:
    if not SYSTEM_BANDS.exists():
        return {}
    with SYSTEM_BANDS.open(encoding="utf-8", newline="") as handle:
        return {
            (row["system_id"], row["elevation_band"]): number(row["area_km2"])
            for row in csv.DictReader(handle)
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--systems", nargs="+", help="headwater system ids; default all")
    parser.add_argument("--levels", nargs="+", type=int, default=[10, 12])
    parser.add_argument("--refresh-geometry", action="store_true", help="re-download GLIMS outlines")
    parser.add_argument("--refresh-stats", action="store_true", help="recompute Earth Engine reductions")
    parser.add_argument("--web-tolerance", type=float, default=0.0005, help="published outline simplification, degrees")
    args = parser.parse_args()
    levels = sorted(set(args.levels))
    if any(level not in {10, 12} for level in levels):
        raise SystemExit("Glacier links are defined for HydroATLAS levels 10 and 12")
    if SYSTEM_LEVEL not in levels:
        raise SystemExit(f"Level {SYSTEM_LEVEL} decides formation-zone membership and cannot be skipped")

    try:
        import ee

        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
    except Exception as error:
        raise SystemExit(
            f"Earth Engine unavailable: {str(error).strip()[:180]}\n"
            f"  Run: earthengine authenticate --project {PROJECT}"
        ) from error

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    inventory_config = config["glacierInventory"]
    asset = inventory_config["asset"]
    bands = config["elevationBandsMetres"]
    band_ids = [band["id"] for band in bands]
    band_by_id = {band["id"]: band for band in bands}
    system_features = json.loads(SYSTEMS.read_text(encoding="utf-8"))["features"]
    wanted = set(args.systems or [f["properties"]["system_id"] for f in system_features])
    unknown = wanted.difference(f["properties"]["system_id"] for f in system_features)
    if unknown:
        raise SystemExit(f"Unknown headwater systems: {', '.join(sorted(unknown))}")

    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    stack = elevation_stack(bands)
    system_band_areas = read_system_band_areas()
    print(f"Glacier inventory | {asset} | levels {levels} | {GLACIER_SCALE} m glacier, {BASIN_SCALE} m basin")
    basins_by_level = {level: basin_index(level) for level in levels}
    for level in levels:
        print(f"  level {level}: {sum(len(entry['records']) for entry in basins_by_level[level].values()):,} basin polygons")

    inventory_rows: list[dict] = []
    glacier_band_rows: list[dict] = []
    link_rows: list[dict] = []
    basin_band_rows: list[dict] = []
    system_band_rows: list[dict] = []
    attribution_rows: list[dict] = []
    web_features: list[dict] = []
    system_summaries: list[dict] = []
    exact_outputs: list[dict] = []

    for feature in system_features:
        props = feature["properties"]
        system_id = props["system_id"]
        if system_id not in wanted:
            continue
        river_system_id = props["river_system_id"]
        geometry = ee.Geometry(feature["geometry"])
        outlines = outline_selection(asset, geometry)
        rocks = rock_selection(asset, geometry)
        print(f"  {system_id}")

        outline_path = GEODATA_DIR / f"glims-{system_id}-outlines.geojson"
        rock_path = GEODATA_DIR / f"glims-{system_id}-internal-rock.geojson"
        outline_doc = load_or_fetch(
            outline_path, args.refresh_geometry,
            lambda: download_or_empty(outlines, OUTLINE_FIELDS, f"{system_id} outlines"),
        )
        rock_doc = load_or_fetch(
            rock_path, args.refresh_geometry,
            lambda: download_or_empty(rocks, ROCK_FIELDS, f"{system_id} internal rock"),
        )
        outline_count = len(outline_doc["features"])
        rock_count = len(rock_doc["features"])
        if not outline_count:
            raise SystemExit(f"{system_id}: GLIMS returned no glacier outlines")
        print(f"    {outline_count:,} glacier outlines, {rock_count:,} internal rock polygons")

        # Each pass is cached on its own: the glacier reduction takes half an
        # hour on the Amu Darya and must not be lost when a later pass fails.
        measured_outlines = load_or_fetch(
            CACHE_DIR / f"{system_id}-glacier-elevation-stats.json",
            args.refresh_stats,
            lambda: reduce_polygons(outlines, outline_count, stack, bands, f"{system_id} glaciers"),
        )
        measured_rock = load_or_fetch(
            CACHE_DIR / f"{system_id}-rock-elevation-stats.json",
            args.refresh_stats,
            lambda: reduce_downloaded(rock_doc["features"], stack, bands, f"{system_id} rock"),
        ) if rock_count else []
        attribution = load_or_fetch(
            CACHE_DIR / f"{system_id}-source-attribution.json",
            args.refresh_stats,
            lambda: with_retry(
                f"{system_id} attribution",
                lambda: outlines.distinct(["subm_id", "rc_id"])
                .select(ATTRIBUTION_FIELDS, retainGeometry=False)
                .getInfo(),
            )["features"],
        )

        outline_stats = {row["glac_id"]: row for row in measured_outlines}
        rock_stats: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for row in measured_rock:
            target = rock_stats[row["glac_id"]]
            target["area_total_sum"] += number(row.get("area_total_sum"))
            target["dem_weighted_sum"] += number(row.get("dem_weighted_sum"))
            for band_id in band_ids:
                target[f"area__{band_id}_sum"] += number(row.get(f"area__{band_id}_sum"))

        rock_geometries: dict[str, list] = defaultdict(list)
        for rock_feature in rock_doc["features"]:
            rock_geometries[rock_feature["properties"]["glac_id"]].append(
                repaired(shape(rock_feature["geometry"]))
            )

        glacier_area_by_band: dict[str, float] = defaultdict(float)
        glacier_count_by_band: dict[str, int] = defaultdict(int)
        basin_glacier_bands: dict[tuple[int, int, str], float] = defaultdict(float)
        basin_glacier_total: dict[tuple[int, int], float] = defaultdict(float)
        glacier_band_areas: dict[str, dict[str, float]] = {}
        pending_pieces: dict[int, list[tuple]] = {level: [] for level in levels}
        linked_ids: dict[int, set[int]] = {level: set() for level in levels}
        submission_totals: dict[tuple, dict] = {}
        system_area = 0.0
        survey_dates: list[str] = []
        outline_area_total = 0.0
        rock_area_total = 0.0

        for position, glacier_feature in enumerate(outline_doc["features"], start=1):
            glacier = glacier_feature["properties"]
            glacier_id = glacier["glac_id"]
            outline_geometry = repaired(shape(glacier_feature["geometry"]))
            rock_parts = rock_geometries.get(glacier_id)
            net_geometry = outline_geometry
            if rock_parts:
                net_geometry = repaired(outline_geometry.difference(unary_union(rock_parts)))
            outline_area = geodesic_area_km2(outline_geometry)
            area_km2 = geodesic_area_km2(net_geometry)
            if area_km2 <= 0:
                continue
            rock_area = max(outline_area - area_km2, 0.0)
            outline_area_total += outline_area
            rock_area_total += rock_area

            measured = outline_stats.get(glacier_id, {})
            subtracted = rock_stats.get(glacier_id, {})
            raster_bands = {
                band_id: max(
                    number(measured.get(f"area__{band_id}_sum")) - subtracted.get(f"area__{band_id}_sum", 0.0),
                    0.0,
                )
                for band_id in band_ids
            }
            raster_total = sum(raster_bands.values())
            raster_area = max(
                number(measured.get("area_total_sum")) - subtracted.get("area_total_sum", 0.0), 0.0
            )
            weighted = number(measured.get("dem_weighted_sum")) - subtracted.get("dem_weighted_sum", 0.0)
            elevation_mean = weighted / raster_area if raster_area > 0 else None
            elevation_min = measured.get("dem_min")
            elevation_max = measured.get("dem_max")
            reported_min = number(glacier.get("min_elev"))
            reported_mean = number(glacier.get("mean_elev"))

            quality = "ok-inventory"
            if raster_total > 0:
                areas = {
                    band_id: area_km2 * raster_bands[band_id] / raster_total for band_id in band_ids
                }
            else:
                # Glaciers smaller than a DEM pixel keep their area but fall back to
                # the reported elevation for the band assignment.
                fallback = elevation_mean or reported_mean or reported_min or elevation_min
                fallback_band = band_for_elevation(bands, fallback if fallback else None)
                areas = {band_id: 0.0 for band_id in band_ids}
                if fallback_band:
                    areas[fallback_band] = area_km2
                    quality = "elevation-band-from-reported-elevation"
                else:
                    quality = "elevation-band-unresolved"

            dominant = max(band_ids, key=lambda band_id: areas[band_id]) if areas else ""
            if areas.get(dominant, 0.0) <= 0:
                dominant = ""
            glacier_band_areas[glacier_id] = areas
            for band_id in band_ids:
                if areas[band_id] <= 0:
                    continue
                band = band_by_id[band_id]
                glacier_band_rows.append({
                    "glacier_id": glacier_id,
                    "system_id": system_id,
                    "river_system_id": river_system_id,
                    "elevation_band": band_id,
                    "minimum_m_inclusive": "" if band["minimum"] is None else band["minimum"],
                    "maximum_m_exclusive": "" if band["maximum"] is None else band["maximum"],
                    "area_km2": f"{areas[band_id]:.6f}",
                    "share_percent": f"{areas[band_id] / area_km2 * 100:.4f}",
                    "method": "srtm_band_mask_rescaled_to_vector_area",
                    "scale_m": GLACIER_SCALE,
                    "retrieved_at": retrieved,
                })
            primary = {}
            subbasin_counts = {}
            headwater_area = 0.0
            for level in levels:
                entry = basins_by_level[level].get(river_system_id)
                if entry is None:
                    continue
                candidates = entry["tree"].query(net_geometry, predicate="intersects")
                pieces = []
                for index in candidates:
                    piece = net_geometry.intersection(entry["geometries"][int(index)])
                    piece_area = geodesic_area_km2(piece)
                    if piece_area < MINIMUM_PIECE_KM2:
                        # A square-metre sliver is disagreement between two datasets
                        # along a shared divide, not a glacier in that subbasin.
                        continue
                    pieces.append((piece_area, entry["records"][int(index)]))
                if not pieces:
                    continue
                pieces.sort(key=lambda item: item[0], reverse=True)
                subbasin_counts[level] = len(pieces)
                primary[level] = pieces[0][1]["hybas_id"]
                for piece_area, record in pieces:
                    share = piece_area / area_km2
                    hybas_id = record["hybas_id"]
                    linked_ids[level].add(hybas_id)
                    basin_glacier_total[(level, hybas_id)] += piece_area
                    # The band split of a single intersection is only resolved once the
                    # subbasin's own elevation is measured, so the pieces are kept and
                    # split after the subbasin reduction below.
                    pending_pieces[level].append(
                        (glacier_id, hybas_id, piece_area, bool(record["in_headwater_formation"]))
                    )
                    # A glacier on the outer divide belongs to the formation zone only
                    # by the part that drains into it, so system totals use the clipped
                    # area of the operational level rather than the whole outline.
                    if level == SYSTEM_LEVEL and record["in_headwater_formation"]:
                        headwater_area += piece_area
                    link_rows.append({
                        "glacier_id": glacier_id,
                        "system_id": system_id,
                        "river_system_id": river_system_id,
                        "basin_level": level,
                        "hybas_id": hybas_id,
                        "in_headwater_formation": int(record["in_headwater_formation"]),
                        "area_km2": f"{piece_area:.6f}",
                        "share_of_glacier_percent": f"{share * 100:.4f}",
                        "is_primary_subbasin": int(record["hybas_id"] == pieces[0][1]["hybas_id"]),
                        "method": "vector_intersection",
                        "retrieved_at": retrieved,
                    })

            if headwater_area > 0:
                system_area += headwater_area
                if dominant:
                    glacier_count_by_band[dominant] += 1

            centroid = net_geometry.centroid
            survey_date = (glacier.get("src_date") or "")[:10]
            if survey_date:
                survey_dates.append(survey_date)
            submission_key = (glacier.get("subm_id"), glacier.get("rc_id"))
            totals = submission_totals.setdefault(
                submission_key, {"count": 0, "area": 0.0, "dates": []}
            )
            totals["count"] += 1
            totals["area"] += area_km2
            if survey_date:
                totals["dates"].append(survey_date)

            inventory_rows.append({
                "glacier_id": glacier_id,
                "system_id": system_id,
                "river_system_id": river_system_id,
                "glacier_name": text(glacier.get("glac_name")),
                "survey_date": survey_date,
                "analysis_date": (glacier.get("anlys_time") or "")[:10],
                "area_km2": f"{area_km2:.6f}",
                "area_in_headwater_km2": f"{headwater_area:.6f}",
                "share_in_headwater_percent": f"{headwater_area / area_km2 * 100:.4f}",
                "outline_area_km2": f"{outline_area:.6f}",
                "internal_rock_area_km2": f"{rock_area:.6f}",
                "reported_area_km2": f"{number(glacier.get('db_area')):.6f}",
                "elevation_min_m": "" if elevation_min is None else f"{number(elevation_min):.0f}",
                "elevation_mean_m": "" if elevation_mean is None else f"{elevation_mean:.0f}",
                "elevation_max_m": "" if elevation_max is None else f"{number(elevation_max):.0f}",
                "elevation_range_m": (
                    f"{number(elevation_max) - number(elevation_min):.0f}"
                    if elevation_min is not None and elevation_max is not None
                    else ""
                ),
                "dominant_elevation_band": dominant,
                "centroid_longitude": f"{centroid.x:.5f}",
                "centroid_latitude": f"{centroid.y:.5f}",
                "hybas_id_level10": primary.get(10, ""),
                "hybas_id_level12": primary.get(12, ""),
                "subbasin_count_level10": subbasin_counts.get(10, ""),
                "glims_submission_id": glacier.get("subm_id") or "",
                "glims_analysis_id": glacier.get("anlys_id") or "",
                "glims_rc_id": glacier.get("rc_id") or "",
                "rgi_region_o1": glacier.get("gtng_o1reg") or "",
                "rgi_region_o2": glacier.get("gtng_o2reg") or "",
                "glacier_status": text(glacier.get("glac_stat")),
                "record_status": text(glacier.get("rec_status")),
                "source_asset": asset,
                "dem_asset": DEM_ASSET,
                "scale_m": GLACIER_SCALE,
                "quality": quality,
                "retrieved_at": retrieved,
            })
            web_features.append({
                "type": "Feature",
                "properties": {
                    "glacier_id": glacier_id,
                    "system_id": system_id,
                    "river_system_id": river_system_id,
                    "area_km2": round(area_km2, 4),
                    "area_in_headwater_km2": round(headwater_area, 4),
                    "elevation_min_m": None if elevation_min is None else int(number(elevation_min)),
                    "elevation_max_m": None if elevation_max is None else int(number(elevation_max)),
                    "dominant_elevation_band": dominant,
                    "hybas_id_level10": primary.get(10, None),
                    "survey_date": survey_date,
                },
                "geometry": mapping(
                    net_geometry.simplify(args.web_tolerance, preserve_topology=True)
                ),
            })
            if position % 2500 == 0:
                print(f"      linked {position:,}/{outline_count:,}", flush=True)

        for record in attribution:
            source = record["properties"]
            key = (source.get("subm_id"), source.get("rc_id"))
            totals = submission_totals.get(key, {"count": 0, "area": 0.0, "dates": []})
            dates = sorted(totals["dates"])
            attribution_rows.append({
                "system_id": system_id,
                "glims_submission_id": source.get("subm_id") or "",
                "glims_rc_id": source.get("rc_id") or "",
                "analysts": text(source.get("analysts")),
                "submitters": text(source.get("submitters")),
                "chief_affiliation": text(source.get("chief_affl")),
                "geographic_area": text(source.get("geog_area")),
                "release_date": (source.get("release_dt") or "")[:10],
                "glacier_count": totals["count"],
                "glacier_area_km2": f"{totals['area']:.4f}",
                "survey_date_min": dates[0] if dates else "",
                "survey_date_max": dates[-1] if dates else "",
                "processing_description": text(source.get("proc_desc")).replace("\n", " "),
            })

        needed = {level: sorted(linked_ids[level] | {
            record["hybas_id"]
            for record in basins_by_level[level].get(river_system_id, {"records": []})["records"]
            if record["in_headwater_formation"]
        }) for level in levels}
        for level in levels:
            asset_name = f"WWF/HydroATLAS/v1/Basins/level{level:02d}"
            cache_path = CACHE_DIR / f"{system_id}-basin-bands-level{level:02d}.json"
            measured = load_or_fetch(
                cache_path,
                args.refresh_stats,
                lambda level=level, ids=needed[level], name=asset_name: reduce_basins(
                    ids, name, stack, bands, f"{system_id} L{level} basins"
                ),
            )
            records = {
                record["hybas_id"]: record
                for record in basins_by_level[level].get(river_system_id, {"records": []})["records"]
            }
            capacity = {
                int(row["HYBAS_ID"]): {
                    band["id"]: number(row.get(f"area__{band['id']}")) / 1e6 for band in bands
                }
                for row in measured
            }
            # Split every glacier-subbasin intersection across the elevation bands the
            # subbasin actually has. Distributing a glacier's own band split by area
            # share alone can place ice above 4000 m in a subbasin that has almost no
            # ground there; weighting by the subbasin's band area keeps the exact
            # intersection area while putting it where that elevation exists.
            for glacier_id, hybas_id, piece_area, inside in pending_pieces[level]:
                split = glacier_band_areas.get(glacier_id, {})
                available = capacity.get(hybas_id, {})
                weights = {
                    band_id: split.get(band_id, 0.0) * available.get(band_id, 0.0)
                    for band_id in band_ids
                }
                total_weight = sum(weights.values())
                if total_weight <= 0:
                    weights = {band_id: split.get(band_id, 0.0) for band_id in band_ids}
                    total_weight = sum(weights.values())
                if total_weight <= 0:
                    continue
                for band_id in band_ids:
                    if weights[band_id] <= 0:
                        continue
                    allocated = piece_area * weights[band_id] / total_weight
                    basin_glacier_bands[(level, hybas_id, band_id)] += allocated
                    if level == SYSTEM_LEVEL and inside:
                        glacier_area_by_band[band_id] += allocated

            for row in measured:
                hybas_id = int(row["HYBAS_ID"])
                record = records.get(hybas_id, {"in_headwater_formation": False})
                basin_area = number(row.get("area_total")) / 1e6
                basin_glacier = basin_glacier_total.get((level, hybas_id), 0.0)
                for band in bands:
                    band_area = number(row.get(f"area__{band['id']}")) / 1e6
                    glacier_area = basin_glacier_bands.get((level, hybas_id, band["id"]), 0.0)
                    if band_area <= 0 and glacier_area <= 0:
                        continue
                    basin_band_rows.append({
                        "observation_unit_id": f"{hybas_id}::{band['id']}",
                        "basin_level": level,
                        "system_id": system_id,
                        "river_system_id": river_system_id,
                        "hybas_id": hybas_id,
                        "in_headwater_formation": int(record["in_headwater_formation"]),
                        "elevation_band": band["id"],
                        "minimum_m_inclusive": "" if band["minimum"] is None else band["minimum"],
                        "maximum_m_exclusive": "" if band["maximum"] is None else band["maximum"],
                        "basin_band_area_km2": f"{band_area:.4f}",
                        "glacier_area_km2": f"{glacier_area:.6f}",
                        "glacier_share_of_band_percent": (
                            f"{glacier_area / band_area * 100:.4f}" if band_area > 0 else ""
                        ),
                        "basin_area_km2": f"{basin_area:.4f}",
                        "basin_glacier_area_km2": f"{basin_glacier:.6f}",
                        "method": "vector_intersection_split_by_subbasin_elevation_band",
                        "basin_scale_m": BASIN_SCALE,
                        "glacier_scale_m": GLACIER_SCALE,
                        "retrieved_at": retrieved,
                    })

        dates = sorted(survey_dates)
        for band in bands:
            band_id = band["id"]
            glacier_area = glacier_area_by_band.get(band_id, 0.0)
            band_area = system_band_areas.get((system_id, band_id))
            system_band_rows.append({
                "observation_unit_id": f"{system_id}::{band_id}",
                "system_id": system_id,
                "river_system_id": river_system_id,
                "elevation_band": band_id,
                "minimum_m_inclusive": "" if band["minimum"] is None else band["minimum"],
                "maximum_m_exclusive": "" if band["maximum"] is None else band["maximum"],
                "glacier_count": glacier_count_by_band.get(band_id, 0),
                "glacier_area_km2": f"{glacier_area:.4f}",
                "band_area_km2": "" if band_area is None else f"{band_area:.3f}",
                "glacier_share_of_band_percent": (
                    f"{glacier_area / band_area * 100:.4f}" if band_area else ""
                ),
                "share_of_system_glacier_area_percent": (
                    f"{glacier_area / system_area * 100:.4f}" if system_area else ""
                ),
                "source_asset": asset,
                "survey_date_min": dates[0] if dates else "",
                "survey_date_max": dates[-1] if dates else "",
                "scale_m": GLACIER_SCALE,
                "retrieved_at": retrieved,
            })

        system_summaries.append({
            "systemId": system_id,
            "riverSystemId": river_system_id,
            "glacierCount": sum(
                1 for row in inventory_rows
                if row["system_id"] == system_id and float(row["area_in_headwater_km2"]) > 0
            ),
            "intersectingGlacierCount": sum(1 for row in inventory_rows if row["system_id"] == system_id),
            "glacierAreaKm2": round(system_area, 3),
            "intersectingGlacierAreaKm2": round(outline_area_total - rock_area_total, 3),
            "outlineAreaKm2": round(outline_area_total, 3),
            "internalRockAreaKm2": round(rock_area_total, 3),
            "internalRockPolygons": rock_count,
            "surveyDateRange": [dates[0], dates[-1]] if dates else [],
            "glacierAreaByBandKm2": {
                band_id: round(glacier_area_by_band.get(band_id, 0.0), 3) for band_id in band_ids
            },
            "linkedSubbasins": {str(level): len(linked_ids[level]) for level in levels},
        })
        exact_outputs.extend([
            {
                "path": str(outline_path.relative_to(ROOT)).replace("\\", "/"),
                "features": outline_count,
                "sha256": sha256(outline_path),
            },
            {
                "path": str(rock_path.relative_to(ROOT)).replace("\\", "/"),
                "features": rock_count,
                "sha256": sha256(rock_path),
            },
        ])
        print(
            f"    {system_area:,.1f} km2 glacier area inside the formation zone "
            f"({outline_area_total - rock_area_total:,.1f} km2 of intersecting outlines) "
            f"over {len(linked_ids[SYSTEM_LEVEL]):,} level-{SYSTEM_LEVEL} subbasins"
        )

    inventory_rows.sort(key=lambda row: (row["system_id"], row["glacier_id"]))
    glacier_band_rows.sort(key=lambda row: (row["system_id"], row["glacier_id"], row["elevation_band"]))
    link_rows.sort(key=lambda row: (row["basin_level"], row["system_id"], row["glacier_id"], row["hybas_id"]))
    basin_band_rows.sort(key=lambda row: (row["basin_level"], row["system_id"], row["hybas_id"], row["elevation_band"]))
    system_band_rows.sort(key=lambda row: (row["system_id"], row["elevation_band"]))
    attribution_rows.sort(key=lambda row: (row["system_id"], str(row["glims_submission_id"])))
    web_features.sort(key=lambda item: (item["properties"]["system_id"], item["properties"]["glacier_id"]))

    inventory_path = PUBLISHED_DIR / "glacier-inventory-headwaters.csv"
    glacier_band_path = PUBLISHED_DIR / "glacier-elevation-bands.csv"
    link_path = PUBLISHED_DIR / "glacier-basin-links.csv"
    basin_band_path = PUBLISHED_DIR / "glacier-basin-elevation-bands.csv"
    system_band_path = PUBLISHED_DIR / "glacier-headwater-systems.csv"
    attribution_path = PUBLISHED_DIR / "glacier-source-attribution.csv"
    web_path = PUBLISHED_DIR / "glaciers-headwaters.geojson"
    summary_path = PUBLISHED_DIR / "glacier-headwater-systems.json"
    manifest_path = PUBLISHED_DIR / "glaciers-headwaters.manifest.json"

    write_csv(inventory_path, INVENTORY_FIELDS, inventory_rows)
    write_csv(glacier_band_path, GLACIER_BAND_FIELDS, glacier_band_rows)
    write_csv(link_path, LINK_FIELDS, link_rows)
    write_csv(basin_band_path, BASIN_BAND_FIELDS, basin_band_rows)
    write_csv(system_band_path, SYSTEM_BAND_FIELDS, system_band_rows)
    write_csv(attribution_path, ATTRIBUTION_CSV_FIELDS, attribution_rows)
    write_json(
        web_path,
        {"type": "FeatureCollection", "name": "glims_headwater_glaciers", "features": web_features},
        compact=True,
    )
    write_json(
        summary_path,
        {
            "version": "1.0",
            "spatialScope": "headwater_formation",
            "observationClass": "inventory",
            "systems": system_summaries,
            "bands": system_band_rows,
        },
        compact=True,
    )

    manifest = {
        "version": "1.0",
        "generatedAt": retrieved,
        "spatialScope": "headwater_formation",
        "observationClass": "inventory",
        "source": {
            "platform": "Google Earth Engine",
            "asset": asset,
            "snapshot": inventory_config.get("snapshot"),
            "demAsset": DEM_ASSET,
            "glacierScaleMetres": GLACIER_SCALE,
            "basinScaleMetres": BASIN_SCALE,
            "catalogUrl": inventory_config.get("catalogUrl"),
        },
        "selection": {
            "outlineFilter": "line_type == glac_bound",
            "deduplication": "latest src_date per glac_id",
            "internalRock": "intrnl_rock polygons of the same glac_id and src_date are subtracted",
            "spatialFilter": "intersects the headwater_formation system polygon",
        },
        "systems": system_summaries,
        "counts": {
            "glaciers": len(inventory_rows),
            "distinctGlaciers": len({row["glacier_id"] for row in inventory_rows}),
            "glaciersSharedBetweenSystems": (
                len(inventory_rows) - len({row["glacier_id"] for row in inventory_rows})
            ),
            "glacierBandRows": len(glacier_band_rows),
            "basinLinks": len(link_rows),
            "basinBandRows": len(basin_band_rows),
            "sourceSubmissions": len(attribution_rows),
        },
        "levels": levels,
        "outputs": {
            "inventoryCSV": str(inventory_path.relative_to(ROOT)).replace("\\", "/"),
            "glacierElevationBandCSV": str(glacier_band_path.relative_to(ROOT)).replace("\\", "/"),
            "basinLinkCSV": str(link_path.relative_to(ROOT)).replace("\\", "/"),
            "basinElevationBandCSV": str(basin_band_path.relative_to(ROOT)).replace("\\", "/"),
            "systemCSV": str(system_band_path.relative_to(ROOT)).replace("\\", "/"),
            "attributionCSV": str(attribution_path.relative_to(ROOT)).replace("\\", "/"),
            "webGeoJSON": str(web_path.relative_to(ROOT)).replace("\\", "/"),
            "summaryJSON": str(summary_path.relative_to(ROOT)).replace("\\", "/"),
            "exactGeoJSON": exact_outputs,
        },
        "semantics": {
            "identity": (
                "glacier_id is the GLIMS glac_id; a row is keyed by system_id and "
                "glacier_id because a glacier on the Amu-Syr divide feeds both systems"
            ),
            "area": "geodesic vector area of the retained outline minus internal rock",
            "areaInHeadwater": (
                f"part of the glacier inside level-{SYSTEM_LEVEL} subbasins of the formation zone; "
                "system and elevation-band totals use this clipped area"
            ),
            "elevationBands": "SRTM band masks at 30 m, rescaled so band areas sum to the vector area",
            "basinAttribution": "exact vector intersection; a glacier crossing a divide appears once per subbasin",
            "basinBandAttribution": "each glacier-subbasin intersection keeps its exact area and is split across bands by the glacier band split weighted by the band area the subbasin has",
            "temporalStatus": "survey epoch inventory, not a current-year state observation",
        },
        "qualityNotes": [
            "GLIMS is multi-temporal: only the latest src_date per glac_id is retained.",
            "Internal rock outcrops are removed so glacier area is ice area, not outline area.",
            "Survey dates differ between submissions; survey_date is published per glacier.",
            "Subbasin band areas are 90 m SRTM sums while glacier band areas are 30 m sums, so a "
            "small subbasin can report a glacier share slightly above 100 percent of a band.",
            "Glaciers on the outer divide are inventoried in full and attributed to the formation "
            "zone only by the intersecting part; area_in_headwater_km2 carries that share.",
            "A glacier astride the Amu-Syr divide appears once per system with the same outline, "
            "so area_km2 must be summed over system_id and glacier_id together, never over "
            "glacier_id alone. area_in_headwater_km2 does not double count.",
        ],
    }
    write_json(manifest_path, manifest, compact=False)

    print(
        f"  {len(inventory_rows):,} glaciers | {len(link_rows):,} subbasin links | "
        f"{len(basin_band_rows):,} basin-band rows | {web_path.stat().st_size / 1e6:.1f} MB web layer"
    )


if __name__ == "__main__":
    main()
