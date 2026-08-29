#!/usr/bin/env python3
"""Download every UZKAD agriculture region into a separate GeoPackage."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from download_uzkad_agriculture import LAYER_URL, NATIVE_CRS, request_session, source_count


REGIONS = (
    ("1703", "andijon", "Andijon viloyati"),
    ("1706", "buxoro", "Buxoro viloyati"),
    ("1708", "jizzax", "Jizzax viloyati"),
    ("1710", "qashqadaryo", "Qashqadaryo viloyati"),
    ("1712", "navoiy", "Navoiy viloyati"),
    ("1714", "namangan", "Namangan viloyati"),
    ("1718", "samarqand", "Samarqand viloyati"),
    ("1722", "surxondaryo", "Surxondaryo viloyati"),
    ("1724", "sirdaryo", "Sirdaryo viloyati"),
    ("1726", "toshkent_shahri", "Toshkent shahri"),
    ("1727", "toshkent", "Toshkent viloyati"),
    ("1730", "fargona", "Farg‘ona viloyati"),
    ("1733", "xorazm", "Xorazm viloyati"),
    ("1735", "qoraqalpogiston", "Qoraqalpog‘iston respublikasi"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("WORKSPACE/downloads/uzkad_agriculture_regions"),
        help="Directory for regional GeoPackages and metadata files.",
    )
    return parser.parse_args()


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest(output_dir: Path) -> tuple[Path, Path]:
    records: list[dict] = []
    all_ids: set[int] = set()
    total_bytes = 0
    total_null_geometries = 0

    for code, slug, region_name in REGIONS:
        gpkg = output_dir / f"{code}_{slug}.gpkg"
        metadata_path = output_dir / f"{code}_{slug}.metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        actual_hash = sha256sum(gpkg)
        if actual_hash != metadata["sha256"]:
            raise RuntimeError(f"Checksum mismatch for {gpkg.name}")

        with closing(sqlite3.connect(gpkg)) as connection, connection:
            count, distinct_count, null_count = connection.execute(
                "SELECT COUNT(*), COUNT(DISTINCT id), "
                "SUM(CASE WHEN geom IS NULL THEN 1 ELSE 0 END) "
                "FROM agricultural_land"
            ).fetchone()
            geometry = connection.execute(
                "SELECT geometry_type_name, srs_id FROM gpkg_geometry_columns "
                "WHERE table_name = 'agricultural_land'"
            ).fetchone()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            region_ids = {
                int(row[0])
                for row in connection.execute("SELECT id FROM agricultural_land")
            }

        if count != distinct_count or len(region_ids) != count:
            raise RuntimeError(f"Duplicate source IDs in {gpkg.name}")
        overlap = all_ids.intersection(region_ids)
        if overlap:
            raise RuntimeError(
                f"{gpkg.name} overlaps another region by {len(overlap):,} IDs"
            )
        if geometry != ("MULTIPOLYGON", 32642) or integrity != "ok":
            raise RuntimeError(f"GeoPackage validation failed for {gpkg.name}")
        if count != int(metadata["feature_count"]):
            raise RuntimeError(f"Feature count mismatch for {gpkg.name}")

        all_ids.update(region_ids)
        size_bytes = gpkg.stat().st_size
        total_bytes += size_bytes
        total_null_geometries += int(null_count or 0)
        records.append(
            {
                "soato_region": code,
                "region_name": region_name,
                "where": f"soato_region='{code}'",
                "file": gpkg.name,
                "metadata_file": metadata_path.name,
                "feature_count": int(count),
                "null_geometry_count": int(null_count or 0),
                "size_bytes": size_bytes,
                "sha256": actual_hash,
            }
        )

    live_national_count = source_count(request_session(), "1=1")
    if len(all_ids) != live_national_count:
        raise RuntimeError(
            f"Regional total {len(all_ids):,} != live national total "
            f"{live_national_count:,}"
        )

    manifest = {
        "source_layer_url": LAYER_URL,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_layer": "agricultural_land",
        "geometry_type": "MultiPolygon",
        "crs": NATIVE_CRS,
        "region_count": len(records),
        "feature_count": len(all_ids),
        "null_geometry_count": total_null_geometries,
        "total_size_bytes": total_bytes,
        "regions": records,
    }
    json_path = output_dir / "manifest.json"
    json_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    csv_path = output_dir / "manifest.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    return json_path, csv_path


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    downloader = Path(__file__).with_name("download_uzkad_agriculture.py")

    for position, (code, slug, _) in enumerate(REGIONS, start=1):
        output = output_dir / f"{code}_{slug}.gpkg"
        print(
            f"\n=== Region {position}/{len(REGIONS)}: {code} {slug} ===",
            flush=True,
        )
        subprocess.run(
            [
                sys.executable,
                str(downloader),
                "--where",
                f"soato_region='{code}'",
                "--output",
                str(output),
            ],
            check=True,
        )

    json_manifest, csv_manifest = build_manifest(output_dir)
    print(f"\nAll {len(REGIONS)} regional downloads are complete: {output_dir}")
    print(f"JSON manifest: {json_manifest}")
    print(f"CSV manifest: {csv_manifest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
