"""Publish every basin as a file, and the metadata once beside them.

python PIPELINES/build_basin_api.py

A reader who wants one basin should fetch one basin, and should be able to tell what
the numbers mean without reading a web page that a downloaded file leaves behind.

The metadata lives in a catalogue fetched once rather than inside every basin file.
Unit, method, source release and period are identical across all 7,445 basins, so
repeating them per basin costs 1.6 GB to say the same thing 7,445 times; held once
and referenced by position, the same information costs 71 KB and the basin files
shrink to about five kilobytes each.

Each basin carries the published BasinATLAS value and the independent substitute side
by side, with the period each covers. Putting the substitute behind a second request
would invite reading it as the published value, which it is not: it is an open-data
estimate over a stated window, and the catalogue says so in the file itself rather
than only in prose somewhere else.

These are static files. `GET /data/atlas/basins/<hybas_id>.json` needs no server, no
database and no query language, and behaves the same on a laptop, a static host or a
CDN.
"""
from __future__ import annotations
import collections
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.runtime import utc_now, write_json

STORE = ROOT / "PUBLISHED/data/atlas/observations"
BATCH = ROOT / "PUBLISHED/data/atlas/batch-latest.json"
OUT = ROOT / "PUBLISHED/data/atlas/basins"
CATALOGUE = ROOT / "PUBLISHED/data/atlas/catalogue.json"
INDEX = OUT / "index.json"
GDB = ROOT / "GEODATA/BasinATLAS_Data_v10.gdb/BasinATLAS_Data_v10.gdb/BasinATLAS_v10.gdb"
LAYER = "BasinATLAS_v10_lev12"
BBOX = (57.0, 33.5, 79.5, 48.0)
SYSTEMS = {4120050220: "amu_darya", 4120050240: "syr_darya"}


def originals(columns):
    """Published BasinATLAS values for every basin in the two systems."""
    import pyogrio
    frame = pyogrio.read_dataframe(GDB, layer=LAYER, bbox=BBOX,
                                   columns=["HYBAS_ID", "MAIN_BAS", "SUB_AREA"] + columns)
    frame = frame[frame.MAIN_BAS.astype("int64").isin(SYSTEMS)]
    out = {}
    for row in frame.itertuples(index=False):
        values = row._asdict()
        basin = str(int(values["HYBAS_ID"]))
        out[basin] = {
            "system": SYSTEMS[int(values["MAIN_BAS"])],
            "area_km2": float(values["SUB_AREA"]),
            "values": {c: (None if values[c] is None else float(values[c])) for c in columns},
        }
    return out


def substitutes():
    """Regional substitute values and their provenance, from the store."""
    values, meta = collections.defaultdict(dict), {}
    for kind in ("static", "source_epoch", "climatology"):
        for row in observations.read_partitions(STORE / f"time_kind={kind}"):
            if not row["geometry_version"].startswith("reg-"):
                continue
            column = row["attribute_id"].split(".")[-1]
            values[row["basin_id"]][column] = (row["value"], row["valid_count"], row["expected_count"])
            meta.setdefault(column, {
                "unit": row["unit"], "time_kind": row["time_kind"],
                "period": [row["valid_start"], row["valid_end"]],
                "statistic": row["temporal_statistic"],
                "source_release": row["source_release_id"], "method": row["recipe_version"],
            })
    return values, meta


def build():
    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    defined = {a["column"]: a for a in batch["attributes"]}
    columns = sorted(defined)
    published = originals(columns)
    estimated, provenance = substitutes()

    catalogue = {
        "generated_at": utc_now(),
        "basin_level": 12, "basins": len(published),
        "attributes": columns,
        "meta": {column: {
            "label": defined[column]["label"],
            "category": defined[column]["category"],
            "unit": defined[column]["units"],
            "support": defined[column]["spatial_support"],
            "time_kind": defined[column]["time_kind"],
            "original": {"dataset": defined[column]["source_dataset"],
                         "citation": defined[column]["source_citation"],
                         "period": defined[column]["reference_period"],
                         "catalogue": defined[column]["source_url"]},
            "substitute": provenance.get(column),
        } for column in columns},
        "reading": {
            "original": "The value BasinATLAS published, imported unchanged. Its vintage is the "
                        "source's, not this project's.",
            "substitute": "An independent open-data estimate over the stated period. It is not a "
                          "reproduction of the published value: different source, different method, "
                          "different years. Agreement between the two would not make it one.",
            "qa": "Where a substitute carries valid and expected counts, they are the observations "
                  "behind it. A value resting on few is not comparable with one resting on many.",
            "reproduction": "No attribute in this atlas has passed independent reproduction. "
                            "Nothing here is a scientific release.",
            "support": "s is this sub-basin; u and p accumulate everything draining through it.",
        },
    }
    CATALOGUE.write_text(json.dumps(catalogue, ensure_ascii=False), encoding="utf-8")

    OUT.mkdir(parents=True, exist_ok=True)
    index = {}
    for basin, record in published.items():
        estimate = estimated.get(basin, {})
        # Aligned to the catalogue order, so the names are never repeated per basin.
        payload = {
            "basin_id": basin, "basin_level": 12, "system": record["system"],
            "area_km2": record["area_km2"],
            "catalogue": "/data/atlas/catalogue.json",
            "original": [record["values"][c] for c in columns],
            "substitute": [estimate.get(c, (None,))[0] for c in columns],
            "substitute_valid": [estimate.get(c, (None, None))[1] if c in estimate else None
                                 for c in columns],
            "substitute_expected": [estimate.get(c, (None, None, None))[2] if c in estimate else None
                                    for c in columns],
            "note": "Values are positional against catalogue.attributes. Substitutes are "
                    "independent estimates, not reproductions; read catalogue.reading first.",
        }
        (OUT / f"{basin}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        index[basin] = {"system": record["system"], "area_km2": round(record["area_km2"], 3),
                        "substitutes": sum(1 for c in columns if estimate.get(c, (None,))[0] is not None)}

    write_json(INDEX, {"generated_at": utc_now(), "basins": len(index),
                       "base_url": "/data/atlas/basins/", "catalogue": "/data/atlas/catalogue.json",
                       "by_basin": index})
    size = sum(f.stat().st_size for f in OUT.glob("*.json"))
    return {"basins": len(index), "attributes": len(columns),
            "with_substitutes": sum(1 for v in index.values() if v["substitutes"]),
            "catalogue_bytes": CATALOGUE.stat().st_size,
            "basin_files_bytes": size,
            "megabytes": round(size / 1e6, 1)}


def main():
    print(json.dumps(build(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
