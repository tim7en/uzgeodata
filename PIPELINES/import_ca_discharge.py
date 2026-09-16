#!/usr/bin/env python3
"""Import the compact CA-discharge GeoPackage into public research evidence.

The 11.8 GB raw-data archive is deliberately not required. The published
GeoPackage contains the gauge registry, basin summaries, quality flags and
discharge series needed for the portal integration. Raw third-party rasters are
not redistributed. Two glacier thinning attributes named by the publishers as
unsafe are explicitly excluded from every output.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "GEODATA/ca-discharge-2023/CA-discharge.gpkg"
ZENODO = ROOT / "GEODATA/ca-discharge-2023/zenodo-record.json"
LOCAL_DAILY = ROOT / "PUBLISHED/data/hydroclimate/pskem-discharge-daily.csv"
OUTPUT = ROOT / "PUBLISHED/data/research"
EXPECTED_MD5 = "e0ba6664aaec3e0b27138abdfd4ba263"
EXCLUDED_ATTRIBUTES = {"gl_dmdt_km3a", "gl_dmdtda_mma"}


def file_hash(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rows(connection: sqlite3.Connection, query: str, parameters=()):
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(query, parameters)]


def safe_float(value, digits=6):
    return None if value is None else round(float(value), digits)


def haversine_km(lon1, lat1, lon2, lat2):
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def local_dekads(path: Path):
    groups = defaultdict(list)
    invalid_dates = []
    with path.open(newline="", encoding="utf-8") as stream:
        for item in csv.DictReader(stream):
            year, month, day = (int(item[key]) for key in ("year", "month", "day"))
            try:
                date(year, month, day)
            except ValueError:
                invalid_dates.append(f"{year:04d}-{month:02d}-{day:02d}")
                continue
            marker = 5 if day <= 10 else 15 if day <= 20 else 25
            groups[f"{year:04d}-{month:02d}-{marker:02d}"].append(float(item["discharge_cms"]))
    return {key: sum(values) / len(values) for key, values in groups.items()}, invalid_dates


def comparison(ca_rows, local_path: Path):
    local, invalid_dates = local_dekads(local_path)
    pairs = []
    for item in ca_rows:
        if item["date"] not in local or item["value"] is None:
            continue
        local_value = local[item["date"]]
        difference = float(item["value"]) - local_value
        pairs.append({
            "date": item["date"], "ca_discharge_cms": float(item["value"]),
            "local_daily_dekad_mean_cms": local_value, "difference_cms": difference,
        })
    ca_values = [item["ca_discharge_cms"] for item in pairs]
    local_values = [item["local_daily_dekad_mean_cms"] for item in pairs]
    differences = [item["difference_cms"] for item in pairs]
    mean_ca, mean_local = sum(ca_values) / len(pairs), sum(local_values) / len(pairs)
    correlation = sum((a - mean_ca) * (b - mean_local) for a, b in zip(ca_values, local_values)) / math.sqrt(
        sum((a - mean_ca) ** 2 for a in ca_values) * sum((b - mean_local) ** 2 for b in local_values)
    )
    metrics = {
        "paired_dekads": len(pairs), "period_start": pairs[0]["date"], "period_end": pairs[-1]["date"],
        "bias_ca_minus_local_cms": round(sum(differences) / len(pairs), 3),
        "mae_cms": round(sum(abs(value) for value in differences) / len(pairs), 3),
        "rmse_cms": round(math.sqrt(sum(value * value for value in differences) / len(pairs)), 3),
        "pearson_r": round(correlation, 4), "invalid_local_calendar_rows_excluded": invalid_dates,
        "interpretation": "Consistency check only. Both records ultimately come from hydrometeorological yearbooks/workbooks and are not independent validation datasets.",
    }
    return metrics, pairs


def build(source: Path = SOURCE, zenodo_path: Path = ZENODO, local_path: Path = LOCAL_DAILY):
    if not source.exists() or not zenodo_path.exists():
        raise FileNotFoundError("Download CA-discharge.gpkg and its Zenodo record into GEODATA/ca-discharge-2023 first")
    md5 = file_hash(source, "md5")
    if md5 != EXPECTED_MD5:
        raise ValueError(f"CA-discharge.gpkg checksum mismatch: {md5}")
    zenodo = json.loads(zenodo_path.read_text(encoding="utf-8"))
    connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    table_names = {row[0] for row in connection.execute("select name from sqlite_master where type='table'")}
    required = {"gauges", "discharge_time_series", "quality_flags", "basin_attributes"}
    if not required <= table_names:
        raise ValueError(f"CA-discharge GeoPackage is missing tables: {sorted(required - table_names)}")

    gauges = rows(connection, """select CODE,NAME_ENG,NAME_RU,RIVER,COUNTRY,BASIN,LON,LAT,q_m3s,SOURCE,res,has_ts,
        ts_start,ts_end,n_complete,n_miss,n_propmiss,n_largestgap from gauges order by CODE""")
    series_stats = rows(connection, "select count(*) records,min(date) first_date,max(date) last_date from discharge_time_series")[0]
    resolutions = rows(connection, "select coalesce(nullif(res,''),'none') resolution,count(*) gauges from gauges group by coalesce(nullif(res,''),'none') order by gauges desc")
    countries = rows(connection, "select coalesce(nullif(COUNTRY,''),'unassigned') country,count(*) gauges,sum(has_ts) with_time_series from gauges group by coalesce(nullif(COUNTRY,''),'unassigned') order by gauges desc")
    pskem = next(item for item in gauges if str(item["CODE"]) == "16290")
    ca_pskem = rows(connection, "select date,value from discharge_time_series where CODE=? order by date", ("16290",))
    quality = rows(connection, "select * from quality_flags where CODE=?", ("16290",))[0]
    quality.pop("fid", None)
    metrics, pairs = comparison(ca_pskem, local_path)

    project_lon, project_lat = 70.2, 41.766666666666666
    crosswalk = {
        "ca_code": "16290", "ca_name": pskem["NAME_ENG"], "uzgeodata_station": "uz:station/gauge-16290",
        "uzgeodata_name": "Pskem (Mullala)", "match_basis": ["same numeric gauge code", "same river and locality name"],
        "ca_coordinate": [safe_float(pskem["LON"]), safe_float(pskem["LAT"])],
        "uzgeodata_coordinate": [project_lon, project_lat],
        "coordinate_separation_km": round(haversine_km(pskem["LON"], pskem["LAT"], project_lon, project_lat), 2),
        "review": "Accepted identity crosswalk; retain both source coordinates and do not average them.",
    }

    features = []
    for item in gauges:
        if item["LON"] is None or item["LAT"] is None:
            continue
        properties = {key.lower(): value for key, value in item.items() if key not in {"LON", "LAT"}}
        properties["has_ts"] = bool(properties["has_ts"])
        features.append({
            "type": "Feature", "id": f"ca-discharge:{item['CODE']}",
            "geometry": {"type": "Point", "coordinates": [safe_float(item["LON"]), safe_float(item["LAT"])]},
            "properties": properties,
        })

    files = {item["key"]: item for item in zenodo["files"]}
    creators = [item["name"] for item in zenodo["metadata"]["creators"]]
    summary = {
        "version": "1.0", "status": "integrated", "source": {
            "title": zenodo["metadata"]["title"], "doi": zenodo["doi"], "record_id": zenodo["id"],
            "dataset_version": zenodo["metadata"].get("version"), "publication_date": zenodo["metadata"]["publication_date"],
            "metadata_updated_at": zenodo.get("updated"), "license": zenodo["metadata"]["license"]["id"],
            "creators": creators, "article_doi": "10.1038/s41597-023-02474-8",
            "gpkg_md5": md5, "gpkg_sha256": file_hash(source), "gpkg_bytes": source.stat().st_size,
        },
        "counts": {
            "gauge_rows": len(gauges), "gauge_points_published": len(features),
            "gauges_with_time_series": sum(bool(item["has_ts"]) for item in gauges),
            "discharge_observations": series_stats["records"],
        },
        "temporal_coverage": {"first": series_stats["first_date"], "last": series_stats["last_date"]},
        "resolutions": resolutions, "countries": countries,
        "article_package_difference": "The version 1.0 GeoPackage contains 297 gauge rows and 136 time-series flags; the article abstract reports 295 locations and 135 series. Portal counts describe the downloaded file, while the article counts remain cited as published.",
        "excluded_attributes": sorted(EXCLUDED_ATTRIBUTES),
        "excluded_attribute_reason": "The Zenodo publisher warns that these glacier thinning fields do not account for ice density. They are not exported or used.",
        "crosswalks": [crosswalk], "pskem_consistency": {**metrics, "quality_flags": quality},
        "research_use": [
            "Extend the historical context of the Pskem–Mullala gauge back to 1932 at 10-day resolution.",
            "Use the regional station registry to identify candidate validation gauges across Central Asia.",
            "Keep this source distinct from satellite-derived or modelled runoff and retain its quality flags.",
        ],
    }
    manifest = {
        "version": "1.0", "record_url": f"https://doi.org/{zenodo['doi']}", "license": zenodo["metadata"]["license"]["id"],
        "attribution": f"{'; '.join(creators)} ({zenodo['metadata']['publication_date'][:4]}), {zenodo['metadata']['title']}, {zenodo['doi']}.",
        "files": [{
            "name": name, "bytes": item["size"], "checksum": item["checksum"],
            "downloaded_for_integration": name == "CA-discharge.gpkg",
            "reason": "compact integration source" if name == "CA-discharge.gpkg" else "not mirrored; optional reproducibility archive",
        } for name, item in files.items()],
        "outputs": ["ca-discharge-summary.json", "ca-discharge-stations.geojson", "ca-discharge-pskem-comparison.csv"],
    }
    connection.close()
    return summary, {"type": "FeatureCollection", "features": features}, pairs, manifest


def write_outputs(summary, stations, pairs, manifest, output: Path = OUTPUT):
    output.mkdir(parents=True, exist_ok=True)
    (output / "ca-discharge-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "ca-discharge-stations.geojson").write_text(json.dumps(stations, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (output / "ca-discharge-source-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "ca-discharge-pskem-comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["date", "ca_discharge_cms", "local_daily_dekad_mean_cms", "difference_cms"])
        writer.writeheader()
        for item in pairs:
            writer.writerow({key: round(value, 4) if isinstance(value, float) else value for key, value in item.items()})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--zenodo", type=Path, default=ZENODO)
    parser.add_argument("--local", type=Path, default=LOCAL_DAILY)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build(args.source, args.zenodo, args.local)
    write_outputs(*result, output=args.output)
    print(json.dumps({"gauges": result[0]["counts"]["gauge_rows"], "observations": result[0]["counts"]["discharge_observations"], "pskem_pairs": result[0]["pskem_consistency"]["paired_dekads"]}))


if __name__ == "__main__":
    main()
