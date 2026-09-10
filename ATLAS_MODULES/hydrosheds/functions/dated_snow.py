"""Dated monthly snow cover for the pilot basins, reduced on the server.

The pilot already carries snow as a climatology: twelve calendar-month averages
pooled over 2003-2022. This adapter produces the dated series that climatology was
made from — one value per basin, year and month — so that a real observation
period exists in the store rather than a normal standing in for one.

It reduces on the server and returns a table. Downloading a raster per month would
mean 240 aligned downloads for one variable in twenty basins, which does not scale
to 7,445; a grouped reduction returns the numbers themselves and stays flat as
basins are added.

The snow definition, the mask and the analysis grid are deliberately identical to
the climatology builder in `surrogates.build_modis_snow`, so the dated series and
the climatology are comparable. What differs is only the period each value covers.
"""
from __future__ import annotations

CRS = "EPSG:4326"
ASSET = "MODIS/061/MYD10A1"
BAND = "NDSI_Snow_Cover"
SNOW_THRESHOLD = 40        # NDSI_Snow_Cover >= 40 counts the day as snow covered
VALID_MAX = 100            # values above 100 are fill/flag codes, excluded, never gap filled
MONTHS = range(1, 13)


def feature_collection(features):
    """The pilot basins as they were pinned, carrying only their HYBAS_ID."""
    import ee
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry(feature["geometry"]),
                   {"hybas_id": str(int(feature["properties"]["HYBAS_ID"]))})
        for feature in features])


def monthly_stack(year, transform):
    """Twelve bands: the fraction of cloud-free days carrying snow, month by month."""
    import ee
    collection = ee.ImageCollection(ASSET).select(BAND)
    projection = collection.first().projection()
    bands = []
    for month in MONTHS:
        start = ee.Date.fromYMD(year, month, 1)
        flags = (collection.filterDate(start, start.advance(1, "month"))
                 .map(lambda image: image.updateMask(image.lte(VALID_MAX)).gte(SNOW_THRESHOLD)))
        image = (flags.mean().multiply(100).rename(f"m{month:02d}")
                 .setDefaultProjection(projection))
        bands.append(image.reduceResolution(ee.Reducer.mean(), maxPixels=1024)
                     .reproject(crs=CRS, crsTransform=transform))
    return ee.Image.cat(bands)


def reducer():
    """Unweighted: a cell belongs to the basin its centre falls in, as when rasterised."""
    import ee
    return ee.Reducer.mean().unweighted().combine(ee.Reducer.count().unweighted(), sharedInputs=True)


def expected_cells(collection, transform):
    """The analysis cells each basin holds, masking aside: the QA denominator."""
    import ee
    ones = ee.Image.constant(1).reproject(crs=CRS, crsTransform=transform)
    table = ones.reduceRegions(collection=collection, reducer=ee.Reducer.count().unweighted(),
                               crs=CRS, crsTransform=transform).getInfo()
    return {f["properties"]["hybas_id"]: int(f["properties"]["count"]) for f in table["features"]}


def source_images(year):
    """How many daily images each month was built from; a reproducible fingerprint."""
    import ee
    collection = ee.ImageCollection(ASSET)
    sizes = [collection.filterDate(ee.Date.fromYMD(year, month, 1),
                                   ee.Date.fromYMD(year, month, 1).advance(1, "month")).size()
             for month in MONTHS]
    return [int(size) for size in ee.List(sizes).getInfo()]


def year_rows(collection, transform, year, expected):
    """One year of monthly values for one collection of basins, in a single call.

    Separated from `extract` so a regional run can hold the expected-cell denominators
    and the basin batching itself, and pay for neither more than once.
    """
    table = monthly_stack(year, transform).reduceRegions(
        collection=collection, reducer=reducer(), crs=CRS, crsTransform=transform).getInfo()
    rows = []
    for feature in table["features"]:
        properties = feature["properties"]
        basin_id = properties["hybas_id"]
        for month in MONTHS:
            valid = properties.get(f"m{month:02d}_count")
            rows.append({
                "hybas_id": basin_id, "year": year, "month": month,
                # An absent property means every cell was masked all month.
                "value": properties.get(f"m{month:02d}_mean"),
                "valid_count": int(valid) if valid is not None else 0,
                "expected_count": expected[basin_id]})
    return rows


def extract(features, transform, years, log=None):
    """One row per basin, year and month. A month with no cloud-free day stays null."""
    collection = feature_collection(features)
    expected = expected_cells(collection, transform)
    rows, provenance = [], {}
    for year in years:
        rows.extend(year_rows(collection, transform, year, expected))
        provenance[str(year)] = {"source_images_by_month": source_images(year)}
        if log:
            log(f"snow {year}: {len(features)} basins x 12 months")
    return rows, provenance
