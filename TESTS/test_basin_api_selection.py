"""Which value the per-basin API publishes when the store holds more than one.

A re-run under a corrected method carries a new recipe version, so its values do not
supersede the earlier ones -- the contract keeps both, as two measurements rather
than a correction. The atlas still has to publish a single number per basin and
column, and that choice is tested here: the finished run over the abandoned one, the
later finished run over the earlier, and never whichever row happened to sort last.
"""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations

PARTIAL = ("regional-glims-20260911T152557692285Z", (False, "2026-09-11T15:25:57.692+00:00"))
COMPLETE = ("regional-glims-20260912T042920691092Z", (True, "2026-09-12T04:29:20.691+00:00"))
EARLIER = ("regional-glims-20260910T000000000000Z", (True, "2026-09-10T00:00:00.000+00:00"))
ORDER = dict([PARTIAL, COMPLETE, EARLIER])


def row(run_id, value):
    return {"run_id": run_id, "value": value}


def test_a_finished_run_outranks_one_that_was_abandoned():
    partial, complete = row(PARTIAL[0], 12.0), row(COMPLETE[0], 15.0)
    assert observations.outranks(complete, partial, ORDER), "the run that covered every basin wins"
    assert not observations.outranks(partial, complete, ORDER), "and the order it is read in changes nothing"


def test_the_later_of_two_finished_runs_is_the_one_published():
    assert observations.outranks(row(COMPLETE[0], 15.0), row(EARLIER[0], 11.0), ORDER)
    assert not observations.outranks(row(EARLIER[0], 11.0), row(COMPLETE[0], 15.0), ORDER)


def test_the_first_value_seen_is_taken_only_because_nothing_stands_against_it():
    assert observations.outranks(row(PARTIAL[0], 12.0), None, ORDER)


def test_a_run_the_table_does_not_know_never_displaces_one_it_does():
    unknown = row("regional-glims-unrecorded", 99.0)
    assert not observations.outranks(unknown, row(PARTIAL[0], 12.0), ORDER), "unattributed is not newer"
    assert observations.outranks(row(PARTIAL[0], 12.0), unknown, ORDER)


def test_the_run_table_is_read_as_completeness_and_time(tmp_path):
    table = tmp_path / "run.csv"
    table.write_text("run_id,started_at,status\n"
                     "run-a,2026-09-10T00:00:00.000+00:00,complete\n"
                     "run-b,2026-09-11T00:00:00.000+00:00,incomplete\n", encoding="utf-8")
    order = observations.run_ranking(tmp_path)
    assert order["run-a"] == (True, "2026-09-10T00:00:00.000+00:00")
    assert order["run-b"] == (False, "2026-09-11T00:00:00.000+00:00")
    assert observations.outranks(row("run-a", 1.0), row("run-b", 2.0), order), "later, but never finished"
