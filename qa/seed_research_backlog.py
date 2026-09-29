"""Register reviewed QA follow-up tasks without approving their execution."""

from __future__ import annotations

import json
from pathlib import Path

from qa.continuity import ResearchStore


ROOT = Path(__file__).resolve().parents[1]
STORE = ResearchStore(ROOT / "qa" / "research_state", ROOT)
PROJECT = "RES-QA-20260929"
OWNERS = {
    "SR-01": "qa_architect",
    "SR-02": "functional_qa",
    "SR-03": "model_validator",
    "SR-04": "model_validator",
    "SR-05": "research_replicator",
    "SR-06": "data_auditor",
}


def main() -> None:
    triage = json.loads((ROOT / "qa" / "scientific_review" / "triage.json").read_text(encoding="utf-8"))
    if not STORE.registry.exists():
        STORE.init()
    data = STORE.read()
    if PROJECT not in data["projects"]:
        STORE.add_project(
            PROJECT,
            "Resolve first-pass scientific QA findings with reproducible evidence",
            ["Which release, interface, topology and model claims can be independently verified?"],
            "Amu Darya and Syr Darya; first-pass findings dated 2026-09-29",
            ["system:amu_darya", "system:syr_darya"],
            ["UZGEODATA release uz-20260924T150158900Z", "WWF/HydroATLAS/v1/Basins/level07 local export 2026-09-08"],
            "Investigate each triage finding using its pinned evidence and retest criterion; require separate review before validation",
        )
    existing = STORE.read()["projects"][PROJECT]["tasks"]
    for finding in triage["findings"]:
        issue_id = finding["id"]
        if issue_id in existing:
            continue
        STORE.add_task(
            PROJECT,
            issue_id,
            finding["claim"],
            OWNERS[issue_id],
            [],
            [finding["action"], "Retest: " + finding["retest"]],
        )
        STORE.add_memory(
            PROJECT,
            "limitation" if finding["class"] == "methodological_limitation" else "unresolved_issue",
            finding["claim"],
            finding["evidence"][:1],
            "scientific_reviewer",
        )
    print(json.dumps(STORE.status(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
