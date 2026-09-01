"""Resolve a dataset's folder by name, never by its number.

The tree numbers datasets by alphabetical position, so inserting one shifts
every folder after it: adding GHM_UNIT_MODIFICATION moved LANDCOVER_ADMIN_YEAR
from 2.1 to 2.2. Any pipeline holding "2_LAND/2.1_LANDCOVER_ADMIN_YEAR" in a
string then writes to a folder that now belongs to a different dataset — which is
exactly what happened, leaving two half-filled copies of the same table.

The convention already says the name is the identity and the number is a
position. This is the code that keeps a pipeline honest about it: give it the
name, it finds the folder whatever the folder is currently numbered.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREE = ROOT / "PUBLISHED" / "data" / "ontology"


def dataset_dir(name: str, domain: str | None = None) -> Path:
    """The folder for a dataset, found by its upper-case name.

    Matches on the part after the number, so it survives renumbering. If the
    folder does not exist yet the caller gets a path built from the domain, which
    build_ontology_structure will renumber into place on its next run.
    """
    matches = sorted(TREE.glob(f"*/*_{name}"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Two folders for one dataset means a rename left an orphan behind.
        raise SystemExit(
            f"{name} resolves to {len(matches)} folders: "
            + ", ".join(str(m.relative_to(ROOT)) for m in matches)
            + "\n  Merge them and delete the stale one before running again."
        )
    if domain is None:
        raise SystemExit(f"No folder for {name} and no domain given to make one.")
    return TREE / f"_{domain}" / f"_{name}"
