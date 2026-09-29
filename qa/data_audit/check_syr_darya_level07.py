"""Independent, bounded HydroATLAS level-07 topology/area audit.

Uses native properties in the local Earth Engine HydroATLAS export. It does
not import production builders or use their membership flags as expectations.
"""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "GEODATA/transboundary_basins_v2/hydroatlas-level07-full-basins.geojson"
MANIFEST = ROOT / "GEODATA/transboundary_basins_v2/manifest.json"
PUBLISHED = ROOT / "PUBLISHED/data/hydroclimate/basin-membership-level07.csv"
OUT = Path(__file__).with_name("results.json")
SYSTEM = "syr_darya"
MAIN_BAS = 4070050240
OUTLET = 4070425650


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    features = [f["properties"] for f in source["features"] if f["properties"]["MAIN_BAS"] == MAIN_BAS]
    ids = [int(p["HYBAS_ID"]) for p in features]
    duplicates = sorted(k for k, n in Counter(ids).items() if n > 1)
    by_id = {int(p["HYBAS_ID"]): p for p in features}
    parents = defaultdict(list)
    for p in features:
        parents[int(p["NEXT_DOWN"])].append(int(p["HYBAS_ID"]))

    reached = set()
    frontier = [OUTLET]
    while frontier:
        node = frontier.pop()
        if node in reached:
            continue
        reached.add(node)
        frontier.extend(parents[node])

    # Follow every selected unit downstream to detect cycles and breaks,
    # independently of the reverse traversal above.
    bad_paths = {}
    for start in reached:
        seen = set()
        node = start
        while node != OUTLET:
            if node in seen:
                bad_paths[start] = "cycle"
                break
            seen.add(node)
            if node not in by_id:
                bad_paths[start] = f"missing unit {node}"
                break
            node = int(by_id[node]["NEXT_DOWN"])

    with PUBLISHED.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    pub_rows = [r for r in rows if r["system_id"] == SYSTEM and r["headwater_formation"] == "1"]
    pub_ids = [int(r["hybas_id"]) for r in pub_rows]
    pub_set = set(pub_ids)
    source_area = sum(float(by_id[k]["SUB_AREA"]) for k in reached)
    native_up_area = float(by_id[OUTLET]["UP_AREA"])
    # Source values and reported totals have one decimal place. Each rounded
    # SUB_AREA contributes at most 0.05 km²; final rounding contributes 0.05.
    area_tolerance = round(0.05 * len(reached) + 0.05, 2)
    reported = next(s for s in manifest["levels"][0]["systems"] if s["systemId"] == SYSTEM)
    reported_area = float(reported["headwaterSourceAreaKm2"])
    checks = {
        "source_export_hash_matches_manifest": sha256(SOURCE) == manifest["levels"][0]["sha256"],
        "unique_source_hybas_ids": not duplicates,
        "outlet_present": OUTLET in by_id,
        "all_selected_paths_reach_outlet": not bad_paths,
        "published_membership_matches_native_routing": pub_set == reached and len(pub_ids) == len(pub_set),
        "source_area_matches_manifest_within_rounding": abs(source_area - reported_area) <= area_tolerance,
        "source_area_matches_native_up_area_within_rounding": abs(source_area - native_up_area) <= area_tolerance,
    }
    result = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {"system": SYSTEM, "level": 7, "main_bas": MAIN_BAS, "headwater_outlet_hybas_id": OUTLET, "variable": "upstream topology and SUB_AREA", "period": "static topology; no temporal aggregation", "units": "km2"},
        "source": {"producer": "WWF HydroATLAS / HydroBASINS via Google Earth Engine", "asset": "WWF/HydroATLAS/v1/Basins/level07", "local_export": str(SOURCE.relative_to(ROOT)), "sha256": sha256(SOURCE), "manifest": str(MANIFEST.relative_to(ROOT)), "export_generated_at": manifest["generatedAt"], "native_fields": ["HYBAS_ID", "MAIN_BAS", "NEXT_DOWN", "SUB_AREA", "UP_AREA"], "resolution": "HydroATLAS level 07 polygons", "missing_policy": "all selected source properties must be present; no imputation"},
        "comparison": {"published_membership": str(PUBLISHED.relative_to(ROOT)), "published_sha256": sha256(PUBLISHED), "source_unit_count": len(features), "reconstructed_upstream_count": len(reached), "published_upstream_count": len(pub_ids), "duplicate_source_ids": duplicates, "bad_downstream_paths": bad_paths, "missing_in_published": sorted(reached - pub_set), "extra_in_published": sorted(pub_set - reached), "reconstructed_upstream_ids": sorted(reached), "source_sub_area_sum_km2": round(source_area, 3), "manifest_headwater_area_km2": reported_area, "outlet_native_up_area_km2": native_up_area, "absolute_error_vs_manifest_km2": round(abs(source_area - reported_area), 3), "absolute_error_vs_native_up_area_km2": round(abs(source_area - native_up_area), 3), "rounding_tolerance_km2": area_tolerance, "relative_error_vs_native_up_area": abs(source_area - native_up_area) / native_up_area, "missing_value_rate": 0.0},
        "checks": checks,
        "limitations": ["The local GeoJSON is a GEE export of the catalog asset, not an independently downloaded original WWF shapefile.", "This verifies routing and source attribute sums for one outlet, not geodesic polygon area or climate raster aggregation.", "Local source files do not pin a licence statement for this exact export."],
    }
    return result


if __name__ == "__main__":
    result = audit()
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{result['status']}: {result['comparison']['reconstructed_upstream_count']} units; area {result['comparison']['source_sub_area_sum_km2']} km2; evidence {OUT}")
    raise SystemExit(0 if result["status"] == "PASS" else 1)
