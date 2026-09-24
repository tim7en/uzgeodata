"""Scientific guards for the Pskem continuation's chronology and release labels."""
import csv
import json
from pathlib import Path

from PIPELINES.build_pskem_climate_continuation import OUT, adjust, fit


def test_fit_does_not_see_held_out_or_future_target():
    raw = {(str(b), y, 1): float(y - 2000 + b)
           for b in range(2) for y in range(2003, 2027)}
    target = {k: v + 2 for k, v in raw.items()}
    original = fit(raw, target, "temperature")
    changed = dict(target)
    for key in changed:
        if key[1] > 2018:
            changed[key] += 10000
    assert original == fit(raw, changed, "temperature")
    assert all(abs(adjust(10, factor, "temperature") - 12) < 1e-9
               for factor in original.values())


def test_published_continuation_is_separate_and_dated():
    report = json.loads((OUT / "report.json").read_text())
    with (OUT / "continuation.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == report["continuation_rows"] == 800
    assert {r["variable"] for r in rows} == {"temperature_midpoint", "precipitation"}
    assert all((int(r["year"]), int(r["month"])) >= (2025, 1) for r in rows)
    assert all((int(r["year"]), int(r["month"])) <= (2026, 8) for r in rows)
    assert all(r["status"] == "estimated_terraclimate_v1_continuation" for r in rows)
    assert report["held_out_years"] == [2019, 2024]
    assert report["station_transfer"]["status"] == "tested"
