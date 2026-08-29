#!/usr/bin/env python3
"""Download a filtered UZKAD agriculture layer to a GeoPackage.

The ArcGIS service limits each response to 2,000 features. This downloader uses
ordered, keyset-paginated GeoJSON requests and appends each page with GDAL's
``ogr2ogr``. If an existing output is supplied, downloading resumes after the
largest saved source ``id``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


LAYER_URL = (
    "https://db.ngis.uz/db/rest/services/UZKAD/"
    "AGR_ONLY_UZKAD_DB16/FeatureServer/0"
)
DEFAULT_OGR2OGR = Path(r"C:\Program Files\QGIS 3.22.5\bin\ogr2ogr.exe")
NATIVE_CRS = "EPSG:32642"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a filtered UZKAD agriculture layer to GeoPackage."
    )
    parser.add_argument(
        "--where",
        default="soato_region='1710'",
        help="ArcGIS SQL filter (default: Qashqadaryo region, SOATO 1710).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "WORKSPACE/downloads/uzkad_agriculture_regions/"
            "1710_qashqadaryo.gpkg"
        ),
        help="Destination GeoPackage path.",
    )
    parser.add_argument(
        "--layer-name",
        default="agricultural_land",
        help="Destination GeoPackage layer name.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=2000,
        choices=range(1, 2001),
        metavar="1..2000",
        help="Features requested per service call (default: 2000).",
    )
    parser.add_argument(
        "--ogr2ogr",
        type=Path,
        default=DEFAULT_OGR2OGR,
        help="Path to ogr2ogr.exe.",
    )
    return parser.parse_args()


def request_session() -> requests.Session:
    retry = Retry(
        total=8,
        connect=8,
        read=8,
        status=8,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.headers["User-Agent"] = "uzgeodata-uzkad-downloader/1.0"
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def query_json(
    session: requests.Session, params: dict[str, str | int | bool]
) -> dict:
    response = session.get(f"{LAYER_URL}/query", params=params, timeout=(20, 180))
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"ArcGIS query failed: {payload['error']}")
    return payload


def source_count(session: requests.Session, where: str) -> int:
    payload = query_json(
        session,
        {"where": where, "returnCountOnly": "true", "f": "json"},
    )
    return int(payload["count"])


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def saved_state(output: Path, layer_name: str) -> tuple[int, int]:
    if not output.exists():
        return 0, -1
    table = quote_identifier(layer_name)
    try:
        with closing(sqlite3.connect(output)) as connection, connection:
            row = connection.execute(
                f"SELECT COUNT(*), COALESCE(MAX(id), -1) FROM {table}"
            ).fetchone()
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Cannot resume from {output}: layer {layer_name!r} is unavailable"
        ) from exc
    return int(row[0]), int(row[1])


def write_page(payload: dict, destination: Path) -> list[int]:
    features = payload.get("features")
    if not isinstance(features, list):
        raise RuntimeError("ArcGIS response is missing its features array")
    ids: list[int] = []
    for feature in features:
        properties = feature.get("properties") or {}
        if "id" not in properties:
            raise RuntimeError("ArcGIS response contains a feature without an id")
        ids.append(int(properties["id"]))
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise RuntimeError("ArcGIS response IDs are not unique and ordered")
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return ids


def append_page(
    ogr2ogr: Path,
    page: Path,
    output: Path,
    layer_name: str,
    output_exists: bool,
) -> None:
    if output_exists:
        command = [
            str(ogr2ogr),
            "-f",
            "GPKG",
            "-update",
            "-append",
            str(output),
            str(page),
            "-nln",
            layer_name,
            "-nlt",
            "PROMOTE_TO_MULTI",
        ]
    else:
        command = [
            str(ogr2ogr),
            "-f",
            "GPKG",
            str(output),
            str(page),
            "-nln",
            layer_name,
            "-nlt",
            "PROMOTE_TO_MULTI",
            "-a_srs",
            NATIVE_CRS,
            "-lco",
            "SPATIAL_INDEX=YES",
        ]
    subprocess.run(command, check=True)


def add_source_id_index(output: Path, layer_name: str) -> None:
    index_name = quote_identifier(f"idx_{layer_name}_source_id")
    table = quote_identifier(layer_name)
    with closing(sqlite3.connect(output)) as connection, connection:
        connection.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table} (id)"
        )


def normalize_output_schema(output: Path, layer_name: str) -> None:
    """Apply authoritative ArcGIS types that GeoJSON cannot fully express."""
    table = quote_identifier(layer_name)
    with closing(sqlite3.connect(output)) as connection, connection:
        geometry_row = connection.execute(
            "SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ?",
            (layer_name,),
        ).fetchone()
        if not geometry_row:
            raise RuntimeError(f"GeoPackage geometry metadata is missing for {layer_name}")

        # ogr2ogr promotes every polygon to a MultiPolygon, but mixed source
        # Polygon/MultiPolygon pages cause the GeoJSON driver to declare the
        # layer as generic GEOMETRY. Record the actual, narrower type.
        connection.execute(
            "UPDATE gpkg_geometry_columns SET geometry_type_name = 'MULTIPOLYGON' "
            "WHERE table_name = ?",
            (layer_name,),
        )

        declared_types = {
            row[1]: str(row[2]).upper()
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
        # GeoPackage RTree maintenance triggers reference GDAL spatial SQL
        # functions that Python's built-in sqlite3 does not provide. Temporarily
        # remove the table's triggers while changing non-spatial columns, then
        # restore their exact definitions within the same transaction.
        triggers = connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'trigger' AND tbl_name = ? AND sql IS NOT NULL",
            (layer_name,),
        ).fetchall()
        for trigger_name, _ in triggers:
            connection.execute(f"DROP TRIGGER {quote_identifier(trigger_name)}")

        conversions = {
            "store_count": ("INTEGER", int),
            "height": ("REAL", float),
        }
        for field_name, (sql_type, parser) in conversions.items():
            if declared_types.get(field_name) == sql_type:
                continue
            field = quote_identifier(field_name)
            values = connection.execute(
                f"SELECT {field} FROM {table} WHERE {field} IS NOT NULL"
            ).fetchall()
            try:
                for (value,) in values:
                    parser(value)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"Cannot safely convert {field_name} to {sql_type}: {value!r}"
                ) from exc

            old_field_name = f"__text_{field_name}"
            old_field = quote_identifier(old_field_name)
            connection.execute(f"ALTER TABLE {table} RENAME COLUMN {field} TO {old_field}")
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {field} {sql_type}")
            connection.execute(
                f"UPDATE {table} SET {field} = CAST({old_field} AS {sql_type}) "
                f"WHERE {old_field} IS NOT NULL"
            )
            connection.execute(f"ALTER TABLE {table} DROP COLUMN {old_field}")

        for _, trigger_sql in triggers:
            connection.execute(trigger_sql)

        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"GeoPackage integrity check failed: {integrity}")


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stabilize_geopackage(path: Path) -> None:
    """Checkpoint inherited WAL state before calculating a container hash."""
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        connection.execute("PRAGMA journal_mode=DELETE").fetchone()
    finally:
        connection.close()


def write_metadata(
    output: Path,
    layer_name: str,
    where: str,
    feature_count: int,
    null_geometry_count: int,
) -> Path:
    stabilize_geopackage(output)
    metadata_path = output.with_suffix(".metadata.json")
    metadata = {
        "source_layer_url": LAYER_URL,
        "query_url": f"{LAYER_URL}/query",
        "where": where,
        "output_layer": layer_name,
        "feature_count": feature_count,
        "source_object_id_field": "id",
        "geometry_type": "MultiPolygon",
        "crs": NATIVE_CRS,
        "null_geometry_count": null_geometry_count,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": sha256sum(output),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata_path


def validate_source_ids(
    session: requests.Session,
    output: Path,
    layer_name: str,
    where: str,
) -> tuple[int, int]:
    payload = query_json(
        session,
        {"where": where, "returnIdsOnly": "true", "f": "json"},
    )
    source_ids = {int(value) for value in payload.get("objectIds") or []}
    table = quote_identifier(layer_name)
    with closing(sqlite3.connect(output)) as connection, connection:
        local_ids = {
            int(row[0])
            for row in connection.execute(f"SELECT id FROM {table}")
        }
        local_null_geometry_ids = {
            int(row[0])
            for row in connection.execute(
                f"SELECT id FROM {table} WHERE geom IS NULL"
            )
        }
        geometry_metadata = connection.execute(
            "SELECT geometry_type_name, srs_id FROM gpkg_geometry_columns "
            "WHERE table_name = ?",
            (layer_name,),
        ).fetchone()

    if local_ids != source_ids:
        missing = len(source_ids - local_ids)
        extra = len(local_ids - source_ids)
        raise RuntimeError(
            f"Source ID mismatch: {missing:,} missing and {extra:,} extra features"
        )
    if local_null_geometry_ids:
        source_null_geometry_ids: set[int] = set()
        null_ids = sorted(local_null_geometry_ids)
        for offset in range(0, len(null_ids), 500):
            batch = null_ids[offset : offset + 500]
            payload = query_json(
                session,
                {
                    "where": f"id IN ({','.join(map(str, batch))})",
                    "outFields": "id",
                    "returnGeometry": "true",
                    "outSR": "32642",
                    "f": "geojson",
                },
            )
            returned_ids: set[int] = set()
            for feature in payload.get("features") or []:
                source_id = int(feature["properties"]["id"])
                returned_ids.add(source_id)
                if feature.get("geometry") is None:
                    source_null_geometry_ids.add(source_id)
            if returned_ids != set(batch):
                raise RuntimeError("Could not re-query every locally null geometry")
        if source_null_geometry_ids != local_null_geometry_ids:
            raise RuntimeError(
                "Local and source null-geometry IDs do not match exactly"
            )
        print(
            f"Preserved {len(local_null_geometry_ids):,} source record(s) with null geometry",
            flush=True,
        )
    if geometry_metadata != ("MULTIPOLYGON", 32642):
        raise RuntimeError(
            f"Unexpected geometry metadata: {geometry_metadata!r}"
        )
    print(
        f"Verified all {len(source_ids):,} source IDs; no missing or extra features",
        flush=True,
    )
    return len(source_ids), len(local_null_geometry_ids)


def resolve_ogr2ogr(candidate: Path) -> Path:
    if candidate.is_file():
        return candidate.resolve()
    discovered = shutil.which(str(candidate)) or shutil.which("ogr2ogr")
    if discovered:
        return Path(discovered).resolve()
    raise FileNotFoundError(
        f"ogr2ogr not found at {candidate}. Supply its path with --ogr2ogr."
    )


def main() -> int:
    args = parse_args()
    ogr2ogr = resolve_ogr2ogr(args.ogr2ogr)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    session = request_session()
    expected_count = source_count(session, args.where)
    saved_count, last_id = saved_state(output, args.layer_name)
    if saved_count > expected_count:
        raise RuntimeError(
            f"Output has {saved_count:,} rows but the source filter has only "
            f"{expected_count:,}; use a different output file."
        )

    print(f"Source filter: {args.where}", flush=True)
    print(f"Expected features: {expected_count:,}", flush=True)
    print(f"Already saved: {saved_count:,}; resuming after id {last_id}", flush=True)

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="uzkad-agriculture-") as temp_dir:
        page_path = Path(temp_dir) / "page.geojson"
        while saved_count < expected_count:
            page_where = f"({args.where}) AND id > {last_id}"
            payload = query_json(
                session,
                {
                    "where": page_where,
                    "outFields": "*",
                    "returnGeometry": "true",
                    "outSR": "32642",
                    "orderByFields": "id ASC",
                    "resultRecordCount": args.page_size,
                    "f": "geojson",
                },
            )
            ids = write_page(payload, page_path)
            if not ids:
                raise RuntimeError(
                    f"Service returned no features after id {last_id}, but "
                    f"{expected_count - saved_count:,} remain according to the count query."
                )
            if ids[0] <= last_id:
                raise RuntimeError("ArcGIS pagination did not advance")

            append_page(
                ogr2ogr,
                page_path,
                output,
                args.layer_name,
                output.exists(),
            )
            saved_count, last_id = saved_state(output, args.layer_name)
            elapsed = max(time.monotonic() - started, 0.001)
            rate = (saved_count / elapsed) if saved_count else 0.0
            print(
                f"Saved {saved_count:,}/{expected_count:,} "
                f"({saved_count / expected_count:.1%}); last id {last_id}; "
                f"{rate:,.0f} features/s",
                flush=True,
            )

    final_count, _ = saved_state(output, args.layer_name)
    if final_count != expected_count:
        raise RuntimeError(
            f"Final count mismatch: saved {final_count:,}, expected {expected_count:,}"
        )
    normalize_output_schema(output, args.layer_name)
    add_source_id_index(output, args.layer_name)
    verified_count, null_geometry_count = validate_source_ids(
        session, output, args.layer_name, args.where
    )
    if verified_count != final_count:
        raise RuntimeError(
            f"Verified ID count mismatch: {verified_count:,} != {final_count:,}"
        )
    metadata_path = write_metadata(
        output,
        args.layer_name,
        args.where,
        final_count,
        null_geometry_count,
    )
    print(f"Complete: {output} ({final_count:,} features, {NATIVE_CRS})", flush=True)
    print(f"Metadata: {metadata_path}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, requests.RequestException, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
