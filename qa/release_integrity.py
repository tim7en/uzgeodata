"""Compare a pinned release manifest with actual local published bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ATLAS_MODULES.core.releases import content_digest  # noqa: E402


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def check(data_root: Path, release_id: str, selected: list[str] | None) -> dict:
    manifest_path = data_root / "releases" / f"{release_id}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("release_id") != release_id:
        raise ValueError("Release ID differs from manifest contents")
    files = manifest["files"]
    names = selected or sorted(files)
    results = []
    for name in names:
        if name not in files:
            raise ValueError(f"Artifact is not in pinned manifest: {name}")
        path = (data_root / name).resolve()
        if not path.is_relative_to(data_root.resolve()):
            raise ValueError(f"Artifact path escapes data root: {name}")
        expected = files[name]
        if not path.is_file():
            results.append({"path": name, "status": "FAIL", "reason": "missing"})
            continue
        # Schema 2 manifests fingerprint content (text normalised to LF, see
        # ATLAS_MODULES/core/releases.py); schema 1 fingerprinted the bytes on disk.
        if manifest.get("schema_version", 1) >= 2:
            actual_bytes, actual_sha256 = content_digest(path)
        else:
            actual_bytes, actual_sha256 = path.stat().st_size, digest(path)
        status = "PASS" if actual_bytes == expected["bytes"] and actual_sha256 == expected["sha256"] else "FAIL"
        results.append({"path": name, "status": status, "expected_bytes": expected["bytes"],
                        "actual_bytes": actual_bytes, "expected_sha256": expected["sha256"],
                        "actual_sha256": actual_sha256})
    return {"schema_version": 1, "check": "release_file_integrity", "release_id": release_id,
            "manifest": str(manifest_path), "scope": names,
            "status": "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL",
            "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("PUBLISHED/data/atlas"))
    parser.add_argument("--release-id", help="Pinned release; default follows local latest.json")
    parser.add_argument("--file", action="append", dest="files", help="Manifest-relative artifact; repeatable. Default: all")
    parser.add_argument("--output", type=Path, help="Write JSON report; stdout is used by default")
    args = parser.parse_args()
    try:
        release_id = args.release_id or json.loads((args.data_root / "latest.json").read_text(encoding="utf-8"))["release_id"]
        report = check(args.data_root, release_id, args.files)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        report = {"schema_version": 1, "check": "release_file_integrity", "status": "ERROR", "error": str(exc)}
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
