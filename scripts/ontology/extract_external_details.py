"""Materialise details that can only be read from an external delivery.

Some facts live inside files the project references but does not hold: where the
monitoring stations are, and how a labelled training set is distributed across
its classes. Both are read once into ontology/instances/external/details.json,
which the build then consumes. Builds stay deterministic whether or not the
source folder is attached; re-run this whenever the delivery is available and the
mapping has changed.

Driven by ontology/vocab/external-sources.json:
  `stations`        a shapefile (read with the encoding the source really uses)
                    or a spreadsheet with coordinate columns
  `classLabelField` the attribute holding the class of each training polygon

Usage:
    python scripts/ontology/extract_external_details.py
    python scripts/ontology/extract_external_details.py --source uzkad-cadastre-2025-08
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    for attempt in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.15 * (attempt + 1))


def clean_key(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "0", "0.0"}:
        return None
    if text.endswith(".0"):
        text = text[:-2]
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or None


def coerce_float(value):
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # reject NaN


def rows_from_vector(path: Path, config: dict):
    from pyogrio import read_dataframe

    frame = read_dataframe(path, read_geometry=False, encoding=config.get("encoding"))
    return frame.to_dict("records")


def rows_from_table(path: Path, config: dict):
    import pandas as pd

    sheet = config.get("sheet", 0)
    book = pd.ExcelFile(path)
    if isinstance(sheet, str) and sheet not in book.sheet_names:
        sheet = book.sheet_names[0]
    return book.parse(sheet).to_dict("records")


def count_classes(delivery_root: Path, dataset: dict, field: str, warnings: list[str]) -> dict | None:
    """Class balance of a labelled training set, read without touching geometry."""
    from pyogrio import read_dataframe

    for relative in dataset["match"]:
        path = delivery_root / relative
        # The shapefile carries the same attributes as its GeoJSON twin and reads
        # from the .dbf alone, so prefer it over parsing hundreds of MB of JSON.
        if path.suffix.lower() != ".shp" or not path.exists():
            continue
        try:
            frame = read_dataframe(path, columns=[field], read_geometry=False)
        except Exception as error:
            warnings.append(f"{dataset['slug']}: class labels unreadable: {type(error).__name__}: {error}")
            return None
        counts: dict[str, int] = {}
        for value in frame[field].astype(str):
            counts[value] = counts.get(value, 0) + 1
        total = sum(counts.values())
        return {
            "field": field,
            "sourceFile": relative,
            "total": total,
            "classes": dict(sorted(counts.items(), key=lambda item: -item[1])),
        }
    warnings.append(f"{dataset['slug']}: no shapefile available for class labels")
    return None


def extract(root: Path, only_source: str | None = None) -> dict:
    mapping = read_json(root / "ontology" / "vocab" / "external-sources.json")
    external_dir = root / "ontology" / "instances" / "external"
    inventories = {}
    for path in sorted(external_dir.glob("*.json")):
        payload = read_json(path)
        if payload and payload.get("name"):
            inventories[payload["name"]] = payload

    stations: list[dict] = []
    class_labels: dict[str, dict] = {}
    gaps: dict[str, dict] = {}
    warnings: list[str] = []

    for source in mapping["sources"]:
        if only_source and source["id"] != only_source:
            continue
        inventory = inventories.get(source.get("inventory"))
        if inventory is None:
            warnings.append(f"{source['id']}: no inventory named {source.get('inventory')}")
            continue
        delivery_root = Path(inventory["source"])
        for dataset in source["datasets"]:
            field = dataset.get("classLabelField")
            if field:
                counts = count_classes(delivery_root, dataset, field, warnings)
                if counts:
                    class_labels[dataset["slug"]] = counts

            config = dataset.get("stations")
            if not config:
                continue
            network = config["network"]
            prefix = re.sub(r"[^a-z0-9]+", "-", network.split("-")[-1].lower())
            found = False
            for relative in dataset["match"]:
                path = delivery_root / relative
                if not path.exists():
                    warnings.append(f"{dataset['slug']}: {relative} is not on disk; skipped")
                    continue
                try:
                    rows = (rows_from_vector(path, config) if path.suffix.lower() in {".shp", ".geojson", ".gpkg"}
                            else rows_from_table(path, config))
                except Exception as error:
                    warnings.append(f"{dataset['slug']}: {type(error).__name__}: {error}")
                    continue
                found = True
                unkeyed = 0
                missing_coordinates = 0
                for row in rows:
                    longitude = coerce_float(row.get(config["xField"]))
                    latitude = coerce_float(row.get(config["yField"]))
                    if longitude is None or latitude is None:
                        missing_coordinates += 1
                        continue
                    if longitude == 0 or latitude == 0:
                        # Null Island is not in Uzbekistan: a zero coordinate is
                        # the source's way of saying it never recorded one.
                        missing_coordinates += 1
                        continue
                    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
                        warnings.append(
                            f"{dataset['slug']}: coordinate out of range ({longitude}, {latitude}); skipped"
                        )
                        continue
                    key = clean_key(row.get(config["keyField"]))
                    if key is None:
                        unkeyed += 1
                        key = f"x{unkeyed:02d}"
                    label = str(row.get(config["nameField"], "")).strip() or key
                    if config.get("labelIncludesClass") and config.get("classField"):
                        # A gauge list names the river, not the site; without the
                        # location every gauge on one river shares a label.
                        place = str(row.get(config["classField"], "")).strip()
                        if place and place.lower() != "nan":
                            label = f"{label} ({place})"
                    station = {
                        "id": f"uz:station/{prefix}-{key}",
                        "type": "MonitoringStation",
                        "label": label,
                        "network": network,
                        "stationKey": clean_key(row.get(config["keyField"])),
                        "stationClass": (str(row.get(config.get("classField"), "")).strip() or None)
                        if config.get("classField") else None,
                        "longitude": round(longitude, 6),
                        "latitude": round(latitude, 6),
                        "datasetSlug": dataset["slug"],
                        "sourceFile": relative,
                    }
                    stations.append(station)
                if missing_coordinates:
                    gaps[dataset["slug"]] = {
                        "missingCoordinates": missing_coordinates,
                        "sourceFile": relative,
                        "totalRows": len(rows),
                    }
                    warnings.append(
                        f"{dataset['slug']}: {missing_coordinates} of {len(rows)} stations "
                        "have no usable coordinates"
                    )
                break  # one file per station config is enough
            if not found:
                warnings.append(f"{dataset['slug']}: no station file could be read")

    # Same station listed twice in a delivery is one station.
    unique: dict[str, dict] = {}
    duplicates = 0
    for station in stations:
        if station["id"] in unique:
            duplicates += 1
            continue
        unique[station["id"]] = station

    return {
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "counts": {
            "stations": len(unique),
            "duplicatesDropped": duplicates,
            "labelledDatasets": len(class_labels),
        },
        "warnings": warnings,
        "stations": sorted(unique.values(), key=lambda s: s["id"]),
        "stationGaps": gaps,
        "classLabels": class_labels,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--source", help="only this external source id")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    root = Path(args.root).resolve()
    result = extract(root, args.source)
    target = root / "ontology" / "instances" / "external" / "details.json"
    if not result["stations"] and not result["classLabels"]:
        print("nothing extracted; leaving the existing file untouched")
        for warning in result["warnings"]:
            print(f"  WARN {warning}")
        return 1
    write_json(target, result)
    networks: dict[str, int] = {}
    for station in result["stations"]:
        networks[station["network"]] = networks.get(station["network"], 0) + 1
    print(f"{result['counts']['stations']} stations, "
          f"{result['counts']['labelledDatasets']} labelled dataset(s) -> {target}")
    for network, count in sorted(networks.items()):
        print(f"  {network}: {count}")
    for slug, labels in result["classLabels"].items():
        top = list(labels["classes"].items())[:4]
        print(f"  {slug}: {labels['total']:,} samples, "
              + ", ".join(f"{k} {v:,}" for k, v in top) + " ...")
    for warning in result["warnings"][:10]:
        print(f"  WARN {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
