"""Resolve profiled files after a delivery folder has moved.

Profiles deliberately retain the root at which a delivery was measured.  That
is useful provenance, but it is not a durable way to find the bytes: this
project regularly moves a delivery between an external drive, ``GEODATA/`` and
other local working folders.  Curated source declarations may therefore list
``searchRoots``.  Each root is searched using the inventory-relative path, and
locations inside the repository are returned in portable, repo-relative form.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _normalise(value: str | Path) -> str:
    return str(value).replace("\\", "/").rstrip("/")


def _candidate(repo_root: Path, root: str | Path, relative: str) -> Path:
    base = Path(root)
    if not base.is_absolute():
        base = repo_root / base
    return base / Path(relative)


def _portable(repo_root: Path, path: Path) -> str:
    """Prefer a stable repo-relative location when the path is inside it."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def location_for_profiled_file(
    repo_root: Path,
    inventory: dict,
    source: dict,
    relative: str,
) -> str:
    """Return the first live location for an inventory-relative file.

    Explicit search roots take precedence over the historical profile root.
    This lets a checkout opt into its current layout while preserving the old
    absolute path as the fallback when the bytes are genuinely offline.
    """
    for root in source.get("searchRoots", []):
        candidate = _candidate(repo_root, root, relative)
        if candidate.exists():
            return _portable(repo_root, candidate)

    historical = Path(inventory["source"]) / Path(relative)
    if historical.exists():
        return _portable(repo_root, historical)
    return _normalise(historical)


def resolve_location(
    repo_root: Path,
    location: str | None,
    inventories: dict[str, dict],
    sources: Iterable[dict],
) -> Path | None:
    """Resolve a recorded location directly or through configured relocations."""
    if not location or "://" in location:
        return None

    direct = Path(location)
    if not direct.is_absolute():
        direct = repo_root / direct
    if direct.exists():
        return direct.resolve()

    normalised = _normalise(location)
    for source in sources:
        inventory = inventories.get(source.get("inventory"))
        if not inventory:
            continue

        inventory_root = _normalise(inventory["source"])
        relative = None
        prefix = inventory_root + "/"
        if normalised.lower().startswith(prefix.lower()):
            relative = normalised[len(prefix):]
        else:
            # Some older manifests recorded the same delivery under a different
            # drive root.  Match only a complete inventoried suffix, which avoids
            # guessing from a basename that may occur in several folders.
            for record in inventory.get("files", []):
                recorded = _normalise(record["path"])
                if normalised.lower().endswith("/" + recorded.lower()):
                    relative = recorded
                    break

        if relative is None:
            continue
        relocated = location_for_profiled_file(repo_root, inventory, source, relative)
        candidate = Path(relocated)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if candidate.exists():
            return candidate.resolve()
    return None


def relocated_location(
    repo_root: Path,
    location: str | None,
    inventories: dict[str, dict],
    sources: Iterable[dict],
) -> str | None:
    """Return a portable live location, or the original unresolved declaration."""
    resolved = resolve_location(repo_root, location, inventories, sources)
    return _portable(repo_root, resolved) if resolved else location
