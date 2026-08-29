"""Seismicity analysis over the published earthquake catalogue.

Produces the numbers behind the portal's seismicity case study: catalogue
completeness, the Gutenberg-Richter recurrence law, depth structure, spatial
clusters and the largest events on record.

Two things are deliberate. First, the magnitude of completeness is estimated
before the b-value, because fitting a recurrence law through the incomplete tail
of a catalogue is the standard way to get a wrong answer. Second, the share of
events outside Uzbekistan is reported up front: this catalogue is regional, so
any national rate computed from it is an overstatement.

Usage:
    python scripts/analysis/seismicity.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

UZ_BBOX = (55.99, 37.17, 73.16, 45.60)
BIN = 0.1  # magnitude bin width of the source catalogue


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    for attempt in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.15 * (attempt + 1))


def load_events(path: Path):
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    events = []
    for feature in data["features"]:
        properties = feature["properties"]
        longitude, latitude = feature["geometry"]["coordinates"][:2]
        magnitude = properties.get("magnitude")
        if magnitude is None:
            continue
        stamp = str(properties.get("date") or "")
        year = int(stamp[:4]) if stamp[:4].isdigit() else None
        events.append({
            "lon": float(longitude),
            "lat": float(latitude),
            "mag": float(magnitude),
            "depth": float(properties.get("depth_km") or 0.0),
            "year": year,
            "place": properties.get("place") or "",
            "date": stamp[:10],
        })
    return events


def completeness_magnitude(magnitudes: np.ndarray) -> float:
    """Maximum-curvature estimate: the bin where the frequency count peaks.

    Simple, transparent and the standard first pass. It tends to run slightly
    low, so the conventional +0.2 correction is applied.
    """
    bins = np.round(magnitudes / BIN) * BIN
    counts = Counter(np.round(bins, 1))
    if not counts:
        return float("nan")
    peak = max(counts.items(), key=lambda item: item[1])[0]
    return round(float(peak) + 0.2, 2)


def b_value(magnitudes: np.ndarray, mc: float):
    """Aki-Utsu maximum likelihood b-value with its standard error."""
    sample = magnitudes[magnitudes >= mc - BIN / 2]
    if sample.size < 50:
        return None
    mean = float(sample.mean())
    denominator = mean - (mc - BIN / 2)
    if denominator <= 0:
        return None
    b = 1.0 / (math.log(10) * denominator)
    # Shi & Bolt (1982) uncertainty
    variance = float(((sample - mean) ** 2).sum()) / (sample.size * (sample.size - 1))
    error = 2.30 * b * b * math.sqrt(variance)
    a = math.log10(sample.size) + b * mc
    return {
        "b": round(b, 3),
        "bStdError": round(error, 3),
        "a": round(a, 3),
        "eventsUsed": int(sample.size),
        "mc": mc,
    }


def recurrence_curve(magnitudes: np.ndarray):
    """Observed cumulative counts per magnitude, for the log-linear plot."""
    edges = np.arange(2.0, float(magnitudes.max()) + 0.3, 0.2)
    return [
        {"magnitude": round(float(edge), 1),
         "cumulativeCount": int((magnitudes >= edge - 1e-9).sum())}
        for edge in edges
        if (magnitudes >= edge - 1e-9).sum() > 0
    ]


def cluster(events, eps_km: float = 30.0, min_samples: int = 40):
    """Spatial clusters with DBSCAN on the sphere.

    Haversine on radians is used rather than treating degrees as a plane: at 41
    degrees north a degree of longitude is a quarter shorter than a degree of
    latitude, and a planar clustering smears clusters east-west.
    """
    from sklearn.cluster import DBSCAN

    coords = np.radians(np.array([[event["lat"], event["lon"]] for event in events]))
    labels = DBSCAN(
        eps=eps_km / 6371.0, min_samples=min_samples, metric="haversine", algorithm="ball_tree"
    ).fit_predict(coords)

    clusters = []
    for label in sorted(set(labels) - {-1}):
        members = [event for event, tag in zip(events, labels) if tag == label]
        magnitudes = np.array([m["mag"] for m in members])
        clusters.append({
            "id": int(label),
            "events": len(members),
            "lon": round(float(np.mean([m["lon"] for m in members])), 4),
            "lat": round(float(np.mean([m["lat"] for m in members])), 4),
            "maxMagnitude": round(float(magnitudes.max()), 1),
            "medianDepthKm": round(float(np.median([m["depth"] for m in members])), 1),
            "centroidInUzBbox": bool(
                UZ_BBOX[0] <= np.mean([m["lon"] for m in members]) <= UZ_BBOX[2]
                and UZ_BBOX[1] <= np.mean([m["lat"] for m in members]) <= UZ_BBOX[3]
            ),
            "topPlace": Counter(m["place"].split(", ")[-1] for m in members).most_common(1)[0][0],
        })
    clusters.sort(key=lambda item: -item["events"])
    return clusters, int((labels == -1).sum())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    events = load_events(root / "public" / "data" / "earthquakes.geojson")
    magnitudes = np.array([event["mag"] for event in events])
    depths = np.array([event["depth"] for event in events])
    years = [event["year"] for event in events if event["year"]]

    inside = [
        event for event in events
        if UZ_BBOX[0] <= event["lon"] <= UZ_BBOX[2] and UZ_BBOX[1] <= event["lat"] <= UZ_BBOX[3]
    ]
    mc = completeness_magnitude(magnitudes)
    gutenberg = b_value(magnitudes, mc)
    clusters, noise = cluster(events)

    by_year = Counter(years)
    span = (min(years), max(years))
    complete = magnitudes[magnitudes >= mc]

    result = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": {
            "dataset": "uz:ds/a205-earthquakes-19902024",
            "file": "/data/earthquakes.geojson",
            "events": len(events),
            "period": {"start": span[0], "end": span[1]},
        },
        "coverage": {
            "insideUzbekistanBbox": len(inside),
            "outsideShare": round(1 - len(inside) / len(events), 3),
            "note": "The catalogue is regional. Rates computed over all events describe "
                    "Uzbekistan and its neighbours, not Uzbekistan alone.",
        },
        "completeness": {
            "magnitudeOfCompleteness": mc,
            "method": "maximum curvature + 0.2",
            "eventsAboveMc": int(complete.size),
            "shareAboveMc": round(float(complete.size) / len(events), 3),
        },
        "recurrence": gutenberg,
        "recurrenceCurve": recurrence_curve(magnitudes),
        "magnitudeHistogram": [
            {"magnitude": round(float(edge), 1),
             "count": int(((magnitudes >= edge) & (magnitudes < edge + 0.5)).sum())}
            for edge in np.arange(2.0, float(magnitudes.max()) + 0.5, 0.5)
        ],
        "depth": {
            "medianKm": round(float(np.median(depths)), 1),
            "shallowShareUnder20km": round(float((depths < 20).mean()), 3),
            "histogram": [
                {"depthKm": int(edge),
                 "count": int(((depths >= edge) & (depths < edge + 10)).sum())}
                for edge in range(0, 130, 10)
            ],
        },
        "annual": [
            {"year": year, "events": by_year.get(year, 0),
             "eventsAboveMc": sum(1 for e in events if e["year"] == year and e["mag"] >= mc)}
            for year in range(span[0], span[1] + 1)
        ],
        "clusters": clusters[:12],
        "unclusteredEvents": noise,
        "largestEvents": [
            {"date": event["date"], "magnitude": event["mag"], "depthKm": event["depth"],
             "place": event["place"], "lon": event["lon"], "lat": event["lat"]}
            for event in sorted(events, key=lambda e: -e["mag"])[:10]
        ],
    }

    target = root / "public" / "data" / "analysis" / "seismicity.json"
    write_json(target, result)

    features = [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
         "properties": {k: v for k, v in c.items() if k not in {"lon", "lat"}}}
        for c in clusters[:12]
    ]
    write_json(root / "public" / "data" / "analysis" / "seismicity-clusters.geojson",
               {"type": "FeatureCollection", "features": features})

    rate = gutenberg and 10 ** (gutenberg["a"] - gutenberg["b"] * 5.0) / (span[1] - span[0] + 1)
    print(f"events            {len(events):,} ({span[0]}-{span[1]})")
    print(f"outside Uzbekistan {result['coverage']['outsideShare']:.0%}")
    print(f"Mc                {mc}")
    if gutenberg:
        print(f"b-value           {gutenberg['b']} +/- {gutenberg['bStdError']} "
              f"(a={gutenberg['a']}, n={gutenberg['eventsUsed']:,})")
        print(f"implied M>=5 rate {rate:.2f} events/year across the catalogue area")
    print(f"clusters          {len(clusters)} ({noise:,} events unclustered)")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
