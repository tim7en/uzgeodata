"""Overlay the administrative boundaries onto the level-12 basin reference.

The graph could already say what drains into what, but only in hydrological
terms: a reach flows into a reach, a reach drains a basin. Nothing connected
either to the administrative geography, so the question a water manager actually
asks — *which districts drain into this point* — had no path through the data.

This measures that path. Every province and district is intersected with the
level-12 basins, and each overlap is recorded as one row carrying the area the
two share. Once a basin knows which administrative units cover it and by how
much, tracing upstream from a reach and summing the overlaps gives the
contributing provinces and districts, weighted by the area they really
contribute rather than by whether they happen to touch.

Two things the arithmetic is careful about:

Areas are measured on EPSG:6933, the equal-area projection the BasinATLAS
extraction already reports in, so an overlap here is comparable with the UZB_KM2
it records there. Measuring on WGS 84 degrees would inflate the north.

Administrative units are matched to the ontology's place concepts by P-code, not
by name. The COD spellings differ from the vocabulary's (Andizhan against
Andijan, Dzhizak against Jizzakh), so a name join would silently drop provinces
while appearing to work.

Districts have no place concept, and deliberately get none: 199 of them would
triple a controlled vocabulary that exists to be read by a person. They live in
the relationship table instead, which is where the schema says individual
features belong.

Usage:
    python PIPELINES/build_admin_basin_links.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ontology_paths import dataset_dir

try:
    import pyproj
    import shapefile
    from shapely.geometry import shape as to_shape
    from shapely.ops import transform as shapely_transform
    from shapely.strtree import STRtree
except ImportError as error:  # pragma: no cover - depends on the workstation
    raise SystemExit(
        "pyshp, shapely and pyproj are required: pip install pyshp shapely pyproj. "
        "They replace geopandas here — a shapefile and an equal-area projection are "
        "all this needs, and the heavier stack is not installed on every workstation."
    ) from error

ROOT = Path(__file__).resolve().parent.parent
# BasinATLAS is the canonical basin identity frame used by the atmospheric and
# land pipelines.  The hydrography browser also publishes a basin layer, but an
# older build used the lake-format HydroBASINS identifiers; using that derivative
# here left roughly 22 percent of Uzbekistan outside the administrative overlay.
BASINS = (ROOT / "PUBLISHED" / "data" / "review" / "basinatlas" /
          "basinatlas_uz_lev12.geojson")
ADMIN_DIR = ROOT / "GEODATA"
WEB_DIR = ROOT / "PUBLISHED" / "data" / "admin"
LINKS_OUT = ROOT / "PUBLISHED" / "data" / "hydrography" / "admin-basin-links.json"
CSV_OUT = dataset_dir("ADMIN_BASIN_LINKS", "REFERENCE") / "admin-basin-links.csv"
MANIFEST_OUT = ROOT / "ONTOLOGY" / "instances" / "admin-basin-links.json"

VECTOR_CRS = "EPSG:4326"
AREA_CRS = "EPSG:6933"
DELIVERY = "uzb_admbnda_{level}_2018b"

# The COD boundary names and the vocabulary's differ, so identity runs through
# the P-code. Every one of the 14 first-level units already has a concept; the
# build fails rather than proceeds if that stops being true.
PLACE_BY_PCODE = {
    "UZ03": "uz:place/andijan",
    "UZ06": "uz:place/bukhara",
    "UZ08": "uz:place/jizzakh",
    "UZ10": "uz:place/kashkadarya",
    "UZ12": "uz:place/navoi",
    "UZ14": "uz:place/namangan",
    "UZ18": "uz:place/samarkand",
    "UZ22": "uz:place/surkhandarya",
    "UZ24": "uz:place/syrdarya",
    "UZ26": "uz:place/tashkent-city",
    "UZ27": "uz:place/tashkent-region",
    "UZ30": "uz:place/fergana",
    "UZ33": "uz:place/khorezm",
    "UZ35": "uz:place/karakalpakstan",
}

# Below this the overlap is a shared border rather than a real intersection: a
# basin edge and a district edge tracing the same river will clip by a few square
# metres, and keeping those would put dozens of meaningless rows on every trace.
MIN_OVERLAP_KM2 = 0.01

_project = pyproj.Transformer.from_crs(VECTOR_CRS, AREA_CRS, always_xy=True).transform


def equal_area(geometry):
    """Reproject to the equal-area CRS, repairing self-intersections on the way.

    Both the COD boundaries and the basin polygons contain rings that are invalid
    under strict OGC rules. `buffer(0)` resolves them; without it an intersection
    against such a polygon raises rather than returning an area.
    """
    projected = shapely_transform(_project, geometry)
    return projected if projected.is_valid else projected.buffer(0)


def load_basins() -> tuple[list[int], list]:
    collection = json.loads(BASINS.read_text(encoding="utf8"))
    ids, geometries = [], []
    for feature in collection["features"]:
        ids.append(feature["properties"]["HYBAS_ID"])
        geometries.append(equal_area(to_shape(feature["geometry"])))
    return ids, geometries


def read_admin(level: int) -> list[dict]:
    name = DELIVERY.format(level=f"adm{level}")
    path = ADMIN_DIR / name / name
    if not path.with_suffix(".shp").exists():
        raise SystemExit(f"Admin level {level} delivery not found at {path.with_suffix('.shp')}")
    reader = shapefile.Reader(str(path))
    units = []
    for record, shaperec in zip(reader.records(), reader.shapes()):
        row = record.as_dict()
        geometry = to_shape(shaperec.__geo_interface__)
        units.append({
            "pcode": row[f"ADM{level}_PCODE"],
            "nameEn": row[f"ADM{level}_EN"],
            "nameRu": row.get(f"ADM{level}_RU"),
            "nameUz": row.get(f"ADM{level}_UZ"),
            "type": row.get("ADM1TYPE_E") if level == 1 else row.get("ADM2TYPEEN"),
            "parent": row.get("ADM1_PCODE") if level == 2 else None,
            "geometry": geometry,
            "wgs84": shaperec.__geo_interface__,
        })
    return units


def overlay(units: list[dict], basin_ids: list[int], basin_geometries: list, index: STRtree) -> tuple[list, dict]:
    """One row per (admin unit, basin) pair that genuinely overlaps."""
    links = []
    per_unit = {}
    for unit in units:
        area_geometry = equal_area(unit["geometry"])
        unit_km2 = area_geometry.area / 1_000_000
        overlaps = 0
        shared_total = 0.0
        for position in index.query(area_geometry):
            basin = basin_geometries[position]
            if not area_geometry.intersects(basin):
                continue
            piece = area_geometry.intersection(basin)
            if piece.is_empty:
                continue
            km2 = piece.area / 1_000_000
            if km2 < MIN_OVERLAP_KM2:
                continue
            links.append({"basin": basin_ids[position], "pcode": unit["pcode"], "km2": round(km2, 4)})
            overlaps += 1
            shared_total += km2
        per_unit[unit["pcode"]] = {"areaKm2": round(unit_km2, 3), "basins": overlaps,
                                   "sharedKm2": round(shared_total, 3)}
    return links, per_unit


def feature_collection(units: list[dict], level: int) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {
                "pcode": unit["pcode"], "level": level, "nameEn": unit["nameEn"],
                "nameRu": unit["nameRu"], "nameUz": unit["nameUz"],
                "type": unit["type"], "parent": unit["parent"],
                "place": PLACE_BY_PCODE.get(unit["pcode"]),
            },
            "geometry": unit["wgs84"],
        } for unit in units],
    }


def main() -> None:
    basin_ids, basin_geometries = load_basins()
    index = STRtree(basin_geometries)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    provinces = read_admin(1)
    districts = read_admin(2)

    missing = [unit["pcode"] for unit in provinces if unit["pcode"] not in PLACE_BY_PCODE]
    if missing:
        raise SystemExit(
            f"These first-level units have no place concept: {', '.join(missing)}. "
            "Add them to ONTOLOGY/vocab/places.json and to PLACE_BY_PCODE."
        )

    province_links, province_stats = overlay(provinces, basin_ids, basin_geometries, index)
    district_links, district_stats = overlay(districts, basin_ids, basin_geometries, index)

    # Pivot onto the basin, which is the direction a trace reads: it holds a set
    # of basins and needs the administrative units under them.
    by_basin: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: {"adm1": {}, "adm2": {}})
    for level, rows in (("adm1", province_links), ("adm2", district_links)):
        for row in rows:
            by_basin[str(row["basin"])][level][row["pcode"]] = row["km2"]

    def unit_rows(units, level, stats):
        return [{
            "pcode": unit["pcode"], "level": level, "nameEn": unit["nameEn"],
            "nameRu": unit["nameRu"], "nameUz": unit["nameUz"], "type": unit["type"],
            "parent": unit["parent"], "place": PLACE_BY_PCODE.get(unit["pcode"]),
            **stats[unit["pcode"]],
        } for unit in units]

    WEB_DIR.mkdir(parents=True, exist_ok=True)
    for level, units in ((1, provinces), (2, districts)):
        target = WEB_DIR / f"adm{level}.geojson"
        target.write_text(json.dumps(feature_collection(units, level), ensure_ascii=False,
                                     separators=(",", ":")), encoding="utf8")

    LINKS_OUT.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": generated_at,
        "source": "OCHA/HDX Common Operational Dataset, uzb_admbnda 2018b",
        "basinReference": (
            "PUBLISHED/data/review/basinatlas/basinatlas_uz_lev12.geojson "
            "(BasinATLAS v10, level 12)"
        ),
        "vectorCrs": VECTOR_CRS,
        "areaCrs": AREA_CRS,
        "minOverlapKm2": MIN_OVERLAP_KM2,
        "note": (
            "km2 is the area a basin and an administrative unit share, measured on the "
            "equal-area CRS. Summing it over a traced set of basins gives each unit's "
            "contribution to that catchment. Basin areas here cover the whole sub-basin as "
            "HydroSHEDS delineated it, so a basin straddling the border contributes only "
            "the part these boundaries cover."
        ),
        "counts": {
            "provinces": len(provinces), "districts": len(districts),
            "provinceLinks": len(province_links), "districtLinks": len(district_links),
            "basinsWithProvince": len({r["basin"] for r in province_links}),
            "basinsWithDistrict": len({r["basin"] for r in district_links}),
            "basins": len(basin_ids),
        },
        "provinces": unit_rows(provinces, 1, province_stats),
        "districts": unit_rows(districts, 2, district_stats),
        "byBasin": by_basin,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf8")

    # The relationship table the ontology registers reads this: one row per link,
    # both levels in one file, which is why admin_level is the scope column. It
    # lives beside the JSON rather than in WORKSPACE/ so the container the graph
    # names is actually present in a checkout.
    with CSV_OUT.open("w", encoding="utf8", newline="") as handle:
        handle.write("basin_id,pcode,admin_level,shared_km2\n")
        for level, rows in ((1, province_links), (2, district_links)):
            for row in rows:
                handle.write(f"{row['basin']},{row['pcode']},{level},{row['km2']}\n")

    unmatched = len(basin_ids) - len({r["basin"] for r in province_links})
    MANIFEST_OUT.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": generated_at,
        "predicate": "uz:intersectsAdminArea",
        "subjectType": "Basin",
        "objectType": "AdminArea",
        "basinLevel": 12,
        "basinReference": "uzbekistan_basinatlas_v10 :: basinatlas_uz_lev12",
        "source": "OCHA/HDX Common Operational Dataset, uzb_admbnda 2018b",
        "vectorCrs": VECTOR_CRS,
        "areaCrs": AREA_CRS,
        "measures": {"km2": "area shared by the basin and the administrative unit"},
        "counts": {
            "provinces": len(provinces), "districts": len(districts),
            "provinceLinks": len(province_links), "districtLinks": len(district_links),
            "basins": len(basin_ids), "basinsWithoutProvince": unmatched,
        },
        "placeConcepts": PLACE_BY_PCODE,
        "output": str(CSV_OUT.relative_to(ROOT)),
        "note": (
            "First-level units carry the ontology place concept they correspond to, matched "
            "by P-code because the COD spellings differ from the vocabulary's. Second-level "
            "units get no concept: 199 districts would swamp a vocabulary meant to be read, "
            "and the entity schema already says individual features belong in a relationship "
            "table rather than in the graph. Basins with no province are those lying wholly "
            "outside the boundary — the basin reference keeps whole sub-basins, so a catchment "
            "clipped at the border can sit entirely beyond it."
        ),
    }, ensure_ascii=False, indent=2), encoding="utf8")

    print(f"{len(provinces)} provinces, {len(districts)} districts x {len(basin_ids):,} basins")
    print(f"  {len(province_links):,} province links, {len(district_links):,} district links "
          f"-> {LINKS_OUT.relative_to(ROOT)} ({LINKS_OUT.stat().st_size / 1024:,.0f} KB)")
    print(f"  {unmatched:,} basins fall outside every province")
    print(f"  {CSV_OUT.relative_to(ROOT)} ({CSV_OUT.stat().st_size / 1024:,.0f} KB)")
    for level in (1, 2):
        target = WEB_DIR / f"adm{level}.geojson"
        print(f"  adm{level}.geojson {target.stat().st_size / 1024:,.0f} KB")


if __name__ == "__main__":
    main()
