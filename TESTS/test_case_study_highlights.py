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

    # The superseded annual regression is no longer published as a headline.
    assert "seasonal-flow-skill" not in by_id

    reservoir = validation["reservoir"]
    assert by_id["charvak-water-surface"]["eligibleMonths"] == reservoir["eligible_months"]
    assert by_id["charvak-water-surface"]["totalMonths"] == reservoir["total_months"]


def daily_model() -> dict:
    return json.loads((STUDY / "pskem-daily-model.json").read_text(encoding="utf-8"))


def test_the_daily_model_is_judged_on_years_it_never_saw():
    """Holds for either split: calibration and validation years cannot overlap."""
    model = daily_model()
    calibration = set(model["model"]["calibration"]["years"])
    validation = {row["year"] for row in model["seasonalVolumes"] if row["period"] == "validation"}
    assert validation
    assert not (calibration & validation)
    assert model["skill"]["validation"]["n"] > 2000
    # Skill has to be positive out of sample, or the finding claiming it is wrong.
    assert model["skill"]["validation"]["nse"] > 0
    assert model["monthlySkill"]["validation"]["nse"] > model["skill"]["validation"]["nse"]


def test_the_model_closes_its_water_balance():
    balance = daily_model()["waterBalance"]
    observed = balance["runoffCoefficientObserved"]
    simulated = balance["runoffCoefficientSimulated"]
    assert 0 < observed < 1, "a catchment cannot yield more water than it receives"
    assert abs(simulated - observed) < 0.15, "simulated yield must stay near the observed one"


def test_the_discharge_record_is_verified_against_the_published_monthly_table():
    """The workbook is named Monthly; the daily series had to be checked, not trusted."""
    provenance = daily_model()["observationProvenance"]
    assert "203 of 204" in provenance["reconciliation"]
    for entry in provenance["screening"]:
        # Each screened month must name the day it removed, verified by reproducing the mean.
        assert entry["identified"], entry["period"]
        assert entry["screenedMean"] != entry["rawMean"]

    # The published audit is extended, never overridden: its days stay excluded,
    # and the dropouts it missed are added with their evidence.
    audited = {entry["identified"] for entry in provenance["screening"]}
    detected = {entry["date"] for entry in provenance["additionalDropoutsDetected"]}
    assert audited and not (audited & detected)
    assert provenance["suspectDaysExcludedFromScoring"] == len(audited | detected)
    # Warm-up and ungauged days are excluded too, but counted separately.
    assert provenance["daysOutsideScoredWindow"] > provenance["suspectDaysExcludedFromScoring"]
    for entry in provenance["additionalDropoutsDetected"]:
        # A dropout has to be far below its neighbourhood, not merely a low day.
        assert entry["ratio"] < 0.5
    # The two repeated readings in peak melt 2016 are the case that motivated this.
    assert {"2016-07-01", "2016-07-02"} <= detected
