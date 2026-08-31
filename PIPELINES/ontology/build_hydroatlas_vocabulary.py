"""Turn the 281 BasinATLAS attribute codes into a documented vocabulary.

BasinATLAS ships each basin with 281 columns named like `dis_m3_pyr` and
`tmp_dc_s07`. Without the catalogue those are unusable: nobody can tell that one
is long-term natural discharge from WaterGAP and the other is the July mean air
temperature from WorldClim, nor that the second is stored multiplied by ten.

This reads the official BasinATLAS_Catalog_v10.pdf - one page per attribute -
and turns it into a concept scheme. Every attribute keeps its source dataset,
citation, licence, units and native resolution, so a value in the portal can be
traced back to the study it came from.

The column name is then decoded against the catalogue's own suffix syntax:

    tmp_dc_s07
    ^^^ variable (air temperature)
        ^^ unit (degrees Celsius, x10)
           ^ spatial extent: s = this sub-basin, u = whole upstream catchment,
             p = at the pour point
            ^^ dimension: 07 = July, yr = annual, se = spatial extent,
               mj = majority class, mn/mx = min/max, av = average, su = sum

Usage:
    python PIPELINES/ontology/build_hydroatlas_vocabulary.py
    python PIPELINES/ontology/build_hydroatlas_vocabulary.py --no-profile
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

CATALOG = "GEODATA/BasinATLAS_Data_v10.gdb/BasinATLAS_Catalog_v10.pdf"
PACKAGE_GPKG = "GEODATA/uzbekistan_basinatlas_v10/uzbekistan_basinatlas_v10.gpkg"

CORE_FIELDS = {
    "HYBAS_ID", "NEXT_DOWN", "NEXT_SINK", "MAIN_BAS", "DIST_SINK", "DIST_MAIN", "SUB_AREA",
    "UP_AREA", "PFAF_ID", "ENDO", "COAST", "ORDER_", "SORT", "Shape_Length", "Shape_Area",
    "SRC_LAYER", "UZB_KM2", "UZB_PCT", "geometry",
}

# The catalogue states these in prose; they are the same for every attribute.
SPATIAL_EXTENT = {
    "s": "this sub-basin",
    "u": "the whole upstream catchment",
    "p": "at the sub-basin pour point",
}
DIMENSION = {
    "yr": "annual average", "mn": "annual minimum", "mx": "annual maximum",
    "se": "spatial extent (percent)", "mj": "majority class", "av": "average",
    "su": "sum", "ix": "index value", "cl": "class",
}
MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]

# What a numeric suffix counts, per variable. HydroATLAS reuses the two digits for
# three different things, and the columns themselves say which is which: the
# monthly variables stop at 12, while glc runs to 22, pnv to 15 and wet carries
# g1/g2 beside its digits — none of which is a month. Human Footprint uses the
# year, 93 and 09 being the 1993 and 2009 snapshots.
#
# Reading every numeric suffix as a month, as this once did, published
# "Land Cover Extent - September average" for GLC class 9 and "Human Footprint -
# September average" for the 2009 index. Class names would need the catalog PDF,
# so the class number is given plainly rather than guessed at.
NUMERIC_DIMENSION = {
    "glc": "class", "pnv": "class", "wet": "class", "hft": "year",
}
NUMERIC_DEFAULT = "month"

# Attributes the ontology already has a property concept for. Anything not listed
# stays a HydroATLAS attribute only - inventing a property per column would bloat
# the vocabulary without telling anyone anything new.
PROPERTY_LINKS = {
    "dis": "uz:prop/surface-runoff", "run": "uz:prop/surface-runoff",
    "lka": "uz:prop/surface-water-extent", "lkv": "uz:prop/reservoir-volume",
    "rev": "uz:prop/reservoir-volume", "inu": "uz:prop/surface-water-extent",
    "gwt": "uz:prop/groundwater-depth", "riv": "uz:prop/river-network",
    "ria": "uz:prop/river-network", "ele": "uz:prop/elevation",
    "tmp": "uz:prop/air-temperature", "pre": "uz:prop/precipitation",
    "snw": "uz:prop/snow-cover-depth", "pet": "uz:prop/evapotranspiration",
    "aet": "uz:prop/evapotranspiration", "cmi": "uz:prop/climatic-water-deficit",
    "ari": "uz:prop/climatic-water-deficit", "glc": "uz:prop/land-cover",
    "pnv": "uz:prop/vegetation-formation", "for": "uz:prop/forest-cover",
    "crp": "uz:prop/cropland-extent", "pst": "uz:prop/pasture-vegetation",
    "ire": "uz:prop/irrigated-area", "gla": "uz:prop/glacier-volume",
    "pac": "uz:prop/protected-area", "wet": "uz:prop/water-ecosystem-extent",
    "soc": "uz:prop/soil-organic-carbon", "swc": "uz:prop/soil-chemistry",
    "cly": "uz:prop/soil-chemistry", "slt": "uz:prop/soil-chemistry",
    "snd": "uz:prop/soil-chemistry", "ero": "uz:prop/land-productivity",
    "urb": "uz:prop/settlement-extent", "ppd": "uz:prop/settlement-extent",
    "pop": "uz:prop/settlement-extent", "rdd": "uz:prop/road-density",
    "tec": "uz:prop/ecoregion", "fec": "uz:prop/ecoregion",
    "tbi": "uz:prop/landscape-type", "clz": "uz:prop/climate-classification",
    "cls": "uz:prop/climate-classification",
}


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    for attempt in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.15 * (attempt + 1))


def parse_catalog(path: Path) -> list[dict]:
    """One page per attribute; the layout puts labels first, then their values."""
    from pypdf import PdfReader

    records = []
    for page in PdfReader(path).pages:
        text = page.extract_text() or ""
        category_id = re.search(r"Category ID-(\w+)", text)
        column = re.search(r"Column name\s+([a-z]{3})_([a-z0-9]{2})_", text)
        if not category_id or not column:
            continue

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        heading = next((i for i, line in enumerate(lines)
                        if line.endswith(">>> Back to Attribute List")), None)
        if heading is None:
            continue

        after = lines[heading + 1:]
        units = re.search(r"Units:\s*(.+?)$", text, re.MULTILINE)
        native = re.search(r"Native format:\s*(.+?)\s+Units:", text)
        website = re.search(r"(https?://\S+)", text)
        licence = re.search(r"(Creative Commons[^\n]*|CC[- ]BY[^\n]*|Public [Dd]omain[^\n]*)", text)

        def field(pattern):
            found = re.search(pattern + r":\s*(.+?)$", text, re.MULTILINE)
            return found.group(1).strip() if found else None

        records.append({
            "catalogId": category_id.group(1),
            "category": lines[heading].replace(">>> Back to Attribute List", "").strip(),
            "label": after[0] if after else None,
            "sourceData": after[1] if len(after) > 1 else None,
            "citation": after[2] if len(after) > 2 else None,
            "variable": column.group(1),
            "unitCode": column.group(2),
            "units": units.group(1).strip() if units else None,
            "nativeFormat": native.group(1).strip() if native else None,
            "spatialExtentSyntax": field(r"Spatial extent \{x\}"),
            "dimensionSyntax": field(r"Dimension \{oo\}"),
            "existingSuffixes": field(r"Existing suffixes \{xoo\}"),
            "website": website.group(1).rstrip(".") if website else None,
            "license": licence.group(1).strip() if licence else None,
        })
    return records


def concept_id(entry: dict, variable_counts: dict) -> str:
    """Some variables carry two attributes - a class code and a percent extent.

    They share a three-letter variable but are different measurements, so the unit
    code disambiguates them rather than one silently overwriting the other.
    """
    variable = entry["variable"]
    if variable_counts[variable] > 1:
        return f"uz:hydroatlas/{variable}-{entry['unitCode']}"
    return f"uz:hydroatlas/{variable}"


def decode(column: str, catalog: dict) -> dict | None:
    """Split a column name into variable, unit and the suffix's meaning."""
    parts = column.split("_")
    if len(parts) != 3:
        return None
    variable, unit, suffix = parts
    entry = catalog.get((variable, unit)) or catalog.get((variable, None))
    if entry is None or len(suffix) != 3:
        return None

    extent, dimension = suffix[0], suffix[1:]
    kind = NUMERIC_DIMENSION.get(variable, NUMERIC_DEFAULT)
    if dimension.isdigit() and kind == "year":
        # Two-digit years, and the atlas predates 2020: 93 is 1993, 09 is 2009.
        index = int(dimension)
        dimension_label = f"{1900 + index if index >= 90 else 2000 + index}"
    elif dimension.isdigit() and kind == "class":
        dimension_label = f"class {int(dimension)}"
    elif dimension.isdigit():
        index = int(dimension)
        if not 1 <= index <= 12:
            raise ValueError(
                f"{column}: {variable} is read as monthly, but {dimension} is not a month. "
                "Give the variable an entry in NUMERIC_DIMENSION."
            )
        dimension_label = f"{MONTHS[index - 1]} average"
    else:
        dimension_label = DIMENSION.get(dimension, dimension)

    return {
        "column": column,
        "variable": variable,
        "unitCode": unit,
        "spatialExtent": extent,
        "spatialExtentLabel": SPATIAL_EXTENT.get(extent, extent),
        "dimension": dimension,
        "dimensionLabel": dimension_label,
        "label": f"{entry['label']} - {dimension_label}, {SPATIAL_EXTENT.get(extent, extent)}",
        "units": entry["units"],
        "concept": entry["conceptId"],
        "catalogId": entry["catalogId"],
        "category": entry["category"],
        "property": PROPERTY_LINKS.get(variable),
    }


