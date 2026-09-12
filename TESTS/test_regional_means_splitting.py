"""What a refused batch does next.

The painted sources carry their basin outlines inside the request, and a level-12
basin in the glaciated headwaters holds far more coordinates than one on the plain.
Earth Engine answers a hundred of the first kind with `Object too large`, which no
amount of waiting changes. Tested here: that such a refusal is halved rather than
retried, that the halves that succeed are checkpointed so a later run does not
repeat them, and that a failure which is not about size still reaches the ledger.
"""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIPELINES import extract_regional_means as means

SPEC = means.SOURCES["glims"]


def features(count, start=4120000000):
    return [{"geometry": {"type": "Polygon", "coordinates": [[[58.0, 40.0], [58.1, 40.0],
                                                              [58.1, 40.1], [58.0, 40.0]]]},
             "properties": {"HYBAS_ID": start + index}} for index in range(count)]


def refusing(limit, calls, heavy=range(0, 10), fail=None):
    """Earth Engine as the painted sources meet it.

    The refusal is not a function of the count alone: a span is refused when it is
    large *and* reaches into the expensive ground, which is what makes one batch of a
    hundred fine and its neighbour impossible.
    """
    expensive = {4120000000 + index for index in heavy}

    def batch_rows(_spec, span, _transform):
        calls.append(len(span))
        if fail is not None and len(span) == fail:
            raise RuntimeError("EEException: Computation timed out.")
        if len(span) > limit and any(f["properties"]["HYBAS_ID"] in expensive for f in span):
            raise RuntimeError(f"EEException: Object too large ({len(span) * 10 ** 6} bytes).")
        return {str(f["properties"]["HYBAS_ID"]): {"gla": 1.0} for f in span}
    return batch_rows


@pytest.fixture
def ledger():
    return {"retries": [], "failures": [], "splits": []}


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """The backoff between transient retries is real seconds; the test needs none."""
    monkeypatch.setattr(means.time, "sleep", lambda _seconds: None)


def test_a_refused_span_is_halved_rather_than_waited_on(tmp_path, monkeypatch, ledger):
    calls = []
    monkeypatch.setattr(means, "CHECKPOINTS", tmp_path)
    monkeypatch.setattr(means, "batch_rows", refusing(30, calls))

    rows, cached = means.extract_span(SPEC, features(100), None, "glims", 2, ledger)

    assert len(rows) == 100, "every basin in the batch is still returned"
    assert not cached
    assert calls == [100, 50, 25, 25, 50], "halved, and only down the half that was refused"
    assert [split["target"] for split in ledger["splits"]] == ["batch-0002", "batch-0002-000-050"]
    assert not ledger["failures"], "a span that succeeded after splitting has not failed"


def test_each_accepted_span_is_checkpointed_so_a_rerun_resumes(tmp_path, monkeypatch, ledger):
    calls = []
    monkeypatch.setattr(means, "CHECKPOINTS", tmp_path)
    monkeypatch.setattr(means, "batch_rows", refusing(30, calls))
    means.extract_span(SPEC, features(100), None, "glims", 2, ledger)

    written = sorted(path.name for path in (tmp_path / "glims").glob("*.json"))
    assert written == ["batch-0002-000-025.json", "batch-0002-000-050.json",
                       "batch-0002-025-050.json", "batch-0002-050-100.json",
                       "batch-0002.json"], "every span that completed, the split whole included"

    calls.clear()
    rows, cached = means.extract_span(SPEC, features(100), None, "glims", 2, ledger)
    assert len(rows) == 100
    assert calls == [], "a resumed run asks Earth Engine for nothing it already holds"


def test_a_whole_batch_that_is_accepted_is_cached_under_its_own_name(tmp_path, monkeypatch, ledger):
    monkeypatch.setattr(means, "CHECKPOINTS", tmp_path)
    monkeypatch.setattr(means, "batch_rows", refusing(200, []))
    means.extract_span(SPEC, features(100), None, "glims", 7, ledger)

    cache = tmp_path / "glims" / "batch-0007.json"
    assert cache.is_file()
    assert len(json.loads(cache.read_text(encoding="utf-8"))) == 100
    assert not ledger["splits"]


def test_splitting_stops_where_the_refusal_is_no_longer_about_size(tmp_path, monkeypatch, ledger):
    calls = []
    monkeypatch.setattr(means, "CHECKPOINTS", tmp_path)
    monkeypatch.setattr(means, "batch_rows", refusing(0, calls, heavy=range(0, 32)))
    monkeypatch.setattr(means, "SMALLEST_SPAN", 8)

    rows, _ = means.extract_span(SPEC, features(32), None, "glims", 1, ledger)

    assert rows == {}, "nothing is invented for a span that never succeeded"
    assert min(calls) == 8, "the smallest span is tried, and nothing smaller"
    assert ledger["failures"], "and the refusal is recorded rather than swallowed"


def test_a_failure_that_is_not_about_size_is_retried_not_split(tmp_path, monkeypatch, ledger):
    calls = []
    monkeypatch.setattr(means, "CHECKPOINTS", tmp_path)
    monkeypatch.setattr(means, "batch_rows", refusing(200, calls, fail=40))

    rows, _ = means.extract_span(SPEC, features(40), None, "glims", 3, ledger)

    assert rows == {}
    assert calls == [40, 40, 40, 40], "one try, then the retrying path, never a split"
    assert not ledger["splits"]
    assert [failure["target"] for failure in ledger["failures"]] == ["batch-0003"]
