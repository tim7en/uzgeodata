"""Set the derived substitutes beside the published HydroATLAS values, basin by basin.

python PIPELINES/compare_substitutes_to_original.py

Every one of the 7,445 basins now carries two numbers for eighty-one attributes: the
value BasinATLAS published, and an independent estimate derived from 2003-2022
observations. This reports how far apart they are.

A difference here is not an error on either side, and reading it as one would be the
main way to misuse this table. The two numbers come from different sources, different
methods and different periods -- BasinATLAS drew on vintages largely from the 1970s
to the 2000s, while these estimates cover 2003-2022 -- so a difference mixes genuine
change over time with method and source disagreement, and nothing here separates
them. A high correlation says the two agree on which basins are wetter or colder than
others; a bias says they disagree on the level. Neither says which is right.

Values are converted into the units BasinATLAS stores before differencing, because
several of its attributes are held as scaled integers.
"""
from __future__ import annotations
import collections
import csv
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.runtime import utc_now, write_json

STORE = ROOT / "PUBLISHED/data/atlas/observations"
BATCH = ROOT / "PUBLISHED/data/atlas/batch-latest.json"
REPORT = ROOT / "PUBLISHED/data/atlas/substitute-vs-original.json"
TABLE = ROOT / "PUBLISHED/data/atlas/substitute-vs-original.csv"
DERIVED = "derived_from_dated_observations"


def family_of(column):
    return column.split("_")[0]


def factors():
    """Surrogate physical units -> the units BasinATLAS stores."""
    batch = json.loads(BATCH.read_text(encoding="utf-8"))
    out = {}
    for family, plan in batch["surrogate_families"].items():
        units = plan.get("units", {})
        out[family] = (float(units.get("factor", 1.0)) if units.get("convertible") else None,
                       units.get("reference_stored", ""))
    return out


def derived_values():
    rows = observations.read_partitions(STORE / "time_kind=climatology")
    out = {}
    for row in rows:
        if row["quality_flag"] != DERIVED or row["value"] is None:
            continue
        out[(row["basin_id"], row["attribute_id"].split(".")[-1])] = row["value"]
    return out


def originals(path):
    out = {}
    with Path(path).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            basin = str(int(float(row["HYBAS_ID"])))
            for column, value in row.items():
                if column in ("HYBAS_ID", "MAIN_BAS") or value in ("", None):
                    continue
                try:
                    out[(basin, column)] = float(value)
                except ValueError:
                    continue
    return out


def summarise(pairs):
    if len(pairs) < 30:
        return None
    differences = [e - o for o, e in pairs]
    observed = [o for o, _ in pairs]
    estimated = [e for _, e in pairs]
    result = {
        "basins": len(pairs),
        "original_mean": statistics.mean(observed),
        "substitute_mean": statistics.mean(estimated),
        "bias": statistics.mean(differences),
        "mean_absolute_difference": statistics.mean(abs(d) for d in differences),
        "root_mean_square_difference": math.sqrt(statistics.mean(d * d for d in differences)),
    }
    if statistics.pstdev(observed) > 0 and statistics.pstdev(estimated) > 0:
        mo, me = statistics.mean(observed), statistics.mean(estimated)
        cov = sum((o - mo) * (e - me) for o, e in pairs) / len(pairs)
        result["correlation"] = cov / (statistics.pstdev(observed) * statistics.pstdev(estimated))
    spread = statistics.pstdev(observed)
    if spread > 0:
        result["difference_over_spread"] = result["root_mean_square_difference"] / spread
    return result


def build(original_path):
    scale = factors()
    derived, published = derived_values(), originals(original_path)
    columns = sorted({column for _, column in derived})

    report, table = {}, []
    for column in columns:
        family = family_of(column)
        factor, stored_unit = scale.get(family, (None, ""))
        pairs = []
        for (basin, name), value in derived.items():
            if name != column:
                continue
            original = published.get((basin, column))
            if original is None:
                continue
            pairs.append((original, value * factor if factor else value))
        found = summarise(pairs) if factor else None
        entry = {"stored_unit": stored_unit,
                 "comparable": factor is not None,
                 "reason": None if factor else "surrogate and stored units do not convert"}
        if found:
            entry.update(found)
            table.append({"column": column, "family": family, **{
                k: round(v, 4) if isinstance(v, float) else v for k, v in found.items()}})
        report[column] = entry

    TABLE.parent.mkdir(parents=True, exist_ok=True)
    if table:
        with TABLE.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(table[0]))
            writer.writeheader()
            writer.writerows(sorted(table, key=lambda r: r["column"]))

    comparable = [v for v in report.values() if v.get("comparable") and "correlation" in v]
    summary = {
        "generated_at": utc_now(),
        "substitute_period": ["2003-01-01", "2023-01-01"],
        "columns_derived": len(columns),
        "columns_compared": len(comparable),
        "columns_not_convertible": sum(1 for v in report.values() if not v["comparable"]),
        "median_correlation": statistics.median([v["correlation"] for v in comparable]) if comparable else None,
        "by_column": report,
        "meaning": "A difference mixes real change since the published vintages with source and "
                   "method disagreement, and nothing here separates them. Correlation says the "
                   "two agree on how basins rank against each other; bias says they disagree on "
                   "the level. Neither establishes which is correct, and none of this is a "
                   "reproduction of the published attribute.",
    }
    write_json(REPORT, summary)
    return summary


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    summary = build(path)
    print(json.dumps({k: v for k, v in summary.items() if k != "by_column"},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
