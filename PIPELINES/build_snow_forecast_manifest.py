"""Write provenance and checksums for the regional snow forecast rerun.

    python PIPELINES/build_snow_forecast_manifest.py

Run after build_snow_forecast_region.py and verify_snow_forecast_region.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
GRIDS = ROOT / "WORKSPACE/derived/snow-forecast-region"
SOURCE = ROOT / "GEODATA/ca-discharge-2023/CA-discharge.gpkg"
REGION = ROOT / "PUBLISHED/data/case-studies/snow-forecast/region"
OUTPUT = REGION / "verification-manifest.json"
ARTIFACTS = ("gauges.json", "gauge-skill.csv", "gauge-basin-links.csv",
             "basin-gauge-association.csv", "basin-glacier-cell-share.csv",
             "basin-predictors.parquet", "page.json", "verify-snow-forecast-region.py")
METHODS = ("PIPELINES/extract_snow_forecast_region.py",
           "PIPELINES/build_snow_forecast_region.py",
           "PIPELINES/build_snow_forecast_study.py",
           "PIPELINES/verify_snow_forecast_region.py")


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def build():
    grids = sorted(GRIDS.glob("wy=*.tif"))
    if not grids or not SOURCE.exists():
        raise FileNotFoundError("The source GeoPackage and regional grids are required")
    years = [int(path.stem.split("=")[1]) for path in grids]
    if years != list(range(years[0], years[-1] + 1)):
        raise ValueError("Regional water-year grids are not consecutive")
    for path in grids:
        if not path.with_suffix(".json").exists():
            raise FileNotFoundError(path.with_suffix(".json"))
    for name in ARTIFACTS:
        if not (REGION / name).exists():
            raise FileNotFoundError(REGION / name)
    report = json.loads((REGION / "gauges.json").read_text())
    if any("operational_inputs" not in issue for gauge in report["gauges"]
           for issue in gauge["issue"].values()):
        raise ValueError("Regional JSON is missing operational inputs")
    base_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "study_generated_at": report["generated_at"],
        "base_commit_before_rerun": base_commit,
        "hash_scope": "Local pre-release file bytes; the launch build compacts JSON, so downloaded JSON has different byte hashes",
        "source": {
            "ca_discharge": {"record": "https://doi.org/10.5281/zenodo.8147591",
                             "file": "CA-discharge.gpkg", **fingerprint(SOURCE)},
            "era5_land": {"earth_engine_daily": "ECMWF/ERA5_LAND/DAILY_AGGR",
                          "earth_engine_monthly": "ECMWF/ERA5_LAND/MONTHLY_AGGR",
                          "earth_engine_elevation": "CGIAR/SRTM90_V4",
                          "water_years": [years[0], years[-1]],
                          "elevation": fingerprint(GRIDS / "elevation.tif"),
                          "grids": {str(year): {"tif": fingerprint(path),
                                                "bands": fingerprint(path.with_suffix(".json"))}
                                    for year, path in zip(years, grids)}},
        },
        "outputs": {name: fingerprint(REGION / name) for name in ARTIFACTS},
        "methods": {name: fingerprint(ROOT / name) for name in METHODS},
        "gauges": len(report["gauges"]),
        "issue_records": sum(len(gauge["issue"]) for gauge in report["gauges"]),
        "verification_command": "python PIPELINES/verify_snow_forecast_region.py",
        "verification_scope": "Refits fixed one-predictor operational hindcasts; does not independently re-extract gridded SWE",
    }
    OUTPUT.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    manifest = build()
    print(f"Wrote {OUTPUT}: {manifest['gauges']} gauges, {manifest['issue_records']} issue records")
