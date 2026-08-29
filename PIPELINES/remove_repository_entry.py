"""Safely remove one imported repository copy while preserving the external source archive."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--storage", type=Path, default=Path("WORKSPACE"))
    args = parser.parse_args()
    metadata_file = (args.storage / "datasets.json").resolve()
    upload_root = (args.storage / "uploads").resolve()
    entries = json.loads(metadata_file.read_text(encoding="utf-8"))
    matches = [entry for entry in entries if entry.get("title") == args.title and entry.get("sourceKey")]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one imported match for {args.title!r}, found {len(matches)}")
    entry = matches[0]
    removed_bytes = 0
    for stored_file in entry.get("files", []):
        target = (upload_root / Path(stored_file["storedName"]).name).resolve()
        if target.parent != upload_root:
            raise RuntimeError(f"Unsafe repository target: {target}")
        if target.exists():
            removed_bytes += target.stat().st_size
            target.unlink()
    temporary = metadata_file.with_suffix(".json.tmp")
    temporary.write_text(json.dumps([item for item in entries if item["id"] != entry["id"]], ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(metadata_file)
    print(json.dumps({"removed": entry["title"], "bytes": removed_bytes, "sourcePreserved": True}, indent=2))


if __name__ == "__main__":
    main()
