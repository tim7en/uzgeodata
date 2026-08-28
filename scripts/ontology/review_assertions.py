"""Review pending assertions. Curator decisions are recorded as training labels.

Accepting a proposal publishes it and marks it reviewed. Rejecting one keeps it
in the graph with status 'rejected' - a negative label the next model run reads,
so a wrong guess is never made twice.

Decisions are written to ontology/instances/curated-assertions.json, which the
build merges back on top of anything it regenerates. Rules and models can be
re-run freely without ever overwriting a human.

Usage:
    python scripts/ontology/review_assertions.py --list --limit 20
    python scripts/ontology/review_assertions.py --list --predicate uz:observes --min-confidence 0.7
    python scripts/ontology/review_assertions.py --accept uz:a/1a2b... uz:a/3c4d...
    python scripts/ontology/review_assertions.py --reject uz:a/5e6f... --note "regional, not national"
    python scripts/ontology/review_assertions.py --accept-above 0.8 --predicate uz:observes
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

CURATOR = "uz:agent/curator"


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


def load_pool(root: Path):
    instances = root / "ontology" / "instances"
    pool: dict[str, dict] = {}
    for name in ("assertions.json", "proposals.json", "curated-assertions.json"):
        for record in (read_json(instances / name, {"assertions": []}) or {}).get("assertions", []):
            pool[record["id"]] = record
    labels = {}
    entities = read_json(instances / "entities.json", {"entities": []})["entities"]
    for entity in entities:
        labels[entity["id"]] = entity.get("label", entity["id"])
    for name in ("properties.json", "themes.json", "analysis.json", "usecases.json", "places.json"):
        payload = read_json(root / "ontology" / "vocab" / name)
        for concept in (payload or {}).get("concepts", []):
            labels[concept["id"]] = concept["prefLabel"]
    return pool, labels


def record_decision(root: Path, records: list[dict], status: str, reviewer: str, note: str | None):
    instances = root / "ontology" / "instances"
    path = instances / "curated-assertions.json"
    document = read_json(path, {"version": "1.0", "assertions": []})
    existing = {record["id"]: record for record in document["assertions"]}
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    for record in records:
        decided = dict(record)
        decided["status"] = status
        decided["reviewedBy"] = reviewer
        decided["reviewedAt"] = stamp
        if status == "asserted":
            # A reviewed fact is certain by definition; the model's score is kept
            # in evidence so calibration can still be measured against it.
            evidence = dict(decided.get("evidence") or {})
            if "score" in evidence:
                evidence["modelScore"] = evidence["score"]
            if note:
                evidence["note"] = note
            decided["evidence"] = evidence or None
            decided["confidence"] = 1.0
        elif note:
            evidence = dict(decided.get("evidence") or {})
            evidence["note"] = note
            decided["evidence"] = evidence
        if decided.get("evidence") is None:
            decided.pop("evidence", None)
        existing[decided["id"]] = decided

    document["assertions"] = sorted(existing.values(), key=lambda r: (r["subject"], r["predicate"]))
    document["version"] = "1.0"
    write_json(path, document)
    return len(records)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--list", action="store_true", help="show pending proposals")
    parser.add_argument("--accept", nargs="+", metavar="ID")
    parser.add_argument("--reject", nargs="+", metavar="ID")
    parser.add_argument("--accept-above", type=float, metavar="CONFIDENCE",
                        help="accept every pending proposal at or above this confidence")
    parser.add_argument("--predicate", help="restrict listing or bulk accept to one predicate")
    parser.add_argument("--min-confidence", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--reviewer", default=CURATOR)
    parser.add_argument("--note", help="reason, stored with the decision")
    parser.add_argument(
        "--assert-fact", nargs=3, metavar=("SUBJECT", "PREDICATE", "OBJECT"),
        help="state a fact the rules and the model both missed; it enters as a reviewed "
             "curator assertion and becomes a training label like any other",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    pool, labels = load_pool(root)
    pending = [r for r in pool.values() if r["status"] == "proposed"]

    if args.assert_fact:
        subject, predicate, obj = args.assert_fact
        if subject not in labels:
            print(f"unknown subject {subject}", file=sys.stderr)
            return 1
        if obj not in labels:
            print(f"unknown object {obj}", file=sys.stderr)
            return 1
        import hashlib

        key = f"{subject}|{predicate}|{json.dumps(obj, ensure_ascii=False, sort_keys=True)}"
        record = {
            "id": "uz:a/" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16],
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "status": "proposed",
            "confidence": 1.0,
            "assertedBy": CURATOR,
            "method": "curator",
            "evidence": {"source": "curator", "note": args.note or "stated by a curator"},
            "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "reviewedBy": None,
            "reviewedAt": None,
        }
        record_decision(root, [record], "asserted", args.reviewer, args.note)
        print(f"asserted {labels[subject]} {predicate.split(':')[-1]} {labels[obj]}")
        print("rebuild to apply: python scripts/ontology/build_ontology.py")
        return 0

    if args.accept or args.reject:
        chosen = [pool[i] for i in (args.accept or []) if i in pool]
        missing = [i for i in (args.accept or []) if i not in pool]
        rejected = [pool[i] for i in (args.reject or []) if i in pool]
        missing += [i for i in (args.reject or []) if i not in pool]
        if missing:
            print(f"unknown assertion IDs: {', '.join(missing)}", file=sys.stderr)
            return 1
        if chosen:
            record_decision(root, chosen, "asserted", args.reviewer, args.note)
            print(f"accepted {len(chosen)}")
        if rejected:
            record_decision(root, rejected, "rejected", args.reviewer, args.note)
            print(f"rejected {len(rejected)}")
        print("rebuild to apply: python scripts/ontology/build_ontology.py")
        return 0

    if args.accept_above is not None:
        batch = [r for r in pending if r["confidence"] >= args.accept_above
                 and (not args.predicate or r["predicate"] == args.predicate)]
        if not batch:
            print("nothing pending at that confidence")
            return 0
        record_decision(root, batch, "asserted", args.reviewer, args.note)
        print(f"accepted {len(batch)} proposals at or above {args.accept_above}")
        print("rebuild to apply: python scripts/ontology/build_ontology.py")
        return 0

    shown = [r for r in pending
             if r["confidence"] >= args.min_confidence
             and (not args.predicate or r["predicate"] == args.predicate)]
    shown.sort(key=lambda r: -r["confidence"])
    print(f"{len(pending)} pending, showing {min(len(shown), args.limit)}\n")
    for record in shown[: args.limit]:
        subject = labels.get(record["subject"], record["subject"])
        target = labels.get(record.get("object"), record.get("object", record.get("value")))
        evidence = record.get("evidence") or {}
        terms = evidence.get("matchedTerms") or []
        detail = f"terms={','.join(terms[:3])}" if terms else f"score={evidence.get('score')}"
        print(f"{record['confidence']:.2f}  {record['id']}")
        print(f"      {subject}")
        print(f"      {record['predicate'].split(':')[-1]} -> {target}")
        print(f"      by {record['assertedBy'].split('/')[-1]}, {detail}")
    if not shown:
        print("nothing pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
