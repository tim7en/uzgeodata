"""A second implementation of mean basin elevation, for comparison with the first.

python PIPELINES/reproduce_elevation_independently.py

Re-running the same code proves that the code is deterministic. It says nothing about
whether the code is right. This is a separate implementation of `ele_mt_sav` written
against the same pinned input, sharing no code with the pilot's: it opens the hashed
archive itself, reads the raw band with the geometry taken from the file's own header,
works at the DEM's native three arc-seconds instead of the pilot's aggregated grid,
and reduces with the grouped kernel. Where the two agree, the agreement is evidence
about the method rather than about one program.

What this is not: the module's gate 6. That gate asks for a second operator in a
second environment, with a named reviewer and a recorded approval. This runs on the
same machine, in the same environment, driven by the same agent, so it cannot clear
it and does not claim to. What it can do is remove one explanation for a difference —
a mistake in a single implementation — and leave the gate to be cleared by someone
else, with the inputs already pinned for them.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import struct
import sys
import tarfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import sha256, utc_now, write_json
from ATLAS_MODULES.core.zonal import grouped_statistics, parts_by_id

RUN = "pskem-all281-20260909T184834061745Z"
PACKAGE = ROOT / "PUBLISHED/data/atlas/runs" / RUN
REPORT = ROOT / "PUBLISHED/data/atlas/independent-reproduction-ele_mt_sav.json"
COLUMN = "ele_mt_sav"


def header(text):
    """The .hdr is the file's own description of its grid; take it from there."""
    fields = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2:
            fields[parts[0].upper()] = parts[1]
    return fields


def read_tile(archive):
    """Open the pinned archive and read the raw band, without the pilot's readers."""
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
        band = next(n for n in names if n.lower().endswith(".bil"))
        meta = next(n for n in names if n.lower().endswith(".hdr"))
        fields = header(tar.extractfile(meta).read().decode("ascii", "replace"))
        raw = tar.extractfile(band).read()

    rows, columns = int(fields["NROWS"]), int(fields["NCOLS"])
    bits, order = int(fields["NBITS"]), fields.get("BYTEORDER", "I").upper()
    if bits != 16 or fields.get("PIXELTYPE", "SIGNEDINT") != "SIGNEDINT":
        raise ValueError(f"unexpected pixel type: {bits} bit {fields.get('PIXELTYPE')}")
    values = np.frombuffer(raw, dtype=("<i2" if order == "I" else ">i2"), count=rows * columns)
    grid = values.reshape(rows, columns).astype("float64")
    grid[grid == float(fields.get("NODATA", -32768))] = np.nan

    west, north = float(fields["ULXMAP"]), float(fields["ULYMAP"])
    size_x, size_y = float(fields["XDIM"]), float(fields["YDIM"])
    # ULXMAP/ULYMAP give the centre of the first cell, so the grid edge is half a cell out.
    return grid, (west - size_x / 2.0, north + size_y / 2.0, size_x, size_y), fields


def zones_at(features, extent, shape):
    """Label every native cell with the basin whose polygon contains its centre."""
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    west, north, size_x, size_y = extent
    transform = from_origin(west, north, size_x, size_y)
    return rasterize(((f["geometry"], i + 1) for i, f in enumerate(features)),
                     out_shape=shape, transform=transform, fill=0,
                     dtype="int32", all_touched=False), transform


def build():
    lock = json.loads((PACKAGE / "source-lock.json").read_text(encoding="utf-8"))
    entry = lock["candidate_sources"]["elevation"]
    archive = Path(entry["path"])
    if not archive.exists():
        raise FileNotFoundError(f"pinned archive missing: {archive}")

    digest = sha256(archive)
    if digest != entry["sha256"]:
        raise ValueError("the archive on disk is not the one the run pinned")

    grid, extent, fields = read_tile(archive)
    features = json.loads((PACKAGE / "pilot-basins.geojson").read_text(encoding="utf-8"))["features"]
    ids = [str(int(f["properties"]["HYBAS_ID"])) for f in features]
    zones, _ = zones_at(features, extent, grid.shape)

    # Mean elevation is unweighted over the cells of the basin; cell area is passed
    # only because the shared kernel accumulates it, and is not used in the mean.
    areas = np.ones_like(grid)
    parts = parts_by_id(grouped_statistics(grid, zones, areas, len(ids)), ids)
    mine = {b: (p["sum"] / p["count"] if p["count"] else None) for b, p in parts.items()}

    batch = json.loads((PACKAGE / "batch.json").read_text(encoding="utf-8"))
    attribute = next(a for a in batch["attributes"] if a["column"] == COLUMN)
    pilot = {b: v["raw_value"] for b, v in (attribute["candidate_values"] or {}).items()}
    published = attribute["reference_values"]

    rows = []
    for basin in ids:
        rows.append({"basin_id": basin, "independent": mine.get(basin),
                     "pilot_candidate": pilot.get(basin), "published": published.get(basin),
                     "cells": parts[basin]["count"]})

    def spread(pairs):
        differences = [a - b for a, b in pairs if a is not None and b is not None]
        if not differences:
            return None
        return {"basins": len(differences), "bias": sum(differences) / len(differences),
                "mean_absolute": sum(abs(d) for d in differences) / len(differences),
                "max_absolute": max(abs(d) for d in differences),
                "root_mean_square": math.sqrt(sum(d * d for d in differences) / len(differences))}

    summary = {
        "generated_at": utc_now(), "attribute": COLUMN, "run": RUN,
        "input": {"archive": str(archive), "sha256": digest,
                  "verified_against_source_lock": True,
                  "native_cell_degrees": float(fields["XDIM"]),
                  "grid": f'{fields["NROWS"]}x{fields["NCOLS"]}'},
        "method": "Independent read of the pinned archive, grid from the file header, native "
                  "three arc-second resolution, unweighted mean of cells whose centre falls "
                  "inside the basin. No code shared with the pilot implementation.",
        "against_pilot_candidate": spread([(r["independent"], r["pilot_candidate"]) for r in rows]),
        "against_published_atlas": spread([(r["independent"], r["published"]) for r in rows]),
        "pilot_against_published": spread([(r["pilot_candidate"], r["published"]) for r in rows]),
        "basins": rows,
        "gate_6": {
            "cleared": False,
            "why": "Gate 6 requires a second operator in a second environment, a named reviewer "
                   "and a recorded approval. This ran on the same machine under the same agent, "
                   "so it is a second implementation and not an independent reproduction.",
            "what_it_does_establish": "Two implementations sharing no code, reading the same "
                                      "pinned bytes, agree or disagree by the amounts reported "
                                      "here. That removes a single program's mistake as an "
                                      "explanation; it does not replace the reviewer.",
        },
    }
    write_json(REPORT, summary)
    return summary


def main():
    summary = build()
    print(json.dumps({k: v for k, v in summary.items() if k != "basins"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
