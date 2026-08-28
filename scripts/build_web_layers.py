"""Build the public atlas index and lightweight GeoJSON layers from ArcGIS packages."""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

import geopandas as gpd
import pyogrio

from inspect_packages import extract_package


ENGLISH_BY_ID = {
    16: "Climate types", 17: "Projected climate types for 2100", 18: "Local climate zones",
    19: "Average start of the growing season (2000–2024)", 20: "Average peak of the growing season (2000–2024)",
    21: "Average growing-season duration (2000–2024)", 22: "Average end of the growing season (2000–2024)",
    23: "Annual temperature trend, 1960–2023", 24: "Annual temperature trend, 1990–2023",
    25: "Warm-season temperature trend, 1960–2023", 26: "Warm-season temperature trend, 1990–2023",
    27: "Maximum temperature trend, 1960–2023", 28: "Precipitation trend, 1960–2023",
    29: "Precipitation trend, 1990–2023", 30: "Snow-cover depth trend, 1960–2024",
    31: "Snow-cover depth trend, 1990–2024", 32: "Climatic water deficit, 1990",
    33: "Climatic water deficit, 2023", 34: "Climatic water-deficit trend, 1960–2023",
    35: "Climatic water-deficit trend, 1990–2023", 36: "Projected temperature change by 2040",
    37: "Projected precipitation change by 2040", 42: "Share of settlement area",
    43: "Settlement area change, 1970–2020", 44: "Disappeared settlements by basin",
    45: "Road network density", 52: "Water management zones", 53: "Irrigated areas by catchment",
    54: "Areas using drainage", 55: "Historical irrigation districts", 56: "Annual runoff volume",
    57: "Dams, reservoirs and glacial lakes", 58: "Lake and reservoir volume", 59: "Groundwater depth",
    60: "Groundwater pollution", 61: "Groundwater resources", 62: "Artesian basins",
    63: "Irrigation canal density", 64: "Agricultural land served by canals", 73: "Water stress",
    74: "Water balance", 75: "Access to sustainable drinking water", 76: "Access to sustainable sanitation",
    77: "Water ecosystem area", 78: "Change in permanently flooded ecosystems, 2001–2004",
    79: "Change in seasonally flooded ecosystems, 2001–2004", 80: "Drainage network",
    81: "Flow in drainage canals", 90: "Land cover, 2000", 91: "Land cover, 2010",
    92: "Land cover", 94: "Bare surface", 95: "Soil chemistry", 96: "Farming systems",
    97: "Land-use types", 98: "Agricultural land types", 99: "Cotton yield", 100: "Livestock",
    101: "Forage lands", 113: "Arable-land dynamics", 114: "Terrestrial land cover",
    115: "Soil salinity", 116: "Irrigated-soil salinity", 117: "Soil-salinity dynamics",
    118: "Average maximum NDVI, 2004–2024", 119: "NDVI dynamics", 120: "Enhanced Vegetation Index dynamics",
    121: "Leaf Area Index", 122: "Land-productivity dynamics", 123: "Arable-land use intensity",
    124: "Pasture vegetation types", 125: "Recommended pasture stocking rate", 126: "Pasture productivity",
    127: "Soil organic carbon", 128: "Carbon-emission volume", 129: "Net carbon balance",
    135: "Forest cover, 2005", 137: "Forest types", 138: "Saxaul distribution",
    139: "Natural and planted forests", 147: "Forest carbon sequestration", 148: "Forest plantation potential",
    149: "Carbon sequestration potential from reforestation", 150: "Forest canopy closure", 151: "Forest age",
    152: "Forest Landscape Integrity Index", 153: "Forest-cover change, 1982–2016",
    158: "Physical-geographic regions", 159: "Landscapes", 160: "Landscape structure",
    161: "Plant formations", 162: "Vegetation", 163: "Zoogeographic regions", 164: "Bird species richness",
    165: "Habitat Diversity Index", 166: "Mammal species richness", 167: "Useful plants",
    168: "Game birds", 169: "Game mammals", 170: "Biodiversity Intactness Index", 171: "Fish",
    172: "Reptiles", 173: "Mammals", 174: "Plants", 175: "Invertebrates", 176: "Birds",
    185: "Protected-area types", 186: "Ecoregions", 187: "Protected areas and key biodiversity areas",
    188: "Nature conservation", 189: "Conservation Value Index", 190: "Ecosystem bioclimatic resilience",
    191: "Habitat dynamics index", 197: "Hypsometric map", 198: "Geomorphology",
    204: "Exposure to adverse geodynamic processes", 205: "Earthquakes, 1990–2024",
    206: "Mudflow zones", 207: "Flood risk", 208: "Flood extent", 209: "Glacier ice volume",
    213: "Economic losses from floods and earthquakes", 214: "Flood and earthquake fatalities",
}


