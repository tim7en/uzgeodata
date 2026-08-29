"""Build the canonical ontology instance from the repository's real registries.

Reads the public catalogue, the private repository, the extracted layer registry
and the polygonised-raster registry, and projects them into one graph:

    ONTOLOGY/instances/identity-map.json   sourceKey -> dataset ID, minted once
    ONTOLOGY/instances/entities.json       Dataset / Distribution / MapLayer / Agent
    ONTOLOGY/instances/assertions.json     every relational fact, with provenance
    PUBLISHED/data/ontology-graph.json        the projection the portal renders

Nothing here guesses silently. Structural facts come from the source metadata or
from measurements made by the extraction pipeline; semantic facts come from the
lexical rules and are labelled as such, so a curator (or a later model) can tell
them apart and correct them.

Usage:
    python PIPELINES/ontology/build_ontology.py [--root .] [--quiet]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# Rule- or model-derived assertions at or above this confidence are published to
# the portal, flagged with their agent. Below it they wait for review. Raising
# this makes the published graph smaller and safer; lowering it makes it fuller
# and noisier. It is deliberately one number in one place.
PROMOTE_THRESHOLD = 0.75

# Bounding box of Uzbekistan (EPSG:4326), used to test whether a layer's measured
# extent reaches beyond the country.
UZ_BBOX = (55.99, 37.17, 73.16, 45.60)
EXTENT_TOLERANCE_DEG = 0.5

AGENT_SOURCE = "uz:agent/atlas-source"
AGENT_PIPELINE = "uz:agent/extraction-pipeline"
AGENT_RULES = "uz:agent/rule-lexical-v1"
AGENT_CURATOR = "uz:agent/curator"
AGENT_HYDROSHEDS = "uz:agent/hydrosheds"

# The five layers published to the public map, keyed by the atlas number their
# extraction script pulls them from (PIPELINES/build_web_layers.py).
PUBLIC_LAYER_ATLAS_NUMBERS = {
    "protected-areas": 185,
    "earthquakes": 205,
    "water-management": 52,
    "glacial-lakes": 57,
    "flood-risk": 207,
}

YEAR_RE = re.compile(r"(?<!\d)(1[89]\d{2}|20\d{2}|21\d{2})(?!\d)")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    replace_with_retry(tmp, path)


def write_json_rows(path: Path, payload, rows_key: str) -> None:
    """Write a table one row per line.

    The triple table is thousands of uniform records. Indenting it triples the
    bytes the browser has to fetch; collapsing it to one line makes every
    rebuild an unreadable diff. One row per line is neither.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    rows = payload[rows_key]
    head = {k: v for k, v in payload.items() if k != rows_key}
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("{\n")
        for key, value in head.items():
            handle.write(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},\n")
        handle.write(f"  {json.dumps(rows_key)}: [\n")
        for index, row in enumerate(rows):
            trailing = "," if index < len(rows) - 1 else ""
            handle.write("    " + json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                         + trailing + "\n")
        handle.write("  ]\n}\n")
    replace_with_retry(tmp, path)


def replace_with_retry(tmp: Path, path: Path, attempts: int = 5) -> None:
    """Atomic rename, retried.

    On Windows the replace transiently fails with a permission error while an
    indexer or virus scanner still holds the freshly written file.
    """
    for attempt in range(attempts):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.15 * (attempt + 1))


def sha_short(text: str, length: int = 6) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def slugify(text: str, limit: int = 48) -> str:
    normalised = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalised.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if not slug:
        slug = "item-" + hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:8]
    return slug[:limit].strip("-")


def normalise_text(text: str) -> str:
    lowered = (text or "").lower().replace("ё", "е")
    return re.sub(r"[^0-9a-zЀ-ӿ]+", " ", lowered)


def term_matches(haystack: str, term: str) -> bool:
    """Word-boundary match that tolerates inflection.

    Titles arrive in two languages and both inflect: 'Climate types' against the
    label 'climate type', 'ландшафты' against 'ландшафт'. Allowing a short
    trailing suffix catches those without matching unrelated longer words.
    """
    term = term.strip()
    if len(term) < 3:
        return False
    return re.search(r" " + re.escape(term) + r"[a-zЀ-ӿ]{0,3}(?= )", haystack) is not None


def match_by_path_tail(container: str, by_location: dict[str, str]) -> str | None:
    """Find the distribution that already stands for this file.

    A relationship table names its container relative to the repository, while a
    delivery file's recorded location is absolute and rooted wherever it was
    profiled, so the two share only a tail. Comparing whole paths breaks the
    moment either root is renamed, and then the build mints a second record for
    bytes it already catalogued.

    Try the longest tail first and stop at the first that is unambiguous. Never
    fall back to the bare filename: relationships/downstream_links.csv exists in
    more than one delivery, and guessing between them would be worse than
    minting a fresh record.
    """
    parts = container.lower().split("/")
    for start in range(len(parts) - 1):
        tail = "/".join(parts[start:])
        matches = {dist for location, dist in by_location.items()
                   if location == tail or location.endswith("/" + tail)}
        if len(matches) == 1:
            return matches.pop()
        if len(matches) > 1:
            return None
    return None


def assertion_id(subject: str, predicate: str, obj) -> str:
    key = f"{subject}|{predicate}|{json.dumps(obj, ensure_ascii=False, sort_keys=True)}"
    return "uz:a/" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


