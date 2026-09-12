"""Publish each basin's dated record as one file it can be read and analysed from.

python PIPELINES/build_basin_history.py

The climatologies in the basin API answer "what is this basin like". They cannot
answer "what happened here in 2011", because a normal is the average that question
was removed from. The store holds the monthly observations those normals were
derived from, and this puts them where a reader can use them: one file per basin,
every month of every year, for every dated variable.

Two decisions shape the file. Values are a flat array of months in order rather than
an object keyed by date, because naming 240 dates in 7,445 files costs more than the
numbers do. And a month with no observation is null, never zero and never omitted:
the gaps are part of the record, and in the snow series they are the part a trend
would otherwise be computed straight through.

The store is read one year partition at a time and held as a fixed array of doubles,
so publishing the whole region costs a few hundred megabytes of memory rather than
several gigabytes of Python objects.
"""
from __future__ import annotations
import argparse
from array import array
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.runtime import utc_now, write_json
from ATLAS_MODULES.hydrosheds.functions import dated_monthly

STORE = ROOT / "PUBLISHED/data/atlas/observations"
OUT = ROOT / "PUBLISHED/data/atlas/history"
INDEX = OUT / "index.json"
PREFIX = "uzgeodata.dated."


def labelled():
    """Every dated attribute the adapters publish, with what it is and its units."""
    found = {}
    for source, spec in dated_monthly.SOURCES.items():
        for band in spec["bands"].values():
            found[band["attribute"]] = {
                "label": band["label"], "unit": band["unit"],
                "source": source, "asset": spec["asset"],
            }
    return found


def collect(store, years, known):
    """Every dated value in the window, as one fixed-width array per basin and series.

    NaN stands for "not observed" inside the array because an array of doubles has no
    room for None; it becomes null on the way out. A zero would be a measurement.
    """
    span = list(years)
    width = len(span) * 12
    slot = {year: index for index, year in enumerate(span)}
    series, releases = {}, {}
    for year in span:
        partition = store / "time_kind=observation" / f"year={year}"
        if not partition.exists():
            continue
        for row in observations.iter_partitions(partition):
            attribute = row["attribute_id"]
            if not attribute.startswith(PREFIX) or attribute not in known:
                continue
            if not row["geometry_version"].startswith("reg-") or row["month"] is None:
                continue
            key = (row["basin_id"], attribute)
            values = series.get(key)
            if values is None:
                values = series[key] = array("d", [math.nan]) * width
            position = slot[row["year"]] * 12 + row["month"] - 1
            if row["value"] is not None:
                values[position] = row["value"]
            releases.setdefault(attribute, {
                "source_release": row["source_release_id"], "method": row["recipe_version"],
                "statistic": row["temporal_statistic"],
            })
    return series, releases


def basin_payload(basin, attributes, series, known, releases, span):
    """One basin's record, with the gaps it actually has rather than filled in."""
    published = {}
    for attribute in attributes:
        values = series.get((basin, attribute))
        if values is None:
            continue
        months = [None if math.isnan(value) else round(value, 4) for value in values]
        observed = sum(1 for value in months if value is not None)
        published[attribute.split(".")[-1]] = {
            **known[attribute], **releases.get(attribute, {}),
            "values": months,
            "observed_months": observed,
            "missing_months": len(months) - observed,
        }
    return {
        "basin_id": basin, "basin_level": 12,
        "years": [span[0], span[-1]],
        "months": len(span) * 12,
        "series": published,
        "note": "Values run month by month from January of the first year. A null is a month "
                "with no observation, never a zero, and the nulls are part of the record: a "
                "trend computed through them can be a trend in what the sensor delivered.",
    }


def build(store=STORE, out=OUT, years=range(2003, 2023)):
    started = time.perf_counter()
    known = labelled()
    span = list(years)
    series, releases = collect(store, span, known)
    if not series:
        raise ValueError("no dated regional observations found for that window")

    basins = sorted({basin for basin, _ in series})
    attributes = sorted({attribute for _, attribute in series})
    out.mkdir(parents=True, exist_ok=True)
    index = {}
    for basin in basins:
        payload = basin_payload(basin, attributes, series, known, releases, span)
        (out / f"{basin}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        index[basin] = {name: entry["observed_months"] for name, entry in payload["series"].items()}

    summary = {
        "generated_at": utc_now(), "basins": len(basins),
        "years": [span[0], span[-1]], "months": len(span) * 12,
        "base_url": "/data/atlas/history/",
        "series": {attribute.split(".")[-1]: {**known[attribute], **releases.get(attribute, {})}
                   for attribute in attributes},
        "observed_months": index,
        "reading": "One file per basin holds every monthly observation behind that basin's "
                   "climatologies. The climatology is the average; this is what was averaged.",
    }
    write_json(INDEX, summary)
    size = sum(path.stat().st_size for path in out.glob("*.json"))
    return {"basins": len(basins), "series": len(attributes),
            "months": len(span) * 12, "megabytes": round(size / 1e6, 1),
            "wall_seconds": round(time.perf_counter() - started, 1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", default="2003-2022")
    first, _, last = parser.parse_args().years.partition("-")
    print(json.dumps(build(years=range(int(first), int(last or first) + 1)), indent=2))


if __name__ == "__main__":
    main()
