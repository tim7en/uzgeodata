"""Propose new ontology assertions with a model, and report how good they are.

This is the reinforcement step. The graph starts with rules; a curator reviews
what the rules produced; those reviews become labels; this script learns from the
labels and proposes the facts the rules missed; the curator reviews again. Each
cycle the labelled set grows and the proposals get better.

Backend: TF-IDF over character n-grams of the bilingual title plus the extracted
field names. Character n-grams are used on purpose - they cope with Russian
inflection and with English/Russian mixing without a language model or a network
call, and they run in under a second on 135 datasets. The graph contract does not
depend on this choice: a satellite-embedding or sentence-transformer backend can
replace `embed()` without touching anything downstream.

Two signals are combined:

  nearest-neighbour    what do the most similar *reviewed* datasets observe?
  concept similarity   how close is this dataset's text to the concept's own
                       label and definition? (works with zero labels)

Raw similarity is not a probability, so confidence is calibrated by leave-one-out
evaluation on the labelled set: a score is converted into the observed precision
of past proposals in the same score band, Laplace-smoothed. With few labels the
calibration is deliberately pessimistic, which keeps machine guesses below the
publication threshold until there is evidence they deserve to be above it.

Usage:
    python PIPELINES/ontology/propose_assertions.py                 # write proposals
    python PIPELINES/ontology/propose_assertions.py --dry-run       # report only
    python PIPELINES/ontology/propose_assertions.py --auto-publish  # publish >= threshold
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

MODEL_AGENT = "uz:agent/model-tfidf-knn-v1"
PROMOTE_THRESHOLD = 0.75
MAX_CONFIDENCE = 0.95
NEIGHBOURS = 8
KNN_WEIGHT = 0.65
MIN_SCORE = 0.18
TOP_PROPERTIES_PER_DATASET = 4
RELATED_PER_DATASET = 3


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    for attempt in range(5):  # Windows can hold a freshly written file briefly
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.15 * (attempt + 1))


def assertion_id(subject: str, predicate: str, obj) -> str:
    import hashlib

    key = f"{subject}|{predicate}|{json.dumps(obj, ensure_ascii=False, sort_keys=True)}"
    return "uz:a/" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


class Proposer:
    def __init__(self, root: Path):
        self.root = root
        self.generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        instances = root / "ONTOLOGY" / "instances"
        vocab = root / "ONTOLOGY" / "vocab"

        self.entities = {e["id"]: e for e in read_json(instances / "entities.json")["entities"]}
        self.assertions = read_json(instances / "assertions.json")["assertions"]
        self.properties = read_json(vocab / "properties.json")["concepts"]
        self.datasets = [e for e in self.entities.values() if e["type"] == "Dataset"]
        self.dataset_ids = [d["id"] for d in self.datasets]
        self.index = {ds_id: i for i, ds_id in enumerate(self.dataset_ids)}

        self.fields_by_dataset = defaultdict(list)
        distributions = defaultdict(list)
        for assertion in self.assertions:
            if assertion["predicate"] == "uz:hasDistribution":
                distributions[assertion["subject"]].append(assertion["object"])
        fields_by_dist = defaultdict(list)
        for assertion in self.assertions:
            if assertion["predicate"] == "uz:hasField":
                fields_by_dist[assertion["subject"]].append(str(assertion["value"]))
        for ds_id, dists in distributions.items():
            for dist_id in dists:
                self.fields_by_dataset[ds_id].extend(fields_by_dist.get(dist_id, []))

    # ------------------------------------------------------------------ text

    def dataset_text(self, dataset: dict) -> str:
        labels = dataset.get("labels") or {}
        parts = [dataset.get("label", ""), labels.get("ru", ""), labels.get("en", "")]
        parts.extend(self.fields_by_dataset.get(dataset["id"], [])[:24])
        return " ".join(p for p in parts if p).lower()

    @staticmethod
    def concept_text(concept: dict) -> str:
        parts = [concept["prefLabel"], *concept.get("altLabels", []), concept.get("definition", "")]
        return " ".join(parts).lower()

    def embed(self):
        """Vectorise datasets and concepts in one shared space.

        Swap this method to change backends - everything below consumes only the
        two matrices it returns.
        """
        dataset_docs = [self.dataset_text(d) for d in self.datasets]
        concept_docs = [self.concept_text(c) for c in self.properties]
        vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1
        )
        matrix = vectorizer.fit_transform(dataset_docs + concept_docs)
        return matrix[: len(dataset_docs)], matrix[len(dataset_docs):]

    # ------------------------------------------------------------------ labels

    def label_sets(self):
        """positive[ds] / negative[ds]: what we know a dataset does and does not observe.

        A fact counts as a label when a human reviewed it, or when the rules were
        confident enough to publish it. Rejections are labels too - they are the
        only way the model learns what *not* to say.
        """
        positive = defaultdict(set)
        negative = defaultdict(set)
        reviewed = 0
        for assertion in self.assertions:
            if assertion["predicate"] != "uz:observes" or "object" not in assertion:
                continue
            if assertion.get("reviewedBy"):
                reviewed += 1
            if assertion["status"] == "asserted":
                positive[assertion["subject"]].add(assertion["object"])
            elif assertion["status"] == "rejected":
                negative[assertion["subject"]].add(assertion["object"])
        return positive, negative, reviewed

    def existing_triples(self):
        return {
            (a["subject"], a["predicate"], a.get("object"))
            for a in self.assertions
            if "object" in a
        }

    # ------------------------------------------------------------------ scoring

    def score_matrix(self, dataset_vectors, concept_vectors, positive, exclude=None):
        """Blended score for every (dataset, property) pair."""
        concept_ids = [c["id"] for c in self.properties]
        zero_shot = cosine_similarity(dataset_vectors, concept_vectors)
        similarity = cosine_similarity(dataset_vectors, dataset_vectors)
        np.fill_diagonal(similarity, 0.0)

        labelled_rows = [
            self.index[ds_id] for ds_id, concepts in positive.items()
            if concepts and ds_id in self.index and ds_id != exclude
        ]
        knn = np.zeros_like(zero_shot)
        if labelled_rows:
            concept_position = {cid: i for i, cid in enumerate(concept_ids)}
            for row in range(similarity.shape[0]):
                sims = [(similarity[row, other], self.dataset_ids[other]) for other in labelled_rows
                        if other != row]
                sims.sort(reverse=True)
                top = [(s, ds) for s, ds in sims[:NEIGHBOURS] if s > 0]
                total = sum(s for s, _ in top)
                if total <= 0:
                    continue
                for weight, neighbour in top:
                    for concept_id in positive.get(neighbour, ()):
                        position = concept_position.get(concept_id)
                        if position is not None:
                            knn[row, position] += weight / total

        blend = KNN_WEIGHT * knn + (1 - KNN_WEIGHT) * (zero_shot / max(zero_shot.max(), 1e-9))
        if not labelled_rows:
            blend = zero_shot / max(zero_shot.max(), 1e-9)
        return blend, concept_ids

    # ------------------------------------------------------------------ calibration

    def calibrate(self, dataset_vectors, concept_vectors, positive, negative):
        """Leave-one-out: how often was a score in this band actually right?

        Returns bucket edges with smoothed precision, and the raw evaluation so
        the report can show its working.
        """
        labelled = [ds_id for ds_id, concepts in positive.items() if concepts and ds_id in self.index]
        buckets = defaultdict(lambda: [0, 0])  # band -> [hits, total]
        samples = []
        for ds_id in labelled:
            held_out = {k: v for k, v in positive.items() if k != ds_id}
            blend, concept_ids = self.score_matrix(
                dataset_vectors, concept_vectors, held_out, exclude=ds_id
            )
            row = blend[self.index[ds_id]]
            order = np.argsort(-row)[:TOP_PROPERTIES_PER_DATASET]
            truth = positive[ds_id]
            for position in order:
                score = float(row[position])
                if score < MIN_SCORE:
                    continue
                band = min(int(score * 10), 9)
                hit = concept_ids[position] in truth
                buckets[band][0] += int(hit)
                buckets[band][1] += 1
                samples.append({"dataset": ds_id, "concept": concept_ids[position],
                                "score": round(score, 3), "correct": bool(hit)})

        table = {}
        running = 0.0
        for band in range(10):
            hits, total = buckets.get(band, [0, 0])
            precision = (hits + 1) / (total + 2)  # Laplace: unseen bands stay modest
            running = max(running, precision)     # confidence must not fall as score rises
            table[band] = round(min(running, MAX_CONFIDENCE), 3)
        return table, samples, len(labelled)

    def confidence_for(self, score: float, table: dict) -> float:
        return float(table[min(int(score * 10), 9)])

    # ------------------------------------------------------------------ proposals

    def run(self, dry_run: bool = False, auto_publish: bool = False):
        dataset_vectors, concept_vectors = self.embed()
        positive, negative, reviewed = self.label_sets()
        table, samples, labelled_count = self.calibrate(
            dataset_vectors, concept_vectors, positive, negative
        )
        blend, concept_ids = self.score_matrix(dataset_vectors, concept_vectors, positive)
        existing = self.existing_triples()

        proposals = []
        for dataset in self.datasets:
            ds_id = dataset["id"]
            row = blend[self.index[ds_id]]
            order = np.argsort(-row)[:TOP_PROPERTIES_PER_DATASET]
            neighbours = self.top_neighbours(dataset_vectors, ds_id)
            for position in order:
                score = float(row[position])
                concept_id = concept_ids[position]
                if score < MIN_SCORE:
                    continue
                if (ds_id, "uz:observes", concept_id) in existing:
                    continue  # already stated, proposed or rejected - never re-litigate
                if concept_id in negative.get(ds_id, set()):
                    continue
                confidence = self.confidence_for(score, table)
                status = "asserted" if (auto_publish and confidence >= PROMOTE_THRESHOLD) else "proposed"
                proposals.append(
                    {
                        "id": assertion_id(ds_id, "uz:observes", concept_id),
                        "subject": ds_id,
                        "predicate": "uz:observes",
                        "object": concept_id,
                        "status": status,
                        "confidence": round(confidence, 3),
                        "assertedBy": MODEL_AGENT,
                        "method": "tfidf-knn",
                        "evidence": {
                            "source": "title+fields",
                            "score": round(score, 3),
                            "neighbours": neighbours,
                            "note": f"calibrated on {labelled_count} labelled datasets",
                        },
                        "generatedAt": self.generated_at,
                        "reviewedBy": None,
                        "reviewedAt": None,
                    }
                )

            for neighbour in neighbours[:RELATED_PER_DATASET]:
                other = neighbour["dataset"]
                if neighbour["similarity"] < 0.35:
                    continue
                if (ds_id, "uz:relatedTo", other) in existing:
                    continue
                confidence = round(min(MAX_CONFIDENCE, 0.4 + neighbour["similarity"] / 2), 3)
                proposals.append(
                    {
                        "id": assertion_id(ds_id, "uz:relatedTo", other),
                        "subject": ds_id,
                        "predicate": "uz:relatedTo",
                        "object": other,
                        "status": "asserted" if (auto_publish and confidence >= PROMOTE_THRESHOLD) else "proposed",
                        "confidence": confidence,
                        "assertedBy": MODEL_AGENT,
                        "method": "tfidf-similarity",
                        "evidence": {"source": "title+fields", "score": neighbour["similarity"],
                                     "note": "nearest neighbour in the shared text space"},
                        "generatedAt": self.generated_at,
                        "reviewedBy": None,
                        "reviewedAt": None,
                    }
                )

        report = {
            "generatedAt": self.generated_at,
            "model": MODEL_AGENT,
            "backend": "tfidf char_wb 3-5grams + knn label propagation",
            "labelledDatasets": labelled_count,
            "humanReviewedAssertions": reviewed,
            "calibration": {str(band): value for band, value in table.items()},
            "leaveOneOut": {
                "evaluated": len(samples),
                "precision": round(sum(s["correct"] for s in samples) / max(len(samples), 1), 3),
                "precisionTop1": self.top1_precision(samples),
            },
            "proposals": {
                "total": len(proposals),
                "observes": sum(1 for p in proposals if p["predicate"] == "uz:observes"),
                "relatedTo": sum(1 for p in proposals if p["predicate"] == "uz:relatedTo"),
                "aboveThreshold": sum(1 for p in proposals if p["confidence"] >= PROMOTE_THRESHOLD),
            },
            "sampleEvaluations": samples[:40],
        }

        if not dry_run:
            instances = self.root / "ONTOLOGY" / "instances"
            write_json(instances / "proposals.json",
                       {"version": "1.0", "generatedAt": self.generated_at, "assertions": proposals})
            write_json(instances / "model-report.json", report)
        return proposals, report

    def top_neighbours(self, dataset_vectors, ds_id: str):
        row = cosine_similarity(dataset_vectors[self.index[ds_id]], dataset_vectors)[0]
        row[self.index[ds_id]] = 0.0
        order = np.argsort(-row)[:NEIGHBOURS]
        return [
            {"dataset": self.dataset_ids[i], "similarity": round(float(row[i]), 3)}
            for i in order if row[i] > 0
        ][:5]

    @staticmethod
    def top1_precision(samples):
        best: dict[str, dict] = {}
        for sample in samples:
            current = best.get(sample["dataset"])
            if current is None or sample["score"] > current["score"]:
                best[sample["dataset"]] = sample
        if not best:
            return None
        return round(sum(s["correct"] for s in best.values()) / len(best), 3)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--dry-run", action="store_true", help="report without writing proposals")
    parser.add_argument(
        "--auto-publish",
        action="store_true",
        help="publish proposals whose calibrated confidence clears the threshold, "
             "instead of holding every one for review",
    )
    args = parser.parse_args(argv)

    proposer = Proposer(Path(args.root).resolve())
    proposals, report = proposer.run(dry_run=args.dry_run, auto_publish=args.auto_publish)

    print(f"model:      {report['backend']}")
    print(f"labels:     {report['labelledDatasets']} labelled datasets, "
          f"{report['humanReviewedAssertions']} human-reviewed assertions")
    loo = report["leaveOneOut"]
    print(f"leave-one-out: {loo['evaluated']} evaluations, precision {loo['precision']}, "
          f"top-1 {loo['precisionTop1']}")
    print(f"calibration by score band: {report['calibration']}")
    counts = report["proposals"]
    print(f"proposals:  {counts['total']} ({counts['observes']} observes, "
          f"{counts['relatedTo']} relatedTo), {counts['aboveThreshold']} clear the threshold")
    if args.dry_run:
        print("(dry run - nothing written)")
    else:
        print("wrote ONTOLOGY/instances/proposals.json and model-report.json")
        print("next: review them, then rebuild - python PIPELINES/ontology/build_ontology.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
