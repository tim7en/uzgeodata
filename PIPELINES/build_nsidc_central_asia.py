"""Ingest NSIDC G02174 Central Asia station records for the two river systems.

python PIPELINES/build_nsidc_central_asia.py

Williams and Konovalov's compilation covers the Northern Tien Shan and the Pamir,
which is where the water in the Amu Darya and the Syr Darya comes from and where our
own station archive is thinnest. The national delivery placed four sites above
1500 m; this one places dozens, and it carries its own coordinates and elevation, so
none of it depends on the name crosswalk.

Two things about it matter for how the records may be used.

Its precipitation has already been corrected for gauge type and for wetting losses,
but explicitly not for wind. Wind is the largest of the three for snow, so these
totals still understate winter precipitation at exposed mountain sites, and they
understate it by more than the national records do in the other direction, because
those carry no correction at all. Comparing a product against both is therefore
comparing it against two different definitions of precipitation, and that difference
belongs in the reading of any bias computed from them.

Its records end in 2003. It extends the network upward and backward, not forward.
"""
from __future__ import annotations
import collections
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core.runtime import sha256, utc_now, write_json

DELIVERY = ROOT / "storage/nsidc_g02174"
SYSTEMS = ROOT / "PUBLISHED/data/hydroclimate/basin-systems.geojson"
STATIONS = ROOT / "PUBLISHED/data/hydromet/nsidc-central-asia-stations.csv"
MONTHLY = ROOT / "PUBLISHED/data/hydromet/nsidc-central-asia-monthly.csv"
SUMMARY = ROOT / "PUBLISHED/data/hydromet/nsidc-central-asia.manifest.json"

MONTH_COLUMNS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")
# The user guide states missing data are indicated by -999.0. Read as a number it
# would land in every mean and every bias as though it were a measurement.
MISSING = -999.0
# Physically implausible readings, kept out of the analysis but counted, not silently
# dropped: the delivery holds one air temperature of 74 C where the next is 34.8.
PLAUSIBLE = {"air_temperature_mean": (-60.0, 50.0), "precipitation_total": (0.0, 2000.0)}
FILES = {
    "precipitation_total": ("Precip_v1_1.txt", "mm", "corrected for gauge type and wetting, not for wind"),
    "air_temperature_mean": ("Taver_v1_1.txt", "degrees Celsius", "monthly mean of daily means"),
}
COUNTRIES = {"211": "Kazakhstan", "213": "Kyrgyzstan", "227": "Tajikistan",
             "229": "Turkmenistan", "231": "Uzbekistan"}


def rings():
    """Outer rings of the two river systems, for a point-in-polygon test."""
    features = json.loads(SYSTEMS.read_text(encoding="utf-8"))["features"]
    out = []
    for feature in features:
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        for polygon in polygons:
            out.append((feature["properties"]["system_id"], polygon[0],
                        [hole for hole in polygon[1:]]))
    return out


def inside(ring, longitude, latitude):
    """Ray casting against one ring."""
    hit = False
    count = len(ring)
    for index in range(count):
        x1, y1 = ring[index][0], ring[index][1]
        x2, y2 = ring[(index + 1) % count][0], ring[(index + 1) % count][1]
        if (y1 > latitude) != (y2 > latitude):
            crossing = x1 + (latitude - y1) * (x2 - x1) / (y2 - y1)
            if crossing > longitude:
                hit = not hit
    return hit


def system_of(polygons, longitude, latitude):
    for system, outer, holes in polygons:
        if inside(outer, longitude, latitude) and not any(inside(h, longitude, latitude) for h in holes):
            return system
    return None


def read_delivery(path):
    with Path(path).open(encoding="utf-8", errors="replace", newline="") as stream:
        yield from csv.DictReader(stream, delimiter="\t")


