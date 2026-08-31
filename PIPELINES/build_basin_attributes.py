"""Publish the BasinATLAS level-12 attributes for the basins the portal can draw.

The hydrography reference gives the browser basin geometry and the ``nextDown``
topology, but none of the 281 documented BasinATLAS attributes. They sit in the
delivery GeoPackage, which is a SQLite database: reading the attribute table
needs no GDAL, only the standard library, so this runs wherever Python does.

Two files come out, both under the hydrography namespace the explorer already
fetches from:

``basin-attributes.json``
    Column-oriented values keyed by HYBAS_ID. Storing each column as one array
    rather than each basin as one object keeps like values adjacent, which is
    what makes the payload compress: 2,604 basins by 299 columns is 4 MB of
    JSON and about 1 MB over the wire.

``attribute-dictionary.json``
    The decoded vocabulary for those columns, carrying the aggregation rule
    each one takes when a caller rolls it up over a traced set of basins.

Only basins present in the published reference are written. The atlas extends
past them, but a basin the explorer cannot select or draw is a basin nothing
can ask about, and carrying it would inflate the payload for nothing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEOPACKAGE = ROOT / "GEODATA" / "uzbekistan_basinatlas_v10" / "uzbekistan_basinatlas_v10.gpkg"
LAYER = "basinatlas_uz_lev12"
VOCABULARY = ROOT / "ONTOLOGY" / "instances" / "hydroatlas-columns.json"
REFERENCE = ROOT / "PUBLISHED" / "data" / "hydrography" / "relationships.json"
OUT_VALUES = ROOT / "PUBLISHED" / "data" / "hydrography" / "basin-attributes.json"
OUT_DICTIONARY = ROOT / "PUBLISHED" / "data" / "hydrography" / "attribute-dictionary.json"

# Columns that are not BasinATLAS measurements. The first group is the topology
# the reference already publishes per basin; the second is bookkeeping the
# Uzbekistan extraction added — Esri geometry fields, the source layer name, and
# the clipped area that the reference carries as uzbekistanKm2/uzbekistanPercent.
# Either way, repeating them would put two copies of the same number in front of
# the browser, so they are read for the join and then dropped.
NOT_ATTRIBUTES = {
    "HYBAS_ID", "NEXT_DOWN", "NEXT_SINK", "MAIN_BAS", "DIST_SINK", "DIST_MAIN",
    "SUB_AREA", "UP_AREA", "PFAF_ID", "ENDO", "COAST", "ORDER_", "SORT",
    "Shape_Length", "Shape_Area", "SRC_LAYER", "UZB_KM2", "UZB_PCT",
}


def aggregation_rule(entry: dict) -> str:
    """How a column combines across several basins.

    The suffix syntax carries this, so it is read rather than curated. A column
    measured over ``the whole upstream catchment`` already integrates everything
    upstream of the basin it sits on — averaging those across a traced set would
    count the headwaters once per basin they flow through. The outlet's own value
    is the answer, so those columns, and the pour-point ones beside them, are
    marked ``outlet``. A majority class cannot be averaged either: mixing class
    codes yields a code that means nothing, so it takes the class holding the
    most area. Everything else describes its own sub-basin and is averaged with
    each basin weighted by its area.
    """
    if entry.get("spatialExtent") in {"u", "p"}:
        return "outlet"
    if entry.get("dimension") == "mj":
        return "majority"
    return "areaWeightedMean"


def main() -> None:
    if not GEOPACKAGE.exists():
        raise SystemExit(f"BasinATLAS GeoPackage not found at {GEOPACKAGE}")

    vocabulary = json.loads(VOCABULARY.read_text(encoding="utf8"))["columns"]
    reference = json.loads(REFERENCE.read_text(encoding="utf8"))

    # Area inside Uzbekistan is the weight, not the full sub-basin area: a basin
    # straddling the border contributes to a national figure only by the part
    # that is in the country.
    weights = {basin["id"]: basin.get("uzbekistanKm2") or 0.0 for basin in reference["basins"]}

    connection = sqlite3.connect(f"file:{GEOPACKAGE}?mode=ro", uri=True)
    try:
        table = [row[1] for row in connection.execute(f"PRAGMA table_info({LAYER})")]
        if not table:
            raise SystemExit(f"Layer {LAYER} not found in {GEOPACKAGE.name}")
        columns = [name for name in table if name not in {"fid", "geom"} and name not in NOT_ATTRIBUTES]

        undecoded = [name for name in columns if name not in vocabulary]
        if undecoded:
            raise SystemExit(
                "These attribute columns are absent from the vocabulary, so they would reach "
                f"the browser as bare codes: {', '.join(undecoded)}. Rebuild it with "
                "npm run ontology:hydroatlas."
            )

        selection = ", ".join(f'"{name}"' for name in ["HYBAS_ID", *columns])
        rows = list(connection.execute(f"SELECT {selection} FROM {LAYER}"))
    finally:
        connection.close()

    # The published reference is the subset the explorer can draw; the atlas is
    # wider. Ordering by that subset keeps the id array aligned with what the map
    # already holds, and drops the rest.
    matched = [row for row in rows if row[0] in weights]
    ids = [row[0] for row in matched]

    values = {
        name: [row[position + 1] for row in matched]
        for position, name in enumerate(columns)
    }

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    OUT_VALUES.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": generated_at,
        "source": "uz:ds/basinatlas-uz-v10",
        "layer": f"{GEOPACKAGE.stem} :: {LAYER}",
        "joinKey": "HYBAS_ID",
        "basins": len(ids),
        "attributes": len(columns),
        "coverage": {
            "publishedBasins": len(weights),
            "atlasBasins": len(rows),
            "matched": len(ids),
            "unmatched": sorted(set(weights) - set(ids)),
        },
        "note": (
            "Attribute values describe the whole sub-basin as HydroSHEDS delineated it, "
            "including any part beyond the Uzbekistan border. Area-weighted aggregation "
            "uses the area inside the country as the weight."
        ),
        "ids": ids,
        "values": values,
    }, separators=(",", ":")), encoding="utf8")

    dictionary = {}
    for name in columns:
        entry = dict(vocabulary[name])
        entry["aggregation"] = aggregation_rule(entry)
        dictionary[name] = entry

    OUT_DICTIONARY.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": generated_at,
        "catalogSource": "BasinATLAS_Data_v10.gdb/BasinATLAS_Catalog_v10.pdf",
        "reference": (
            "Linke, S., Lehner, B., Ouellet Dallaire, C. et al. (2019). Global "
            "hydro-environmental sub-basin and river reach characteristics at high "
            "spatial resolution. Scientific Data 6, 283. doi:10.1038/s41597-019-0300-6"
        ),
        "aggregationRules": {
            "outlet": (
                "Taken from the outlet basin alone. These columns already describe the "
                "whole upstream catchment or the pour point, so combining them across "
                "basins would count the same water twice."
            ),
            "majority": "The class covering the most area across the set.",
            "areaWeightedMean": "Mean over the set, each basin weighted by its area inside Uzbekistan.",
        },
        "columns": dictionary,
    }, indent=2), encoding="utf8")

    unmatched = len(weights) - len(ids)
    print(f"{len(ids):,} basins x {len(columns):,} attributes -> {OUT_VALUES.relative_to(ROOT)}")
    print(f"  {OUT_VALUES.stat().st_size / 1024:,.0f} KB values, "
          f"{OUT_DICTIONARY.stat().st_size / 1024:,.0f} KB dictionary")
    print(f"  {unmatched:,} published basins carry no atlas attributes "
          f"({unmatched / len(weights):.1%} of the reference)")
    counts: dict[str, int] = {}
    for entry in dictionary.values():
        counts[entry["aggregation"]] = counts.get(entry["aggregation"], 0) + 1
    print("  aggregation: " + ", ".join(f"{rule} {count}" for rule, count in sorted(counts.items())))


if __name__ == "__main__":
    main()
