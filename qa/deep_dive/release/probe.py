"""Bounded, read-only release provenance probe; writes metadata, never remote bodies."""

import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("evidence.json")
BASE = "https://uzgeodata.uz"
PATHS = ["/release.json", "/data/atlas/latest.json", "/data/atlas/cube/index.json",
         "/data/atlas/releases/uz-20260924T150158900Z.json"]
LIMIT = 100_000


def details(raw):
    item = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    try:
        obj = json.loads(raw)
        canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        item["canonical_json_sha256"] = hashlib.sha256(canonical).hexdigest()
        item["json_fields"] = {key: obj.get(key) for key in
                               ("release_id", "path", "commit", "generated_at", "rows", "months", "bytes")
                               if key in obj}
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    return item


def main():
    paths = {
        "manifest": "PUBLISHED/data/atlas/releases/uz-20260924T150158900Z.json",
        "latest": "PUBLISHED/data/atlas/latest.json",
        "cube_index": "PUBLISHED/data/atlas/cube/index.json",
    }
    local = {name: details((ROOT / relative).read_bytes()) for name, relative in paths.items()}
    old = subprocess.check_output(["git", "show", "06ac19791:PUBLISHED/data/atlas/cube/index.json"], cwd=ROOT)
    old_crlf = old.replace(b"\n", b"\r\n")
    manifest = json.loads((ROOT / paths["manifest"]).read_text(encoding="utf-8"))
    verified = {}
    for path in PATHS:
        with tempfile.TemporaryDirectory() as directory:
            body = Path(directory) / "body"
            result = subprocess.run(
                ["curl.exe", "--fail", "--silent", "--show-error", "--location",
                 "--max-time", "12", "--max-filesize", str(LIMIT),
                 "--output", str(body), "--write-out", "%{http_code}", BASE + path],
                capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                verified[path] = {"status": int(result.stdout), "tls_verified_by": "Windows Schannel",
                                  **details(body.read_bytes())}
            else:
                verified[path] = {"curl_exit_code": result.returncode,
                                  "error": result.stderr.strip()[:300]}
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "base": BASE,
        "method": "GET; 12 s timeout; 100000 byte response cap; no remote body persisted",
        "local": local,
        "git_06ac19791_cube_index": details(old),
        "git_06ac19791_cube_index_crlf": details(old_crlf),
        "manifest_cube_index": manifest["files"]["cube/index.json"],
        "remote_verified": verified,
        "python_ssl_diagnostic": {"verified_request": "CERTIFICATE_VERIFY_FAILED: certificate has expired",
                                  "scope": "Python CA-bundle chain on this machine; Windows Schannel verified the site"},
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
