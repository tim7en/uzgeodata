# UzGeoData ontology

A working ontology over the 134 packages of the Uzbekistan environmental atlas,
built so that machine learning can strengthen it over time without ever being
able to quietly corrupt it.

The portal previously derived its "ontology" from a regex over dataset titles at
render time. Nothing was stored, nothing could be corrected, and nothing could be
learned from. This package replaces that with a stored graph of typed, provenanced,
confidence-scored facts.

```
ontology/
  schema/      JSON Schema for concepts, predicates, entities, assertions
  vocab/       the controlled vocabularies and the seeding rules
  instances/   the built graph, the curator's decisions, the model's proposals
scripts/ontology/
  build_ontology.py      project the real registries into the graph
  propose_assertions.py  the model: propose new facts, calibrated
  review_assertions.py   the curator: accept, reject, or state a fact
  validate_ontology.py   schema + integrity + ML guard rails
```

## The model

Five entity types, and everything relational between them is an assertion.

| Entity | What it is | Example |
| --- | --- | --- |
| `Dataset` | the intellectual resource | `uz:ds/a205-earthquakes-19902024` |
| `Distribution` | one concrete encoding of it | the LPKX package, a GeoJSON, a PNG preview |
| `MapLayer` | what the browser actually draws | `uz:layer/earthquakes` |
| `Concept` | a term in a controlled vocabulary | `uz:prop/seismicity`, `uz:theme/water` |
| `MonitoringStation` | a fixed installation that measures | `uz:station/meteo-408724` |
| `Agent` | anything that can make a claim | the atlas, a rule, a model, a curator |

Separating these four data-side types is the point. A `.lpkx` package is not a
dataset, and the GeoJSON extracted from its first readable layer is not the same
thing as the dataset either — it is one derivative, and the graph records which
choice the pipeline made to produce it.

### Identity

Dataset IDs are minted **once** from the source filename and then frozen in
`instances/identity-map.json`. Two ideas that look like identity are not:

- the public catalogue's `atlas-001…134` is assigned by directory sort order, so
  it moves whenever a file is added;
- `atlasNumber` is not unique — ten Palmer Drought Severity Index packages share
  three numbers.

### Assertions

Every relational fact looks like this:

```json
{
  "id": "uz:a/8f2c…", "subject": "uz:ds/a205-earthquakes-19902024",
  "predicate": "uz:observes", "object": "uz:prop/seismicity",
  "status": "asserted", "confidence": 0.9,
  "assertedBy": "uz:agent/rule-lexical-v1", "method": "lexical-rule",
  "evidence": {"source": "title+fields", "matchedTerms": ["earthquake", "землетрясен"]},
  "reviewedBy": null, "reviewedAt": null
}
```

`status` is the lifecycle: `proposed` → `asserted` or `rejected`. Only `asserted`
facts reach the portal. **Rejections are kept**, because a negative label is worth
as much to the next model as a positive one.

`uz:qualityFlag` carries known defects instead of hiding them. The seismic
catalogue's measured extent reaches into Afghanistan, Tajikistan and Kyrgyzstan,
so the graph says so, and any national statistic computed from it inherits the
caveat.

## The reinforcement loop

```
   rules seed          model proposes         curator decides
        │                     │                      │
        ▼                     ▼                      ▼
  weak labels ───────► calibrated candidates ───► reviewed facts
        ▲                                            │
        └──────────── training set grows ◄───────────┘
```

1. **Seed.** `build_ontology.py` reads the catalogue, the private repository, the
   extracted-layer registry and the polygonised-raster registry. Structural facts
   (distributions, lineage, fields, extents) are measured, not guessed. Semantic
   facts are matched from the vocabulary labels and the rules in
   `vocab/lexical-rules.json` — rules live as data so a curator can edit them.
2. **Propose.** `propose_assertions.py` combines nearest-neighbour label
   propagation over reviewed datasets with concept-definition similarity, then
   calibrates the score into a confidence by leave-one-out evaluation on the
   labelled set. It never re-proposes a triple that was already stated or rejected.
3. **Review.** `review_assertions.py` accepts, rejects, or states a missing fact.
   Decisions land in `instances/curated-assertions.json` and are merged back on
   top of anything a rebuild regenerates — rules and models can be re-run freely
   without ever overwriting a human.
