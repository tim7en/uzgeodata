"""Can a parcel's shape tell you what it is used for?

Trains a gradient-boosted classifier on the 198,615 labelled polygons in the
cadastre training set, using only geometry - size, elongation, compactness,
convexity, vertex count and location. No imagery is involved, which is the point:
it establishes what a shape-only baseline achieves before anyone spends money on
satellite features.

The result that matters is not the headline accuracy. It is the gap between two
validation schemes:

    random split    polygons from the same neighbourhood land in train and test,
                    so the model can memorise localities and the score flatters it
    spatial split   whole 0.5-degree blocks are held out, so the model has to
                    generalise to ground it has never seen

Geospatial models are routinely reported with the first number. The second is the
one that predicts how the model behaves on a new district.

Usage:
    python scripts/analysis/landuse_shape_model.py
    python scripts/analysis/landuse_shape_model.py --sample 50000   # quick pass
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

MIN_CLASS_SAMPLES = 100
BLOCK_DEGREES = 0.5
FOLDS = 5
RANDOM_STATE = 42


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


def source_path(root: Path) -> Path | None:
    """Find the training shapefile through the ontology, not a hard-coded path."""
    entities = json.loads((root / "ontology" / "instances" / "entities.json").read_text(encoding="utf-8"))
    assertions = json.loads((root / "ontology" / "instances" / "assertions.json").read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in entities["entities"]}
    for assertion in assertions["assertions"]:
        if (assertion["subject"] == "uz:ds/landcover-training-samples"
                and assertion["predicate"] == "uz:hasDistribution"):
            entity = by_id.get(assertion["object"], {})
            path = entity.get("externalPath")
            if path and path.lower().endswith(".shp"):
                return Path(path)
    return None


def build_features(path: Path, sample: int | None):
    """Geometry in, feature matrix out.

    Areas and lengths are measured in an equal-area projection; degrees would make
    a hectare in Termez differ from a hectare in Nukus.
    """
    import geopandas as gpd

    frame = gpd.read_file(path, engine="pyogrio")
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty]
    if sample and len(frame) > sample:
        frame = frame.sample(sample, random_state=RANDOM_STATE)

    metric = frame.to_crs("EPSG:6933")  # World Cylindrical Equal Area
    geometry = metric.geometry

    # Centroids are taken in the projected CRS and converted back: a centroid of
    # latitudes and longitudes is not a centroid of the shape.
    centroids = metric.geometry.centroid.to_crs("EPSG:4326")
    lon = centroids.x.to_numpy()
    lat = centroids.y.to_numpy()
    area = geometry.area.to_numpy()
    perimeter = geometry.length.to_numpy()
    hull_area = geometry.convex_hull.area.to_numpy()
    bounds = geometry.bounds.to_numpy()
    width = np.maximum(bounds[:, 2] - bounds[:, 0], 1e-6)
    height = np.maximum(bounds[:, 3] - bounds[:, 1], 1e-6)
    vertices = np.array([
        len(g.exterior.coords) if g.geom_type == "Polygon"
        else sum(len(part.exterior.coords) for part in g.geoms)
        for g in geometry
    ], dtype=float)
    parts = np.array([1 if g.geom_type == "Polygon" else len(g.geoms) for g in geometry], dtype=float)

    area = np.maximum(area, 1e-6)
    perimeter = np.maximum(perimeter, 1e-6)

    features = np.column_stack([
        np.log10(area),                                  # size
        np.log10(perimeter),
        4 * np.pi * area / perimeter ** 2,               # compactness, 1 = circle
        area / np.maximum(hull_area, 1e-6),              # convexity
        area / (width * height),                         # rectangularity
        np.maximum(width, height) / np.minimum(width, height),  # elongation
        np.log10(np.maximum(vertices, 1)),               # outline complexity
        parts,
        lon,
        lat,
    ])
    names = ["log_area", "log_perimeter", "compactness", "convexity", "rectangularity",
             "elongation", "log_vertices", "parts", "centroid_lon", "centroid_lat"]
    labels = frame["class"].astype(str).to_numpy()
    return features, labels, names, lon, lat


def evaluate(features, labels, groups, scheme: str):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import GroupKFold, StratifiedKFold

    predictions = np.empty(len(labels), dtype=object)
    if scheme == "spatial":
        splitter = GroupKFold(n_splits=FOLDS).split(features, labels, groups)
    else:
        splitter = StratifiedKFold(n_splits=FOLDS, shuffle=True,
                                   random_state=RANDOM_STATE).split(features, labels)

    for train_index, test_index in splitter:
        model = HistGradientBoostingClassifier(
            max_iter=150, learning_rate=0.12, max_depth=None, random_state=RANDOM_STATE
        )
        model.fit(features[train_index], labels[train_index])
        predictions[test_index] = model.predict(features[test_index])

    predictions = predictions.astype(str)
    return {
        "scheme": scheme,
        "accuracy": round(float(accuracy_score(labels, predictions)), 4),
        "macroF1": round(float(f1_score(labels, predictions, average="macro")), 4),
        "weightedF1": round(float(f1_score(labels, predictions, average="weighted")), 4),
    }, predictions


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--sample", type=int, help="train on a random subset, for a quick pass")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    path = source_path(root)
    if path is None or not path.exists():
        print("training shapefile is not reachable; is the delivery folder attached?",
              file=sys.stderr)
        return 1

    started = time.time()
    print(f"reading {path.name} ...")
    features, labels, names, lon, lat = build_features(path, args.sample)

    values, counts = np.unique(labels, return_counts=True)
    keep = {value for value, count in zip(values, counts) if count >= MIN_CLASS_SAMPLES}
    dropped = {str(value): int(count) for value, count in zip(values, counts) if value not in keep}
    mask = np.isin(labels, list(keep))
    features, labels, lon, lat = features[mask], labels[mask], lon[mask], lat[mask]

    blocks = np.array([f"{int(x / BLOCK_DEGREES)}_{int(y / BLOCK_DEGREES)}"
                       for x, y in zip(lon, lat)])
    print(f"{len(labels):,} polygons, {len(keep)} classes, "
          f"{len(set(blocks))} spatial blocks; dropped {dropped or 'nothing'}")

    print("random-split cross-validation ...")
    random_scores, _ = evaluate(features, labels, blocks, "random")
    print(f"  accuracy {random_scores['accuracy']:.3f}  macro-F1 {random_scores['macroF1']:.3f}")

    print("spatial-block cross-validation ...")
    spatial_scores, spatial_predictions = evaluate(features, labels, blocks, "spatial")
    print(f"  accuracy {spatial_scores['accuracy']:.3f}  macro-F1 {spatial_scores['macroF1']:.3f}")

    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.model_selection import GroupShuffleSplit

    train_index, test_index = next(
        GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RANDOM_STATE)
        .split(features, labels, blocks)
    )
    final = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.12,
                                           random_state=RANDOM_STATE)
    final.fit(features[train_index], labels[train_index])

    subset = np.random.default_rng(RANDOM_STATE).choice(
        test_index, size=min(8000, len(test_index)), replace=False
    )
    print("permutation importance ...")
    importance = permutation_importance(final, features[subset], labels[subset],
                                        n_repeats=3, random_state=RANDOM_STATE, n_jobs=1)

    classes = sorted(set(labels))
    report = classification_report(labels, spatial_predictions, output_dict=True, zero_division=0)
    matrix = confusion_matrix(labels, spatial_predictions, labels=classes)

    # Where does the model work? Accuracy per spatial block, for the map.
    correct = spatial_predictions == labels
    block_scores = {}
    for block, hit, x, y in zip(blocks, correct, lon, lat):
        entry = block_scores.setdefault(block, {"n": 0, "hits": 0, "lon": 0.0, "lat": 0.0})
        entry["n"] += 1
        entry["hits"] += int(hit)
        entry["lon"] += x
        entry["lat"] += y

    grid = []
    for block, entry in block_scores.items():
        if entry["n"] < 50:
            continue
        grid.append({
            "block": block,
            "samples": entry["n"],
            "accuracy": round(entry["hits"] / entry["n"], 3),
            "lon": round(entry["lon"] / entry["n"], 4),
            "lat": round(entry["lat"] / entry["n"], 4),
        })
    grid.sort(key=lambda item: -item["samples"])

    result = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": {
            "dataset": "uz:ds/landcover-training-samples",
            "file": path.name,
            "polygonsUsed": int(len(labels)),
            "classesUsed": classes,
            "classesDropped": dropped,
            "droppedRule": f"fewer than {MIN_CLASS_SAMPLES} samples",
        },
        "model": {
            "estimator": "HistGradientBoostingClassifier",
            "maxIter": 150,
            "features": names,
            "featureNote": "geometry and location only; no imagery, no attributes",
        },
        "validation": {
            "random": random_scores,
            "spatial": spatial_scores,
            "blockDegrees": BLOCK_DEGREES,
            "blocks": len(set(blocks)),
            "optimismGap": round(random_scores["accuracy"] - spatial_scores["accuracy"], 4),
            "note": "The gap is how much a random split would have overstated field performance.",
        },
        "perClass": {
            name: {"f1": round(report[name]["f1-score"], 3),
                   "precision": round(report[name]["precision"], 3),
                   "recall": round(report[name]["recall"], 3),
                   "support": int(report[name]["support"])}
            for name in classes if name in report
        },
        "confusionMatrix": {"labels": classes, "counts": matrix.tolist()},
        "featureImportance": sorted(
            [{"feature": name, "importance": round(float(value), 4)}
             for name, value in zip(names, importance.importances_mean)],
            key=lambda item: -item["importance"],
        ),
        "spatialAccuracyGrid": grid[:200],
        "runtimeSeconds": round(time.time() - started, 1),
    }

    target = root / "public" / "data" / "analysis" / "landuse-shape-model.json"
    write_json(target, result)
    print(f"\noptimism gap {result['validation']['optimismGap']:.3f} "
          f"({random_scores['accuracy']:.3f} random vs {spatial_scores['accuracy']:.3f} spatial)")
    print("top features: " + ", ".join(
        f"{item['feature']} {item['importance']:.3f}" for item in result["featureImportance"][:4]))
    print(f"wrote {target} in {result['runtimeSeconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
