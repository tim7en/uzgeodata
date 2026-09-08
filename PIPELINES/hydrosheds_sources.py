"""Find a HydroSHEDS source package wherever this checkout keeps it.

The ontology already solved this problem for profiled deliveries: a source
declaration in ``ONTOLOGY/vocab/external-sources.json`` carries ``searchRoots``,
and a package is looked for under each of them in turn.  The pipelines did not
share that convention — they hard-coded ``GEODATA/`` — so a checkout that keeps
the geodatabases under ``earth_engine/earth_engine/`` could not run them at all,
even though the ontology could catalogue and validate the very same bytes.

This module reads the roots from the same declaration rather than inventing a
second list, so moving a delivery stays a one-line edit in the vocabulary.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "ONTOLOGY/vocab/external-sources.json"
FALLBACK_ROOTS = ("GEODATA", ".", "earth_engine/earth_engine")


def search_roots(source_id: str = "hydrosheds-uz-2026") -> tuple[str, ...]:
    """Roots declared for a source, falling back to the conventional three."""
    try:
        declared = json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    except (OSError, ValueError, KeyError):
        return FALLBACK_ROOTS
    for source in declared:
        if source.get("id") == source_id and source.get("searchRoots"):
            return tuple(source["searchRoots"])
    return FALLBACK_ROOTS


def find(relative: str, source_id: str = "hydrosheds-uz-2026") -> Path | None:
    """First live path for an inventory-relative package, or None."""
    for root in search_roots(source_id):
        candidate = (ROOT / root / relative) if not Path(root).is_absolute() else Path(root) / relative
        if candidate.exists():
            return candidate.resolve()
    return None


def require(relative: str, hint: str = "", source_id: str = "hydrosheds-uz-2026") -> Path:
    """Resolve a package or exit naming every root that was tried.

    A missing source is a setup problem, not a bug, so the message says where
    the build looked instead of raising a bare FileNotFoundError from deep
    inside a reader.
    """
    found = find(relative, source_id)
    if found is not None:
        return found
    tried = "\n  ".join(f"{root}/{relative}" for root in search_roots(source_id))
    raise SystemExit(
        f"Missing {relative}. Looked under:\n  {tried}\n"
        + (f"{hint}\n" if hint else "")
        + "Add the parent to searchRoots in ONTOLOGY/vocab/external-sources.json "
          "if the delivery lives somewhere else."
    )
