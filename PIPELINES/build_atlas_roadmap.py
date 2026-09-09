"""Publish the atlas specifications and curated updates; never generate observations."""
from __future__ import annotations
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def assemble(root=ROOT):
    base = root / "ATLAS_MODULES"
    roadmap = read(base / "roadmap.json")
    updates = read(base / "updates.json")["updates"]
    phase_ids = {p["id"] for p in roadmap["phases"]}
    assert len(phase_ids) == len(roadmap["phases"]), "Duplicate phases"
    seen = set()
    for phase in roadmap["phases"]:
        assert set(phase["depends_on"]) <= seen, "Dependencies must precede phase"
        assert phase["status"] in {"planned", "in_progress", "blocked", "complete"}
        assert phase["status"] == "planned" or phase["evidence"], "Status needs evidence"
        seen.add(phase["id"])
    assert len({u["id"] for u in updates}) == len(updates), "Duplicate update IDs"
    for update in updates:
        assert update["phase"] in phase_ids and update["source"]
    modules = []
    attributes = []
    functions = []
    for manifest in sorted(base.glob("*/module.json")):
        module = read(manifest)
        assert module["scientific_reproduction_required"] is True
        library = read(manifest.parent / module["recipes"])
        source_ids = {s["id"] for s in read(manifest.parent / module["sources"])["sources"]}
        fn_ids = {f["id"] for f in library["functions"]}
        assert len(fn_ids) == len(library["functions"])
        for attribute in library["attributes"]:
            assert attribute["source_id"] in source_ids
            assert attribute["function"] in fn_ids and attribute["pseudocode"]
            assert attribute["status"] in {"specified", "implemented"}, "Validated/reproduced status requires independent review evidence integration"
            if attribute["status"] == "implemented":
                implementation = attribute["implementation"]
                assert (root / implementation["entrypoint"]).is_file(), "Missing implementation"
                assert (root / implementation["tests"]).is_file(), "Missing implementation tests"
                report = read(root / implementation["comparison_report"])
                assert report["attribute"] == attribute["column"] and report["basin_count"] > 0
                assert report["implementation_status"] == "implemented"
        module["attribute_count"] = len(library["attributes"])
        modules.append(module)
        attributes.extend(library["attributes"])
        functions.extend(library["functions"])
    assert len({a["id"] for a in attributes}) == len(attributes)
    dictionary = read(root / "PUBLISHED/data/hydrography/attribute-dictionary.json")["columns"]
    actual = {a["column"] for a in attributes if a["id"].startswith("hydrosheds.")}
    assert actual == set(dictionary), "HydroSHEDS recipe coverage differs from project dictionary"
    payload = {**roadmap, "modules": modules, "attributes": attributes, "functions": functions,
               "updates": sorted(updates, key=lambda u: (u["date"], u["id"]), reverse=True),
               "years": list(range(2000, 2027)),
               "counts": {"specified": len(attributes), "implemented": sum(a["status"] == "implemented" for a in attributes), "reproduced": 0},
               "refresh_policy": "Curated updates and module changes are republished at dev start/build; browser checks every 60 seconds."}
    payload["revision"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


def main():
    payload = assemble()
    out = ROOT / "PUBLISHED/data/atlas"
    out.mkdir(parents=True, exist_ok=True)
    (out / "roadmap.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Portable documentation downloads; do not serve arbitrary workspace files.
    for name, source in {"methodology.md": "hydrosheds/METHODOLOGY.md",
                         "recipes.md": "hydrosheds/RECIPES.md",
                         "surrogates.md": "hydrosheds/SURROGATES.md",
                         "reproducibility.md": "core/REPRODUCIBILITY.md"}.items():
        (out / name).write_text((ROOT / "ATLAS_MODULES" / source).read_text(encoding="utf-8"), encoding="utf-8")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["attribute_id", "year", "availability", "value", "reason"])
    for attribute in payload["attributes"]:
        for year in payload["years"]:
            writer.writerow([attribute["id"], year, attribute["annual_policy"], "",
                             "Planning record only; no basin observation or source availability validated"])
    (out / "history-plan.csv").write_text(stream.getvalue(), encoding="utf-8")
    print(f"Atlas roadmap: {len(payload['attributes'])} specifications; 0 scientific reproductions claimed")


if __name__ == "__main__":
    main()
