"""Are the independent estimates on the same TerraClimate release as the monthly record?

Run from repository root: python qa/deep_dive/other_tabs/check_estimate_versions.py

The Independent estimates tab shows monthly normals derived from TerraClimate; the
Monthly tab, catchment statistics, drought study and reports use the producer's
v1.1 release. This recomputes 2003-2025 monthly normals of precipitation, actual and
potential evapotranspiration for every level-12 basin from the published v1.1
catchment matrices and sets them beside each basin's published estimate.

It FAILS while the estimates are on another release and differ from v1.1 by more
than 5% (median annual precipitation), because the two tabs then disagree for the
same basin and month. It passes once the estimates are re-derived from v1.1.
"""
import gzip
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
ATLAS = ROOT / "PUBLISHED/data/atlas"
OUT = Path(__file__).with_name("estimate-versions.json")
YEARS = (2003, 2025)
LIMIT_PCT = 5.0


def matrix(index, name, n):
    """Basins x months from the delta-coded, byte-planed catchment matrix; NaN where empty."""
    path = ROOT / "PUBLISHED" / index["series"][name]["url"].lstrip("/")
    raw = np.frombuffer(gzip.decompress(path.read_bytes()), np.uint8)
    planes = raw.reshape(4, n * index["months"]).astype(np.uint32)
    coded = (planes[0] | planes[1] << 8 | planes[2] << 16 | planes[3] << 24).view(np.int32)
    values = np.cumsum(coded.reshape(n, index["months"]).astype(np.int64), axis=1)
    values = (values + 2**31) % 2**32 - 2**31
    out = values / index["scale"]
    out[values == index["null_sentinel"]] = np.nan
    return out


def main():
    index = json.loads((ATLAS / "catchments/index.json").read_text(encoding="utf-8"))
    catalogue = json.loads((ATLAS / "catalogue.json").read_text(encoding="utf-8"))
    ids = [str(x) for x in index["ids"]]
    attributes = catalogue["attributes"]
    estimates = np.full((len(ids), len(attributes)), np.nan)
    for row, basin in enumerate(ids):
        values = json.loads((ATLAS / f"basins/{basin}.json").read_text(encoding="utf-8"))["substitute"]
        estimates[row] = [np.nan if v is None else v for v in values]

    months = (YEARS[1] - YEARS[0] + 1) * 12
    first = (YEARS[0] - index["years"][0]) * 12
    variables = {}
    for name in ("pre_mm_s", "aet_mm_s", "pet_mm_s"):
        record = matrix(index, name, len(ids))[:, first:first + months]
        normals = np.nanmean(record.reshape(len(ids), -1, 12), axis=1)
        release = catalogue["meta"][f"{name}01"]["substitute"]["source_release"]
        by_month = []
        for month in range(12):
            published = estimates[:, attributes.index(f"{name}{month + 1:02}")]
            ok = np.isfinite(published) & np.isfinite(normals[:, month]) & (published > 0.5)
            relative = (normals[ok, month] / published[ok] - 1) * 100
            by_month.append({"month": month + 1, "basins": int(ok.sum()),
                             "mean_estimate": float(published[ok].mean()), "mean_v1_1": float(normals[ok, month].mean()),
                             "median_pct": float(np.median(relative)),
                             "p10_pct": float(np.percentile(relative, 10)), "p90_pct": float(np.percentile(relative, 90))})
        annual_estimate = np.nansum(estimates[:, [attributes.index(f"{name}{m:02}") for m in range(1, 13)]], axis=1)
        annual_v11 = normals.sum(axis=1)
        ok = annual_estimate > 1
        variables[name] = {
            "estimate_release": release, "estimate_method": catalogue["meta"][f"{name}01"]["substitute"]["method"],
            "record_release": index["series"][name]["provenance"][0]["source_release"],
            "annual_median_pct": float(np.median((annual_v11[ok] / annual_estimate[ok] - 1) * 100)),
            "months": by_month,
        }
    gap = variables["pre_mm_s"]["annual_median_pct"]
    same_release = variables["pre_mm_s"]["estimate_release"] == variables["pre_mm_s"]["record_release"]
    status = "PASS" if same_release or abs(gap) <= LIMIT_PCT else "FAIL"
    result = {
        "scope": f"{len(ids)} level-12 basins, monthly normals {YEARS[0]}-{YEARS[1]}",
        "status": status,
        "finding": (f"Independent estimates use {variables['pre_mm_s']['estimate_release']}; the monthly record uses "
                    f"{variables['pre_mm_s']['record_release']}. Recomputed from v1.1, annual precipitation normals "
                    f"are {gap:+.1f}% (median basin) against the published estimates."),
        "variables": variables,
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "finding": result["finding"],
                      "annual_median_pct": {k: round(v["annual_median_pct"], 2) for k, v in variables.items()}}, indent=2))
    if status == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
