"""Does the answer depend on the size of the unit it was computed on?

A trend computed per basin is a trend computed on an arbitrary polygon. Make the
polygons bigger and several things change at once: each unit averages more source
cells, the series gets smoother, the number of simultaneous tests falls by an order of
magnitude, and the multiple-testing burden falls with it. A result that survives at one
size and vanishes at another is telling you about the polygons.

So the study is run twice, at level 12 and level 7, and this compares them. Level 7 is
the level at which every product resolves -- 70 TerraClimate cells per basin and 12
ERA5-Land cells, against 6.3 and 1.05 at level 12 -- so it is the level at which the
two ERA5 variables can be analysed at all. Level 12 is where the detail is, for the
products fine enough to support it.

The comparison is the defensible form of the result. Agreement across an order of
magnitude in unit area is not proof, but disagreement would have been disproof, and
running only one scale leaves that untested.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now, write_json

TRENDS = ROOT / "PUBLISHED/data/trends"
OUT = TRENDS / "scale-check.json"

# Above this share of tested units the signal is treated as present at that scale. It
# is a reporting threshold for the comparison, not a statistical one: every underlying
# verdict is already false-discovery controlled.
PRESENT = 0.05


def build(out=OUT):
    fine = json.loads((TRENDS / "index.json").read_text(encoding="utf-8"))
    coarse = json.loads((TRENDS / "level7/index.json").read_text(encoding="utf-8"))

    rows = []
    for identifier in sorted(set(fine["summary"]) | set(coarse["summary"])):
        a, b = fine["summary"].get(identifier), coarse["summary"].get(identifier)
        entry = {
            "variable": identifier,
            "native_resolution_m": (a or b).get("native_resolution_m"),
            "level12": _side(a),
            "level7": _side(b),
        }
        share_a, share_b = entry["level12"]["share"], entry["level7"]["share"]
        if share_a is None or share_b is None:
            entry["verdict"] = "one scale only"
            entry["note"] = ("Not testable at level 12: the basin is smaller than the "
                             "source cell, so only the coarser scale carries a result.")
        elif (share_a > PRESENT) == (share_b > PRESENT):
            entry["verdict"] = "consistent"
            entry["note"] = None
        else:
            entry["verdict"] = "diverges"
            entry["note"] = ("Present at one scale and absent at the other. The polygons "
                             "are doing work the data is not.")
        rows.append(entry)

    consistent = [r for r in rows if r["verdict"] == "consistent"]
    report = {
        "generated_at": utc_now(),
        "title": "Does the answer depend on the size of the unit?",
        "scales": {
            "level12": {"units": 7445, "median_area_km2": 136,
                        "terraclimate_cells_per_unit": 6.03,
                        "era5_cells_per_unit": 1.05},
            "level7": {"units": 438, "median_area_km2": 1510,
                       "terraclimate_cells_per_unit": 70.2,
                       "era5_cells_per_unit": 12.2},
        },
        "threshold": PRESENT,
        "variables": rows,
        "summary": {
            "consistent": len(consistent),
            "diverging": len([r for r in rows if r["verdict"] == "diverges"]),
            "one_scale_only": len([r for r in rows if r["verdict"] == "one scale only"]),
        },
        "reading": {
            "what_this_tests": "Whether a surviving signal is a property of the record or "
                               "of the polygons it was averaged over. Unit area differs by "
                               "an order of magnitude between the two scales, and the "
                               "number of simultaneous tests by a factor of seventeen.",
            "what_it_cannot_do": "Agreement across scales is not independent confirmation. "
                                 "Both scales read the same underlying grids, so a bias in "
                                 "the source product appears identically in both. This "
                                 "tests the aggregation, not the data.",
            "era5": "ERA5-Land is analysable only at level 7, where it holds about twelve "
                    "cells per unit. Analysed there, neither runoff nor mean temperature "
                    "retains a meaningful share of significant units -- which is a result, "
                    "and one the level-12 analysis could not have produced honestly.",
        },
    }
    write_json(out, report)
    return report


def _side(block):
    if not block or not block.get("basins_tested"):
        return {"tested": 0, "significant": 0, "share": None,
                "median_source_cells": block.get("median_source_cells") if block else None,
                "withheld_unresolved": block.get("basins_withheld_unresolved") if block else None}
    tested = block["basins_tested"]
    return {
        "tested": tested,
        "significant": block["significant_after_fdr"],
        "share": round(block["significant_after_fdr"] / tested, 4),
        "median_source_cells": block.get("median_source_cells"),
        "withheld_unresolved": block.get("basins_withheld_unresolved"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    report = build()
    print(f"{'variable':<12}{'L12':>16}{'L7':>16}   verdict")
    for row in report["variables"]:
        name = row["variable"].replace("uz:", "").replace("-monthly-v1", "")
        a, b = row["level12"], row["level7"]
        left = f"{a['significant']}/{a['tested']}" if a["tested"] else "not testable"
        right = f"{b['significant']}/{b['tested']}" if b["tested"] else "not testable"
        print(f"{name:<12}{left:>16}{right:>16}   {row['verdict']}")
    print(f"\n{report['summary']}")


if __name__ == "__main__":
    main()
