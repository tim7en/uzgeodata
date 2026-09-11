"""Check the name-matched stations against an independent physical relationship.

python PIPELINES/verify_station_crosswalk.py

The crosswalk joins observations to coordinates by name, which makes a comparison
possible but establishes nothing. This asks a separate question of every match: does
the station's own recorded temperature behave the way a station at that coordinate
should?

Station and reanalysis disagree for a reason that has nothing to do with identity.
A reanalysis cell some ten kilometres across averages the terrain inside it, so in
mountains its effective surface sits well above the valley floor where a station
actually stands, and it reads cold. That error grows with elevation, and it is
physical: it should appear as an orderly relationship across the whole network, not
as noise. A station whose difference departs from that relationship is the one worth
looking at, because a name matched to the wrong place has no reason to land on it.

What this can and cannot say: a station that fits the relationship has not been
verified, only left uncontradicted by one independent check. A station that departs
from it has not been shown wrong either — a deep valley, a sheltered hollow or a
genuinely unusual site can do the same. Both outcomes are reasons to look, and
neither is a finding on its own.
"""
from __future__ import annotations
import collections
import csv
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now, write_json
from PIPELINES.build_station_crosswalk import OUT as CROSSWALK, read

OBSERVATIONS = ROOT / "PUBLISHED/data/hydromet/station-monthly.csv"
CONTEXT = ROOT / "PUBLISHED/data/case-studies/regional-station-context.csv"
VERIFIED = ROOT / "PUBLISHED/data/hydromet/station-crosswalk-verified.csv"
SUMMARY = ROOT / "PUBLISHED/data/hydromet/station-crosswalk-verified.manifest.json"

WINDOW = (2015, 2020)      # the period the reanalysis comparison was computed over
MINIMUM_MONTHS = 24        # two years of station record before a mean is worth using
OUTLIER_SIGMA = 3.0        # robust departures, measured in MAD-derived sigma


def station_means(observations, keep, window=WINDOW):
    """Mean recorded air temperature per station over the comparison window."""
    values = collections.defaultdict(list)
    for row in observations:
        if (row["variable"] == "air_temperature_mean" and row["quality"] == "ok"
                and row["year"].isdigit() and window[0] <= int(row["year"]) <= window[1]
                and row["station_id"] in keep):
            values[row["station_id"]].append(float(row["value"]))
    return {station: (statistics.mean(v), len(v)) for station, v in values.items()
            if len(v) >= MINIMUM_MONTHS}


def fit(points):
    """Least squares of difference against elevation; the lapse-like term."""
    mean_x = statistics.mean(x for x, _ in points)
    mean_y = statistics.mean(y for _, y in points)
    spread = sum((x - mean_x) ** 2 for x, _ in points)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / spread if spread else 0.0
    return mean_y - slope * mean_x, slope


def verify(crosswalk, observations, context):
    sites = {row["station_id"]: row for row in context}
    matched = {row["observation_station_id"]: row for row in crosswalk
               if row["match_status"] == "matched_by_name"}
    means = station_means(observations, set(matched))

    points, rows = [], {}
    for station, (recorded, months) in means.items():
        entry = matched[station]
        site = sites.get(entry["network_entity_id"], {})
        if not site.get("era5_air_c") or not entry.get("elevation_m"):
            continue
        difference = recorded - float(site["era5_air_c"])
        elevation = float(entry["elevation_m"])
        points.append((elevation, difference))
        rows[station] = {"recorded": recorded, "reanalysis": float(site["era5_air_c"]),
                         "difference": difference, "elevation": elevation, "months": months}
    if len(points) < 8:
        raise ValueError("too few comparable stations to establish a relationship")

    intercept, slope = fit(points)
    for entry in rows.values():
        entry["residual"] = entry["difference"] - (intercept + slope * entry["elevation"])
    residuals = [e["residual"] for e in rows.values()]
    middle = statistics.median(residuals)
    spread = statistics.median([abs(r - middle) for r in residuals]) * 1.4826
    limit = OUTLIER_SIGMA * spread

    for entry in rows.values():
        entry["status"] = ("departs_from_network_relationship"
                           if abs(entry["residual"] - middle) > limit else "consistent_with_network")

    raw = statistics.pstdev([e["difference"] for e in rows.values()])
    left = statistics.pstdev(residuals)
    return rows, {
        "intercept_c": intercept, "slope_c_per_1000m": slope * 1000,
        "explained_share": 1 - (left / raw) ** 2 if raw else 0.0,
        "residual_sigma_c": spread, "flag_limit_c": limit,
        "spread_before_c": raw, "spread_after_c": left,
    }


def build():
    crosswalk, observations = read(CROSSWALK), read(OBSERVATIONS)
    context = read(CONTEXT)
    checked, model = verify(crosswalk, observations, context)

    rows = []
    for entry in crosswalk:
        found = checked.get(entry["observation_station_id"])
        rows.append({**entry,
                     "verification": found["status"] if found else "not_checked",
                     "recorded_air_c": round(found["recorded"], 3) if found else "",
                     "reanalysis_air_c": round(found["reanalysis"], 3) if found else "",
                     "difference_c": round(found["difference"], 3) if found else "",
                     "residual_c": round(found["residual"], 3) if found else "",
                     "months_compared": found["months"] if found else ""})
    VERIFIED.parent.mkdir(parents=True, exist_ok=True)
    with VERIFIED.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    counted = collections.Counter(row["verification"] for row in rows)
    flagged = [r for r in rows if r["verification"] == "departs_from_network_relationship"]
    summary = {
        "generated_at": utc_now(), "window": list(WINDOW),
        "checked": len(checked), "counts": dict(counted),
        "relationship": model,
        "flagged": [{"name": r["observation_name"], "residual_c": r["residual_c"],
                     "elevation_m": r["elevation_m"]} for r in flagged],
        "status": "one_independent_check_applied",
        "meaning": "Stations consistent with the network relationship are not verified, only "
                   "left uncontradicted. Flagged stations are not shown to be wrong: a deep "
                   "valley can depart from the relationship as easily as a bad match can. "
                   "Both are reasons to look, and only air temperature was checked, so "
                   "precipitation and soil-temperature matches rest on the name alone.",
    }
    write_json(SUMMARY, summary)
    return summary


def main():
    import json
    print(json.dumps(build(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
