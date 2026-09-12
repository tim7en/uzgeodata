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
import csv
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
from ATLAS_MODULES.hydrosheds.functions import dated_snow

STORE = ROOT / "PUBLISHED/data/atlas/observations"
OUT = ROOT / "PUBLISHED/data/atlas/history"
PREFIX = "uzgeodata.dated."


def labelled():
    """Every dated attribute the adapters publish, with what it is and its units."""
    found = {PREFIX + 'v1.snw_pc_s': {
        'label': 'snow cover', 'unit': 'percent', 'source': 'snow',
        'asset': dated_snow.ASSET, 'trend_use': 'withdrawn',
        'limitation': 'Not for trend analysis: regional missing months increase across '
                      '2003–2022 and the cause has not been established.',
    }}
    for source, spec in dated_monthly.SOURCES.items():
        for band in spec["bands"].values():
            found[band["attribute"]] = {
                "label": band["label"], "unit": band["unit"],
                "source": source, "asset": spec["asset"],
            }
    return found


def vouched_years(store):
    """Which years a completed extraction covered, per source release.

    The store records the run that *first* established a value. A later run that
    re-derives the identical number is a no-op, so an extraction interrupted and then
    re-run leaves the interrupted run's id on rows the completed one also covered.
    Judging eligibility by the run id alone would drop years a finished extraction
    does vouch for -- seven of ERA5 temperature's twenty, in the run this was written
    for -- and publish a record full of holes the evidence does not have.

    The ledger is the claim that matters: it states the span covered and whether the
    run finished, and it is written only on completion.
    """
    covered = {}
    for path in sorted(Path(store).glob("regional-*-ledger.json")):
        try:
            ledger = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        span = ledger.get("years")
        if not ledger.get("complete") or not span or not ledger.get("source"):
            continue
        release = f"{ledger['source']}@{ledger.get('asset')}"
        covered.setdefault(release, set()).update(range(span[0], span[1] + 1))
    return covered


def write_compact(path, payload):
    """One basin's record, written without the whitespace that doubles it.

    These files are arrays of numbers, and indenting them puts every value on its own
    padded line: the same record costs 41 KB pretty-printed and 20 KB compact, which
    across 7,445 basins is the difference between a deployable artifact and one over
    the host's size limit. Nothing is rounded away -- only the spaces.

    Written aside and moved into place, as the store's own partitions are, so a reader
    during a long publish sees the previous file or the new one and never half of one.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                    separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def collect(store, years, known):
    """Every dated value in the window, as one fixed-width array per basin and series.

    NaN stands for "not observed" inside the array because an array of doubles has no
    room for None; it becomes null on the way out. A zero would be a measurement.
    """
    span = list(years)
    width = len(span) * 12
    slot = {year: index for index, year in enumerate(span)}
    series, releases = {}, {}
    # Freeze eligibility before reading: an extraction finishing during publication
    # must not introduce half a new variable into this snapshot.
    ranking = observations.run_ranking(store)
    completed = {run for run, rank in ranking.items() if rank[0]}
    covered = vouched_years(store)
    for year in span:
        partition = store / "time_kind=observation" / f"year={year}"
        if not partition.exists():
            continue
        current, superseded = {}, set()
        for path in sorted(partition.glob('**/part.csv')):
            with path.open(encoding='utf-8', newline='') as stream:
                for row in csv.DictReader(stream):
                    if (row['run_id'] not in completed
                            and year not in covered.get(row['source_release_id'], ())):
                        continue
                    if row['supersedes']:
                        superseded.add(row['supersedes'])
                    attribute = row['attribute_id']
                    if attribute not in known or not row['geometry_version'].startswith('reg-') or not row['month']:
                        continue
                    # Keep only publication fields, bounded to one year.
                    kept = {key: row[key] for key in ('observation_id', 'revision', 'basin_id',
                        'attribute_id', 'month', 'value', 'run_id', 'source_release_id',
                        'recipe_version', 'temporal_statistic', 'geometry_version')}
                    kept['revision'] = int(kept['revision'])
                    held = current.get(row['observation_id'])
                    if held is None or kept['revision'] > held['revision']:
                        current[row['observation_id']] = kept
        chosen = {}
        for row in current.values():
            if observations.row_key(row) in superseded:
                continue
            key = (row['basin_id'], row['attribute_id'], row['month'])
            if observations.outranks(row, chosen.get(key), ranking):
                chosen[key] = row
        for row in chosen.values():
            attribute = row["attribute_id"]
            if not attribute.startswith(PREFIX) or attribute not in known:
                continue
            if not row["geometry_version"].startswith("reg-") or row["month"] is None:
                continue
            key = (row["basin_id"], attribute)
            values = series.get(key)
            if values is None:
                values = series[key] = array("d", [math.nan]) * width
            position = slot[year] * 12 + int(row["month"]) - 1
            values[position] = float(row['value']) if row['value'] else math.nan
            # What must not vary across a series is the measurement: the release it
            # came from, the method that derived it, the statistic it is, and the
            # geometry it was reduced on. Which run performed the work may vary and
            # says nothing about the number -- an extraction interrupted and resumed
            # produces one series from two runs, and both are named rather than one
            # of them being grounds to refuse the series.
            identity = {
                "source_release": row["source_release_id"], "method": row["recipe_version"],
                "statistic": row["temporal_statistic"],
                "geometry_version": row["geometry_version"],
            }
            held = releases.get(attribute)
            if held is None:
                releases[attribute] = {**identity, "run_ids": [row["run_id"]]}
            else:
                if {key: value for key, value in held.items() if key != "run_ids"} != identity:
                    raise ValueError(f'Mixed provenance in {attribute}; publish separate series')
                if row["run_id"] not in held["run_ids"]:
                    held["run_ids"] = sorted(held["run_ids"] + [row["run_id"]])
        print(f'Collected completed runs for {year}', flush=True)
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
        write_compact(out / f"{basin}.json", payload)
        index[basin] = {name: entry["observed_months"] for name, entry in payload["series"].items()}

    summary = {
        "generated_at": utc_now(), "basins": len(basins),
        "years": [span[0], span[-1]], "months": len(span) * 12,
        "base_url": "/data/atlas/history/",
        "series": {attribute.split(".")[-1]: {**known[attribute], **releases.get(attribute, {})}
                   for attribute in attributes},
        "observed_months": index,
        "reading": "One file per basin holds monthly open-data estimates from completed runs. "
                   "Their period may differ from the published climatologies. "
                   "Snow is withdrawn from trend use pending investigation of missing months.",
    }
    write_json(out / 'index.json', summary)
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
