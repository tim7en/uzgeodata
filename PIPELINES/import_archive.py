"""Import the environmental atlas packages into UzGeoData's private repository."""
from __future__ import annotations

import argparse
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--catalog", type=Path, default=Path("PUBLISHED/data/archive-catalog.json"))
    parser.add_argument("--storage", type=Path, default=Path("WORKSPACE"))
    args = parser.parse_args()

    uploads = args.storage / "uploads"
    metadata_file = args.storage / "datasets.json"
    uploads.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    current = json.loads(metadata_file.read_text(encoding="utf-8")) if metadata_file.exists() else []
    imported = {item.get("sourceKey") for item in current}
    records_by_source = {item["sourceTitle"]: item for item in catalog}
    added = 0

    for source_file in sorted(args.source.glob("*.lpkx"), key=lambda item: item.name.casefold()):
        source_key = f"environmental-atlas/{source_file.name}"
        if source_key in imported:
            continue
        catalog_item = records_by_source.get(source_file.stem)
        if not catalog_item:
            continue
        stored_name = f"{uuid.uuid4()}.lpkx"
        shutil.copy2(source_file, uploads / stored_name)
        current.append({
            "id": str(uuid.uuid4()),
            "sourceKey": source_key,
            "title": catalog_item["title"],
            "category": catalog_item["category"],
            "access": "Request",
            "description": f"Original ArcGIS layer package from the Uzbekistan environmental atlas. Source title: {catalog_item['sourceTitle']}",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "files": [{"storedName": stored_name, "originalName": source_file.name, "size": source_file.stat().st_size}],
        })
        added += 1
        print(f"[{added:03d}] {catalog_item['title']}")

    temporary = metadata_file.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(metadata_file)
    print(json.dumps({"added": added, "total": len(current)}, indent=2))


if __name__ == "__main__":
    main()