def data_columns(root: Path) -> list[str]:
    import pyogrio

    info = pyogrio.read_info(root / PACKAGE_GPKG, layer="basinatlas_uz_lev12")
    return [str(f) for f in info["fields"] if str(f) not in CORE_FIELDS]


def country_profile(root: Path, decoded: dict) -> dict:
    """What each attribute actually reads across Uzbekistan.

    Values are weighted by the area of each level-12 basin that falls inside the
    country, so a basin half outside the border counts for the half inside. Class
    and majority attributes are summarised by their commonest value instead of
    averaged: the mean of two land-cover class codes is meaningless.
    """
    import numpy as np
    import pyogrio

    frame = pyogrio.read_dataframe(root / PACKAGE_GPKG, layer="basinatlas_uz_lev12",
                                   read_geometry=False)
    weights = frame["UZB_KM2"].astype(float).to_numpy()
    total = float(weights.sum())

    profile = {}
    for column, meaning in decoded.items():
        if column not in frame.columns:
            continue
        values = frame[column].astype(float).to_numpy()
        valid = np.isfinite(values)
        if not valid.any():
            continue
        categorical = meaning["dimension"] in {"mj", "cl"} or meaning["unitCode"] in {"cl", "id"}
        entry = {
            "column": column,
            "label": meaning["label"],
            "units": meaning["units"],
            "category": meaning["category"],
            "catalogId": meaning["catalogId"],
            "basinsWithData": int(valid.sum()),
        }
        if categorical:
            classes, counts = np.unique(values[valid].astype(int), return_counts=True)
            order = np.argsort(-counts)[:5]
            entry["mode"] = int(classes[order[0]])
            entry["classShare"] = {int(classes[i]): round(float(counts[i] / valid.sum()), 4)
                                   for i in order}
        else:
            weighted = float((values[valid] * weights[valid]).sum() / max(weights[valid].sum(), 1e-9))
            entry["areaWeightedMean"] = round(weighted, 4)
            entry["min"] = round(float(values[valid].min()), 4)
            entry["max"] = round(float(values[valid].max()), 4)
        profile[column] = entry

    return {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": "uz:ds/basinatlas-uz-v10",
        "basis": "BasinATLAS level 12, weighted by the area of each basin inside Uzbekistan",
        "caveat": "Attribute values describe the whole sub-basin, including any part "
                  "outside the border, so these are close approximations of national "
                  "figures rather than exact ones. Level 12 basins average about 110 km2, "
                  "which keeps the error small; the same calculation at level 3 would not.",
        "basins": int(len(frame)),
        "weightedAreaKm2": round(total, 3),
        "attributes": profile,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--no-profile", action="store_true",
                        help="build the vocabulary without computing national values")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    root = Path(args.root).resolve()
    catalog_path = root / CATALOG
    if not catalog_path.exists():
        print(f"catalogue not found: {catalog_path}", file=sys.stderr)
        return 1

    print(f"parsing {catalog_path.name} ...")
    entries = parse_catalog(catalog_path)
    variable_counts: dict[str, int] = {}
    for entry in entries:
        variable_counts[entry["variable"]] = variable_counts.get(entry["variable"], 0) + 1
    for entry in entries:
        entry["conceptId"] = concept_id(entry, variable_counts)
    catalog = {(entry["variable"], entry["unitCode"]): entry for entry in entries}
    for entry in entries:  # fallback for columns whose unit code is not the catalogued one
        catalog.setdefault((entry["variable"], None), entry)
    print(f"  {len(entries)} attribute pages, {len(variable_counts)} distinct variables")

    columns = data_columns(root)
    decoded, undecoded = {}, []
    for column in columns:
        meaning = decode(column, catalog)
        if meaning:
            decoded[column] = meaning
        else:
            undecoded.append(column)
    print(f"  decoded {len(decoded)} of {len(columns)} data columns")
    if undecoded:
        print(f"  NOT decoded: {undecoded}")

    scheme = {
        "scheme": "hydroatlas",
        "title": "HydroATLAS attributes",
        "description": "The BasinATLAS v1.0 attribute set, parsed from the official "
                       "BasinATLAS_Catalog_v10.pdf. Each variable keeps its source dataset, "
                       "citation, licence, units and native resolution so any value shown in "
                       "the portal can be traced to the study it came from. Column names are "
                       "decoded against the catalogue's own suffix syntax.",
        "version": "1.0",
        "reference": "Linke, S., Lehner, B., Ouellet Dallaire, C. et al. (2019). Global "
                     "hydro-environmental sub-basin and river reach characteristics at high "
                     "spatial resolution. Scientific Data 6, 283. doi:10.1038/s41597-019-0300-6",
        "concepts": [
            {
                "id": entry["conceptId"],
                "prefLabel": entry["label"],
                "altLabels": [entry["variable"], f"{entry['variable']}_{entry['unitCode']}"],
                "definition": (f"{entry['label']}. Source: {entry['sourceData']}. "
                               f"Units: {entry['units']}. Native format: {entry['nativeFormat']}."),
                "unit": entry["units"],
                "note": (f"Catalogue {entry['catalogId']} ({entry['category']}). "
                         f"Citation: {entry['citation']}. Licence: {entry['license'] or 'see source'}. "
                         f"Suffixes in this release: {entry['existingSuffixes']}."),
                "related": [PROPERTY_LINKS[entry["variable"]]]
                if entry["variable"] in PROPERTY_LINKS else [],
            }
            for entry in sorted(entries, key=lambda item: item["catalogId"])
            if entry["label"]
        ],
    }
    write_json(root / "ONTOLOGY" / "vocab" / "hydroatlas-attributes.json", scheme)

    # The column decoding is measured detail about one release, not vocabulary,
    # so it lives with the instances and keeps the concept scheme schema-clean.
    write_json(root / "ONTOLOGY" / "instances" / "hydroatlas-columns.json", {
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "catalogSource": CATALOG,
        "reference": scheme["reference"],
        "suffixSyntax": {"spatialExtent": SPATIAL_EXTENT, "dimension": DIMENSION,
                         "numeric": "A numeric suffix is a calendar month for the monthly climate variables, "
                                    "a legend class for glc, pnv and wet, and a year for hft"},
        "columns": decoded,
        "undecodedColumns": undecoded,
    })
    print(f"  wrote ONTOLOGY/vocab/hydroatlas-attributes.json "
          f"({len(scheme['concepts'])} concepts, {len(decoded)} decoded columns)")

    linked = {meaning["property"] for meaning in decoded.values() if meaning["property"]}
    print(f"  {len(linked)} existing portal properties are measured by BasinATLAS")

    if not args.no_profile:
        print("computing the national profile ...")
        profile = country_profile(root, decoded)
        write_json(root / "ONTOLOGY" / "instances" / "hydroatlas-uz-profile.json", profile)
        print(f"  {len(profile['attributes'])} attributes summarised over "
              f"{profile['basins']:,} basins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
