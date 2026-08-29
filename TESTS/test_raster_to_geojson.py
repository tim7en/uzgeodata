from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "PIPELINES"))

from raster_to_geojson import (  # noqa: E402
    QuotaExceeded,
    extract_lpkx_tiffs,
    supported_files_in_directory,
    vectorize_raster,
)
from build_all_web_layers import archive_preview, raster_layer, useful_fields  # noqa: E402


class RasterToGeoJSONTests(unittest.TestCase):
    def write_raster(self, path: Path, values: np.ndarray, nodata: int | float | None = None) -> None:
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=values.shape[1],
            height=values.shape[0],
            count=1,
            dtype=values.dtype,
            crs="EPSG:4326",
            transform=from_origin(60, 45, 0.1, 0.1),
            nodata=nodata,
        ) as target:
            target.write(values, 1)

    def convert(self, source: Path, target: Path, byte_limit: int = 1024 * 1024) -> dict:
        return vectorize_raster(
            source,
            target,
            source.name,
            byte_limit=byte_limit,
            band=1,
            max_pixels=10_000,
            max_features=1_000,
            bins=4,
            categorical="auto",
            max_categories=16,
            source_crs=None,
        )

    def test_categorical_raster_becomes_valid_feature_collection(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "classes.tif"
            target = root / "classes.geojson"
            self.write_raster(source, np.array([[1, 1], [2, 2]], dtype=np.uint8))

            result = self.convert(source, target)
            payload = json.loads(target.read_text(encoding="utf-8"))

            self.assertEqual(payload["type"], "FeatureCollection")
            self.assertEqual(payload["metadata"]["value_type"], "categorical")
            self.assertEqual(result["classes"], 2)
            self.assertEqual(result["features"], 2)
            self.assertTrue(all(item["geometry"]["type"] == "Polygon" for item in payload["features"]))

    def test_quota_failure_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "classes.tif"
            target = root / "classes.geojson"
            self.write_raster(source, np.array([[1, 1], [2, 2]], dtype=np.uint8))

            with self.assertRaises(QuotaExceeded):
                self.convert(source, target, byte_limit=32)

            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix(".geojson.tmp").exists())

    def test_continuous_raster_is_downsampled_and_binned(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "continuous.tif"
            target = root / "continuous.geojson"
            self.write_raster(source, np.arange(10_000, dtype=np.float32).reshape(100, 100))

            result = vectorize_raster(
                source,
                target,
                source.name,
                byte_limit=4 * 1024 * 1024,
                band=1,
                max_pixels=400,
                max_features=1_000,
                bins=4,
                categorical="auto",
                max_categories=16,
                source_crs=None,
            )

            self.assertEqual(result["valueType"], "continuous")
            self.assertEqual(result["processedDimensions"], [20, 20])
            self.assertEqual(result["classes"], 4)

    def test_masked_integer_nodata_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "masked.tif"
            target = root / "masked.geojson"
            self.write_raster(source, np.array([[1, 255], [2, 2]], dtype=np.uint8), nodata=255)

            result = self.convert(source, target)
            payload = json.loads(target.read_text(encoding="utf-8"))

            self.assertEqual(result["classes"], 2)
            self.assertNotIn(255, [item["properties"]["value"] for item in payload["features"]])

    def test_web_preview_handles_masked_integer_raster(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "masked-preview.tif"
            target = root / "masked-preview.png"
            self.write_raster(source, np.array([[1, 255], [2, 2]], dtype=np.uint8), nodata=255)

            result = raster_layer(source, target)

            self.assertEqual(result["kind"], "raster")
            self.assertTrue(target.exists())
            self.assertGreater(result["bytes"], 0)

    def test_binary_geodatabase_fields_are_not_exported(self) -> None:
        import geopandas as gpd
        from shapely.geometry import Point

        data = gpd.GeoDataFrame(
            {"name": ["safe"], "binary_blob": [b"\x00\x01"], "geometry": [Point(60, 45)]},
            crs="EPSG:4326",
        )

        self.assertEqual(useful_fields(data), ["name"])

    def test_tiff_can_be_discovered_and_extracted_from_lpkx(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.tif"
            package = root / "atlas.lpkx"
            destination = root / "extracted"
            destination.mkdir()
            self.write_raster(source, np.array([[3, 3], [4, 4]], dtype=np.uint8))
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(source, "commondata/raster_data/source.tif")

            extracted = extract_lpkx_tiffs(package, destination, 1024 * 1024)

            self.assertEqual(len(extracted), 1)
            with rasterio.open(extracted[0][0]) as raster:
                self.assertEqual((raster.width, raster.height), (2, 2))

            discovered = list(supported_files_in_directory(root))
            self.assertIn(source, discovered)
            self.assertIn(package, discovered)

    def test_archive_preview_does_not_expand_the_package(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = root / "preview.lpkx"
            target = root / "preview.png"
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("esriinfo/thumbnail/thumbnail.png", b"small-preview")
                archive.writestr("commondata/large.gdb/table", b"0" * 100_000)

            result = archive_preview(package, target)

            self.assertEqual(result["kind"], "preview")
            self.assertEqual(target.read_bytes(), b"small-preview")


if __name__ == "__main__":
    unittest.main()
