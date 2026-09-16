"""Inventory every registered variable/product without acquisition or invented dates.

The output is public metadata. Private job state and schedules live in WORKSPACE.
Run after data publication; the browser computes age against its current clock.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import variables


def read(root, name, default=None):
    path = root / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else (default or {})


def table_variables(root, table):
    """Read each distinct variable and its own observed time range, not a table max.

    A table with no named variable still gets a row for its measure/relationship.
    Missing registered tables remain visible. No filesystem mtime is a data date.
    """
    path = root / table["container"]
    found = {}
    if path.is_file() and path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if table.get("scopeValue") is not None and row.get(table.get("scopeColumn")) != str(table["scopeValue"]):
                    continue
                name = row.get("variable") or table.get("measureColumn") or "relationship"
                entry = found.setdefault(name, {"unit": row.get(table.get("measureUnitColumn", "unit")),
                                                "first": None, "last": None, "rows": 0})
                entry["rows"] += 1
                # Only year/date observation dimensions, never a climatology's month.
                stamp = row.get("date")
                if not stamp and row.get("year"):
                    try:
                        stamp = f"{int(row['year']):04d}"
                        if row.get("month"):
                            stamp += f"-{int(row['month']):02d}"
                    except ValueError:
                        stamp = None
                if stamp:
                    entry["first"] = min(entry["first"] or stamp, stamp)
                    entry["last"] = max(entry["last"] or stamp, stamp)
    return found or {table.get("measureColumn") or "relationship": {"first": None, "last": None, "rows": 0}}


def build(root=ROOT, *, updates=None):
    root = Path(root)
    rows = []
    groups = read(root, "ATLAS_MODULES/update-groups.json").get("groups", [])
    catalogue = read(root, "PUBLISHED/data/atlas/catalogue.json")
    history = read(root, "PUBLISHED/data/atlas/history/index.json")
    cube = read(root, "PUBLISHED/data/atlas/cube/index.json")
    registry = cube.get("registry") or variables.registry()
    # A variable registered but not yet published stays visible as missing, with its update group.
    registry = {**registry, "variables": {**variables.registry()["variables"], **registry.get("variables", {})}}
    currency = read(root, "PUBLISHED/data/data-currency.json")
    currency_by_id = {t["id"]: t for t in currency.get("tables", [])}
    from PIPELINES.build_data_currency import SOURCES

    def add(id, label, layer, collection, **kwargs):
        rows.append(dict(id=id, label=label, layer=layer, collection=collection,
                         last_updated=None, updated_basis="Not recorded", coverage_to=None,
                         interval_days=None, group_id=None, status="unknown", **kwargs))

    # Reference and independent estimates are different products, never one date.
    for code in catalogue.get("attributes", []):
        meta = catalogue["meta"][code]
        base = dict(id=f"reference:{code}", label=meta["label"], layer=1,
                    collection="Reference atlas", source=meta.get("original", {}).get("dataset"),
                    unit=meta.get("unit"), last_updated=None, updated_basis="Reference acquisition date not recorded",
                    published_at=catalogue.get("generated_at"), coverage_to=None, interval_days=None,
                    group_id=None, status="reference", evidence="/data/atlas/catalogue.json",
                    note="Fixed source edition. Rebuilding the website does not refresh this reference. Review a new source edition before replacing it.")
        rows.append(base)
        sub = meta.get("substitute")
        if sub:
            family = meta.get("family")
            group = {"aet": "terraclimate", "pet": "terraclimate", "pre": "terraclimate", "soil": "terraclimate",
                     "tmp": "era5_temperature", "tmx": "terraclimate_temperature", "tmn": "terraclimate_temperature",
                     "run": "era5_runoff", "snw": "snow"}.get(family)
            period = sub.get("period")
            rows.append({**base, "id": f"estimate:{code}", "collection": "Independent estimates",
                         "source": sub.get("source_release"), "unit": sub.get("unit"),
                         "coverage_label": " → ".join(str(v or "unspecified") for v in period) if isinstance(period, list) else period,
                         "status": "reference", "group_id": f"regional-{group}" if group else None,
                         "note": "Comparable descriptive estimate; its stated reference window is intentional. Updating the source group rebuilds the dependent estimates."})

    ledgers = {}
    for path in sorted((root / "PUBLISHED/data/atlas/observations").glob("regional-*-ledger.json")):
        ledger = json.loads(path.read_text(encoding="utf-8"))
        for attribute in ledger.get("attributes", []):
            ledgers[attribute] = (path, ledger)
    for id, spec in registry.get("variables", {}).items():
        code = spec["attribute"].split(".")[-1]
        path, ledger = ledgers.get(spec["attribute"], (None, {}))
        series = history.get("series", {}).get(code, {})
        # A source appended without the store keeps its ledger in WORKSPACE; the history says which it is.
        source = ledger.get("source") or series.get("source") or ("snow" if code == "snw_pc_s" else None)
        # Snow's ledger predates the shared source/attribute fields.
        if code == "snw_pc_s" and not ledger:
            path = root / "PUBLISHED/data/atlas/observations/regional-snow-ledger.json"
            ledger = read(root, str(path.relative_to(root)))
            source = "snow"
        coverage = spec.get("coverage", [])
        last = spec.get("observed_through") if "observed_through" in spec else (series.get("last_month") or (f"{coverage[-1]}-12" if coverage else None))
        rows.append(dict(id=id, label=spec["concept"].capitalize(), layer=2, collection="Basin observations",
                         source=spec.get("preferred"), unit=spec.get("unit"),
                         last_updated=ledger.get("finished_at") if ledger.get("complete") else None,
                         updated_basis="Completed extraction run", published_at=history.get("generated_at"),
                         coverage_to=last, interval_days=30, group_id=f"regional-{source}" if source else None,
                         status="available" if code in history.get("series", {}) else "missing",
                         note=spec.get("caution") or spec.get("why"),
                         evidence="/" + str(path.relative_to(root / "PUBLISHED")) if path else "/data/atlas/history/index.json"))

    tables = read(root, "ONTOLOGY/vocab/relationship-tables.json").get("tables", [])
    table_datasets = set()
    for table in tables:
        table_datasets.add("uz:ds/" + table["dataset"])
        state = currency_by_id.get(table["id"], {})
        policy = SOURCES.get(table["id"], {})
        cadence = policy.get("cadence")
        layer = 3 if "anomaly" in table["id"] else (2 if cadence in ("daily", "monthly", "annual", "pentadal", "closed") else 1)
        group = "hydroclimate" if table["id"].startswith(("era5-land-", "modis-snow-headwaters")) else (
            "landcover" if table["id"] == "landcover-admin-year" else None)
        for variable, measured in table_variables(root, table).items():
            rows.append(dict(id=f"table:{table['id']}:{variable}",
                             label=variable.replace("_", " ").capitalize() if variable != "relationship" else table["label"],
                             layer=layer, collection=table["label"], source=table["dataset"], unit=measured.get("unit"),
                             last_updated=state.get("lastModified"), updated_basis="Recorded table modification (legacy currency audit)",
                             coverage_to=measured["last"], interval_days={"daily": 7, "monthly": 30, "pentadal": 10, "annual": 365}.get(cadence),
                             group_id=group, status="missing" if not (root / table["container"]).exists() else (
                                 "archival" if cadence == "closed" else "reference" if layer == 1 else "available"),
                             evidence="/" + table["container"].removeprefix("PUBLISHED/") if table["container"].startswith("PUBLISHED/") else None,
                             note=table.get("note"), manual_command=policy.get("command")))

    # Keep catalogue-only variables visible, including those without an extraction recipe.
    datasets = read(root, "PUBLISHED/data/data-catalogue.json").get("datasets", [])
    for dataset in datasets:
        if dataset["id"] in table_datasets:
            continue
        for prop in dataset.get("observes") or [{"id": "dataset", "label": dataset["label"]}]:
            add(f"catalogue:{dataset['id']}:{prop['id']}", prop["label"], 1, dataset["label"],
                source=dataset["label"], note="Catalogue product. An acquisition date and refresh recipe have not yet been registered.",
                evidence="/catalogue.html")

    ca_discharge = read(root, "PUBLISHED/data/research/ca-discharge-summary.json")
    if ca_discharge:
        counts = ca_discharge.get("counts", {})
        add("research:ca-discharge", "Observed river discharge", 2, "CA-discharge v1.0",
            source="10.5281/zenodo.8147591", unit="m³/s",
            coverage_to=ca_discharge.get("temporal_coverage", {}).get("last"),
            coverage_label=(f"{ca_discharge.get('temporal_coverage', {}).get('first')} → "
                            f"{ca_discharge.get('temporal_coverage', {}).get('last')}"),
            published_at=ca_discharge.get("source", {}).get("publication_date"),
            group_id=None, status="archival",
            evidence="/data/research/ca-discharge-summary.json",
            note=(f"Versioned regional research archive: {counts.get('gauge_rows', 0)} gauges, "
                  f"{counts.get('gauges_with_time_series', 0)} with series and "
                  f"{counts.get('discharge_observations', 0):,} observations. "
                  "Quality flags are retained; this is distinct from modelled runoff."))

    for name in ("normals", "anomalies", "seasonal", "trend", "water_balance", "spi"):
        add(f"derived:{name}", name.replace("_", " ").capitalize(), 3, "Analytical products",
            source="Basin observation cube", note="Computed on demand from the selected release; no separate cached update timestamp.",
            evidence="/data/atlas/analysis-layers.md")
        rows[-1]["status"] = "on_demand"
    model = read(root, "PUBLISHED/data/atlas/models/pskem-discharge.json")
    rows.append(dict(id="model:pskem-discharge", label="Pskem monthly discharge model", layer=4, collection="Models",
                     source="Basin observations + Pskem gauge", last_updated=model.get("generated_at"),
                     updated_basis="Model evaluation run", coverage_to=(model.get("evaluate", {}).get("period") or [None])[-1],
                     interval_days=None, group_id="pskem-model", status="archival" if model else "missing",
                     note="Historical held-out evaluation. Re-running does not extend the gauge record or establish forecasting skill.",
                     evidence="/data/atlas/models/pskem-discharge.json"))
    # Group success dates survive inventory rebuilds and remain separate from file mtimes.
    if updates is None:
        updates = read(root, "PUBLISHED/data/variable-updates.json")
    for row in rows:
        updated = updates.get(row.get("group_id"))
        if updated:
            row["last_updated"] = updated["finished_at"]
            row["updated_basis"] = "Successful admin update job"
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate inventory identifiers")
    return {"version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "rows": rows, "counts": dict(Counter(str(row["layer"]) for row in rows)),
            "groups": [{key: value for key, value in group.items() if key not in ("commands", "requires", "modules")}
                       for group in groups],
            "reading": "Freshness measures elapsed time since the recorded update against the expected interval. Data coverage is separate. Unknown dates, fixed references and on-demand products are never silently scored as current."}


def main():
    result = build()
    out = ROOT / "PUBLISHED/data/variable-inventory.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(out)
    print(json.dumps({"rows": len(result["rows"]), "layers": result["counts"]}))


if __name__ == "__main__":
    main()
