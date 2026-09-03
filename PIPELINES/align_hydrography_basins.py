"""Publish the canonical BasinATLAS level-12 frame to the hydrography explorer.

Older builds exported the lake-format HydroBASINS selection even though the
manifest and downstream climate tables use standard BasinATLAS identifiers.
This repair is deliberately independent of GDAL: it strips the already-reviewed
BasinATLAS GeoJSON to web fields, simplifies geometry, refreshes basin nodes in
the relationship graph, and records any legacy river/lake joins that do not
resolve instead of silently dropping them.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "PUBLISHED/data/review/basinatlas/basinatlas_uz_lev12.geojson"
TARGET = ROOT / "PUBLISHED/data/hydrography/basins.geojson"
RELATIONSHIPS = ROOT / "PUBLISHED/data/hydrography/relationships.json"
MANIFEST = ROOT / "ONTOLOGY/instances/hydrography.json"

FIELDS = ["HYBAS_ID", "NEXT_DOWN", "MAIN_BAS", "PFAF_ID", "SUB_AREA", "UP_AREA",
          "ENDO", "ORDER_", "UZB_KM2", "UZB_PCT"]


def write_json(path: Path, payload: object, *, compact: bool = False) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False,
                  separators=(",", ":") if compact else None,
                  indent=None if compact else 2)
        handle.write("\n")
    os.replace(temporary, path)


def number(value, digits: int = 3):
    return None if value is None else round(float(value), digits)


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    graph = json.loads(RELATIONSHIPS.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    features = []
    nodes = []
    for feature in source["features"]:
        p = feature["properties"]
        geometry = mapping(shape(feature["geometry"]).simplify(0.003, preserve_topology=True))
        features.append({"type": "Feature", "properties": {key: p.get(key) for key in FIELDS},
                         "geometry": geometry})
        nodes.append({
            "id": int(p["HYBAS_ID"]),
            "pfafId": int(p["PFAF_ID"]),
            "nextDown": int(p.get("NEXT_DOWN") or 0),
            "mainBasin": int(p.get("MAIN_BAS") or 0),
            "areaKm2": number(p.get("SUB_AREA")),
            "upstreamKm2": number(p.get("UP_AREA")),
            "uzbekistanKm2": number(p.get("UZB_KM2")),
            "uzbekistanPercent": number(p.get("UZB_PCT")),
            "endorheic": bool(int(p.get("ENDO") or 0)),
            "order": int(p.get("ORDER_") or 0),
            "sourceLayer": "BasinATLAS_v10_lev12",
        })

    known = {node["id"] for node in nodes}
    missing_river = sorted({row.get("basinId") for row in graph["rivers"]
                            if row.get("basinId") and row["basinId"] not in known})
    missing_lake = sorted({row.get("basinId") for row in graph["lakes"]
                           if row.get("basinId") and row["basinId"] not in known})
    warnings = []
    if missing_river:
        warnings.append({
            "code": "river-basin-legacy-ids",
            "message": "Some retained HydroRIVERS links use IDs absent from standard BasinATLAS.",
            "unresolvedDistinctIds": len(missing_river),
            "sample": missing_river[:10],
        })
    if missing_lake:
        warnings.append({
            "code": "lake-basin-legacy-ids",
            "message": "Some retained HydroLAKES links use lake-format HydroBASINS IDs.",
            "unresolvedDistinctIds": len(missing_lake),
            "sample": missing_lake[:10],
        })

    write_json(TARGET, {"type": "FeatureCollection", "name": "basins_level12",
                        "features": features}, compact=True)
    graph["generatedAt"] = generated
    graph["basins"] = nodes
    graph["counts"]["basins"] = len(nodes)
    graph["integrity"] = {
        "basinReference": "BasinATLAS v1.0 standard HydroBASINS level 12",
        "basinsPublished": len(nodes),
        "riverBasinUnresolvedDistinctIds": len(missing_river),
        "lakeBasinUnresolvedDistinctIds": len(missing_lake),
    }
    graph["warnings"] = warnings
    graph["sources"]["basins"] = SOURCE.relative_to(ROOT).as_posix()
    graph["selection"] = ("whole standard-format BasinATLAS level-12 catchments intersecting "
                          "Uzbekistan; river and lake geometry remains clipped to ADM0")
    write_json(RELATIONSHIPS, graph)

    manifest["generatedAt"] = generated
    manifest["source"] = "HydroSHEDS / BasinATLAS v1.0 / HydroRIVERS v1.0 / HydroLAKES v1.0"
    manifest["attribution"] = ("HydroSHEDS (Lehner, Grill et al.), BasinATLAS "
                               "(Linke, Lehner et al.) and HydroLAKES (Messager et al.)")
    manifest["selection"] = graph["selection"]
    manifest["counts"] = graph["counts"]
    manifest["integrity"] = graph["integrity"]
    manifest["warnings"] = warnings
    manifest["sources"]["basins"] = SOURCE.relative_to(ROOT).as_posix()
    manifest["basinReference"] = {
        "package": "GEODATA/uzbekistan_basinatlas_v10",
        "layer": "basinatlas_uz_lev12",
        "format": "standard HydroBASINS, the identifier family used by HydroRIVERS",
        "geometry": "whole catchments selected by intersection with Uzbekistan",
        "key": "HYBAS_ID",
    }
    manifest["fields"]["basins"] = FIELDS
    write_json(MANIFEST, manifest)

    print(f"{len(nodes):,} canonical basins published")
    print(f"  unresolved legacy IDs: rivers {len(missing_river)}, lakes {len(missing_lake)}")


if __name__ == "__main__":
    main()
