"""Independent, bounded check of screenshot basin 4121292070. Run from repo root."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "PUBLISHED/data/atlas"
OUT = Path(__file__).resolve().parent / "result.json"
BASIN = "4121292070"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix_row(path, nbasins, months, position, scale, missing):
    raw = gzip.decompress(path.read_bytes())
    n = nbasins * months
    assert len(raw) == n * 4
    # The four byte planes are stored separately. Delta restarts each basin.
    vals = []
    previous = 0
    for month in range(months):
        j = position * months + month
        encoded = raw[j] | raw[n + j] << 8 | raw[2 * n + j] << 16 | raw[3 * n + j] << 24
        signed = struct.unpack("<i", struct.pack("<I", encoded))[0]
        current = (signed + previous + 2**31) % 2**32 - 2**31 if month else signed
        previous = current
        vals.append(None if current == missing else current / scale)
    return vals


def main():
    index_path = DATA / "catchments/index.json"
    morph_path = DATA / "catchments/morphology.json"
    catalogue_path = DATA / "catalogue.json"
    basin_path = DATA / f"basins/{BASIN}.json"
    history_path = DATA / f"history/{BASIN}.json"
    paths = [index_path, morph_path, catalogue_path, basin_path, history_path]
    index, morph, cat, basin, history = map(read, paths)
    ids = [str(x) for x in index["ids"]]
    next_down = [str(x) for x in index["next_down"]]
    position = {bid: i for i, bid in enumerate(ids)}
    assert BASIN in position
    upstream = {BASIN}
    while True:
        additions = {bid for bid, downstream in zip(ids, next_down) if downstream in upstream}
        next_set = upstream | additions
        if next_set == upstream:
            break
        upstream = next_set
    members = [position[bid] for bid in upstream]
    total_area = sum(index["areas_km2"][i] for i in members)
    published_morph = morph["basins"][BASIN]
    result = {
        "basin": BASIN,
        "inputs_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): digest(path) for path in paths},
        "network": {
            "member_count_including_selected": len(members),
            "upstream_count_excluding_selected": len(members) - 1,
            "traced_area_km2_recalculated": total_area,
            "traced_area_km2_published": published_morph["traced_area_km2"],
            "reported_upstream_area_km2": published_morph["reported_upstream_area_km2"],
            "difference_traced_minus_reported_km2": total_area - published_morph["reported_upstream_area_km2"],
        },
        "morphology": {
            "relief_m_recalculated": published_morph["highest_elevation_m"] - published_morph["lowest_elevation_m"],
            "relief_m_published": published_morph["relief_m"],
            "circularity_recalculated": 4 * math.pi * published_morph["geometry_area_km2"] / published_morph["outer_perimeter_km"] ** 2,
            "circularity_published": published_morph["circularity"],
        },
        "catchment_months": {},
        "substitutes": {},
    }
    for name in ("pre_mm_s", "snw_pc_s"):
        entry = index["series"][name]
        path = ROOT / "PUBLISHED" / entry["url"].lstrip("/").removeprefix("data/")
        # URLs are rooted at /data; repository files are under PUBLISHED/data.
        path = ROOT / "PUBLISHED" / entry["url"].lstrip("/")
        compressed_hash = digest(path)
        assert compressed_hash == entry["sha256"]
        paths.append(path)
        rows = {i: matrix_row(path, len(ids), index["months"], i, index["scale"], index["null_sentinel"]) for i in members}
        summaries = {}
        month_indices = [0, 275]
        if name == "snw_pc_s":
            incomplete = next((m for m in range(index["months"]) if any(rows[i][m] is None for i in members)), None)
            if incomplete is not None:
                month_indices.append(incomplete)
        for m in sorted(set(month_indices)):
            valid = [(i, rows[i][m]) for i in members if rows[i][m] is not None]
            area = sum(index["areas_km2"][i] for i, _ in valid)
            weighted = sum(index["areas_km2"][i] * value for i, value in valid)
            summaries[f"{index['years'][0] + m // 12}-{m % 12 + 1:02}"] = {
                "observed_basins": len(valid), "basin_count": len(members),
                "covered_area_km2": area, "coverage_percent": area / total_area * 100,
                "weighted_mean_observed_area": weighted / area if area else None,
                "full_catchment_total": weighted * (1000 if name == "pre_mm_s" else .01) if len(valid) == len(members) else None,
                "covered_area_total": weighted * (1000 if name == "pre_mm_s" else .01) if valid else None,
                "subbasin_min": min((v for _, v in valid), default=None),
                "subbasin_max": max((v for _, v in valid), default=None),
            }
        result["catchment_months"][name] = {"compressed_sha256": compressed_hash, "provenance": entry["provenance"], "months": summaries}

    for column, hist_name, calendar_month in (("pre_mm_s01", "pre_mm_s", 1), ("aet_mm_s01", "aet_mm_s", 1)):
        col = cat["attributes"].index(column)
        values = history["series"][hist_name]["values"]
        observed = [v for j, v in enumerate(values) if j % 12 + 1 == calendar_month and v is not None]
        current_mean = sum(observed) / len(observed)
        substitute = basin["substitute"][col]
        result["substitutes"][column] = {
            "published_estimate": substitute,
            "published_valid": basin["substitute_valid"][col],
            "published_expected": basin["substitute_expected"][col],
            "published_source": cat["meta"][column]["substitute"],
            "reestimated_mean_from_current_monthly_history": current_mean,
            "history_valid": len(observed),
            "difference_current_history_minus_published": current_mean - substitute,
            "history_source": history["series"][hist_name]["source_release"],
        }
    result["substitutes"]["counts"] = {
        "attributes": len(cat["attributes"]),
        "non_null_estimates": sum(v is not None for v in basin["substitute"]),
        "non_null_originals": sum(v is not None for v in basin["original"]),
    }
    result["inputs_sha256"].update({str(path.relative_to(ROOT)).replace("\\", "/"): digest(path) for path in paths})
    network, shape = result["network"], result["morphology"]
    result["checks"] = {
        "upstream_members": "PASS" if network["member_count_including_selected"] == published_morph["basin_count"] else "FAIL",
        "traced_area": "PASS" if abs(network["traced_area_km2_recalculated"] - network["traced_area_km2_published"]) < 0.01 else "FAIL",
        "relief": "PASS" if shape["relief_m_recalculated"] == shape["relief_m_published"] else "FAIL",
        "circularity": "PASS" if abs(shape["circularity_recalculated"] - shape["circularity_published"]) < 1e-9 else "FAIL",
        # Precipitation must cover the whole catchment; snow cover is allowed gaps, reported not failed.
        "precipitation_coverage": "PASS" if all(m["coverage_percent"] == 100
                                                for m in result["catchment_months"]["pre_mm_s"]["months"].values()) else "FAIL",
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "network": network}, indent=2))
    if "FAIL" in result["checks"].values():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
