"""A published dataset needs an identity, or nobody can say which one they used.

The platform has been publishing by overwriting. The site is rebuilt in place, the
cube is rewritten, and `release.json` records when that last happened. That is enough
to serve a page and not enough for anyone to depend on: a reader cannot pin what they
analysed, cannot tell whether their copy is current, and cannot detect a truncated
download. Two people running the same notebook a month apart get different numbers and
no way to discover that they did.

A release fixes an answer to "which data". It is immutable once cut, identified by
when it was cut and the commit it came from, and it carries a hash of every file it
names. What it deliberately is not is a copy: it points at artefacts, so cutting one
costs a manifest rather than a duplicate of the record.

Three properties, each of which is a way a published dataset goes wrong:

**Atomic.** The `latest` pointer is written after every artefact it names is in place,
and never before. A publish interrupted halfway leaves the previous release current
rather than promoting a half-written one. This is the whole reason the pointer is a
separate small file.

**Verifiable.** Every file is named with its size and SHA-256, so a consumer can prove
it has what the release says rather than assuming a download completed. A silent
truncation is otherwise indistinguishable from a short record.

**Immutable.** A release is never rewritten. Correcting one means cutting the next and
moving the pointer, so an analysis that cites a release keeps meaning what it meant.
Superseding is recorded on the new release rather than erasing the old.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from .runtime import sha256, utc_now, write_json

RELEASES = "releases"
POINTER = "latest.json"
SCHEMA = 1


class ReleaseError(Exception):
    """A release that cannot be trusted to be what it claims."""


# Milliseconds, not seconds. Two publishes inside one second are not hypothetical --
# a pipeline that cuts a release per step does it routinely -- and at second precision
# the second one collides with the first and is refused as a rewrite. The id still
# sorts chronologically and still reads as a timestamp.
STAMP = "uz-%Y%m%dT%H%M%S%fZ"


def identifier(at=None):
    """A release id that sorts chronologically and reads as a date."""
    moment = at or datetime.now(timezone.utc)
    return moment.strftime(STAMP)[:-4] + "Z"   # microseconds trimmed to milliseconds


def moment(release_id):
    """The instant a release id encodes, for ordering and for tests."""
    return datetime.strptime(release_id, "uz-%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)


def describe(paths, base):
    """Name each artefact with its size and digest, relative to the published root."""
    described = {}
    for path in sorted(paths):
        path = Path(path)
        if not path.is_file():
            raise ReleaseError(f"{path} is named by the release but is not a file")
        described[path.relative_to(base).as_posix()] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    return described


def cut(directory, paths, base, commit=None, span=None, rows=None, registry=None,
        supersedes=None, notes=None, at=None):
    """Write an immutable release record. Does not move the pointer.

    Separating this from `promote` is what makes a publish atomic: the record can be
    written, inspected and even discarded while the previous release is still the one
    readers resolve to.
    """
    directory = Path(directory)
    folder = directory / RELEASES
    folder.mkdir(parents=True, exist_ok=True)

    # A collision means two different things depending on where the timestamp came
    # from. Given one explicitly, it is an attempt to rewrite a release that already
    # exists, and refusing is the whole point. Generated here, it only means two
    # publishes landed in the same millisecond, and the second is a genuinely new
    # release that should get the next free instant rather than an error.
    release_id = identifier(at)
    path = folder / f"{release_id}.json"
    if path.exists():
        if at is not None:
            raise ReleaseError(f"{release_id} already exists; a release is never rewritten")
        moment_of = moment(release_id)
        while path.exists():
            moment_of += timedelta(milliseconds=1)
            release_id = identifier(moment_of)
            path = folder / f"{release_id}.json"

    record = {
        "schema_version": SCHEMA,
        "release_id": release_id,
        "cut_at": utc_now(),
        "commit": commit,
        "span": span,
        "rows": rows,
        "supersedes": supersedes,
        "notes": notes,
        "files": describe(paths, base),
        "registry": registry,
        "reading": {
            "identity": "Cite this release_id. The artefacts it names may be rebuilt at "
                        "the same paths by a later release; only the id fixes which bytes "
                        "were used.",
            "verification": "Every file carries its size and SHA-256. A consumer that does "
                            "not check them cannot distinguish a complete download from a "
                            "truncated one.",
            "immutability": "This record is never rewritten. A correction is the next "
                            "release, naming this one in supersedes.",
        },
    }
    write_json(path, record)
    return record


def promote(directory, release_id, verify=True):
    """Make a release the one readers resolve to. The last step of a publish.

    Verifies before promoting by default, because promoting a release whose files do
    not match its own manifest publishes a broken dataset under a trusted name -- the
    failure this whole module exists to prevent.
    """
    directory = Path(directory)
    record = read(directory, release_id)
    if verify:
        problems = check(directory, release_id)
        if problems:
            raise ReleaseError(
                f"{release_id} does not match its own manifest, so it will not be "
                f"promoted: {'; '.join(problems[:3])}")
    write_json(directory / POINTER, {
        "schema_version": SCHEMA,
        "release_id": release_id,
        "cut_at": record["cut_at"],
        "promoted_at": utc_now(),
        "span": record.get("span"),
        "rows": record.get("rows"),
        "path": f"{RELEASES}/{release_id}.json",
        "reading": "The release a reader gets by default. Pin the release_id to keep an "
                   "analysis reproducible; follow this pointer to track the current one.",
    })
    return record


def read(directory, release_id=None):
    """One release record, or whichever the pointer names."""
    directory = Path(directory)
    if release_id is None:
        pointer = directory / POINTER
        if not pointer.exists():
            raise ReleaseError(f"no release has been promoted in {directory}")
        release_id = json.loads(pointer.read_text(encoding="utf-8"))["release_id"]
    path = directory / RELEASES / f"{release_id}.json"
    if not path.exists():
        raise ReleaseError(f"{release_id} is not a release in {directory}")
    return json.loads(path.read_text(encoding="utf-8"))


def history(directory):
    """Every release, newest first. The record of what was published when."""
    folder = Path(directory) / RELEASES
    if not folder.is_dir():
        return []
    return sorted((json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("uz-*.json")),
                  key=lambda record: record["release_id"], reverse=True)


def check(directory, release_id=None, base=None):
    """Which of a release's files are missing, resized or altered.

    Returns a list of problems and not a boolean, because "it does not verify" is not
    actionable and "cube/pre.parquet is 12 bytes short" is.
    """
    directory = Path(directory)
    record = read(directory, release_id)
    base = Path(base) if base else directory
    problems = []
    for name, stated in record["files"].items():
        path = base / name
        if not path.is_file():
            problems.append(f"{name} is named by the release but missing")
            continue
        size = path.stat().st_size
        if size != stated["bytes"]:
            problems.append(f"{name} is {size} bytes, the release says {stated['bytes']}")
            continue
        if sha256(path) != stated["sha256"]:
            problems.append(f"{name} does not match its recorded digest")
    return problems
