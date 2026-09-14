"""A published dataset that cannot be identified or verified cannot be depended on.

Each test here is a way a release quietly stops meaning what it said: a pointer that
moves before the files are in place, a record rewritten after someone cited it, a
download truncated without anyone noticing, a half-finished publish promoted over a
working one.
"""
import json

import pytest

from ATLAS_MODULES.core import releases


def artefact(directory, name, content):
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_a_release_names_every_file_with_its_digest(tmp_path):
    one = artefact(tmp_path, "cube/a.parquet", "alpha")
    two = artefact(tmp_path, "catalogue.json", "{}")
    record = releases.cut(tmp_path, [one, two], base=tmp_path, rows=10)

    assert set(record["files"]) == {"cube/a.parquet", "catalogue.json"}
    assert record["files"]["cube/a.parquet"]["bytes"] == 5
    assert len(record["files"]["cube/a.parquet"]["sha256"]) == 64
    assert releases.check(tmp_path, record["release_id"]) == []


def test_an_altered_file_is_detected_rather_than_served(tmp_path):
    path = artefact(tmp_path, "cube/a.parquet", "alpha")
    record = releases.cut(tmp_path, [path], base=tmp_path)
    path.write_text("alphb", encoding="utf-8")  # same length, different bytes

    problems = releases.check(tmp_path, record["release_id"])
    assert problems and "digest" in problems[0], \
        "a same-length edit is exactly what a size check alone would miss"


def test_a_truncated_file_is_detected(tmp_path):
    path = artefact(tmp_path, "cube/a.parquet", "alphabet")
    record = releases.cut(tmp_path, [path], base=tmp_path)
    path.write_text("alph", encoding="utf-8")
    problems = releases.check(tmp_path, record["release_id"])
    assert problems and "bytes" in problems[0]


def test_a_missing_file_is_detected(tmp_path):
    path = artefact(tmp_path, "cube/a.parquet", "alpha")
    record = releases.cut(tmp_path, [path], base=tmp_path)
    path.unlink()
    assert "missing" in releases.check(tmp_path, record["release_id"])[0]


def test_a_release_is_never_rewritten(tmp_path):
    path = artefact(tmp_path, "a.json", "{}")
    record = releases.cut(tmp_path, [path], base=tmp_path)
    # Naming the same instant explicitly is a rewrite attempt, and is refused. Two
    # publishes that merely land together are not, and are given the next instant.
    with pytest.raises(releases.ReleaseError, match="never rewritten"):
        releases.cut(tmp_path, [path], base=tmp_path,
                     at=releases.moment(record["release_id"]))


def test_two_publishes_in_the_same_instant_get_separate_releases(tmp_path):
    path = artefact(tmp_path, "a.json", "{}")
    first = releases.cut(tmp_path, [path], base=tmp_path)
    second = releases.cut(tmp_path, [path], base=tmp_path)
    assert first["release_id"] != second["release_id"],         "a second publish is a new release, not a rewrite of the one before it"
    assert second["release_id"] > first["release_id"], "ids still order by time"


def test_a_release_that_does_not_verify_is_not_promoted(tmp_path):
    """The failure that matters: publishing a broken dataset under a trusted name."""
    path = artefact(tmp_path, "cube/a.parquet", "alpha")
    record = releases.cut(tmp_path, [path], base=tmp_path)
    path.write_text("corrupted", encoding="utf-8")

    with pytest.raises(releases.ReleaseError, match="will not be promoted"):
        releases.promote(tmp_path, record["release_id"])
    assert not (tmp_path / releases.POINTER).exists(), "nothing became current"


def test_an_interrupted_publish_leaves_the_previous_release_current(tmp_path):
    good = artefact(tmp_path, "cube/a.parquet", "alpha")
    first = releases.cut(tmp_path, [good], base=tmp_path)
    releases.promote(tmp_path, first["release_id"])

    # A second publish writes its record, then its artefact turns out to be wrong.
    broken = artefact(tmp_path, "cube/b.parquet", "beta")
    second = releases.cut(tmp_path, [good, broken], base=tmp_path,
                          supersedes=first["release_id"])
    broken.write_text("tampered", encoding="utf-8")
    with pytest.raises(releases.ReleaseError):
        releases.promote(tmp_path, second["release_id"])

    pointer = json.loads((tmp_path / releases.POINTER).read_text(encoding="utf-8"))
    assert pointer["release_id"] == first["release_id"], \
        "a failed publish must not displace the release that works"
    assert releases.read(tmp_path)["release_id"] == first["release_id"]


def test_the_pointer_resolves_to_a_readable_record(tmp_path):
    path = artefact(tmp_path, "a.json", "{}")
    record = releases.cut(tmp_path, [path], base=tmp_path, span=["2003-01", "2024-12"])
    releases.promote(tmp_path, record["release_id"])

    assert releases.read(tmp_path)["release_id"] == record["release_id"]
    pointer = json.loads((tmp_path / releases.POINTER).read_text(encoding="utf-8"))
    assert pointer["span"] == ["2003-01", "2024-12"]
    assert pointer["path"].endswith(f"{record['release_id']}.json")


def test_reading_an_unpromoted_directory_says_so(tmp_path):
    with pytest.raises(releases.ReleaseError, match="no release has been promoted"):
        releases.read(tmp_path)


def test_history_is_newest_first_and_records_what_superseded_what(tmp_path):
    from datetime import datetime, timezone

    path = artefact(tmp_path, "a.json", "{}")
    early = releases.cut(tmp_path, [path], base=tmp_path,
                         at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    late = releases.cut(tmp_path, [path], base=tmp_path,
                        at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                        supersedes=early["release_id"])
    found = releases.history(tmp_path)
    assert [r["release_id"] for r in found] == [late["release_id"], early["release_id"]]
    assert found[0]["supersedes"] == early["release_id"]


def test_a_release_refuses_to_name_something_that_is_not_a_file(tmp_path):
    (tmp_path / "cube").mkdir()
    with pytest.raises(releases.ReleaseError, match="not a file"):
        releases.cut(tmp_path, [tmp_path / "cube"], base=tmp_path)
