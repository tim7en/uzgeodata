#!/usr/bin/env python3
"""Download a filtered UZKAD agriculture layer to a GeoPackage.

The ArcGIS service limits each response to 2,000 features. This downloader uses
ordered, keyset-paginated GeoJSON requests and appends each page with GDAL's
``ogr2ogr``. If an existing output is supplied, downloading resumes after the
largest saved source ``id``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
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
        default=Path("WORKSPACE/downloads/uzkad_agriculture_qashqadaryo.gpkg"),
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
        with sqlite3.connect(output) as connection:
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
    with sqlite3.connect(output) as connection:
        connection.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table} (id)"
        )


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
    add_source_id_index(output, args.layer_name)
    print(f"Complete: {output} ({final_count:,} features, {NATIVE_CRS})", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, requests.RequestException, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
