from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "PUBLISHED/data/case-studies"
KINDS = {"validated", "negative", "limitation"}


def highlights() -> dict:
    return json.loads((STUDY / "case-study-highlights.json").read_text(encoding="utf-8"))


def test_every_finding_carries_a_value_and_the_evidence_behind_it():
    payload = highlights()
    assert payload["counts"]["findings"] == len(payload["findings"])
    for finding in payload["findings"]:
        assert finding["kind"] in KINDS
        assert finding["headline"] and finding["detail"]
        assert finding["value"] is not None and finding["valueLabel"]
        evidence = ROOT / finding["evidence"]
        assert evidence.exists(), finding["evidence"]


def test_the_summary_publishes_what_did_not_work():
    """A study page showing only successes would misrepresent the study."""
    kinds = {finding["kind"] for finding in highlights()["findings"]}
    assert "negative" in kinds
    assert "limitation" in kinds


def test_figures_and_reports_referenced_by_the_page_exist():
    payload = highlights()
    for finding in payload["findings"]:
        if finding.get("figure"):
            assert (ROOT / "PUBLISHED" / finding["figure"].lstrip("/")).exists(), finding["figure"]
    assert payload["reports"]
    for report in payload["reports"]:
        assert (ROOT / "PUBLISHED" / report["href"].lstrip("/")).exists(), report["href"]
    for figure in payload["figures"]:
        assert (ROOT / "PUBLISHED" / figure.lstrip("/")).exists(), figure


def test_headline_numbers_match_the_evidence_they_cite():
    """The values are derived, not typed: check them against the source file."""
    payload = highlights()
    validation = json.loads((STUDY / "advanced-validation.json").read_text(encoding="utf-8"))
    by_id = {finding["id"]: finding for finding in payload["findings"]}

    scored = [row for row in validation["climate_validation"] if row["raw"].get("nse") is not None]
    assert by_id["product-station-agreement"]["value"] == round(max(row["raw"]["nse"] for row in scored), 3)

    flow = by_id["seasonal-flow-skill"]
    best = min(validation["seasonal_flow"]["models"], key=lambda entry: entry["scores"]["rmse"])
    assert flow["value"] == round(best["scores"]["nse"], 3)
    # The finding claims every model is worse than the mean; hold it to that.
    assert all(entry["scores"]["nse"] < 0 for entry in validation["seasonal_flow"]["models"])

    reservoir = validation["reservoir"]
    assert by_id["charvak-water-surface"]["eligibleMonths"] == reservoir["eligible_months"]
    assert by_id["charvak-water-surface"]["totalMonths"] == reservoir["total_months"]
