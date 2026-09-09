"""Open-data surrogate adapters for the Pskem pilot.

Every builder here produces an independent estimate from an open dataset. None of
them reproduces an atlas attribute, and none of them ever reads a reference value.
Builders return values in the surrogate's own physical units; the runner applies the
registry conversion factor before any comparison. Field construction, resolution
handling and the reduction statistic stay explicit so that a future geodatabase can
record how each number was made.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Geod
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from ATLAS_MODULES.core.runtime import sha256, write_json, utc_now

CELL = 15 / 3600
GEOD = Geod(ellps="WGS84")
NODATA = -9999.0
CLIMATOLOGY = ("1991-01-01", "2021-01-01")
DAYS_PER_MONTH = (31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
SECONDS_PER_YEAR = 365.25 * 86400

# Copernicus discrete classes -> GLC2000 legend positions. Shrubs are assigned to the
# deciduous shrub class because deciduous shrubland dominates the Western Tien Shan;
# the Copernicus legend does not resolve shrub phenology.
GLC2000_FROM_COPERNICUS = {
    112: 1, 122: 1, 114: 2, 124: 3, 111: 4, 121: 4, 113: 5, 123: 5,
    115: 6, 125: 6, 116: 6, 126: 6, 90: 15, 20: 12, 30: 13, 100: 14,
    60: 19, 40: 16, 50: 22, 70: 21, 80: 20, 200: 20,
}

# BIOME 6000 potential biomes -> EarthStat potential natural vegetation legend.
EARTHSTAT_PNV_FROM_BIOME00K = {
    1: 1, 2: 1, 3: 2, 4: 3, 7: 8, 8: 4, 9: 8, 13: 5, 14: 7, 15: 6,
    16: 11, 17: 4, 18: 9, 20: 12, 22: 10, 27: 14, 28: 13, 30: 13, 31: 13, 32: 13,
}

GFSAD_IRRIGATED = (1, 2)


def pilot_grid(features):
    """The shared 15 arc-second analysis grid, aligned to whole cells."""
    bounds = unary_union([shape(f["geometry"]) for f in features]).bounds
    west, south = [math.floor(bounds[i] / CELL) * CELL for i in (0, 1)]
    east, north = [math.ceil(bounds[i] / CELL) * CELL for i in (2, 3)]
    transform = [CELL, 0, west, 0, -CELL, north]
    return transform, round((east - west) / CELL), round((north - south) / CELL), (west, south, east, north)


class Domain:
    """Pilot geometry, grid and caching context shared by every surrogate builder."""

    def __init__(self, features, members, zones, areas, transform, width, height, bounds, cache, timer, offline):
        self.features = features
        self.ids = [str(int(f["properties"]["HYBAS_ID"])) for f in features]
        self.members = members
        self.zones = zones
        self.areas = areas
        self.transform = transform
        self.width = width
        self.height = height
        self.bounds = bounds
        self.cache = Path(cache)
        self.timer = timer
        self.offline = offline
        self.cache.mkdir(parents=True, exist_ok=True)
        self._geometries = {bid: shape(f["geometry"]) for bid, f in zip(self.ids, features)}
        self._areas_m2 = {bid: abs(GEOD.geometry_area_perimeter(g)[0]) for bid, g in self._geometries.items()}

    def region(self):
        import ee
        west, south, east, north = self.bounds
        return ee.Geometry.Rectangle([west, south, east, north], None, False)

    def geometry(self, bid):
        return self._geometries[bid]

    def basin_area_m2(self, bid):
        return self._areas_m2[bid]

    def support(self, bid, kind):
        return sorted(self.members[bid]) if kind in ("u", "p") else [bid]


def upstream_column(column):
    """Swap the support character of an attribute column from local to upstream."""
    if column[7] != "s":
        raise ValueError(f"{column} is not a local-support column")
    return column[:7] + "u" + column[8:]


def result(value, method, support_count, coverage=1.0, valid=None, expected=None):
    return {"raw_value": value, "valid_cells": valid, "expected_cells": expected,
            "coverage_fraction": coverage, "support_basin_count": support_count, "method": method}


def export(build, name, domain, bands, record):
    """Download one aligned multi-band subset, cache it, and pin its bytes.

    ``build`` is called only on a cache miss, so an offline rerun never touches the
    remote catalogue. It may add fields to ``record`` before returning its image.
    """
    import requests
    path = domain.cache / f"{name}.tif"
    metadata_path = domain.cache / f"{name}.json"
    if path.exists() and metadata_path.exists():
        cached = json.loads(metadata_path.read_text(encoding="utf-8"))
        if cached["sha256"] != sha256(path) or cached["transform"] != domain.transform or cached["bands"] != bands:
            raise ValueError(f"Cached surrogate raster {name} no longer matches its pinned grid or bands")
        domain.timer.event(f"Verified cached surrogate raster {name}")
        record = cached
    else:
        if domain.offline:
            raise FileNotFoundError(f"Surrogate raster {name} is not cached")
        image = build()
        url = image.unmask(NODATA).toFloat().getDownloadURL({
            "crs": "EPSG:4326", "crs_transform": domain.transform,
            "dimensions": [domain.width, domain.height], "format": "GEO_TIFF", "filePerBand": False})
        response = requests.get(url, timeout=(30, 600))
        response.raise_for_status()
        temporary = path.with_suffix(".part.tif")
        temporary.write_bytes(response.content)
        with rasterio.open(temporary) as source:
            if source.count != len(bands):
                raise ValueError(f"{name} returned {source.count} bands, expected {len(bands)}")
        temporary.replace(path)
        record = {**record, "sha256": sha256(path), "retrieved_at": utc_now(), "bytes": len(response.content),
                  "transform": domain.transform, "bands": bands, "nodata": NODATA}
        write_json(metadata_path, record)
        domain.timer.event(f"Downloaded surrogate raster {name}: {len(response.content):,} bytes")
    with rasterio.open(path) as source:
        arrays = source.read().astype("float64")
    arrays[arrays == NODATA] = np.nan
    return {band: arrays[i] for i, band in enumerate(bands)}, record


def cell_statistics(values, domain):
    """Per-basin sufficient statistics on the pilot grid."""
    parts = {}
    for index, bid in enumerate(domain.ids, 1):
        mask = domain.zones == index
        valid = mask & np.isfinite(values)
        parts[bid] = {"count": int(valid.sum()), "expected": int(mask.sum()),
                      "sum": float(values[valid].sum()), "area": float(domain.areas[valid].sum()),
                      "weighted": float((values[valid] * domain.areas[valid]).sum())}
    return parts


def reduce_general(values, domain, support, statistic="mean"):
    """Local or upstream reduction.

    ``mean`` is an unweighted local mean and a cell-area-weighted upstream mean.
    ``sum_over_km2`` and ``sum_over_m2`` accumulate a per-area density into a total.
    """
    parts = cell_statistics(values, domain)
    results = {}
    for bid in domain.ids:
        keys = domain.support(bid, support)
        selected = [parts[key] for key in keys]
        valid = sum(part["count"] for part in selected)
        expected = sum(part["expected"] for part in selected)
        if not valid:
            value = None
        elif statistic == "sum_over_km2":
            value = sum(part["weighted"] for part in selected) / 1e6
        elif statistic == "sum_over_m2":
            value = sum(part["weighted"] for part in selected)
        elif len(selected) > 1:
            total = sum(part["area"] for part in selected)
            value = sum(part["weighted"] for part in selected) / total if total else None
        else:
            value = selected[0]["sum"] / valid
        results[bid] = result(value, f"{statistic} over {'upstream' if len(keys) > 1 else 'local'} support",
                              len(keys), valid / expected if expected else 0.0, valid, expected)
    return results


def majority_from_fractions(fractions, domain, support):
    """Pick the class holding the largest reduced area share within the support."""
    reduced = {code: reduce_general(field, domain, support) for code, field in fractions.items()}
    codes = sorted(fractions)
    results = {}
    for bid in domain.ids:
        shares = [(reduced[code][bid]["raw_value"], code) for code in codes
                  if reduced[code][bid]["raw_value"] is not None]
        best = max(shares) if shares else None
        sample = reduced[codes[0]][bid]
        entry = result(float(best[1]) if best and best[0] > 0 else None,
                       "largest reduced class share within the support", sample["support_basin_count"],
                       sample["coverage_fraction"], sample["valid_cells"], sample["expected_cells"])
        entry["class_share_percent"] = best[0] if best else None
        results[bid] = entry
    return results


def vector_cover(polygons, domain, support):
    """Exact geodesic share of the support area covered by a dissolved polygon set."""
    covered = unary_union(polygons) if polygons else None
    local = {}
    for bid in domain.ids:
        geometry = domain.geometry(bid)
        piece = geometry.intersection(covered) if covered is not None else None
        local[bid] = (abs(GEOD.geometry_area_perimeter(piece)[0]) if piece is not None and not piece.is_empty else 0.0,
                      domain.basin_area_m2(bid))
    results = {}
    for bid in domain.ids:
        keys = domain.support(bid, support)
        cover = sum(local[key][0] for key in keys)
        total = sum(local[key][1] for key in keys)
        results[bid] = result(100.0 * cover / total if total else None,
                              "exact geodesic polygon intersection", len(keys))
    return results


def moisture_index(precipitation, potential):
    """Willmott and Feddema climate moisture index, bounded to -1..1."""
    with np.errstate(divide="ignore", invalid="ignore"):
        wet = np.where(precipitation > 0, 1.0 - potential / precipitation, np.nan)
        dry = np.where(potential > 0, precipitation / potential - 1.0, np.nan)
    return np.where(precipitation >= potential, wet, dry)


def package(record, fields=None, majority=None, direct=None):
    return {"record": record, "fields": fields or {}, "majority": majority or {}, "direct": direct or {}}


# --------------------------------------------------------------------------- builders

def build_terraclimate(domain):
    """Monthly 1991-2020 climatology for actual and potential ET, soil water, precipitation."""
    scales = {"aet": 0.1, "pet": 0.1, "soil": 0.1, "pr": 1.0}
    bands = [f"{band}_{month:02d}" for month in range(1, 13) for band in scales]
    record = {"asset": "IDAHO_EPSCOR/TERRACLIMATE", "climatology": list(CLIMATOLOGY), "band_scales": scales,
              "reduction": "per-calendar-month mean over 1991-2020"}

    def build():
        import ee
        collection = ee.ImageCollection("IDAHO_EPSCOR/TERRACLIMATE").filterDate(*CLIMATOLOGY)
        images = []
        for month in range(1, 13):
            monthly = collection.filter(ee.Filter.calendarRange(month, month, "month"))
            for band, scale in scales.items():
                images.append(monthly.select(band).mean().multiply(scale).rename(f"{band}_{month:02d}"))
        return ee.Image.cat(images)

    fields, record = export(build, "terraclimate-15s", domain, bands, record)

    aet_year = sum(fields[f"aet_{m:02d}"] for m in range(1, 13))
    pet_year = sum(fields[f"pet_{m:02d}"] for m in range(1, 13))
    pre_year = sum(fields[f"pr_{m:02d}"] for m in range(1, 13))
    out = {}
    for month in range(1, 13):
        out[f"aet_mm_s{month:02d}"] = (fields[f"aet_{month:02d}"], "mean")
        out[f"pet_mm_s{month:02d}"] = (fields[f"pet_{month:02d}"], "mean")
        out[f"swc_pc_s{month:02d}"] = (fields[f"soil_{month:02d}"], "mean")
        out[f"cmi_ix_s{month:02d}"] = (moisture_index(fields[f"pr_{month:02d}"], fields[f"pet_{month:02d}"]), "mean")
    out["aet_mm_syr"] = out["aet_mm_uyr"] = (aet_year, "mean")
    out["pet_mm_syr"] = out["pet_mm_uyr"] = (pet_year, "mean")
    out["swc_pc_syr"] = out["swc_pc_uyr"] = (sum(fields[f"soil_{m:02d}"] for m in range(1, 13)) / 12.0, "mean")
    out["cmi_ix_syr"] = out["cmi_ix_uyr"] = (moisture_index(pre_year, pet_year), "mean")
    with np.errstate(divide="ignore", invalid="ignore"):
        aridity = np.where(pet_year > 0, pre_year / pet_year, np.nan)
    out["ari_ix_sav"] = out["ari_ix_uav"] = (aridity, "mean")
    return package(record, fields=out)


def build_modis_snow(domain):
    """Fraction of cloud-free days carrying snow, by calendar month, 2003-2022."""
    monthly, record = {}, None
    for month in range(1, 13):
        name = f"snw_{month:02d}"

        def build(month=month, name=name):
            import ee
            collection = (ee.ImageCollection("MODIS/061/MYD10A1")
                          .filterDate("2003-01-01", "2023-01-01").select("NDSI_Snow_Cover"))
            subset = collection.filter(ee.Filter.calendarRange(month, month, "month"))
            flags = subset.map(lambda image: image.updateMask(image.lte(100)).gte(40))
            image = flags.mean().multiply(100).rename(name).setDefaultProjection(collection.first().projection())
            return image.reduceResolution(ee.Reducer.mean(), maxPixels=1024).reproject(
                crs="EPSG:4326", crsTransform=domain.transform)

        fields, record = export(build, f"modis-snow-{month:02d}-15s", domain, [name],
                                {"asset": "MODIS/061/MYD10A1", "period": ["2003-01-01", "2023-01-01"],
                                 "snow_threshold": "NDSI_Snow_Cover >= 40",
                                 "masking": "fill values above 100 excluded, not gap filled",
                                 "reduction": "mean of cloud-free daily snow flags for this calendar month"})
        monthly.update(fields)
    stack = np.stack([monthly[f"snw_{m:02d}"] for m in range(1, 13)])
    out = {f"snw_pc_s{m:02d}": (stack[m - 1], "mean") for m in range(1, 13)}
    out["snw_pc_smx"] = (stack.max(axis=0), "mean")
    out["snw_pc_syr"] = out["snw_pc_uyr"] = (stack.mean(axis=0), "mean")
    record = {**record, "months": 12, "annual": "mean of the twelve monthly climatologies"}
    return package(record, fields=out)


def build_dem_terrain(domain, native_path=None):
    """Horn slope on the native 3 arc-second DEM, then mean aggregation to the pilot grid."""
    from ATLAS_MODULES.hydrosheds.functions.elevation import aggregate_5x5
    with rasterio.open(native_path) as source:
        elevation = source.read(1, masked=True)
        native = source.transform
    values = elevation.astype("float64").filled(np.nan)
    latitudes = native.f + (np.arange(values.shape[0]) + 0.5) * native.e
    metres_y = abs(native.e) * 111_320.0
    metres_x = abs(native.a) * 111_320.0 * np.cos(np.radians(latitudes))[:, None]
    padded = np.pad(values, 1, mode="edge")
    horn_x = ((padded[:-2, 2:] + 2 * padded[1:-1, 2:] + padded[2:, 2:])
              - (padded[:-2, :-2] + 2 * padded[1:-1, :-2] + padded[2:, :-2])) / (8 * metres_x)
    horn_y = ((padded[2:, :-2] + 2 * padded[2:, 1:-1] + padded[2:, 2:])
              - (padded[:-2, :-2] + 2 * padded[:-2, 1:-1] + padded[:-2, 2:])) / (8 * metres_y)
    slope = np.degrees(np.arctan(np.hypot(horn_x, horn_y)))
    aggregated, counts = aggregate_5x5(slope)
    aggregated[counts != 25] = np.nan
    column = int(round((domain.transform[2] - native.c) / CELL))
    row = int(round((native.f - domain.transform[5]) / CELL))
    if row < 0 or column < 0 or row + domain.height > aggregated.shape[0] or column + domain.width > aggregated.shape[1]:
        raise ValueError("Pilot grid falls outside the aggregated elevation tile")
    aggregated = aggregated[row:row + domain.height, column:column + domain.width]
    record = {"asset": "EarthEnv-DEM90 v1", "native_arcsec": 3.0, "algorithm": "Horn 3x3 slope",
              "window": {"row": row, "column": column, "height": domain.height, "width": domain.width},
              "cell_metres": "geodetic degree-to-metre scaling by latitude",
              "aggregation": "5x5 arithmetic mean to 15 arc-seconds, complete blocks only",
              "native_source": str(native_path)}
    return package(record, fields={"slp_dg_sav": (aggregated, "mean"), "slp_dg_uav": (aggregated, "mean")})


def _class_fraction(image, codes, name, domain):
    import ee
    mask = image.eq(codes[0]) if codes else image.multiply(0)
    for code in codes[1:]:
        mask = mask.Or(image.eq(code))
    return (mask.reduceResolution(ee.Reducer.mean(), maxPixels=1024)
            .reproject(crs="EPSG:4326", crsTransform=domain.transform).multiply(100).rename(name))


def build_copernicus_lc(domain):
    """GLC2000-legend class fractions crosswalked from the 2015 Copernicus classification."""
    fractions = (("tree-coverfraction", "for_frac"), ("crops-coverfraction", "crp_frac"),
                 ("grass-coverfraction", "pst_frac"))
    bands = [f"glc_{target:02d}" for target in range(1, 23)] + [alias for _, alias in fractions]
    record = {"asset": "COPERNICUS/Landcover/100m/Proba-V-C3/Global", "epoch": "2015",
              "crosswalk": "glc2000_from_copernicus",
              "crosswalk_table": {str(k): v for k, v in sorted(GLC2000_FROM_COPERNICUS.items())},
              "unmapped_glc2000_classes": sorted(set(range(1, 23)) - set(GLC2000_FROM_COPERNICUS.values())),
              "aggregation": "class mask mean at 100 m, reprojected to the pilot 15 arc-second grid"}

    def build():
        import ee
        image = ee.Image(ee.ImageCollection("COPERNICUS/Landcover/100m/Proba-V-C3/Global")
                         .filter(ee.Filter.eq("system:index", "2015")).first())
        discrete = image.select("discrete_classification")
        layers = [_class_fraction(discrete, sorted(code for code, mapped in GLC2000_FROM_COPERNICUS.items()
                                                   if mapped == target), f"glc_{target:02d}", domain)
                  for target in range(1, 23)]
        layers += [image.select(band).reduceResolution(ee.Reducer.mean(), maxPixels=1024)
                   .reproject(crs="EPSG:4326", crsTransform=domain.transform).rename(alias)
                   for band, alias in fractions]
        return ee.Image.cat(layers)

    fields, record = export(build, "copernicus-lc-15s", domain, bands, record)
    out = {}
    for target in range(1, 23):
        field = fields[f"glc_{target:02d}"]
        out[f"glc_pc_s{target:02d}"] = (field, "mean")
        out[f"glc_pc_u{target:02d}"] = (field, "mean")
    out["for_pc_sse"] = out["for_pc_use"] = (fields["for_frac"], "mean")
    out["crp_pc_sse"] = out["crp_pc_use"] = (fields["crp_frac"], "mean")
    out["pst_pc_sse"] = out["pst_pc_use"] = (fields["pst_frac"], "mean")
    majority = {"glc_cl_smj": ({t: fields[f"glc_{t:02d}"] for t in range(1, 23)}, "s")}
    return package(record, fields=out, majority=majority)


def build_pnv_biome(domain):
    """EarthStat PNV-legend class fractions crosswalked from BIOME 6000 potential biomes."""
    bands = [f"pnv_{target:02d}" for target in range(1, 16)]
    record = {"asset": "OpenLandMap/PNV/PNV_BIOME-TYPE_BIOME00K_C/v01",
              "crosswalk": "earthstat_pnv_from_biome00k",
              "crosswalk_table": {str(k): v for k, v in sorted(EARTHSTAT_PNV_FROM_BIOME00K.items())},
              "unmapped_earthstat_classes": sorted(set(range(1, 16)) - set(EARTHSTAT_PNV_FROM_BIOME00K.values())),
              "aggregation": "class mask mean at 1 km, reprojected to the pilot 15 arc-second grid"}

    def build():
        import ee
        image = ee.Image("OpenLandMap/PNV/PNV_BIOME-TYPE_BIOME00K_C/v01").select("biome_type")
        return ee.Image.cat([_class_fraction(image, sorted(code for code, mapped in
                                                           EARTHSTAT_PNV_FROM_BIOME00K.items() if mapped == target),
                                             f"pnv_{target:02d}", domain) for target in range(1, 16)])

    fields, record = export(build, "pnv-biome-15s", domain, bands, record)
    out = {}
    for target in range(1, 16):
        field = fields[f"pnv_{target:02d}"]
        out[f"pnv_pc_s{target:02d}"] = (field, "mean")
        out[f"pnv_pc_u{target:02d}"] = (field, "mean")
    majority = {"pnv_cl_smj": ({t: fields[f"pnv_{t:02d}"] for t in range(1, 16)}, "s")}
    return package(record, fields=out, majority=majority)


def build_openlandmap_soil(domain):
    """Depth-integrated 0-100 cm texture fractions and an organic-carbon stock."""
    depths = [0, 10, 30, 60, 100]
    weights = np.zeros(len(depths))
    for index in range(len(depths) - 1):
        span = depths[index + 1] - depths[index]
        weights[index] += span / 2
        weights[index + 1] += span / 2
    weights = weights / weights.sum()
    bands = ["clay", "sand", "orgc", "bulk", "soc"]

    def build():
        import ee

        def integrate(asset, scale, name):
            image = ee.Image(asset)
            total = image.select(f"b{depths[0]}").multiply(scale * float(weights[0]))
            for depth, weight in zip(depths[1:], weights[1:]):
                total = total.add(image.select(f"b{depth}").multiply(scale * float(weight)))
            return total.rename(name)

        clay = integrate("OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02", 1.0, "clay")
        sand = integrate("OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02", 1.0, "sand")
        carbon = integrate("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02", 5.0, "orgc")
        density = integrate("OpenLandMap/SOL/SOL_BULKDENS-FINEEARTH_USDA-4A1H_M/v02", 10.0, "bulk")
        # g/kg times kg/m3 over a 1 m column gives g/m2; 1 g/m2 is 0.01 t/ha.
        stock = carbon.multiply(density).multiply(0.01).rename("soc")
        return ee.Image.cat([clay, sand, carbon, density, stock])

    record = {"assets": ["OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02",
                         "OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02",
                         "OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02",
                         "OpenLandMap/SOL/SOL_BULKDENS-FINEEARTH_USDA-4A1H_M/v02"],
              "band_scales": {"clay": 1.0, "sand": 1.0, "orgc": 5.0, "bulk": 10.0},
              "depth_weights": {f"b{d}": round(float(w), 6) for d, w in zip(depths, weights)},
              "silt": "closed as 100 minus clay minus sand",
              "carbon_stock": "organic carbon content times bulk density over 0-100 cm, no coarse-fragment correction"}
    fields, record = export(build, "openlandmap-soil-15s", domain, bands, record)
    silt = 100.0 - fields["clay"] - fields["sand"]
    out = {}
    for local_column, field in (("cly_pc_sav", fields["clay"]), ("snd_pc_sav", fields["sand"]),
                                ("slt_pc_sav", silt), ("soc_th_sav", fields["soc"])):
        out[local_column] = (field, "mean")
        out[upstream_column(local_column)] = (field, "mean")
    return package(record, fields=out)


def build_gpw(domain):
    """Population density for 2015, accumulated by cell area for counts."""
    record = {"asset": "CIESIN/GPWv411/GPW_Population_Density", "epoch": "2015", "revision": "v4.11",
              "counts": "density multiplied by geodesic cell area and summed over the support"}

    def build():
        import ee
        return ee.Image(ee.ImageCollection("CIESIN/GPWv411/GPW_Population_Density")
                        .filter(ee.Filter.eq("system:index",
                                             "gpw_v4_population_density_rev11_2015_30_sec")).first()).rename("ppd")

    fields, record = export(build, "gpw-density-15s", domain, ["ppd"], record)
    field = fields["ppd"]
    return package(record, fields={"ppd_pk_sav": (field, "mean"), "ppd_pk_uav": (field, "mean"),
                                   "pop_ct_ssu": (field, "sum_over_km2"), "pop_ct_usu": (field, "sum_over_km2")})


def build_ghsl(domain):
    """Built-up surface fraction for the 2015 epoch, as a percentage of cell area."""
    record = {"asset": "JRC/GHSL/P2023A/GHS_BUILT_S", "epoch": "2015",
              "conversion": "built surface in square metres per 100 m cell divided by 100 to give percent"}

    def build():
        import ee
        image = ee.Image(ee.ImageCollection("JRC/GHSL/P2023A/GHS_BUILT_S")
                         .filter(ee.Filter.eq("system:index", "2015")).first()).select("built_surface")
        return image.divide(100.0).reduceResolution(ee.Reducer.mean(), maxPixels=1024).reproject(
            crs="EPSG:4326", crsTransform=domain.transform).rename("urb")

    fields, record = export(build, "ghsl-built-15s", domain, ["urb"], record)
    return package(record, fields={"urb_pc_sse": (fields["urb"], "mean"), "urb_pc_use": (fields["urb"], "mean")})


def build_dmsp_lights(domain):
    """DMSP-OLS stable lights for 2010, reported as the raw digital number."""
    record = {"asset": "NOAA/DMSP-OLS/NIGHTTIME_LIGHTS", "epoch": "F182010", "band": "stable_lights",
              "units": "digital number 0-63; the atlas index transformation is not applied"}

    def build():
        import ee
        return ee.Image(ee.ImageCollection("NOAA/DMSP-OLS/NIGHTTIME_LIGHTS")
                        .filter(ee.Filter.eq("system:index", "F182010"))
                        .first()).select("stable_lights").rename("nli")

    fields, record = export(build, "dmsp-lights-15s", domain, ["nli"], record)
    return package(record, fields={"nli_ix_sav": (fields["nli"], "mean"), "nli_ix_uav": (fields["nli"], "mean")})


def build_human_modification(domain):
    """Global Human Modification 2016, reported as an independent index."""
    record = {"asset": "CSP/HM/GlobalHumanModification", "epoch": "2016",
              "units": "modification index 0-1; not the Human Footprint index",
              "dimension_note": "offered against the 2009 dimension only; no 1993 surface is available"}

    def build():
        import ee
        return ee.Image(ee.ImageCollection("CSP/HM/GlobalHumanModification").first()).select("gHM").rename("hft")

    fields, record = export(build, "human-modification-15s", domain, ["hft"], record)
    return package(record, fields={"hft_ix_s09": (fields["hft"], "mean"), "hft_ix_u09": (fields["hft"], "mean")})


def build_surface_water(domain):
    """Optical surface-water shares from JRC occurrence, seasonality and maximum extent."""
    record = {"asset": "JRC/GSW1_4/GlobalSurfaceWater",
              "long_term": "mean water occurrence percentage 1984-2021",
              "minimum": "share of the support classified as permanent water, twelve months of seasonality",
              "maximum": "share of the support ever observed as water"}

    def build():
        import ee
        water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater")

        def coarsen(image, name, factor=1.0):
            return (image.reduceResolution(ee.Reducer.mean(), maxPixels=4096)
                    .reproject(crs="EPSG:4326", crsTransform=domain.transform).multiply(factor).rename(name))

        return ee.Image.cat([coarsen(water.select("occurrence").unmask(0), "inu_lt"),
                             coarsen(water.select("seasonality").unmask(0).gte(12), "inu_mn", 100.0),
                             coarsen(water.select("max_extent").unmask(0), "inu_mx", 100.0)])

    fields, record = export(build, "surface-water-15s", domain, ["inu_lt", "inu_mn", "inu_mx"], record)
    out = {}
    for suffix, key in (("lt", "inu_lt"), ("mn", "inu_mn"), ("mx", "inu_mx")):
        out[f"inu_pc_s{suffix}"] = (fields[key], "mean")
        out[f"inu_pc_u{suffix}"] = (fields[key], "mean")
    return package(record, fields=out)


def build_gfsad(domain):
    """Irrigated cropland share from the GFSAD1000 cropland extent product."""
    record = {"asset": "USGS/GFSAD1000_V1", "epoch": "2010", "irrigated_classes": list(GFSAD_IRRIGATED),
              "units": "percent of the support classified as irrigated cropland"}

    def build():
        import ee
        image = ee.Image("USGS/GFSAD1000_V1").select("landcover")
        mask = image.eq(GFSAD_IRRIGATED[0])
        for code in GFSAD_IRRIGATED[1:]:
            mask = mask.Or(image.eq(code))
        return mask.multiply(100).rename("ire")

    fields, record = export(build, "gfsad-irrigated-15s", domain, ["ire"], record)
    return package(record, fields={"ire_pc_sse": (fields["ire"], "mean"), "ire_pc_use": (fields["ire"], "mean")})


def build_era5_runoff(domain):
    """ERA5-Land runoff climatology, and discharge accumulated over the pilot units only."""
    import ee
    collection = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").filterDate(*CLIMATOLOGY).select("runoff_sum")
    images, bands = [], []
    for month in range(1, 13):
        name = f"ro_{month:02d}"
        images.append(collection.filter(ee.Filter.calendarRange(month, month, "month"))
                      .mean().multiply(1000.0).rename(name))
        bands.append(name)
    record = {"asset": "ECMWF/ERA5_LAND/MONTHLY_AGGR", "band": "runoff_sum", "climatology": list(CLIMATOLOGY),
              "conversion": "metres of monthly runoff multiplied by 1000 to give millimetres",
              "discharge": "runoff depth times support area divided by the length of the month or year",
              "boundary": "accumulation covers pilot units only; inflow from outside the pilot is absent by construction"}
    fields, record = export(ee.Image.cat(images), "era5-runoff-15s", domain, bands, record)
    monthly = [fields[f"ro_{m:02d}"] for m in range(1, 13)]
    annual = sum(monthly)
    reduced = [reduce_general(field / 1000.0 / (days * 86400), domain, "p", "sum_over_m2")
               for field, days in zip(monthly, DAYS_PER_MONTH)]
    yearly = reduce_general(annual / 1000.0 / SECONDS_PER_YEAR, domain, "p", "sum_over_m2")
    direct = {"dis_m3_pyr": yearly, "dis_m3_pmn": {}, "dis_m3_pmx": {}}
    for bid in domain.ids:
        series = [month[bid]["raw_value"] for month in reduced if month[bid]["raw_value"] is not None]
        for column, value in (("dis_m3_pmn", min(series) if series else None),
                              ("dis_m3_pmx", max(series) if series else None)):
            direct[column][bid] = result(value, "extreme monthly accumulated runoff over the pilot support",
                                         yearly[bid]["support_basin_count"], yearly[bid]["coverage_fraction"],
                                         yearly[bid]["valid_cells"], yearly[bid]["expected_cells"])
    return package(record, fields={"run_mm_syr": (annual, "mean")}, direct=direct)


def _painted_fraction(collection, name, domain):
    import ee
    painted = ee.Image().byte().paint(collection, 1).unmask(0).setDefaultProjection(crs="EPSG:4326", scale=30)
    return (painted.reduceResolution(ee.Reducer.mean(), maxPixels=4096)
            .reproject(crs="EPSG:4326", crsTransform=domain.transform).multiply(100).rename(name))


def build_glims(domain):
    """Glacier share from GLIMS outlines, rasterised at 30 m before aggregation."""
    record = {"asset": "GLIMS/current",
              "filter": "line_type equals glac_bound; most recent analysis per glac_id",
              "rasterisation": "outlines painted at 30 m, mean-aggregated to 15 arc-seconds",
              "note": "outline dates still vary between glaciers and are not a single epoch"}

    def build():
        import ee
        outlines = (ee.FeatureCollection("GLIMS/current").filterBounds(domain.region())
                    .filter(ee.Filter.eq("line_type", "glac_bound")))
        # Repeat submissions for one glacier would union into an inflated envelope, so
        # keep only the most recent analysis of each glacier.
        collection = outlines.sort("anlys_time", False).distinct("glac_id")
        record["outlines_in_domain"] = outlines.size().getInfo()
        record["features_in_domain"] = collection.size().getInfo()
        return _painted_fraction(collection, "gla", domain)

    fields, record = export(build, "glims-cover-15s", domain, ["gla"], record)
    return package(record, fields={"gla_pc_sse": (fields["gla"], "mean"), "gla_pc_use": (fields["gla"], "mean")})


def build_wdpa(domain):
    """Protected-area share from the current WDPA polygon release."""
    record = {"asset": "WCMC/WDPA/current/polygons",
              "rasterisation": "polygons painted at 30 m, mean-aggregated to 15 arc-seconds",
              "note": "current release, later than the 2014 snapshot cited by the atlas"}

    def build():
        import ee
        collection = ee.FeatureCollection("WCMC/WDPA/current/polygons").filterBounds(domain.region())
        record["features_in_domain"] = collection.size().getInfo()
        return _painted_fraction(collection, "pac", domain)

    fields, record = export(build, "wdpa-cover-15s", domain, ["pac"], record)
    return package(record, fields={"pac_pc_sse": (fields["pac"], "mean"), "pac_pc_use": (fields["pac"], "mean")})


def build_ecoregions(domain):
    """Majority RESOLVE ecoregion and biome by exact geodesic intersection area."""
    cache = domain.cache / "resolve-ecoregions.json"
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        domain.timer.event("Verified cached RESOLVE ecoregion features")
    elif domain.offline:
        raise FileNotFoundError("RESOLVE ecoregion features are not cached")
    else:
        import ee
        payload = ee.FeatureCollection("RESOLVE/ECOREGIONS/2017").filterBounds(domain.region()).getInfo()["features"]
        write_json(cache, payload)
    parts = [(shape(f["geometry"]), f["properties"]) for f in payload if f.get("geometry")]
    record = {"asset": "RESOLVE/ECOREGIONS/2017", "features_in_domain": len(parts),
              "cache": cache.name, "sha256": sha256(cache),
              "method": "largest geodesic intersection area within the basin",
              "ecoregions": sorted({p["ECO_NAME"] for _, p in parts})}
    direct = {"tec_cl_smj": {}, "tbi_cl_smj": {}}
    for bid in domain.ids:
        geometry = domain.geometry(bid)
        shares = []
        for polygon, properties in parts:
            piece = geometry.intersection(polygon)
            if not piece.is_empty:
                shares.append((abs(GEOD.geometry_area_perimeter(piece)[0]), properties["ECO_ID"], properties))
        best = max(shares)[2] if shares else None
        for column, key in (("tec_cl_smj", "ECO_ID"), ("tbi_cl_smj", "BIOME_NUM")):
            direct[column][bid] = result(float(best[key]) if best else None,
                                         "exact geodesic polygon intersection", 1)
    return package(record, direct=direct)


def build_hydrolakes(domain, gdb=None):
    """Lake share and stored volume from the local HydroLAKES v1.0 archive."""
    import pyogrio
    frame = pyogrio.read_dataframe(gdb, bbox=domain.bounds)
    record = {"asset": str(gdb), "lakes_in_domain": int(len(frame)),
              "cover": "exact geodesic intersection of lake polygons with basin polygons",
              "volume": "lake total volume assigned to the basin containing the lake pour point"}
    polygons = [shape(geometry.__geo_interface__) for geometry in frame.geometry]
    direct = {"lka_pc_sse": vector_cover(polygons, domain, "s"),
              "lka_pc_use": vector_cover(polygons, domain, "u")}
    volumes = {bid: 0.0 for bid in domain.ids}
    for _, row in frame.iterrows():
        pour = Point(float(row["Pour_long"]), float(row["Pour_lat"]))
        for bid in domain.ids:
            if domain.geometry(bid).contains(pour):
                volumes[bid] += float(row["Vol_total"])
                break
    direct["lkv_mc_usu"] = {
        bid: result(sum(volumes[key] for key in domain.support(bid, "u")),
                    "sum of lake volumes with pour points inside the support", len(domain.support(bid, "u")))
        for bid in domain.ids}
    return package(record, direct=direct)


BUILDERS = {
    "terraclimate": build_terraclimate,
    "modis_snow": build_modis_snow,
    "dem_terrain": build_dem_terrain,
    "copernicus_lc": build_copernicus_lc,
    "pnv_biome": build_pnv_biome,
    "openlandmap_soil": build_openlandmap_soil,
    "gpw": build_gpw,
    "ghsl": build_ghsl,
    "dmsp_lights": build_dmsp_lights,
    "human_modification": build_human_modification,
    "surface_water": build_surface_water,
    "gfsad": build_gfsad,
    "era5_runoff": build_era5_runoff,
    "glims": build_glims,
    "wdpa": build_wdpa,
    "ecoregions": build_ecoregions,
    "hydrolakes": build_hydrolakes,
}
