"""Publish the meteorological stations as a map layer.

python PIPELINES/build_station_map_layer.py

The basemap shows what the region holds — basins, rivers, dams, water bodies — but
not the instruments the whole validation rests on. This puts them there, from both
archives, with enough on each point to judge what it is worth before using it.

The two archives reach their coordinates differently and the map says so on every
point. A national station was placed by matching its name to a separate coordinate
registry, because the observations and the registry share no identifier; that match
was checked against an independent physical relationship, but a check that fails to
contradict is not a verified identity. An NSIDC station carries the coordinate its
own source published, and nothing about its placement is inferred.

A station is drawn where it is recorded, not where it is confirmed to be, and the
modal states which of those applies.
"""
from __future__ import annotations
import collections
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import utc_now, write_json

HYDROMET = ROOT / "PUBLISHED/data/hydromet"
OUT = ROOT / "PUBLISHED/data/hydroclimate/meteo-stations.geojson"
SUMMARY = ROOT / "PUBLISHED/data/hydroclimate/meteo-stations.manifest.json"

MEASURE_LABELS = {"air_temperature_mean": "air temperature",
                  "precipitation_total": "precipitation",
                  "soil_temperature_mean": "soil temperature"}
PLACEMENT = {
    "national": "Matched by station name to a separate coordinate registry; the observations "
                "carry no identifier the registry shares.",
    "nsidc": "Coordinate published by the source with the observations; nothing inferred.",
}


def read(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def record_span(rows, key="station_id"):
    """First and last year, and how many monthly values, per station and measure."""
    span, counts = {}, collections.defaultdict(collections.Counter)
    for row in rows:
        if not row.get("year", "").isdigit():
            continue
        station, year = row[key], int(row["year"])
        low, high = span.get(station, (year, year))
        span[station] = (min(low, year), max(high, year))
        counts[station][row["variable"]] += 1
    return span, counts


def feature(longitude, latitude, properties):
    return {"type": "Feature", "properties": properties,
            "geometry": {"type": "Point", "coordinates": [round(longitude, 5), round(latitude, 5)]}}


def build():
    national_span, national_counts = record_span(read(HYDROMET / "station-monthly.csv"))
    nsidc_span, nsidc_counts = record_span(read(HYDROMET / "nsidc-central-asia-monthly.csv"))

    features = []
    for row in read(HYDROMET / "station-crosswalk-verified.csv"):
        if row["match_status"] != "matched_by_name" or not row["longitude"]:
            continue
        station = row["observation_station_id"]
        counts = national_counts.get(station, {})
        low, high = national_span.get(station, ("", ""))
        features.append(feature(float(row["longitude"]), float(row["latitude"]), {
            "station_id": station, "name": row["observation_name"], "archive": "national",
            "archive_label": "National hydrometeorological archive",
            "province": row["province"], "country": "Uzbekistan",
            "elevation_m": float(row["elevation_m"]) if row["elevation_m"] else None,
            "measures": sorted(MEASURE_LABELS.get(m, m) for m in counts),
            "observations": sum(counts.values()),
            "first_year": low, "last_year": high,
            "placement": PLACEMENT["national"],
            "placement_status": row.get("verification", "not_checked"),
            "recorded_air_c": row.get("recorded_air_c") or None,
            "reanalysis_air_c": row.get("reanalysis_air_c") or None,
            "residual_c": row.get("residual_c") or None,
        }))

    for row in read(HYDROMET / "nsidc-central-asia-stations.csv"):
        if row["in_domain"] != "True":
            continue
        station = row["station_id"]
        counts = nsidc_counts.get(station, {})
        low, high = nsidc_span.get(station, ("", ""))
        features.append(feature(float(row["longitude"]), float(row["latitude"]), {
            "station_id": station, "name": row["name"], "archive": "nsidc",
            "archive_label": "NSIDC G02174 Central Asia compilation",
            "province": "", "country": row["country"],
            "elevation_m": float(row["elevation_m"]) if row["elevation_m"] else None,
            "measures": sorted(MEASURE_LABELS.get(m, m) for m in counts),
            "observations": sum(counts.values()),
            "first_year": low, "last_year": high,
            "wmo_code": row["wmo_code"], "system_id": row["system_id"],
            "placement": PLACEMENT["nsidc"],
            "placement_status": "coordinate_supplied_by_source",
        }))

    features.sort(key=lambda f: (f["properties"]["archive"], f["properties"]["name"]))
    layer = {"type": "FeatureCollection", "features": features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(layer, ensure_ascii=False), encoding="utf-8")

    archives = collections.Counter(f["properties"]["archive"] for f in features)
    measures = collections.Counter(m for f in features for m in f["properties"]["measures"])
    elevations = [f["properties"]["elevation_m"] for f in features if f["properties"]["elevation_m"]]
    summary = {
        "generated_at": utc_now(), "stations": len(features),
        "by_archive": dict(archives), "by_measure": dict(measures),
        "observations": sum(f["properties"]["observations"] for f in features),
        "elevation_m": {"min": min(elevations), "max": max(elevations)} if elevations else {},
        "above_1500m": sum(1 for e in elevations if e >= 1500),
        "meaning": "A station is drawn where it is recorded. National stations reached their "
                   "coordinate through a name match that one check did not contradict, which "
                   "is not a verified identity; NSIDC stations carry the coordinate their "
                   "source published. Every point states which applies.",
    }
    write_json(SUMMARY, summary)
    return summary


def main():
    print(json.dumps(build(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
