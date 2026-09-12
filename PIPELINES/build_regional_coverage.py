"""What the region actually holds, attribute by attribute.

python PIPELINES/build_regional_coverage.py

The pilot's own report says how twenty basins fared. Scaling to 7,445 raises a
different question, and one the per-source ledgers cannot answer between them: of the
281 published attributes, which now carry an independent estimate for every basin,
which carry one for some, and which carry none at all. A run that covered three
quarters of the region looks the same in its own ledger as one that covered all of it,
and only a view across every source shows the difference.

Two distinctions are kept rather than collapsed. An attribute the pilot estimated but
the region has not is not the same as one nothing has estimated: the first is work not
yet done, the second is a family with no adapter behind it, and one number for both
would hide which. And where two runs hold a current value for a basin -- a re-run
under a corrected method does not supersede the earlier one -- the store's own ranking
decides which is counted, so coverage is measured against the values the atlas
publishes rather than against every value it has ever held.

Nothing here is a quality statement. A column at full coverage is one where an
open-data estimate exists for every basin; whether it is any good is what the method
reviews and the reproduction gate are for.
"""
from __future__ import annotations
import collections
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.runtime import utc_now, write_json

STORE = ROOT / "PUBLISHED/data/atlas/observations"
BATCH = ROOT / "PUBLISHED/data/atlas/batch-latest.json"
OUT = ROOT / "PUBLISHED/data/atlas/regional-coverage.json"
UNDATED = ("static", "source_epoch", "climatology")
REGIONAL = "reg-"

# Why an attribute is not at full regional coverage. The order is the order of
# progress, from finished to never started.
REASONS = {
    "regional": "an estimate exists for every basin",
    "source_gaps": "the source held no value in {short} basins, each recorded with its reason",
    "partial": "the run that produced it did not reach every basin",
    "pilot_only": "no regional adapter has been run for this family",
    "absent": "nothing has estimated this attribute",
}


def definitions(path=BATCH):
    """The 281 published attributes, as the pilot batch defines them."""
    batch = json.loads(path.read_text(encoding="utf-8"))
    return {a["column"]: a for a in batch["attributes"]}, set(batch["basin_ids"])


def sources_by_column(store):
    """Which runs produced each column regionally, and the metadata they wrote.

    A first pass, because which run's rows should be counted cannot be decided until
    every run that touched the column is known.
    """
    runs, detail = collections.defaultdict(set), {}
    for kind in UNDATED:
        for row in observations.iter_partitions(store / f"time_kind={kind}"):
            if not row["geometry_version"].startswith(REGIONAL):
                continue
            column = row["attribute_id"].split(".")[-1]
            runs[column].add(row["run_id"])
            detail[(column, row["run_id"])] = {
                "time_kind": row["time_kind"], "unit": row["unit"],
                "period": [row["valid_start"], row["valid_end"]],
                "statistic": row["temporal_statistic"],
                "source_release": row["source_release_id"], "method": row["recipe_version"],
            }
    return runs, detail


def published_run(runs, ranking):
    """The run whose values the atlas publishes for each column."""
    chosen = {}
    for column, candidates in runs.items():
        for run_id in sorted(candidates):
            if observations.outranks({"run_id": run_id}, chosen.get(column), ranking):
                chosen[column] = {"run_id": run_id}
    return {column: held["run_id"] for column, held in chosen.items()}


def counts(store, published):
    """Basins reached, and basins carrying a value, counted on the run that won.

    The two differ, and the difference is why they are separated. A basin the run
    never reached has no row at all; a basin where the source held nothing has a row
    stating why it is empty. One number for both would present a product that
    genuinely says nothing about a basin as work left undone.

    Distinct basins rather than rows: a corrected value is a second revision of the
    same observation, and counting rows would report it as a second basin.
    """
    reached, covered, basins = collections.defaultdict(set), collections.defaultdict(set), set()
    for kind in UNDATED:
        for row in observations.iter_partitions(store / f"time_kind={kind}"):
            if not row["geometry_version"].startswith(REGIONAL):
                continue
            basins.add(row["basin_id"])
            column = row["attribute_id"].split(".")[-1]
            if row["run_id"] != published.get(column):
                continue
            reached[column].add(row["basin_id"])
            if row["value"] is not None:
                covered[column].add(row["basin_id"])
    return ({column: len(found) for column, found in covered.items()},
            {column: len(found) for column, found in reached.items()}, len(basins))


def state_of(covered, reached, total, in_pilot):
    """Where an attribute stands, and whose limit stopped it short of the whole region."""
    if not total:
        return "absent"
    if covered >= total:
        return "regional"
    if reached >= total:
        # Every basin was asked; the source had nothing to say about some of them.
        return "source_gaps"
    if reached:
        return "partial"
    return "pilot_only" if in_pilot else "absent"


def build(store=STORE, out=OUT):
    defined, pilot_basins = definitions()
    ranking = observations.run_ranking(store)
    runs, detail = sources_by_column(store)
    published = published_run(runs, ranking)
    covered, reached, total = counts(store, published)

    columns, pending = [], []
    for column in sorted(defined):
        attribute = defined[column]
        found, asked = covered.get(column, 0), reached.get(column, 0)
        estimated = attribute.get("surrogate_values") or attribute.get("candidate_values")
        state = state_of(found, asked, total, bool(estimated))
        entry = {
            "column": column, "label": attribute["label"], "category": attribute["category"],
            "support": attribute["spatial_support"], "state": state,
            "basins": found, "basins_reached": asked,
            "coverage": round(found / total, 6) if total else 0.0,
        }
        entry.update(detail.get((column, published.get(column)), {}))
        columns.append(entry)
        if state != "regional":
            pending.append({
                "column": column, "category": attribute["category"], "state": state,
                "basins": found, "basins_reached": asked,
                "reason": (REASONS[state].format(short=total - found) if state == "source_gaps"
                           else attribute.get("surrogate_pending_reason") or REASONS[state]),
            })

    by_state = collections.Counter(entry["state"] for entry in columns)
    by_category = collections.defaultdict(collections.Counter)
    for entry in columns:
        by_category[entry["category"]][entry["state"]] += 1

    summary = {
        "generated_at": utc_now(),
        "basin_level": 12, "basins": total, "pilot_basins": len(pilot_basins),
        "attributes": len(columns),
        "summary": {state: by_state.get(state, 0) for state in REASONS},
        "values": sum(entry["basins"] for entry in columns),
        "by_category": {category: dict(states) for category, states in sorted(by_category.items())},
        "columns": columns,
        "pending": pending,
        "reading": {
            "regional": "An independent open-data estimate exists for every basin in the domain.",
            "source_gaps": "Every basin was asked and the source held no value for some of them, "
                           "each recorded with its own reason. That is the source's limit rather "
                           "than an unfinished run, and closing it would mean inventing a value.",
            "partial": "A run produced this column but did not reach every basin; the ledger of "
                       "the run that made it says where it stopped.",
            "pilot_only": "The twenty-basin pilot estimated this attribute and no regional "
                          "adapter has been run for it.",
            "absent": "Nothing has estimated this attribute. No substitute is implied and none "
                      "should be invented for it.",
            "quality": "Coverage counts values, not accuracy. No attribute in this atlas has "
                       "passed independent reproduction, whatever its coverage.",
        },
    }
    write_json(out, summary)
    return summary


def main():
    summary = build()
    print(json.dumps({k: v for k, v in summary.items() if k not in ("columns", "pending")},
                     indent=2, ensure_ascii=False))
    print(f"pending: {len(summary['pending'])} attributes")


if __name__ == "__main__":
    main()
