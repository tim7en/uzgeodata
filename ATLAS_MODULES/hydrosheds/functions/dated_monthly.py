"""Dated monthly values for sources that already publish monthly imagery.

`dated_snow` dates a daily product: it decides, day by day, whether a cell carried
snow, then averages the decisions. TerraClimate and ERA5-Land already publish one
image per month, so dating them is simpler — take the month's image, apply the
source's own scale factor, and reduce it over the basins.

Each source is described once, here, using exactly the bands, scale factors and
units the reviewed climatology builders in `surrogates` use. That is deliberate:
the dated series and the climatology must differ only in the period they cover, or
comparing them means nothing. `verify_against_climatology` in the pipeline runs
that comparison over the climatology's own window, which is what catches a wrong
scale factor before a regional run rather than after it.

Units are recorded as what the number actually is. TerraClimate `soil` is soil
moisture in millimetres, so it is published in millimetres; it is not relabelled as
the percentage that the HydroATLAS `swc_pc` attribute holds.
"""
from __future__ import annotations

CRS = "EPSG:4326"
MONTHS = range(1, 13)

# Bands, the source's own scale factor, and what the scaled number is.
SOURCES = {
    "terraclimate": {
        "asset": "IDAHO_EPSCOR/TERRACLIMATE",
        "bands": {
            "aet": {"scale": 0.1, "unit": "millimetres per month",
                    "attribute": "uzgeodata.dated.v1.aet_mm_s",
                    "label": "actual evapotranspiration"},
            "pet": {"scale": 0.1, "unit": "millimetres per month",
                    "attribute": "uzgeodata.dated.v1.pet_mm_s",
                    "label": "potential evapotranspiration"},
            "soil": {"scale": 0.1, "unit": "millimetres of soil moisture",
                     "attribute": "uzgeodata.dated.v1.soil_mm_s",
                     "label": "soil moisture"},
            "pr": {"scale": 1.0, "unit": "millimetres per month",
                   "attribute": "uzgeodata.dated.v1.pre_mm_s",
                   "label": "precipitation"},
        },
        "climatology": ("1991-01-01", "2021-01-01"),
        "note": "One image per month; the month's image is taken as it stands.",
    },
    "era5_runoff": {
        "asset": "ECMWF/ERA5_LAND/MONTHLY_AGGR",
        "bands": {
            "runoff_sum": {"scale": 1000.0, "unit": "millimetres per month",
                           "attribute": "uzgeodata.dated.v1.run_mm_s",
                           "label": "total runoff"},
        },
        "climatology": ("1991-01-01", "2021-01-01"),
        "note": "Metres of monthly runoff, multiplied by 1000 to give millimetres.",
    },
}


def feature_collection(features):
    import ee
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry(feature["geometry"]),
                   {"hybas_id": str(int(feature["properties"]["HYBAS_ID"]))})
        for feature in features])


def reducer():
    """Unweighted: a cell belongs to the basin its centre falls in, as when rasterised."""
    import ee
    return ee.Reducer.mean().unweighted().combine(ee.Reducer.count().unweighted(), sharedInputs=True)


def monthly_stack(source, year, transform, bands=None):
    """Every band of one year, in a single image, so one reduction serves them all.

    Reducing over basin geometry costs the same whether the image carries one band
    or many, so a year's worth of every variable travels in one call.
    """
    import ee
    spec = SOURCES[source]
    collection = ee.ImageCollection(spec["asset"])
    stack = []
    for band in (bands or spec["bands"]):
        scale = spec["bands"][band]["scale"]
        projection = collection.first().select(band).projection()
        for month in MONTHS:
            start = ee.Date.fromYMD(year, month, 1)
            image = (collection.select(band).filterDate(start, start.advance(1, "month"))
                     .mean().multiply(scale).rename(f"{band}_{month:02d}")
                     .setDefaultProjection(projection))
            stack.append(image.reduceResolution(ee.Reducer.mean(), maxPixels=1024)
                         .reproject(crs=CRS, crsTransform=transform))
    return ee.Image.cat(stack)


def expected_cells(collection, transform):
    """The analysis cells each basin holds, masking aside: the QA denominator."""
    import ee
    ones = ee.Image.constant(1).reproject(crs=CRS, crsTransform=transform)
    table = ones.reduceRegions(collection=collection, reducer=ee.Reducer.count().unweighted(),
                               crs=CRS, crsTransform=transform).getInfo()
    return {f["properties"]["hybas_id"]: int(f["properties"]["count"]) for f in table["features"]}


def year_rows(source, collection, transform, year, expected, bands=None):
    """One row per basin, band and month. A band with no value stays null."""
    table = monthly_stack(source, year, transform, bands).reduceRegions(
        collection=collection, reducer=reducer(), crs=CRS, crsTransform=transform).getInfo()
    rows = []
    for feature in table["features"]:
        properties = feature["properties"]
        basin_id = properties["hybas_id"]
        for band in (bands or SOURCES[source]["bands"]):
            for month in MONTHS:
                valid = properties.get(f"{band}_{month:02d}_count")
                rows.append({
                    "hybas_id": basin_id, "band": band, "year": year, "month": month,
                    "value": properties.get(f"{band}_{month:02d}_mean"),
                    "valid_count": int(valid) if valid is not None else 0,
                    "expected_count": expected[basin_id]})
    return rows


def extract(source, features, transform, years, bands=None, log=None):
    """Every band, every month, every year, for these basins."""
    collection = feature_collection(features)
    expected = expected_cells(collection, transform)
    rows = []
    for year in years:
        rows.extend(year_rows(source, collection, transform, year, expected, bands))
        if log:
            log(f"{source} {year}: {len(features)} basins x 12 months "
                f"x {len(bands or SOURCES[source]['bands'])} bands")
    return rows
