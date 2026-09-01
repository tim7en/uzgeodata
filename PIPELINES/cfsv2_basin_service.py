"""Basin environmental state from CFSv2, as three separately scoped services.

CFSv2 gives a global land-atmosphere field every six hours. On its own that is a
raster nobody can act on. What makes it usable is reducing it to a basin record,
and then saying how abnormal today's value is against that basin's own history —
"root-zone soil moisture is 0.19" tells a policymaker nothing, "1.8 standard
deviations below the September normal" tells them something.

The work splits into three services that are deliberately kept apart, because
they have different scopes, different refresh rates and different failure modes:

    observe      What the field says over each basin, per month. Pure
                 measurement, no interpretation. Re-runnable, append-only.

    climatology   The baseline: mean and standard deviation per basin, per
                 calendar month, over a stated reference period. Changes rarely
                 and deliberately — it is the thing every anomaly is measured
                 against, so it must not move under them.

    anomaly       Observations expressed as z-scores against the baseline, with
                 a classification. Derived: it holds no measurement of its own
                 and can always be rebuilt from the other two.

Two findings from the data shape the defaults, and both are worth knowing before
changing them.

The grid is 34.8 km, not the 22 km often quoted, so a pixel covers about
1,209 km². Level-12 basins average 127 km², which puts roughly nine and a half
of them inside a single pixel — a level-12 CFSv2 table would be mostly the same
number repeated. Level 7 averages 2,725 km², a little over two pixels each, and
a test reduction returned 242 distinct soil-moisture values across 263 basins.
That is the level this reads.

The record runs from 1979, but it is not homogeneous. CFSR reanalysis feeds it
to 2010 and the operational CFSv2 from 2011, and 25 cm soil moisture steps up by
1.41 standard deviations across that boundary. A baseline spanning it would make
every post-2011 reading look wet and every earlier one dry, which is precisely
the bias an anomaly service exists to avoid. The reference period therefore
starts in 2011 and stays inside the operational era.

    python PIPELINES/cfsv2_basin_service.py observe --start 2024-01 --end 2025-12
    python PIPELINES/cfsv2_basin_service.py climatology
    python PIPELINES/cfsv2_basin_service.py anomaly
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASINS = ROOT / "PUBLISHED" / "data" / "review" / "basinatlas" / "basinatlas_uz_lev07.geojson"
OUT_DIR = ROOT / "PUBLISHED" / "data" / "analysis"
MANIFEST = ROOT / "ONTOLOGY" / "instances" / "cfsv2-basin-service.json"

OBSERVATIONS = OUT_DIR / "cfsv2-basin-monthly.csv"
CLIMATOLOGY = OUT_DIR / "cfsv2-basin-climatology.csv"
ANOMALIES = OUT_DIR / "cfsv2-basin-anomaly.csv"

PROJECT = "ee-sabitovty"
ASSET = "NOAA/CFSV2/FOR6H_HARMONIZED"
BASIN_LEVEL = 7
SCALE = 35000

# The operational era. See the module docstring: 2011 is where CFSR hands over
# and where the soil-moisture step sits.
BASELINE_START = 2011
BASELINE_END = 2025

# band, output name, unit, and how a 6-hourly rate becomes something readable.
VARIABLES = [
    ("Precipitation_rate_surface_6_Hour_Average", "precipitation", "mm/day", 86400.0, 0.0),
    ("Temperature_height_above_ground", "temperature_mean", "degC", 1.0, -273.15),
    ("Maximum_temperature_height_above_ground_6_Hour_Interval", "temperature_max", "degC", 1.0, -273.15),
    ("Minimum_temperature_height_above_ground_6_Hour_Interval", "temperature_min", "degC", 1.0, -273.15),
    ("Volumetric_Soil_Moisture_Content_depth_below_surface_layer_5_cm", "soil_moisture_5cm", "m3/m3", 1.0, 0.0),
    ("Volumetric_Soil_Moisture_Content_depth_below_surface_layer_25_cm", "soil_moisture_25cm", "m3/m3", 1.0, 0.0),
    ("Volumetric_Soil_Moisture_Content_depth_below_surface_layer_70_cm", "soil_moisture_70cm", "m3/m3", 1.0, 0.0),
    ("Volumetric_Soil_Moisture_Content_depth_below_surface_layer_150_cm", "soil_moisture_150cm", "m3/m3", 1.0, 0.0),
    ("Potential_Evaporation_Rate_surface_6_Hour_Average", "potential_evaporation", "mm/day", 86400.0, 0.0),
    ("Downward_Short-Wave_Radiation_Flux_surface_6_Hour_Average", "shortwave_down", "W/m2", 1.0, 0.0),
    ("Specific_humidity_height_above_ground", "specific_humidity", "kg/kg", 1.0, 0.0),
]
BANDS = [entry[0] for entry in VARIABLES]
NAMES = {band: name for band, name, *_ in VARIABLES}
UNITS = {name: unit for _, name, unit, *_ in VARIABLES}
CONVERT = {band: (scale, offset) for band, _, _, scale, offset in VARIABLES}

# Standard anomaly bands. Deliberately symmetric: the same cut that calls a
# drought severe calls a wet spell extreme, so the vocabulary does not smuggle in
# an assumption that dry is the only interesting direction.
CLASSES = [
    (-math.inf, -2.0, "extremely dry"), (-2.0, -1.0, "dry"),
    (-1.0, 1.0, "normal"), (1.0, 2.0, "wet"), (2.0, math.inf, "extremely wet"),
]


def classify(z: float) -> str:
    for low, high, label in CLASSES:
        if low <= z < high:
            return label
    return "normal"


def initialise():
    try:
        import ee
        ee.Initialize(project=PROJECT)
        ee.Number(1).getInfo()
        return ee
    except Exception as error:
        raise SystemExit(
            f"Earth Engine unavailable: {str(error).strip()[:160]}\n"
            f"  Run: earthengine authenticate --project {PROJECT}") from error


def basin_collection(ee):
    document = json.loads(BASINS.read_text(encoding="utf8"))
    features = [ee.Feature(ee.Geometry(f["geometry"]), {"basin": int(f["properties"]["HYBAS_ID"])})
                for f in document["features"]]
    return ee.FeatureCollection(features), len(features)


def months(start: str, end: str) -> list[tuple[int, int]]:
    sy, sm = (int(part) for part in start.split("-"))
    ey, em = (int(part) for part in end.split("-"))
    out = []
    year, month = sy, sm
    while (year, month) <= (ey, em):
        out.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def existing(path: Path, keys: tuple[str, ...]) -> set:
    if not path.exists():
        return set()
    with path.open(encoding="utf8", newline="") as handle:
        return {tuple(row[key] for key in keys) for row in csv.DictReader(handle)}


# ----------------------------------------------------------------- observe

def observe(args) -> None:
    ee = initialise()
    collection, count = basin_collection(ee)
    source = ee.ImageCollection(ASSET)
    wanted = months(args.start, args.end)
    done = existing(OBSERVATIONS, ("year", "month"))
    todo = [(y, m) for y, m in wanted if (str(y), str(m)) not in done]

    print(f"observe · {count} level-{BASIN_LEVEL} basins · {len(wanted)} months requested, "
          f"{len(todo)} to measure")
    if not todo:
        print("  nothing to do")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fresh = not OBSERVATIONS.exists()
    started = time.time()
    rows = 0
    with OBSERVATIONS.open("a", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle)
        if fresh:
            writer.writerow(["basin_id", "year", "month", "variable", "value", "unit"])
        for position, (year, month) in enumerate(todo, start=1):
            start = ee.Date.fromYMD(year, month, 1)
            monthly = source.filterDate(start, start.advance(1, "month")).select(BANDS).mean()
            try:
                result = monthly.reduceRegions(
                    collection=collection, reducer=ee.Reducer.mean(), scale=SCALE).getInfo()
            except Exception as error:
                print(f"  ! {year}-{month:02d}: {str(error).strip()[:110]}", flush=True)
                continue
            for feature in result["features"]:
                properties = feature["properties"]
                basin = properties["basin"]
                for band in BANDS:
                    raw = properties.get(band)
                    if raw is None:
                        continue
                    scale, offset = CONVERT[band]
                    writer.writerow([basin, year, month, NAMES[band],
                                     round(raw * scale + offset, 5), UNITS[NAMES[band]]])
                    rows += 1
            handle.flush()
            rate = (time.time() - started) / position
            print(f"  {year}-{month:02d} · {position}/{len(todo)} · {rate:.0f}s each · "
                  f"{(len(todo) - position) * rate / 60:.0f} min left", flush=True)
    print(f"\n  {rows:,} observations written -> {OBSERVATIONS.relative_to(ROOT)}")


# ------------------------------------------------------------- climatology

def climatology(args) -> None:
    """Mean and standard deviation per basin, month and variable.

    Built from the observation table rather than from Earth Engine: the baseline
    has to be exactly the numbers the anomalies are compared against, and reading
    it back from the same file is what guarantees that.
    """
    if not OBSERVATIONS.exists():
        raise SystemExit(f"No observations yet. Run: {Path(__file__).name} observe")

    buckets: dict[tuple, list[float]] = defaultdict(list)
    with OBSERVATIONS.open(encoding="utf8", newline="") as handle:
        for row in csv.DictReader(handle):
            year = int(row["year"])
            if not args.start <= year <= args.end:
                continue
            buckets[(row["basin_id"], row["month"], row["variable"])].append(float(row["value"]))

    if not buckets:
        raise SystemExit(f"No observations inside {args.start}-{args.end}.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    thin = 0
    with CLIMATOLOGY.open("w", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["basin_id", "month", "variable", "mean", "sd", "years",
                         "baseline_start", "baseline_end"])
        for (basin, month, variable), values in sorted(buckets.items()):
            # A standard deviation from two points is not a baseline; say so by
            # leaving it empty rather than emitting a number that will divide.
            sd = statistics.pstdev(values) if len(values) >= 3 else ""
            if len(values) < 3:
                thin += 1
            writer.writerow([basin, month, variable, round(statistics.mean(values), 5),
                             round(sd, 5) if sd != "" else "", len(values),
                             args.start, args.end])
    print(f"climatology · baseline {args.start}-{args.end} · {len(buckets):,} basin-month-variable cells")
    if thin:
        print(f"  {thin:,} cells have fewer than three years and carry no standard deviation")
    print(f"  -> {CLIMATOLOGY.relative_to(ROOT)}")


# ----------------------------------------------------------------- anomaly

def anomaly(args) -> None:
    for path in (OBSERVATIONS, CLIMATOLOGY):
        if not path.exists():
            raise SystemExit(f"Missing {path.relative_to(ROOT)}; run observe and climatology first.")

    baseline = {}
    with CLIMATOLOGY.open(encoding="utf8", newline="") as handle:
        for row in csv.DictReader(handle):
            baseline[(row["basin_id"], row["month"], row["variable"])] = row

    written = skipped = 0
    with OBSERVATIONS.open(encoding="utf8", newline="") as source, \
            ANOMALIES.open("w", encoding="utf8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["basin_id", "year", "month", "variable", "value", "unit",
                         "baseline_mean", "baseline_sd", "z_score", "classification"])
        for row in csv.DictReader(source):
            key = (row["basin_id"], row["month"], row["variable"])
            stats = baseline.get(key)
            if not stats or not stats["sd"]:
                skipped += 1
                continue
            sd = float(stats["sd"])
            if sd == 0:
                # A flat baseline cannot express an anomaly; dividing would
                # manufacture an infinite one.
                skipped += 1
                continue
            z = (float(row["value"]) - float(stats["mean"])) / sd
            writer.writerow([row["basin_id"], row["year"], row["month"], row["variable"],
                             row["value"], row["unit"], stats["mean"], stats["sd"],
                             round(z, 3), classify(z)])
            written += 1

    print(f"anomaly · {written:,} z-scores written, {skipped:,} skipped for want of a usable baseline")
    print(f"  -> {ANOMALIES.relative_to(ROOT)}")

    MANIFEST.write_text(json.dumps({
        "version": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "services": {
            "observe": {"scope": "measurement", "output": str(OBSERVATIONS.relative_to(ROOT)),
                        "predicate": "uz:hasBasinStatistic"},
            "climatology": {"scope": "reference baseline",
                            "output": str(CLIMATOLOGY.relative_to(ROOT)),
                            "baseline": [BASELINE_START, BASELINE_END]},
            "anomaly": {"scope": "derived indicator", "output": str(ANOMALIES.relative_to(ROOT)),
                        "predicate": "uz:hasBasinAnomaly", "derivedFrom": ["observe", "climatology"]},
        },
        "source": {"platform": "Google Earth Engine", "asset": ASSET,
                   "gridMetres": SCALE, "cadence": "6-hourly, aggregated to monthly means"},
        "basinLevel": BASIN_LEVEL,
        "variables": [{"name": name, "unit": unit, "band": band}
                      for band, name, unit, *_ in VARIABLES],
        "classification": [{"from": None if low == -math.inf else low,
                            "to": None if high == math.inf else high, "label": label}
                           for low, high, label in CLASSES],
        "caveats": [
            f"The grid is {SCALE / 1000:.1f} km, so a pixel covers about "
            f"{(SCALE / 1000) ** 2:,.0f} km². Level-12 basins average 127 km² and roughly nine "
            "and a half of them share one pixel, which is why this reads level 7.",
            "The record starts in 1979 but is not homogeneous: CFSR feeds it to 2010 and "
            "operational CFSv2 from 2011, and 25 cm soil moisture steps up by 1.41 standard "
            "deviations across that boundary. The baseline stays inside the operational era.",
            "This is the 6-hourly analysis product, not a seasonal forecast. It describes the "
            "state that has happened, and nothing about the state to come.",
        ],
    }, ensure_ascii=False, indent=2), encoding="utf8")
    print(f"  -> {MANIFEST.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="service", required=True)

    p = sub.add_parser("observe", help="Measure basin monthly means from CFSv2.")
    p.add_argument("--start", default=f"{BASELINE_START}-01", help="First month, YYYY-MM.")
    p.add_argument("--end", default=f"{BASELINE_END}-12", help="Last month, YYYY-MM.")
    p.set_defaults(run=observe)

    p = sub.add_parser("climatology", help="Build the reference baseline.")
    p.add_argument("--start", type=int, default=BASELINE_START)
    p.add_argument("--end", type=int, default=BASELINE_END)
    p.set_defaults(run=climatology)

    p = sub.add_parser("anomaly", help="Express observations as z-scores.")
    p.set_defaults(run=anomaly)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
