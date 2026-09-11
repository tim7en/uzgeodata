"""Publish each station's own record, so a reader can take one station away.

python PIPELINES/build_station_downloads.py

The map can now be read, but reading is not the same as using. A reader who opens a
station and finds it useful should be able to leave with that station's observations
rather than the whole archive, which is a third of a million rows and mostly about
somewhere else.

One compact file per station. The rows travel as arrays rather than objects because
the column names are the same for every row and repeating them three hundred thousand
times would treble the size for nothing. The browser turns the same file into CSV, so
the two formats cannot describe different numbers.

Each file carries the station's placement and the treatment of its measurements with
it. A file that leaves the portal loses the modal that explained it, so whatever a
reader needs in order to use the numbers honestly has to travel inside the file.
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
LAYER = ROOT / "PUBLISHED/data/hydroclimate/meteo-stations.geojson"
OUT = HYDROMET / "stations"
INDEX = HYDROMET / "stations/index.json"

COLUMNS = ("variable", "year", "month", "value", "unit", "quality")
TREATMENT = {
    "national": "Observations as delivered by the national hydrometeorological archive. "
                "Precipitation carries no gauge correction, so totals understate true "
                "precipitation, most of all for snow at windy sites.",
    "nsidc": "NSIDC G02174 (Williams and Konovalov 2008, doi:10.7265/N5NK3BZ8). Precipitation "
             "is corrected for gauge type and wetting but not for wind. Records end in 2003.",
}


def key_for(station_id):
    """A filename-safe key: the identifier's last segment, which is already unique."""
    return station_id.rsplit("/", 1)[-1]


def read(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def observations():
    """Every monthly value, grouped by station, from both archives."""
    rows = collections.defaultdict(list)
    for row in read(HYDROMET / "station-monthly.csv"):
        rows[row["station_id"]].append((row["variable"], row["year"], row["month"],
                                        row["value"], row["unit"], row["quality"]))
    for row in read(HYDROMET / "nsidc-central-asia-monthly.csv"):
        rows[row["station_id"]].append((row["variable"], row["year"], row["month"],
                                        row["value"], row["unit"], "ok"))
    return rows


def build():
    layer = json.loads(LAYER.read_text(encoding="utf-8"))
    records = observations()
    OUT.mkdir(parents=True, exist_ok=True)

    index, written, missing = {}, 0, []
    for feature in layer["features"]:
        station = feature["properties"]
        rows = records.get(station["station_id"], [])
        if not rows:
            missing.append(station["station_id"])
            continue
        key = key_for(station["station_id"])
        ordered = sorted(rows, key=lambda r: (r[0], int(r[1]) if r[1].isdigit() else 0,
                                              int(r[2]) if r[2].isdigit() else 0))
        payload = {
            "station_id": station["station_id"], "name": station["name"],
            "archive": station["archive"], "archive_label": station["archive_label"],
            "country": station["country"], "elevation_m": station["elevation_m"],
            "longitude": feature["geometry"]["coordinates"][0],
            "latitude": feature["geometry"]["coordinates"][1],
            "placement": station["placement"],
            "placement_status": station["placement_status"],
            "treatment": TREATMENT[station["archive"]],
            "generated_at": utc_now(),
            "columns": list(COLUMNS),
            "rows": [[r[0], int(r[1]) if r[1].isdigit() else None,
                      int(r[2]) if r[2].isdigit() else None,
                      float(r[3]) if r[3] not in ("", None) else None, r[4], r[5]] for r in ordered],
        }
        (OUT / f"{key}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        index[station["station_id"]] = {"key": key, "rows": len(ordered)}
        written += 1

        # The map needs to know where a station's record lives.
        station["data_key"] = key
        station["data_rows"] = len(ordered)

    LAYER.write_text(json.dumps(layer, ensure_ascii=False), encoding="utf-8")
    write_json(INDEX, {"generated_at": utc_now(), "stations": written,
                       "base_url": "/data/hydromet/stations/", "by_station": index,
                       "note": "One file per station, rows as arrays under the shared column "
                               "list. CSV is produced from the same file in the browser, so the "
                               "two formats cannot disagree."})
    return {"stations_written": written, "without_observations": missing,
            "total_rows": sum(v["rows"] for v in index.values())}


def main():
    print(json.dumps(build(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