def category_for(number: int | None, title: str) -> str:
    if number is None:
        return "Forests & carbon"
    if number <= 37:
        return "Climate"
    if number <= 45:
        return "Infrastructure"
    if number <= 81:
        return "Water"
    if number <= 129:
        return "Land & agriculture"
    if number <= 153:
        return "Forests & carbon"
    if number <= 191:
        return "Biodiversity"
    return "Hazards & terrain"


def english_title(number: int | None, original: str) -> str:
    if "Палмера" in original:
        year = re.search(r"20\d{2}", original)
        return f"Palmer Drought Severity Index ({year.group(0) if year else 'annual'})"
    if number in ENGLISH_BY_ID:
        return ENGLISH_BY_ID[number]
    return "Forest cover" if "Покрытие" in original else "Environmental atlas layer"


def build_catalog(source: Path, output: Path) -> list[dict]:
    records = []
    for package in sorted(source.glob("*.lpkx"), key=lambda item: item.name.casefold()):
        original = package.stem
        match = re.match(r"(\d+)[_-]?(.*)", original)
        number = int(match.group(1)) if match else None
        records.append({
            "id": f"atlas-{len(records) + 1:03d}",
            "atlasNumber": number,
            "title": english_title(number, original),
            "sourceTitle": original,
            "category": category_for(number, original),
            "format": "ArcGIS Layer Package",
            "extension": "LPKX",
            "size": package.stat().st_size,
        })
    output.write_text(json.dumps(records, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return records


LAYER_SPECS = [
    {"prefix": "185_", "slug": "protected-areas", "title": "Protected areas", "fields": {"meth_nomi": "name", "meth_turi": "type", "j_joyi": "location", "u_m_ga": "area_ha"}, "simplify": 700},
    {"prefix": "205_", "slug": "earthquakes", "title": "Earthquakes 1990–2024", "fields": {"time": "date", "mag": "magnitude", "depth": "depth_km", "place": "place"}, "point": True},
    {"prefix": "52_", "slug": "water-management", "title": "Water management zones", "fields": {"Type": "type"}, "simplify": 650},
    {"prefix": "57_", "slug": "glacial-lakes", "title": "Glacial lakes", "fields": {"x": "longitude", "y": "latitude"}, "point": True},
    {"prefix": "207_", "slug": "flood-risk", "title": "Flood risk", "fields": {"name_1": "region", "rfr_label": "risk", "rfr_score": "risk_score", "area_km2": "area_km2"}, "simplify": 900},
]


def find_vector(folder: Path) -> tuple[Path, str | None]:
    for geodatabase in folder.rglob("*.gdb"):
        try:
            layers = pyogrio.list_layers(geodatabase)
            if len(layers):
                return geodatabase, str(layers[0][0])
        except Exception:
            continue
    shapefile = next(folder.rglob("*.shp"), None)
    if shapefile:
        return shapefile, None
    raise RuntimeError(f"No readable vector layer in {folder}")


def build_layer(spec: dict, source: Path, working: Path, output: Path) -> dict:
    package = next(source.glob(f"{spec['prefix']}*.lpkx"))
    extracted = working / package.stem
    if not extracted.exists():
        extract_package(package, extracted)
    vector, layer = find_vector(extracted)
    data = gpd.read_file(vector, layer=layer)
    if data.crs is None:
        data = data.set_crs(4326)
    data = data.to_crs(4326)
    if spec["slug"] == "earthquakes":
        data = data.cx[54.8:74.3, 36.5:46.5]
        data = data[data["mag"].fillna(0) >= 3.0]
    keep = [field for field in spec["fields"] if field in data.columns] + ["geometry"]
    data = data[keep].rename(columns=spec["fields"])
    for column in data.columns:
        if column != "geometry" and str(data[column].dtype).startswith("datetime"):
            data[column] = data[column].astype(str)
    if spec.get("simplify"):
        projected = data.to_crs(3857)
        projected.geometry = projected.geometry.simplify(spec["simplify"], preserve_topology=True)
        data = projected.to_crs(4326)
    data = data[~data.geometry.is_empty & data.geometry.notna()]
    target = output / f"{spec['slug']}.geojson"
    target.write_text(data.to_json(drop_id=True, to_wgs84=True), encoding="utf-8")
    return {"id": spec["slug"], "title": spec["title"], "url": f"/data/{target.name}", "features": len(data), "geometry": "point" if spec.get("point") else "polygon"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("public/data"))
    parser.add_argument("--working", type=Path, default=Path("tmp/map-extract"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.working.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog(args.source, args.output / "archive-catalog.json")
    layers = [build_layer(spec, args.source, args.working, args.output) for spec in LAYER_SPECS]
    (args.output / "map-layers.json").write_text(json.dumps(layers, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"packages": len(catalog), "layers": layers}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