def parse():
    polygons = rings()
    stations, observations = {}, []
    skipped, rejected = collections.Counter(), []
    for variable, (name, unit, note) in FILES.items():
        path = DELIVERY / name
        if not path.exists():
            raise FileNotFoundError(f"{path} is not in the delivery")
        for row in read_delivery(path):
            try:
                longitude, latitude = float(row["Long"]), float(row["Lat"])
                altitude, year = float(row["Alt"]), int(row["Years"])
            except (TypeError, ValueError, KeyError):
                continue
            code = (row.get("Code_WMO") or row.get("Code") or "").strip()
            station = f"uz:station/nsidc-{code or row['Name'].strip().lower()}"
            system = system_of(polygons, longitude, latitude)
            stations.setdefault(station, {
                "station_id": station, "name": row["Name"].strip(), "wmo_code": code,
                "country": COUNTRIES.get(row["Country"].strip(), row["Country"].strip()),
                "longitude": longitude, "latitude": latitude, "elevation_m": altitude,
                "system_id": system or "", "in_domain": bool(system)})
            for index, column in enumerate(MONTH_COLUMNS, start=1):
                raw = (row.get(column) or "").strip()
                if not raw:
                    continue
                try:
                    value = float(raw)
                except ValueError:
                    continue
                if value == MISSING:
                    skipped["missing_sentinel"] += 1
                    continue
                low, high = PLAUSIBLE[variable]
                if not low <= value <= high:
                    skipped["outside_plausible_range"] += 1
                    rejected.append({"station_id": station, "variable": variable, "year": year,
                                     "month": index, "value": value})
                    continue
                observations.append({
                    "station_id": station, "variable": variable, "year": year, "month": index,
                    "value": value, "unit": unit, "treatment": note,
                    "source_file": name})
    return stations, observations, skipped, rejected


def build():
    stations, observations, skipped, rejected = parse()
    inside_domain = {s for s, row in stations.items() if row["in_domain"]}
    kept = [row for row in observations if row["station_id"] in inside_domain]

    STATIONS.parent.mkdir(parents=True, exist_ok=True)
    with STATIONS.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(next(iter(stations.values()))))
        writer.writeheader()
        writer.writerows(sorted(stations.values(), key=lambda r: r["station_id"]))
    with MONTHLY.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(kept[0]))
        writer.writeheader()
        writer.writerows(kept)

    bands = {}
    for row in stations.values():
        if not row["in_domain"]:
            continue
        for low, high in ((0, 500), (500, 1000), (1000, 1500), (1500, 2500), (2500, 5000)):
            if low <= row["elevation_m"] < high:
                bands[f"{low}-{high} m"] = bands.get(f"{low}-{high} m", 0) + 1
    years = [row["year"] for row in kept]
    summary = {
        "generated_at": utc_now(),
        "dataset": "NSIDC G02174 Central Asia Temperature and Precipitation Data, 1879-2003, v1",
        "citation": "Williams, M. W. and V. G. Konovalov. 2008. NSIDC. doi:10.7265/N5NK3BZ8",
        "endpoint": "https://noaadata.apps.nsidc.org/NOAA/G02174/",
        "files": {name: {"sha256": sha256(DELIVERY / name), "bytes": (DELIVERY / name).stat().st_size}
                  for name, *_ in ((v[0],) for v in FILES.values())},
        "stations_in_delivery": len(stations),
        "stations_in_domain": len(inside_domain),
        "observations_in_domain": len(kept),
        "years": [min(years), max(years)],
        "elevation_bands_in_domain": dict(sorted(bands.items())),
        "by_variable": {v: sum(1 for r in kept if r["variable"] == v) for v in FILES},
        "excluded": dict(skipped),
        "rejected_as_implausible": rejected,
        "precipitation_treatment": FILES["precipitation_total"][2],
        "meaning": "Precipitation here is corrected for gauge type and wetting but not for "
                   "wind, and the national archive is not corrected at all. A bias computed "
                   "against one is not comparable with a bias computed against the other "
                   "without saying which definition of precipitation was used.",
    }
    write_json(SUMMARY, summary)
    return summary


def main():
    print(json.dumps(build(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
