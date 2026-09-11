"""Join station observations to station coordinates, and say how good the join is.

python PIPELINES/build_station_crosswalk.py

The monthly observations and the station network arrived from different deliveries
and identify sites differently. The observations use WMO-style codes for air and
precipitation (`meteo-38023`) and place names for soil temperature (`soil-aktumsuk`);
the network shapefile uses a national code (`meteo-373673`). The two id spaces do
not intersect at all, so almost every observation in the archive is currently
unlocatable, and a station with no coordinates cannot be compared with anything
gridded. That is why the regional study pairs two stations out of sixty-nine.

The only bridge in the deliveries is the station name, so this builds that bridge
and is explicit about what it is worth. A name is matched only when it resolves to
exactly one site on each side; anything ambiguous or unmatched is published as such
rather than resolved by guesswork.

A name match is not verification. Two sites can share a name, a name can be
transliterated inconsistently, and a coordinate in the shapefile can be wrong. This
table is a reviewable proposal that makes the comparison possible; it does not
establish that a row of observations was recorded at the coordinate now attached
to it, and it carries no status that would let it be treated as though it had.
"""
from __future__ import annotations
import collections
import csv
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now, write_json

OBSERVATIONS = ROOT / "PUBLISHED/data/hydromet/station-monthly.csv"
NETWORK = ROOT / "PUBLISHED/data/hydroclimate/hydromet-meteo-network.csv"
CONTEXT = ROOT / "PUBLISHED/data/case-studies/regional-station-context.csv"
OUT = ROOT / "PUBLISHED/data/hydromet/station-crosswalk.csv"
SUMMARY = ROOT / "PUBLISHED/data/hydromet/station-crosswalk.manifest.json"

OBSERVATION_NAMES = ("station_name", "station_name_original")
NETWORK_NAMES = ("name_raw", "name_cyrillic", "name_latin")


def normalise(name):
    """Fold case, accents and punctuation, and drop a station code used as a prefix."""
    folded = unicodedata.normalize("NFKD", (name or "").strip().lower())
    return re.sub(r"^\d+", "", re.sub(r"[^\w]+", "", folded))


def index(rows, id_field, name_fields):
    names = collections.defaultdict(set)
    for row in rows:
        for field in name_fields:
            key = normalise(row.get(field))
            if key:
                names[key].add(row[id_field])
    return names


def read(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def crosswalk(observations, network, context=None):
    """One row per observation station, matched or not, with the evidence for it."""
    elevation = {row["station_id"]: row for row in (context or [])}
    sites = {row["entity_id"]: row for row in network}
    by_name = index(network, "entity_id", NETWORK_NAMES)

    counts = collections.Counter()
    variables = collections.defaultdict(set)
    for row in observations:
        counts[row["station_id"]] += 1
        variables[row["station_id"]].add(row["variable"])

    observed = {}
    for row in observations:
        observed.setdefault(row["station_id"], row)

    rows = []
    for station_id, sample in sorted(observed.items()):
        keys = {normalise(sample.get(field)) for field in OBSERVATION_NAMES}
        keys.discard("")
        candidates = set()
        for key in keys:
            candidates |= by_name.get(key, set())
        if len(candidates) == 1:
            entity = next(iter(candidates))
            site = sites[entity]
            status, matched = "matched_by_name", entity
        else:
            site, status, matched = {}, "ambiguous_name" if candidates else "no_name_match", ""
        detail = elevation.get(matched, {})
        rows.append({
            "observation_station_id": station_id,
            "observation_name": sample.get("station_name", ""),
            "province": sample.get("province", ""),
            "measures": "|".join(sorted(variables[station_id])),
            "monthly_observations": counts[station_id],
            "match_status": status,
            "candidates": len(candidates),
            "network_entity_id": matched,
            "network_name": site.get("name_latin", ""),
            "longitude": site.get("longitude", ""),
            "latitude": site.get("latitude", ""),
            "elevation_m": detail.get("elevation_m", ""),
            "evidence": "normalised station name resolved to exactly one network site"
                        if status == "matched_by_name" else "",
        })
    return rows


def build():
    observations, network = read(OBSERVATIONS), read(NETWORK)
    context = read(CONTEXT) if CONTEXT.exists() else []
    rows = crosswalk(observations, network, context)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    matched = [r for r in rows if r["match_status"] == "matched_by_name"]
    located = sum(r["monthly_observations"] for r in matched)
    total = sum(r["monthly_observations"] for r in rows)
    # Counted per row, not per station: a site that records both air temperature and
    # precipitation must not contribute its whole total to each of them.
    locatable_ids = {row["observation_station_id"] for row in matched}
    by_measure = collections.Counter(
        row["variable"] for row in observations if row["station_id"] in locatable_ids)
    summary = {
        "generated_at": utc_now(),
        "observation_stations": len(rows),
        "matched": len(matched),
        "ambiguous": sum(1 for r in rows if r["match_status"] == "ambiguous_name"),
        "unmatched": sum(1 for r in rows if r["match_status"] == "no_name_match"),
        "monthly_observations": total,
        "locatable_observations": located,
        "locatable_share": round(located / total, 4) if total else 0,
        "locatable_by_measure": dict(by_measure),
        "with_elevation": sum(1 for r in matched if r["elevation_m"]),
        "status": "proposed_crosswalk_pending_review",
        "meaning": "A name match makes a comparison possible; it does not establish that these "
                   "observations were recorded at this coordinate. Ambiguous and unmatched "
                   "stations are published rather than resolved by guesswork, and no station "
                   "here carries a verified identity.",
    }
    write_json(SUMMARY, summary)
    return summary


def main():
    import json
    print(json.dumps(build(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