4. **Repeat.** The labelled set grows, calibration tightens, proposals improve.

Measured on the first two cycles of this repository: 30 curator decisions moved
leave-one-out top-1 precision from 0.591 to 0.635, and removed 21 similarity
artefacts from the candidate pool permanently.

### Guard rails

A model is allowed to write into this graph only because the validator can refuse
it. Every rule below is covered by a test in `tests/test_ontology.py`:

- predicates are typed: domain, range, scheme and cardinality are all enforced;
- a predicate must be marked `mlProposable` before a model may assert it —
  structural facts like `uz:hasDistribution` are pipeline-only;
- heuristic and predicted assertions must carry evidence;
- an unreviewed model assertion cannot be published below the promote threshold
  (`PROMOTE_THRESHOLD`, currently 0.75);
- a rejection must name its reviewer;
- every subject, object and agent must resolve.

Validation warnings are the curation backlog rather than failures. They currently
surface three real data problems: one public catalogue record with no counterpart
in the private repository, and one repository record whose category (`Atlas`) is a
format rather than a domain.

## Taking in an external delivery

Data arrives as a folder someone hands over, far too large to copy into the repo
and with no usable metadata of its own. The intake is three steps and no manual
cataloguing:

```bash
npm run ontology:profile -- "C:/Users/User/Desktop/MAPS" \
    --name maps-drop-2026-08 --out ontology/instances/external/maps-drop.json
# add a block to ontology/vocab/external-sources.json saying what the files are
npm run ontology:details       # station coordinates, training-set class balance
npm run ontology:build
```

**Profile** measures rather than trusts: driver, CRS, geometry type, feature
count, fields and extent for every vector file, sheet names and headers for every
workbook, and a flag against anything the project already holds. It reads headers
where the format allows, so a 500 MB GeoJSON is scanned, not loaded.

**Map** is the only manual step, and it is deliberately manual: a human decides
that these files are one dataset, that it observes these properties, and that it
carries this licence. Those assertions are attributed to `uz:agent/curator`. The
build measures everything else and attributes it to the pipeline, so the two are
never confused.

**Reference, don't copy.** External files stay where they are; their distributions
carry `uz:externalLocation` and no `storedName`. A 1.02 GB package can be
catalogued, licensed and linked without entering the repository.

Licence and attribution are first-class (`uz:license`, `uz:attributedTo`) because
ODbL and restricted-internal terms both travel with every derivative made from the
data, and the portal has to be able to display the credit.

The August 2026 delivery added 34 datasets, 190 monitoring stations and 130
distributions: an OpenStreetMap extract, a cadastre export, Uzhydromet station
series, agricultural and fertiliser statistics, and a labelled land-cover training
set of 198,615 polygons. It also supplied the 1.02 GB package behind atlas
number 92, which the ontology had been reporting as a dataset with no distribution.

## Upgrading the model

`propose_assertions.py` isolates the backend in `embed()`, which returns one
dataset matrix and one concept matrix. TF-IDF character n-grams are the current
choice because they handle Russian inflection and bilingual titles with no
network call and no training. Swapping in sentence embeddings, or satellite
embeddings such as AlphaEarth for the layers themselves, means replacing that one
method — the calibration, the guard rails, the review workflow and the portal
projection are unaffected.

The natural next targets, in order of value: `uz:observes` on the packages that
have no vector fields yet, `uz:coversPlace` at region rather than country level
once administrative boundaries are ingested, and `uz:relatedTo` from layer
statistics rather than titles.

## Commands

```bash
npm run ontology:profile -- <folder> --name <id> --out ontology/instances/external/<id>.json
npm run ontology:details     # station coordinates and class balances from a delivery
npm run ontology:build       # rebuild the graph from the registries
npm run ontology:validate    # schema + integrity + guard rails
npm run ontology:propose     # run the model, write calibrated proposals
npm run ontology:review -- --list --limit 20
npm run ontology:review -- --accept uz:a/…  --note "checked against the source"
python -m pytest tests/test_ontology.py
```

The build also writes `public/data/ontology-graph.json`: the published projection,
carrying only `asserted` facts, each with the agent and confidence behind it, ready
for the ontology explorer to render provenance instead of a regex.