class GraphBuilder:
    def __init__(self, root: Path, quiet: bool = False):
        self.root = root
        self.quiet = quiet
        self.generated_at = now_iso()
        self.entities: dict[str, dict] = {}
        self.assertions: dict[str, dict] = {}
        self.warnings: list[str] = []

        vocab = root / "ONTOLOGY" / "vocab"
        self.themes = read_json(vocab / "themes.json")["concepts"]
        self.properties = read_json(vocab / "properties.json")["concepts"]
        self.analysis = read_json(vocab / "analysis.json")["concepts"]
        self.usecases = read_json(vocab / "usecases.json")["concepts"]
        self.places = read_json(vocab / "places.json")["concepts"]
        self.rules = read_json(vocab / "lexical-rules.json")
        self.agents = read_json(vocab / "agents.json")["agents"]

        self.theme_by_label = {}
        for concept in self.themes:
            for label in [concept["prefLabel"], *concept.get("altLabels", [])]:
                self.theme_by_label[label.strip().lower()] = concept["id"]

        self.identity_map = read_json(
            root / "ONTOLOGY" / "instances" / "identity-map.json", {"version": "1.0", "ids": {}}
        )

    def log(self, message: str) -> None:
        if not self.quiet:
            print(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    # ------------------------------------------------------------------ identity

    def dataset_id(self, source_key: str, atlas_number, title: str, preferred: str = None) -> str:
        """Mint a dataset ID once, then never change it.

        atlasNumber alone is not unique (ten PDSI packages share three numbers)
        and the public catalogue's sequential atlas-NNN ids move whenever the
        directory is re-sorted, so identity is keyed on the immutable source
        filename and cached in identity-map.json.
        """
        existing = self.identity_map["ids"].get(source_key)
        if existing:
            return existing
        if preferred:
            minted = f"uz:ds/{slugify(preferred)}"
        else:
            prefix = f"a{atlas_number}-" if atlas_number is not None else "x-"
            minted = f"uz:ds/{prefix}{slugify(title)}"
        if minted in set(self.identity_map["ids"].values()):
            minted = f"{minted}-{hashlib.sha1(source_key.encode('utf-8')).hexdigest()[:6]}"
        self.identity_map["ids"][source_key] = minted
        return minted

    # ------------------------------------------------------------------ entities

    def add_entity(self, entity: dict) -> str:
        entity_id = entity["id"]
        if entity_id in self.entities:
            self.entities[entity_id].update({k: v for k, v in entity.items() if v is not None})
        else:
            self.entities[entity_id] = entity
        return entity_id

    def add(
        self,
        subject: str,
        predicate: str,
        obj=None,
        *,
        value=None,
        agent: str,
        confidence: float,
        status: str | None = None,
        method: str = "source-metadata",
        evidence: dict | None = None,
    ) -> str:
        payload = obj if obj is not None else value
        aid = assertion_id(subject, predicate, payload)
        if status is None:
            status = "asserted" if confidence >= PROMOTE_THRESHOLD else "proposed"

        # The same triple can be reached by more than one route - the atlas
        # metadata, a curator's mapping of an external delivery, and the lexical
        # rules all have opinions about what a dataset observes. The strongest
        # claim wins, so a later, weaker pass never quietly downgrades an earlier
        # one. Build order settles genuine ties.
        existing = self.assertions.get(aid)
        if existing is not None:
            rank = {"superseded": 0, "proposed": 1, "asserted": 2, "rejected": 3}
            if (rank[existing["status"]], existing["confidence"]) >= (rank[status], confidence):
                return aid
        record = {
            "id": aid,
            "subject": subject,
            "predicate": predicate,
            "status": status,
            "confidence": round(float(confidence), 3),
            "assertedBy": agent,
            "method": method,
            "generatedAt": self.generated_at,
            "reviewedBy": None,
            "reviewedAt": None,
        }
        if obj is not None:
            record["object"] = obj
        else:
            record["value"] = value
        if evidence:
            record["evidence"] = evidence
        self.assertions[aid] = record
        return aid

    # ------------------------------------------------------------------ sources

    def load_sources(self) -> None:
        root = self.root
        self.catalog = read_json(root / "PUBLISHED" / "data" / "archive-catalog.json", [])
        self.repository = read_json(root / "WORKSPACE" / "datasets.json", [])
        self.layers = read_json(root / "WORKSPACE" / "derived" / "all-map-layers.json", [])
        self.rasters = read_json(root / "WORKSPACE" / "derived" / "raster-geojson.json", [])
        self.public_layers = read_json(root / "PUBLISHED" / "data" / "map-layers.json", [])

        self.repo_by_source_title = {}
        for record in self.repository:
            source_key = record.get("sourceKey") or ""
            stem = Path(source_key).stem
            if stem:
                self.repo_by_source_title[stem] = record

        # External deliveries: profiled inventories plus the curator's mapping of
        # which files make up which dataset.
        external_dir = root / "ONTOLOGY" / "instances" / "external"
        self.inventories = {}
        for path in sorted(external_dir.glob("*.json")):
            payload = read_json(path)
            if payload and payload.get("name") and "files" in payload:
                self.inventories[payload["name"]] = payload
        self.external_mapping = read_json(root / "ONTOLOGY" / "vocab" / "external-sources.json",
                                          {"sources": []})
        self.external_details = read_json(external_dir / "details.json",
                                          {"stations": [], "classLabels": {}})
        self.hydrography = read_json(
            root / "ONTOLOGY" / "instances" / "hydrography.json", {}
        )
        self.relationship_tables = read_json(
            root / "ONTOLOGY" / "vocab" / "relationship-tables.json", {"tables": []}
        )
        # Row counts a producing build already measured, keyed by the name a
        # table declares in rowCountFrom.manifest.
        self.relationship_counts = {
            "hydrography": (self.hydrography or {}).get("counts", {}),
            "atlasBasinLinks": (read_json(
                root / "ONTOLOGY" / "instances" / "atlas-basin-links.json", {}
            ) or {}).get("counts", {}),
            "basinZonalStats": (read_json(
                root / "ONTOLOGY" / "instances" / "basin-zonal-stats.json", {}
            ) or {}).get("counts", {}),
        }

    # ------------------------------------------------------------------ build

    def build(self) -> None:
        self.load_sources()
        for agent in self.agents:
            self.add_entity(dict(agent))
        self.build_datasets()
        self.build_derived_distributions()
        self.build_public_layers()
        self.build_external_sources()
        self.build_hydrography_sources()
        self.build_relationship_tables()
        self.assert_hydroatlas_attributes()
        self.seed_semantics()
        self.merge_preserved_assertions()

    def build_datasets(self) -> None:
        self.dataset_by_source_title = {}
        self.dataset_by_package = {}
        self.dataset_by_atlas_number = {}

        for record in self.catalog:
            source_title = record.get("sourceTitle") or record.get("title")
            title = record.get("title") or source_title
            atlas_number = record.get("atlasNumber")
            ds_id = self.dataset_id(source_title, atlas_number, title)
            repo = self.repo_by_source_title.get(source_title)

            self.add_entity(
                {
                    "id": ds_id,
                    "type": "Dataset",
                    "label": title,
                    "labels": {"en": title, "ru": source_title},
                    "sourceKey": source_title,
                    "atlasNumber": atlas_number,
                    "catalogId": record.get("id"),
                    "repositoryId": repo.get("id") if repo else None,
                    "description": (repo or {}).get("description") or "",
                }
            )
            self.dataset_by_source_title[source_title] = ds_id
            if atlas_number is not None:
                self.dataset_by_atlas_number.setdefault(atlas_number, []).append(ds_id)

            theme_id = self.theme_by_label.get((record.get("category") or "").strip().lower())
            if theme_id:
                self.add(
                    ds_id,
                    "uz:belongsToTheme",
                    theme_id,
                    agent=AGENT_SOURCE,
                    confidence=1.0,
                    status="asserted",
                    evidence={"source": "archive-catalog.category", "matchedTerms": [record.get("category")]},
                )
            else:
                self.warn(f"{ds_id}: category '{record.get('category')}' does not resolve to a theme")

            if repo:
                for file_record in repo.get("files", []):
                    stored = file_record.get("storedName") or ""
                    suffix = Path(stored).suffix.lower().lstrip(".")
                    role = "source-document" if suffix == "pdf" else "source-package"
                    dist_id = f"uz:dist/{ds_id.split('/')[-1]}-{slugify(suffix or 'file', 12)}"
                    self.add_entity(
                        {
                            "id": dist_id,
                            "type": "Distribution",
                            "label": f"{title} ({suffix.upper() or 'file'})",
                            "role": role,
                            "format": record.get("format") or suffix.upper(),
                            "byteSize": file_record.get("size"),
                            "storedName": stored,
                            "url": None,
                            "accessPolicy": (repo.get("access") or "request").lower(),
                        }
                    )
                    self.add(
                        ds_id,
                        "uz:hasDistribution",
                        dist_id,
                        agent=AGENT_SOURCE,
                        confidence=1.0,
                        status="asserted",
                    )
                    if stored:
                        self.dataset_by_package[stored] = (ds_id, dist_id)
            else:
                self.warn(f"{ds_id}: no matching record in the private repository")

        # Repository records with no public catalogue entry still belong in the graph.
        for record in self.repository:
            source_key = record.get("sourceKey") or ""
            stem = Path(source_key).stem
            if stem and stem in self.dataset_by_source_title:
                continue
            key = source_key or record["id"]
            ds_id = self.dataset_id(key, None, record.get("title") or record["id"])
            self.add_entity(
                {
                    "id": ds_id,
                    "type": "Dataset",
                    "label": record.get("title") or record["id"],
                    "labels": {"en": record.get("title") or record["id"]},
                    "sourceKey": key,
                    "atlasNumber": None,
                    "catalogId": None,
                    "repositoryId": record["id"],
                    "description": record.get("description") or "",
                }
            )
            self.dataset_by_source_title[key] = ds_id
            theme_id = self.theme_by_label.get((record.get("category") or "").strip().lower())
            if theme_id:
                self.add(ds_id, "uz:belongsToTheme", theme_id, agent=AGENT_SOURCE,
                         confidence=1.0, status="asserted")
            else:
                self.warn(
                    f"{ds_id}: repository category '{record.get('category')}' has no theme; "
                    "needs a curator decision"
                )
            for file_record in record.get("files", []):
                stored = file_record.get("storedName") or ""
                suffix = Path(stored).suffix.lower().lstrip(".")
                dist_id = f"uz:dist/{ds_id.split('/')[-1]}-{slugify(suffix or 'file', 12)}-{stored[:8]}"
                self.add_entity(
                    {
                        "id": dist_id,
                        "type": "Distribution",
                        "label": f"{record.get('title')} ({suffix.upper()})",
                        "role": "source-document" if suffix == "pdf" else "source-package",
                        "format": suffix.upper(),
                        "byteSize": file_record.get("size"),
                        "storedName": stored,
                        "url": None,
                        "accessPolicy": (record.get("access") or "request").lower(),
                    }
                )
                self.add(ds_id, "uz:hasDistribution", dist_id, agent=AGENT_SOURCE,
                         confidence=1.0, status="asserted")
                if stored:
                    self.dataset_by_package[stored] = (ds_id, dist_id)

    def build_derived_distributions(self) -> None:
        """Web layers and polygonised rasters, linked back to the package they came from."""
        for entry in self.layers:
            package = entry.get("package") or ""
            link = self.dataset_by_package.get(package)
            if not link:
                self.warn(f"derived layer for package {package} has no dataset")
                continue
            ds_id, source_dist = link
            kind = entry.get("kind")
            role = {"vector": "web-vector", "raster": "web-raster-preview"}.get(kind, "web-raster-preview")
            url = entry.get("url") or ""
            dist_id = f"uz:dist/{ds_id.split('/')[-1]}-{slugify(Path(url).stem or kind, 20)}"
            self.add_entity(
                {
                    "id": dist_id,
                    "type": "Distribution",
                    "label": f"{entry.get('title')} ({role})",
                    "role": role,
                    "format": "GeoJSON" if kind == "vector" else "PNG",
                    "byteSize": entry.get("bytes"),
                    "storedName": Path(url).name or None,
                    "url": url or None,
                    "accessPolicy": (entry.get("access") or "request").lower(),
                }
            )
            self.add(ds_id, "uz:hasDistribution", dist_id, agent=AGENT_PIPELINE,
                     confidence=1.0, status="asserted", method="extraction")
            self.add(
                dist_id,
                "uz:derivedFrom",
                source_dist,
                agent=AGENT_PIPELINE,
                confidence=1.0,
                status="asserted",
                method="extraction",
                evidence={
                    "source": "all-map-layers.json",
                    "note": f"first readable {kind} layer of the package",
                    "featureCount": entry.get("sourceFeatures"),
                },
            )
            for field in entry.get("fields") or []:
                self.add(dist_id, "uz:hasField", value=field, agent=AGENT_PIPELINE,
                         confidence=1.0, status="asserted", method="extraction")
            bounds = entry.get("bounds")
            if bounds and len(bounds) == 4:
                self.add(ds_id, "uz:spatialExtent", value=[round(float(b), 5) for b in bounds],
                         agent=AGENT_PIPELINE, confidence=1.0, status="asserted", method="measurement")
                self.assert_coverage(ds_id, bounds, "all-map-layers.json")

        for entry in self.rasters:
            source = entry.get("source") or ""
            link = self.dataset_by_package.get(source)
            if not link:
                self.warn(f"polygonised raster {entry.get('id')} has no dataset for package {source}")
                continue
            ds_id, source_dist = link
            dist_id = f"uz:dist/{ds_id.split('/')[-1]}-poly-{slugify(entry.get('sourceRaster', ''), 14)}"
            self.add_entity(
                {
                    "id": dist_id,
                    "type": "Distribution",
                    "label": f"{self.entities[ds_id]['label']} (polygonised raster)",
                    "role": "raster-polygonized",
                    "format": "GeoJSON",
                    "byteSize": entry.get("bytes"),
                    "storedName": entry.get("storedName"),
                    "url": None,
                    "accessPolicy": "internal",
                }
            )
            self.add(ds_id, "uz:hasDistribution", dist_id, agent=AGENT_PIPELINE,
                     confidence=1.0, status="asserted", method="extraction")
            self.add(
                dist_id,
                "uz:derivedFrom",
                source_dist,
                agent=AGENT_PIPELINE,
                confidence=1.0,
                status="asserted",
                method="raster-polygonisation",
                evidence={
                    "source": "raster-geojson.json",
                    "note": f"band {entry.get('band')} {entry.get('valueType')} in {entry.get('classes')} classes",
                    "featureCount": entry.get("features"),
                },
            )

    def build_public_layers(self) -> None:
        """The five layers actually drawn on the portal map."""
        for entry in self.public_layers:
            slug = entry.get("id")
            atlas_number = PUBLIC_LAYER_ATLAS_NUMBERS.get(slug)
            candidates = self.dataset_by_atlas_number.get(atlas_number, [])
            ds_id = candidates[0] if candidates else None
            if ds_id is None:
                self.warn(f"public map layer '{slug}' has no dataset for atlas number {atlas_number}")
                continue

            dist_id = f"uz:dist/{slug}-public-geojson"
            path = self.root / "PUBLISHED" / (entry.get("url") or "").lstrip("/")
            size = path.stat().st_size if path.exists() else None
            self.add_entity(
                {
                    "id": dist_id,
                    "type": "Distribution",
                    "label": f"{entry.get('title')} (published GeoJSON)",
                    "role": "web-vector",
                    "format": "GeoJSON",
                    "byteSize": size,
                    "storedName": Path(entry.get("url", "")).name,
                    "url": entry.get("url"),
                    "accessPolicy": "free",
                }
            )
            self.add(ds_id, "uz:hasDistribution", dist_id, agent=AGENT_PIPELINE,
                     confidence=1.0, status="asserted", method="extraction")

            layer_id = f"uz:layer/{slug}"
            self.add_entity(
                {
                    "id": layer_id,
                    "type": "MapLayer",
                    "label": entry.get("title"),
                    "geometryType": entry.get("geometry") or "unknown",
                    "featureCount": entry.get("features"),
                    "url": entry.get("url"),
                    "legend": None,
                }
            )
            self.add(layer_id, "uz:rendersDistribution", dist_id, agent=AGENT_PIPELINE,
                     confidence=1.0, status="asserted", method="extraction")

            bbox = self.geojson_bbox(path)
            if bbox:
                self.add(layer_id, "uz:spatialExtent", value=[round(v, 5) for v in bbox],
                         agent=AGENT_PIPELINE, confidence=1.0, status="asserted", method="measurement")
                self.assert_coverage(layer_id, bbox, entry.get("url"))

    # ------------------------------------------------------------------ external deliveries

    ROLE_BY_KIND = {
        "vector": "external-vector",
        "raster": "external-vector",
        "table": "external-table",
        "document": "external-document",
        "archive": "external-archive",
        "other": "external-archive",
    }

    @staticmethod
    def match_files(files_by_path: dict, patterns: list) -> list:
        """A pattern ending in / is a folder prefix; anything else is an exact path."""
        matched: dict[str, dict] = {}
        for pattern in patterns:
            if pattern.endswith("/"):
                for path, record in files_by_path.items():
                    if path.startswith(pattern):
                        matched[path] = record
            elif pattern in files_by_path:
                matched[pattern] = files_by_path[pattern]
        return sorted(matched.items())

    def build_external_sources(self) -> None:
        """Catalogue deliveries that are referenced in place rather than copied in.

        The mapping in vocab/external-sources.json says which files form a dataset
        and what it observes - a curator's judgement, asserted as such. Everything
        else here is measured: extents, fields, feature counts, class balance and
        station coordinates all come from the profiler and the detail extractor.
        """
        stations_by_slug: dict[str, list] = {}
        for station in self.external_details.get("stations", []):
            stations_by_slug.setdefault(station["datasetSlug"], []).append(station)
        class_labels = self.external_details.get("classLabels", {})

        for source in self.external_mapping.get("sources", []):
            inventory = self.inventories.get(source.get("inventory"))
            if inventory is None:
                self.warn(f"external source {source['id']}: inventory "
                          f"'{source.get('inventory')}' has not been profiled")
                continue
            delivery_root = inventory["source"].replace("\\", "/").rstrip("/")
            files_by_path = {record["path"]: record for record in inventory["files"]}

            for dataset in source["datasets"]:
                matches = self.match_files(files_by_path, dataset["match"])
                if not matches:
                    self.warn(f"external dataset {dataset.get('slug') or dataset.get('attachTo')}: "
                              f"no files matched in {source['id']}")
                    continue

                attach_to = dataset.get("attachTo")
                if attach_to:
                    if attach_to not in self.entities:
                        self.warn(f"external source {source['id']}: {attach_to} does not exist")
                        continue
                    ds_id = attach_to
                else:
                    slug = dataset["slug"]
                    ds_id = self.dataset_id(f"{source['id']}/{slug}", None, dataset["label"],
                                            preferred=slug)
                    self.add_entity({
                        "id": ds_id,
                        "type": "Dataset",
                        "label": dataset["label"],
                        "labels": {"en": dataset["label"]},
                        "sourceKey": f"{source['id']}/{slug}",
                        "atlasNumber": None,
                        "catalogId": None,
                        "repositoryId": None,
                        "description": dataset.get("note") or source.get("note") or "",
                    })

                extent_asserted = attach_to is not None
                for path, record in matches:
                    profile = record.get("profile") or {}
                    role = "source-package" if attach_to else self.ROLE_BY_KIND.get(
                        record["kind"], "external-archive")
                    dist_id = "uz:dist/" + slugify(
                        f"{ds_id.split('/')[-1]}-{Path(path).stem}-{sha_short(path)}", 60)
                    self.add_entity({
                        "id": dist_id,
                        "type": "Distribution",
                        "label": record["name"],
                        "role": role,
                        "format": (record["suffix"].lstrip(".") or "file").upper(),
                        "byteSize": record["bytes"],
                        "storedName": None,
                        "url": None,
                        "accessPolicy": source.get("accessPolicy", "internal"),
                        "externalPath": f"{delivery_root}/{path}",
                        "featureCount": profile.get("features"),
                        "crs": profile.get("crs"),
                    })
                    self.add(ds_id, "uz:hasDistribution", dist_id, agent=AGENT_CURATOR,
                             confidence=1.0, status="asserted", method="external-source-mapping",
                             evidence={"source": f"{source['id']}:{path}"})
                    self.add(dist_id, "uz:externalLocation", value=f"{delivery_root}/{path}",
                             agent=AGENT_PIPELINE, confidence=1.0, status="asserted",
                             method="measurement",
                             evidence={"source": inventory["name"],
                                       "note": "referenced in place, not copied into the project"})
                    for field in profile.get("fields") or []:
                        self.add(dist_id, "uz:hasField", value=field, agent=AGENT_PIPELINE,
                                 confidence=1.0, status="asserted", method="measurement")

                    crs = profile.get("crs")
                    if crs and "4326" not in str(crs):
                        self.add(ds_id, "uz:qualityFlag", value="crs-not-wgs84",
                                 agent=AGENT_PIPELINE, confidence=1.0, status="asserted",
                                 method="measurement",
                                 evidence={"source": path, "note": f"declared CRS is {crs}; "
                                                                  "reproject before overlaying"})
                    bounds = profile.get("bounds")
                    if bounds and len(bounds) == 4 and not extent_asserted:
                        self.add(ds_id, "uz:spatialExtent", value=[round(float(b), 5) for b in bounds],
                                 agent=AGENT_PIPELINE, confidence=1.0, status="asserted",
                                 method="measurement", evidence={"source": path})
                        self.assert_coverage(ds_id, bounds, path)
                        extent_asserted = True

                if attach_to:
                    continue  # the rest is already stated by the atlas record

                self.assert_external_semantics(ds_id, source, dataset)
                self.assert_external_stations(ds_id, dataset, stations_by_slug)
                self.assert_station_gaps(ds_id, dataset)
                labels = class_labels.get(dataset.get("slug"))
                if labels:
                    for name, count in labels["classes"].items():
                        self.add(ds_id, "uz:hasClassLabel", value=name, agent=AGENT_PIPELINE,
                                 confidence=1.0, status="asserted", method="measurement",
                                 evidence={"source": labels["sourceFile"], "featureCount": count,
                                           "note": f"{count / labels['total']:.1%} of "
                                                   f"{labels['total']:,} labelled samples"})
                    smallest = min(labels["classes"].values())
                    largest = max(labels["classes"].values())
                    if smallest * 100 < largest:
                        self.add(ds_id, "uz:qualityFlag", value="severe-class-imbalance",
                                 agent=AGENT_PIPELINE, confidence=1.0, status="asserted",
                                 method="measurement",
                                 evidence={"source": labels["sourceFile"],
                                           "score": round(largest / max(smallest, 1), 1),
                                           "note": "rarest class is more than 100x smaller than the "
                                                   "commonest; stratify before training"})

    def build_hydrography_sources(self) -> None:
        """Add the measured Uzbekistan HydroSHEDS relationship database.

        Feature-level routing stays in the GeoPackage/JSON projection where it
        can be queried without inflating the catalogue graph with tens of
        thousands of geometry nodes.  The canonical ontology records the three
        intellectual datasets, their source and derived distributions, map
        layers, lineage, coverage and curated meaning.
        """
        manifest = self.hydrography
        if not manifest:
            self.warn("HydroSHEDS reference has not been built; run npm run hydrography:build")
            return

        counts = manifest.get("counts", {})
        sources = manifest.get("sources", {})
        web = manifest.get("web", {})
        fields = manifest.get("fields", {})
        extent = manifest.get("extent")
        database_path = (manifest.get("database") or {}).get("path")
        licence = manifest.get("license")
        attribution = manifest.get("attribution")
        evidence = {
            "source": "ONTOLOGY/instances/hydrography.json",
            "note": manifest.get("selection", "Uzbekistan hydrography selection"),
        }

        configs = [
            {
                "slug": "hydrorivers-uzbekistan",
                "label": "HydroRIVERS river network — Uzbekistan",
                "description": "Hydrologically routed river reaches intersecting Uzbekistan, clipped to the national boundary while preserving native HydroRIVERS identifiers and downstream links.",
                "sourceKey": "hydrosheds/hydrorivers-v10-uzbekistan",
                "source": sources.get("rivers"),
                "sourceLabel": "HydroRIVERS v1.0 Asia FileGDB",
                "sourceFormat": "FileGDB",
                "web": web.get("rivers"),
                "webFile": "PUBLISHED/data/hydrography/rivers.geojson",
                "geometry": "line",
                "count": counts.get("rivers"),
                "fields": fields.get("rivers", []),
                "observes": ["uz:prop/river-network", "uz:prop/river-discharge"],
            },
            {
                "slug": "hydrolakes-uzbekistan",
                "label": "HydroLAKES water bodies — Uzbekistan",
                "description": "Lakes and reservoirs intersecting Uzbekistan, with native HydroLAKES identifiers and measured links to HydroBASINS level-12 catchments.",
                "sourceKey": "hydrosheds/hydrolakes-v10-uzbekistan",
                "source": sources.get("lakes"),
                "sourceLabel": "HydroLAKES v1.0 global FileGDB",
                "sourceFormat": "FileGDB",
                "web": web.get("lakes"),
                "webFile": "PUBLISHED/data/hydrography/lakes.geojson",
                "geometry": "polygon",
                "count": counts.get("lakes"),
                "fields": fields.get("lakes", []),
                "observes": ["uz:prop/surface-water-extent", "uz:prop/reservoir-volume"],
            },
            {
                "slug": "hydrobasins-level12-uzbekistan",
                "label": "HydroBASINS level-12 catchments — Uzbekistan",
                "description": "Level-12 Pfafstetter catchments from the BasinATLAS Uzbekistan extraction. This is the reference frame the river and lake layers are joined onto, and its HYBAS_ID is the key the 281 BasinATLAS attributes join on.",
                # The source key is frozen in identity-map.json and names the
                # dataset, not the package behind it; the package changed from the
                # lake-format extraction to BasinATLAS, the dataset did not.
                "sourceKey": "hydrosheds/hydrobasins-v1c-level12-uzbekistan",
                "source": sources.get("basins"),
                "sourceLabel": "Uzbekistan BasinATLAS extraction, level 12 (standard HydroBASINS format)",
                "sourceFormat": "GPKG",
                "web": web.get("basins"),
                "webFile": "PUBLISHED/data/hydrography/basins.geojson",
                "geometry": "polygon",
                "count": counts.get("basins"),
                "fields": fields.get("basins", []),
                "observes": ["uz:prop/drainage-basin"],
            },
        ]

        dataset_ids = {}
        for config in configs:
            ds_id = self.dataset_id(
                config["sourceKey"], None, config["label"], preferred=config["slug"]
            )
            dataset_ids[config["slug"]] = ds_id
            self.add_entity({
                "id": ds_id,
                "type": "Dataset",
                "label": config["label"],
                "labels": {"en": config["label"]},
                "sourceKey": config["sourceKey"],
                "atlasNumber": None,
                "catalogId": None,
                "repositoryId": None,
                "description": config["description"],
            })

            source_dist = f"uz:dist/{config['slug']}-source"
            self.add_entity({
                "id": source_dist,
                "type": "Distribution",
                "label": config["sourceLabel"],
                "role": "external-vector",
                "format": config["sourceFormat"],
                "byteSize": None,
                "storedName": None,
                "url": None,
                "accessPolicy": "free",
                "externalPath": config["source"],
            })
            database_dist = f"uz:dist/{config['slug']}-relationship-database"
            database_file = Path(database_path) if database_path else None
            self.add_entity({
                "id": database_dist,
                "type": "Distribution",
                "label": f"{config['label']} (relationship database)",
                "role": "web-vector",
                "format": "GeoPackage",
                "byteSize": database_file.stat().st_size if database_file and database_file.exists() else None,
                "storedName": "WORKSPACE/derived/hydrography/uzbekistan-hydrography.gpkg",
                "url": None,
                "accessPolicy": "free",
                "featureCount": config["count"],
                "crs": manifest.get("crs"),
            })
            web_dist = f"uz:dist/{config['slug']}-web"
            web_file = self.root / config["webFile"]
            self.add_entity({
                "id": web_dist,
                "type": "Distribution",
                "label": f"{config['label']} (web GeoJSON)",
                "role": "web-vector",
                "format": "GeoJSON",
                "byteSize": web_file.stat().st_size if web_file.exists() else None,
                "storedName": config["webFile"],
                "url": config["web"],
                "accessPolicy": "free",
                "featureCount": config["count"],
                "crs": manifest.get("crs"),
            })
            layer_id = f"uz:layer/{config['slug']}"
            self.add_entity({
                "id": layer_id,
                "type": "MapLayer",
                "label": config["label"],
                "geometryType": config["geometry"],
                "featureCount": config["count"],
                "url": config["web"],
                "legend": {"group": "Hydrography", "source": "HydroSHEDS"},
            })

            for distribution in (source_dist, database_dist, web_dist):
                self.add(ds_id, "uz:hasDistribution", distribution, agent=AGENT_PIPELINE,
                         confidence=1.0, status="asserted", method="hydrography-build",
                         evidence=evidence)
            if config["source"]:
                self.add(source_dist, "uz:externalLocation", value=config["source"],
                         agent=AGENT_PIPELINE, confidence=1.0, status="asserted",
                         method="measurement", evidence=evidence)
            self.add(database_dist, "uz:derivedFrom", source_dist, agent=AGENT_PIPELINE,
                     confidence=1.0, status="asserted", method="spatial-intersection",
                     evidence=evidence)
            self.add(web_dist, "uz:derivedFrom", database_dist, agent=AGENT_PIPELINE,
                     confidence=1.0, status="asserted", method="simplification",
                     evidence=evidence)
            self.add(layer_id, "uz:rendersDistribution", web_dist, agent=AGENT_PIPELINE,
                     confidence=1.0, status="asserted", method="portal-configuration")
            self.add(ds_id, "uz:belongsToTheme", "uz:theme/water", agent=AGENT_CURATOR,
                     confidence=1.0, status="asserted", method="curator-mapping", evidence=evidence)
            self.add(ds_id, "uz:hasAnalysisConcept", "uz:analysis/environmental-feature",
                     agent=AGENT_CURATOR, confidence=1.0, status="asserted",
                     method="curator-mapping", evidence=evidence)
            for concept in config["observes"]:
                self.add(ds_id, "uz:observes", concept, agent=AGENT_CURATOR,
                         confidence=1.0, status="asserted", method="curator-mapping",
                         evidence=evidence)
            self.add(ds_id, "uz:supportsUseCase", "uz:usecase/water-resource-allocation",
                     agent=AGENT_CURATOR, confidence=1.0, status="asserted",
                     method="curator-mapping", evidence=evidence)
            for subject in (ds_id, layer_id):
                self.add(subject, "uz:coversPlace", "uz:place/uzbekistan",
                         agent=AGENT_PIPELINE, confidence=1.0, status="asserted",
                         method="boundary-clip", evidence=evidence)
                if extent:
                    self.add(subject, "uz:spatialExtent", value=extent,
                             agent=AGENT_PIPELINE, confidence=1.0, status="asserted",
                             method="measurement", evidence=evidence)
            if licence:
                self.add(ds_id, "uz:license", value=licence, agent=AGENT_CURATOR,
                         confidence=1.0, status="asserted", method="curator-mapping",
                         evidence=evidence)
            if attribution:
                self.add(ds_id, "uz:attributedTo", value=attribution, agent=AGENT_CURATOR,
                         confidence=1.0, status="asserted", method="curator-mapping",
                         evidence=evidence)
            for field in config["fields"]:
                self.add(source_dist, "uz:hasField", value=field, agent=AGENT_PIPELINE,
                         confidence=1.0, status="asserted", method="measurement",
                         evidence=evidence)

        river_id = dataset_ids["hydrorivers-uzbekistan"]
        lake_id = dataset_ids["hydrolakes-uzbekistan"]
        basin_id = dataset_ids["hydrobasins-level12-uzbekistan"]
        for subject, related in [
            (river_id, lake_id), (lake_id, river_id),
            (river_id, basin_id), (basin_id, river_id),
            (lake_id, basin_id), (basin_id, lake_id),
        ]:
            self.add(subject, "uz:relatedTo", related, agent=AGENT_CURATOR,
                     confidence=1.0, status="asserted", method="curator-mapping",
                     evidence=evidence)

    def build_relationship_tables(self) -> None:
        """Register the measured feature topology without expanding it.

        The HydroSHEDS packages carry more than 126,000 links between basins,
        reaches and water bodies. Expanding them into assertions.json would bury
        the curated facts under measurements no human will ever review, and would
        mint tens of thousands of feature entities to point at.

        So each edge list is registered as one typed relationship-table
        Distribution instead. It names the predicate every row asserts, the
        feature types on each end, the columns holding the identifiers and the
        measured row count. The graph knows the links exist, what they mean and
        where to read them; the file that produced them stays the system of
        record, and the validator checks the declaration against the predicate
        registry.
        """
        tables = self.relationship_tables.get("tables", [])
        if not tables:
            self.warn("no relationship tables declared; feature topology is unregistered")
            return

        # A CSV the delivery ships already has a distribution, minted from the
        # file profile as a generic external table. Upgrade that record rather
        # than minting a second one for the same bytes.
        by_location = {}
        for entity in self.entities.values():
            if entity.get("type") != "Distribution":
                continue
            location = entity.get("externalPath") or entity.get("storedName") or ""
            if location:
                by_location[location.replace("\\", "/").lower()] = entity["id"]

        counts = self.relationship_counts
        registered = 0
        for table in tables:
            dataset = f"uz:ds/{table['dataset']}"
            if dataset not in self.entities:
                self.warn(
                    f"relationship table {table['id']} names dataset {table['dataset']}, "
                    "which is not in the graph"
                )
                continue

            container = table["container"]
            row_count = self.count_relationship_rows(table, counts)
            if row_count is None:
                self.warn(
                    f"relationship table {table['id']}: no row count available; "
                    f"{container} has not been built"
                )
                continue

            # Only a standalone file can be identified by its path. Several
            # tables share one GeoPackage, so matching those on the container
            # would collapse them onto each other and onto the database
            # distribution that holds them.
            existing = None
            if not table.get("containerTable"):
                existing = match_by_path_tail(container, by_location)
            dist_id = existing or f"uz:dist/{table['id']}"

            local = self.root / container
            evidence = {
                "source": "ONTOLOGY/vocab/relationship-tables.json",
                "note": table.get("note", table["label"]),
            }
            self.add_entity({
                "id": dist_id,
                "type": "Distribution",
                "label": table["label"],
                "role": "relationship-table",
                "format": table["format"],
                "byteSize": local.stat().st_size if local.exists() else None,
                # A delivery CSV is already located by its externalPath and must
                # stay referenced rather than copied; only a table this build
                # writes itself gets an in-repo storedName. Its access policy is
                # the curator's, set when the delivery was mapped, and upgrading
                # the record to a typed table must not relax it.
                "storedName": None if existing else container,
                "url": None,
                "accessPolicy": None if existing else "free",
                "predicate": table["predicate"],
                "subjectType": table["subjectType"],
                "objectType": table["objectType"],
                "subjectColumn": table["subjectColumn"],
                "objectColumn": table["objectColumn"],
                # The file this table stands for, repo-relative. storedName and
                # externalPath say where the bytes are, which depends on the
                # machine that profiled them; this says which declared table it
                # is, so nothing downstream has to match paths by guesswork.
                "container": container,
                "scopeColumn": table.get("scopeColumn"),
                "measureColumn": table.get("measureColumn"),
                "measureUnitColumn": table.get("measureUnitColumn"),
                "containerTable": table.get("containerTable"),
                "identifierScheme": table["identifierScheme"],
                "rowCount": row_count,
            })
            self.add(dataset, "uz:hasDistribution", dist_id, agent=AGENT_PIPELINE,
                     confidence=1.0, status="asserted", method="relationship-table",
                     evidence=evidence)
            if table.get("containerTable"):
                # A table inside the hydrography GeoPackage is a product of the
                # same build that wrote the geometry it links.
                database = f"uz:dist/{table['dataset']}-relationship-database"
                if database in self.entities:
                    self.add(dist_id, "uz:derivedFrom", database, agent=AGENT_PIPELINE,
                             confidence=1.0, status="asserted", method="hydrography-build",
                             evidence=evidence)
            registered += 1

        total = sum(
            e.get("rowCount", 0) for e in self.entities.values()
            if e.get("role") == "relationship-table"
        )
        self.log(f"  relationship tables: {registered} registered, {total:,} links declared")

    def count_relationship_rows(self, table: dict, counts: dict):
        """Measure the table, or read the count the producing build already measured."""
        source = table.get("rowCountFrom")
        if source:
            value = counts.get(source["manifest"], {}).get(source["key"])
            return int(value) if value is not None else None
        path = self.root / table["container"]
        if not path.exists():
            return None
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return max(sum(1 for _ in handle) - 1, 0)  # discount the header

    def assert_hydroatlas_attributes(self) -> None:
        """Say what BasinATLAS measures, one property at a time.

        The dataset carries 281 attribute columns. Registering it as observing a
        single 'drainage basin' concept hides that it also holds temperature,
        precipitation, irrigated extent, population and two dozen other measured
        properties the portal already has concepts for. The decoding comes from
        the official catalogue, so each link cites the columns behind it.
        """
        columns = read_json(self.root / "ONTOLOGY" / "instances" / "hydroatlas-columns.json", {})
        decoded = columns.get("columns") or {}
        if not decoded:
            return
        target = "uz:ds/basinatlas-uz-v10"
        if target not in self.entities:
            return

        by_property: dict[str, list[str]] = {}
        for column, meaning in decoded.items():
            if meaning.get("property"):
                by_property.setdefault(meaning["property"], []).append(column)

        for concept, source_columns in sorted(by_property.items()):
            self.add(
                target, "uz:observes", concept, agent=AGENT_PIPELINE, confidence=1.0,
                status="asserted", method="hydroatlas-catalog",
                evidence={
                    "source": columns.get("catalogSource", "BasinATLAS catalogue"),
                    "matchedTerms": sorted(source_columns)[:6],
                    "featureCount": len(source_columns),
                    "note": f"{len(source_columns)} BasinATLAS columns measure this property",
                },
            )
        self.log(f"  hydroatlas: {len(by_property)} properties from {len(decoded)} decoded columns")

    def assert_external_semantics(self, ds_id: str, source: dict, dataset: dict) -> None:
        evidence = {"source": "external-sources.json",
                    "note": dataset.get("note") or source.get("note") or "curator mapping"}
        if dataset.get("theme"):
            self.add(ds_id, "uz:belongsToTheme", dataset["theme"], agent=AGENT_CURATOR,
                     confidence=1.0, status="asserted", method="external-source-mapping",
                     evidence=evidence)
        if dataset.get("analysis"):
            self.add(ds_id, "uz:hasAnalysisConcept", dataset["analysis"], agent=AGENT_CURATOR,
                     confidence=1.0, status="asserted", method="external-source-mapping",
                     evidence=evidence)
        for concept in dataset.get("observes", []):
            self.add(ds_id, "uz:observes", concept, agent=AGENT_CURATOR, confidence=1.0,
                     status="asserted", method="external-source-mapping", evidence=evidence)
        for concept in dataset.get("useCases", []):
            self.add(ds_id, "uz:supportsUseCase", concept, agent=AGENT_CURATOR, confidence=1.0,
                     status="asserted", method="external-source-mapping", evidence=evidence)
        for place in dataset.get("places", []):
            self.add(ds_id, "uz:coversPlace", place, agent=AGENT_CURATOR, confidence=1.0,
                     status="asserted", method="external-source-mapping", evidence=evidence)
        interval = dataset.get("temporal") or source.get("temporal")
        if interval:
            self.add(ds_id, "uz:temporalCoverage", value=interval, agent=AGENT_CURATOR,
                     confidence=1.0, status="asserted", method="external-source-mapping",
                     evidence=evidence)
        if source.get("license"):
            self.add(ds_id, "uz:license", value=source["license"], agent=AGENT_CURATOR,
                     confidence=1.0, status="asserted", method="external-source-mapping",
                     evidence=evidence)
        if source.get("attribution"):
            self.add(ds_id, "uz:attributedTo", value=source["attribution"], agent=AGENT_CURATOR,
                     confidence=1.0, status="asserted", method="external-source-mapping",
                     evidence=evidence)
        for flag in list(source.get("qualityFlags", [])) + list(dataset.get("qualityFlags", [])):
            self.add(ds_id, "uz:qualityFlag", value=flag, agent=AGENT_CURATOR, confidence=1.0,
                     status="asserted", method="external-source-mapping", evidence=evidence)

    def assert_station_gaps(self, ds_id: str, dataset: dict) -> None:
        gap = (self.external_details.get("stationGaps") or {}).get(dataset.get("slug"))
        if not gap:
            return
        self.add(ds_id, "uz:qualityFlag", value="stations-missing-coordinates",
                 agent=AGENT_PIPELINE, confidence=1.0, status="asserted", method="measurement",
                 evidence={"source": gap["sourceFile"],
                           "featureCount": gap["missingCoordinates"],
                           "note": f"{gap['missingCoordinates']} of {gap['totalRows']} rows carry no "
                                   "usable coordinate and cannot be mapped"})

    def assert_external_stations(self, ds_id: str, dataset: dict, stations_by_slug: dict) -> None:
        for station in stations_by_slug.get(dataset.get("slug"), []):
            self.add_entity({
                "id": station["id"],
                "type": "MonitoringStation",
                "label": station["label"],
                "network": station["network"],
                "stationKey": station.get("stationKey"),
                "stationClass": station.get("stationClass"),
                "longitude": station["longitude"],
                "latitude": station["latitude"],
            })
            self.add(ds_id, "uz:operatesStation", station["id"], agent=AGENT_PIPELINE,
                     confidence=1.0, status="asserted", method="measurement",
                     evidence={"source": station["sourceFile"]})

    @staticmethod
    def geojson_bbox(path: Path):
        if not path.exists():
            return None
        data = read_json(path)
        if not data:
            return None
        xs: list[float] = []
        ys: list[float] = []

        def walk(coords):
            if not coords:
                return
            if isinstance(coords[0], (int, float)):
                xs.append(float(coords[0]))
                ys.append(float(coords[1]))
                return
            for part in coords:
                walk(part)

        for feature in data.get("features", []):
            geometry = feature.get("geometry") or {}
            walk(geometry.get("coordinates"))
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def assert_coverage(self, subject: str, bbox, source: str) -> None:
        west, south, east, north = (float(v) for v in bbox)
        self.add(subject, "uz:coversPlace", "uz:place/uzbekistan", agent=AGENT_PIPELINE,
                 confidence=0.95, status="asserted", method="extent-test",
                 evidence={"source": source, "note": "measured extent intersects Uzbekistan"})
        overshoot = max(
            UZ_BBOX[0] - west, UZ_BBOX[1] - south, east - UZ_BBOX[2], north - UZ_BBOX[3]
        )
        if overshoot > EXTENT_TOLERANCE_DEG:
            self.add(subject, "uz:coversPlace", "uz:place/central-asia", agent=AGENT_PIPELINE,
                     confidence=0.9, status="asserted", method="extent-test",
                     evidence={"source": source, "score": round(overshoot, 3),
                               "note": "measured extent reaches beyond Uzbekistan"})
            self.add(subject, "uz:qualityFlag", value="extent-exceeds-uzbekistan",
                     agent=AGENT_PIPELINE, confidence=0.9, status="asserted", method="extent-test",
                     evidence={"source": source, "score": round(overshoot, 3),
                               "note": "national statistics computed from this layer would include "
                                       "territory outside Uzbekistan"})

    # ------------------------------------------------------------------ semantics

    def seed_semantics(self) -> None:
        """Lexical seeding of observes / analysis concept / temporal coverage / use cases."""
        matching = self.rules["matching"]
        label_index: list[tuple[str, str, bool]] = []
        for concept in self.properties:
            label_index.append((normalise_text(concept["prefLabel"]).strip(), concept["id"], True))
            for alt in concept.get("altLabels", []):
                label_index.append((normalise_text(alt).strip(), concept["id"], False))

        # Single-valued predicates already settled by the source or by a curator
        # mapping are not up for re-inference; the rules would otherwise publish a
        # second value and break cardinality.
        settled = {
            (a["subject"], a["predicate"])
            for a in self.assertions.values()
            if a["status"] == "asserted"
        }

        datasets = [e for e in self.entities.values() if e["type"] == "Dataset"]
        for dataset in datasets:
            ds_id = dataset["id"]
            text_parts = [dataset.get("label", ""), (dataset.get("labels") or {}).get("ru", "")]
            for dist_id, fields in self.fields_by_dataset(ds_id):
                text_parts.extend(fields)
            haystack = " " + normalise_text(" ".join(p for p in text_parts if p)) + " "

            hits: dict[str, dict] = {}
            for label, concept_id, is_pref in label_index:
                if not term_matches(haystack, label):
                    continue
                score = matching["labelMatchBase"] + (matching["prefLabelBonus"] if is_pref else 0.0)
                entry = hits.setdefault(concept_id, {"score": 0.0, "terms": []})
                entry["terms"].append(label)
                entry["score"] = max(entry["score"], score)
            for rule in self.rules["propertyTerms"]:
                for term in rule["terms"]:
                    if term_matches(haystack, normalise_text(term)):
                        entry = hits.setdefault(rule["concept"], {"score": 0.0, "terms": []})
                        entry["terms"].append(term)
                        entry["score"] = max(entry["score"], rule["weight"])
                        break
            for concept_id, hit in hits.items():
                score = min(matching["maxConfidence"],
                            hit["score"] + (matching["multiTermBonus"] if len(hit["terms"]) > 1 else 0.0))
                self.add(
                    ds_id,
                    "uz:observes",
                    concept_id,
                    agent=AGENT_RULES,
                    confidence=score,
                    method="lexical-rule",
                    evidence={"source": "title+fields", "matchedTerms": sorted(set(hit["terms"]))[:6]},
                )

            interval = self.parse_interval(dataset)
            if interval and (ds_id, "uz:temporalCoverage") not in settled:
                self.add(ds_id, "uz:temporalCoverage", value=interval, agent=AGENT_RULES,
                         confidence=0.85, method="year-parse",
                         evidence={"source": "title", "note": "years parsed from the source title"})

            if (ds_id, "uz:hasAnalysisConcept") not in settled:
                concept_id, weight, terms = self.pick_analysis_concept(haystack, interval)
                self.add(ds_id, "uz:hasAnalysisConcept", concept_id, agent=AGENT_RULES,
                         confidence=weight, method="lexical-rule",
                         evidence={"source": "title", "matchedTerms": terms})

            observed = {a["object"] for a in self.assertions.values()
                        if a["subject"] == ds_id and a["predicate"] == "uz:observes"}
            for rule in self.rules["useCaseFromProperty"]:
                if rule["property"] in observed:
                    self.add(ds_id, "uz:supportsUseCase", rule["usecase"], agent=AGENT_RULES,
                             confidence=rule["weight"], method="property-inference",
                             evidence={"source": "uz:observes", "matchedTerms": [rule["property"]]})

    def fields_by_dataset(self, ds_id: str):
        for assertion in self.assertions.values():
            if assertion["subject"] != ds_id or assertion["predicate"] != "uz:hasDistribution":
                continue
            dist_id = assertion["object"]
            fields = [a["value"] for a in self.assertions.values()
                      if a["subject"] == dist_id and a["predicate"] == "uz:hasField"]
            if fields:
                yield dist_id, fields

    @staticmethod
    def parse_interval(dataset: dict):
        text = f"{dataset.get('label', '')} {(dataset.get('labels') or {}).get('ru', '')}"
        years = sorted({int(y) for y in YEAR_RE.findall(text)})
        if not years:
            return None
        if len(years) == 1:
            return {"start": years[0], "end": years[0]}
        return {"start": years[0], "end": years[-1]}

    def pick_analysis_concept(self, haystack: str, interval):
        rules = sorted(self.rules["analysisRules"], key=lambda r: -r["priority"])
        spans_years = bool(interval and interval["end"] > interval["start"])
        for rule in rules:
            if rule.get("default"):
                continue
            matched = [t for t in rule.get("terms", []) if normalise_text(t).strip() in haystack]
            if matched:
                return rule["concept"], rule["weight"], matched[:5]
            if rule.get("requiresIntervalOrTerm") and spans_years:
                return rule["concept"], rule["weight"] - 0.1, ["multi-year interval"]
        default = next(r for r in rules if r.get("default"))
        return default["concept"], default["weight"], []

    # ------------------------------------------------------------------ merging

    def merge_preserved_assertions(self) -> None:
        """Keep curator decisions and model proposals across rebuilds.

        A rebuild regenerates source, pipeline and rule assertions. Anything a
        human reviewed, and anything produced by another agent (model proposals,
        hand-written curator facts), is carried over. A reviewed assertion always
        wins over the freshly generated one with the same subject/predicate/object.
        """
        instances = self.root / "ONTOLOGY" / "instances"
        previous = read_json(instances / "assertions.json", {"assertions": []})["assertions"]
        curated = read_json(instances / "curated-assertions.json", {"assertions": []})["assertions"]
        proposals = read_json(instances / "proposals.json", {"assertions": []})["assertions"]

        entity_ids = set(self.entities)
        concept_ids = {c["id"] for c in
                       self.properties + self.themes + self.analysis + self.usecases + self.places}
        known = entity_ids | concept_ids

        generated_agents = {AGENT_SOURCE, AGENT_PIPELINE, AGENT_RULES}
        carried = 0
        dropped = 0
        for record in previous + proposals + curated:
            if record["subject"] not in known:
                dropped += 1
                continue
            if record.get("object") and record["object"] not in known:
                dropped += 1
                continue
            reviewed = bool(record.get("reviewedBy"))
            from_other_agent = record.get("assertedBy") not in generated_agents
            if not reviewed and not from_other_agent:
                continue  # regenerated this run
            existing = self.assertions.get(record["id"])
            if existing and not reviewed:
                continue
            merged = dict(record)
            if existing:
                merged["evidence"] = record.get("evidence") or existing.get("evidence")
            self.assertions[record["id"]] = merged
            carried += 1
        if dropped:
            self.warn(f"{dropped} preserved assertions dropped: subject or object no longer exists")
        self.log(f"  carried over {carried} reviewed or externally asserted facts")

    # ------------------------------------------------------------------ output

    def portal_graph(self) -> dict:
        published = [a for a in self.assertions.values() if a["status"] == "asserted"]
        by_subject: dict[str, list[dict]] = {}
        for assertion in published:
            by_subject.setdefault(assertion["subject"], []).append(assertion)

        nodes = []
        for entity in self.entities.values():
            if entity["type"] != "Dataset":
                continue
            facts = by_subject.get(entity["id"], [])
            theme = next((f["object"] for f in facts if f["predicate"] == "uz:belongsToTheme"), None)
            analysis = next((f["object"] for f in facts if f["predicate"] == "uz:hasAnalysisConcept"), None)
            observes = [
                {"concept": f["object"], "confidence": f["confidence"], "by": f["assertedBy"],
                 "reviewed": bool(f.get("reviewedBy"))}
                for f in facts if f["predicate"] == "uz:observes"
            ]
            nodes.append(
                {
                    "id": entity["id"],
                    "label": entity["label"],
                    "sourceTitle": (entity.get("labels") or {}).get("ru"),
                    "atlasNumber": entity.get("atlasNumber"),
                    "catalogId": entity.get("catalogId"),
                    "theme": theme,
                    "analysis": analysis,
                    "observes": sorted(observes, key=lambda o: -o["confidence"])[:6],
                    "useCases": sorted({f["object"] for f in facts if f["predicate"] == "uz:supportsUseCase"}),
                    "places": sorted({f["object"] for f in facts if f["predicate"] == "uz:coversPlace"}),
                    "temporal": next((f["value"] for f in facts if f["predicate"] == "uz:temporalCoverage"), None),
                    "license": next((f["value"] for f in facts if f["predicate"] == "uz:license"), None),
                    "attribution": next((f["value"] for f in facts if f["predicate"] == "uz:attributedTo"), None),
                    "extent": next((f["value"] for f in facts if f["predicate"] == "uz:spatialExtent"), None),
                    "flags": sorted({f["value"] for f in facts if f["predicate"] == "uz:qualityFlag"}),
                    "distributions": sum(1 for f in facts if f["predicate"] == "uz:hasDistribution"),
                    "related": [f["object"] for f in facts if f["predicate"] == "uz:relatedTo"],
                }
            )

        def trim(concepts, keys=("id", "prefLabel", "definition", "color", "broader")):
            return [{k: c[k] for k in keys if k in c} for c in concepts]

        return {
            "version": "1.0",
            "generatedAt": self.generated_at,
            "promoteThreshold": PROMOTE_THRESHOLD,
            "vocabularies": {
                "themes": trim(self.themes),
                "analysis": trim(self.analysis),
                "properties": trim(self.properties),
                "usecases": trim(self.usecases),
                "places": trim(self.places),
            },
            "agents": [{"id": a["id"], "label": a["label"], "kind": a["agentKind"],
                        "trustTier": a["trustTier"]} for a in self.agents],
            "datasets": sorted(nodes, key=lambda n: (n["atlasNumber"] is None, n["atlasNumber"] or 0)),
            "stations": [
                {"id": e["id"], "label": e["label"], "network": e["network"],
                 "stationClass": e.get("stationClass"),
                 "lon": e["longitude"], "lat": e["latitude"]}
                for e in sorted(self.entities.values(), key=lambda e: e["id"])
                if e["type"] == "MonitoringStation"
            ],
            "counts": {
                "datasets": len(nodes),
                "atlasPackages": sum(1 for n in nodes if n["catalogId"]),
                "stations": sum(1 for e in self.entities.values() if e["type"] == "MonitoringStation"),
                "publishedAssertions": len(published),
                "proposedAssertions": sum(1 for a in self.assertions.values() if a["status"] == "proposed"),
                # The measured topology is held outside the graph, so the portal
                # cannot count it by walking assertions; carry the totals across.
                "relationshipTables": sum(
                    1 for e in self.entities.values() if e.get("role") == "relationship-table"),
                "relationshipLinks": sum(
                    e.get("rowCount", 0) for e in self.entities.values()
                    if e.get("role") == "relationship-table"),
            },
            # What the hydrography build measured, so the portal can describe the
            # explorer without fetching its 7 MB relationship graph to count rows.
            "hydrography": (self.hydrography or {}).get("counts", {}),
            # Proposals and rejections are deliberately not inlined here: this is
            # what the portal renders, and the portal renders facts. The review
            # table fetches the companion file instead, so the front page never
            # pays for rows it does not show.
            "triples": "/data/ontology-triples.json",
        }

    def triple_table(self) -> dict:
        """Every assertion, flat, for the relationship table.

        The portal graph publishes only what is asserted, which is right for a
        page that presents facts. A review table has the opposite job: the
        proposals and the rejections are its most interesting rows, because they
        are the backlog and the negative labels. So they get their own file and
        the portal keeps fetching only what it renders.
        """
        labels = {e["id"]: e["label"] for e in self.entities.values()}
        types = {e["id"]: e["type"] for e in self.entities.values()}
        for scheme in (self.themes, self.properties, self.analysis, self.usecases, self.places):
            for concept in scheme:
                labels[concept["id"]] = concept["prefLabel"]
                types[concept["id"]] = "Concept"

        predicates = read_json(
            self.root / "ONTOLOGY" / "vocab" / "predicates.json", {"predicates": []}
        )["predicates"]

        rows = [
            {
                "id": a["id"],
                "s": a["subject"],
                "p": a["predicate"],
                "o": a.get("object"),
                "v": a.get("value"),
                "st": a["status"],
                "a": a["assertedBy"],
                "c": a["confidence"],
                "r": a.get("reviewedBy"),
                "m": a.get("method"),
            }
            for a in sorted(self.assertions.values(),
                            key=lambda a: (a["subject"], a["predicate"], a["id"]))
        ]

        used = {row["s"] for row in rows} | {row["o"] for row in rows if row["o"]}
        counts: dict[str, int] = {"total": len(rows)}
        for row in rows:
            counts[row["st"]] = counts.get(row["st"], 0) + 1
        return {
            "version": "1.0",
            "generatedAt": self.generated_at,
            "promoteThreshold": PROMOTE_THRESHOLD,
            "counts": counts,
            "predicates": [
                {"id": p["id"], "label": p["label"], "definition": p["definition"],
                 "cardinality": p["cardinality"],
                 "mlProposable": bool(p.get("mlProposable")),
                 "viaRelationshipTable": bool(p.get("viaRelationshipTable"))}
                for p in predicates
            ],
            "agents": [{"id": a["id"], "label": a["label"], "kind": a["agentKind"],
                        "trustTier": a["trustTier"]} for a in self.agents],
            "labels": {k: v for k, v in sorted(labels.items()) if k in used},
            "types": {k: v for k, v in sorted(types.items()) if k in used},
            "triples": rows,
        }

    def save(self) -> dict:
        instances = self.root / "ONTOLOGY" / "instances"
        write_json(instances / "identity-map.json", self.identity_map)
        write_json(
            instances / "entities.json",
            {"version": "1.0", "generatedAt": self.generated_at,
             "entities": sorted(self.entities.values(), key=lambda e: (e["type"], e["id"]))},
        )
        write_json(
            instances / "assertions.json",
            {"version": "1.0", "generatedAt": self.generated_at,
             "assertions": sorted(self.assertions.values(), key=lambda a: (a["subject"], a["predicate"], a["id"]))},
        )
        graph = self.portal_graph()
        write_json(self.root / "PUBLISHED" / "data" / "ontology-graph.json", graph)
        write_json_rows(self.root / "PUBLISHED" / "data" / "ontology-triples.json",
                        self.triple_table(), "triples")
        return graph


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    builder = GraphBuilder(root, quiet=args.quiet)
    builder.log("Building ontology instance...")
    builder.build()
    graph = builder.save()

    by_type: dict[str, int] = {}
    for entity in builder.entities.values():
        by_type[entity["type"]] = by_type.get(entity["type"], 0) + 1
    by_status: dict[str, int] = {}
    for assertion in builder.assertions.values():
        by_status[assertion["status"]] = by_status.get(assertion["status"], 0) + 1

    builder.log("  entities:   " + ", ".join(f"{k} {v}" for k, v in sorted(by_type.items())))
    builder.log("  assertions: " + ", ".join(f"{k} {v}" for k, v in sorted(by_status.items())))
    builder.log(f"  portal graph: {graph['counts']['datasets']} datasets")
    if builder.warnings:
        builder.log(f"  {len(builder.warnings)} warnings:")
        for warning in builder.warnings[:12]:
            builder.log(f"    - {warning}")
        if len(builder.warnings) > 12:
            builder.log(f"    ... and {len(builder.warnings) - 12} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
