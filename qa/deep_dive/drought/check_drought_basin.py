"""Independent check of the served drought record for screenshot basin 4121292070.

Run from repository root: python qa/deep_dive/drought/check_drought_basin.py [--offline]

The drought-study basin files are not in the Git checkout, so this reads the bytes
the portal actually serves (https://uzgeodata.uz/data/atlas/drought-study/...) and
keeps a copy beside this script; --offline reuses that copy. It then checks the
served record three ways, with code that shares nothing with build_drought_study.py:

1. Water-year totals 1992-2025 against the v1.1 monthly table in this checkout
   (PUBLISHED/data/atlas/climate-continuation/terraclimate-v1.1-history).
2. The 1991-2020 WMO normal and every percent anomaly, from the served totals.
3. SPI-12 refitted with Thom's (1958) maximum-likelihood approximation, the method of
   McKee et al. (1993), instead of the pipeline's numerical scipy fit.

It does not check PDSI, runoff q or the upstream columns, and it cannot check
water year 1991 against local monthly data: October-December 1990 is not in the
checkout.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASIN = "4121292070"
URL = f"https://uzgeodata.uz/data/atlas/drought-study/basins/{BASIN}.json"
CACHE = HERE / f"served-{BASIN}.json"
OUT = HERE / "result.json"
MONTHLY = ROOT / "PUBLISHED/data/atlas/climate-continuation/terraclimate-v1.1-history"
WMO = range(1991, 2021)
TOTAL_TOL = 0.01      # served totals are rounded to 3 decimals; local monthly to 4
ANOMALY_TOL = 0.01    # percentage points
SPI_TOL = 0.05        # two gamma estimators agree to a few hundredths


def served(offline):
    if not offline:
        request = urllib.request.Request(URL, headers={"User-Agent": "uzgeodata-qa"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                CACHE.write_bytes(response.read())
        except urllib.error.URLError:
            # Some local Python installs carry an outdated CA bundle; curl uses the system store.
            subprocess.run(["curl", "-sSf", "--max-time", "60", "-o", str(CACHE), URL], check=True)
    raw = CACHE.read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def local_water_years():
    ppt = {}
    for year in range(1991, 2026):
        path = MONTHLY / f"year={year}.parquet"
        table = pq.read_table(path, filters=[("basin_id", "=", BASIN), ("variable", "=", "ppt")]).to_pylist()
        for row in table:
            ppt[(year, row["month"])] = row["value"]
    totals = {}
    for year in range(1992, 2026):
        months = [(year - 1, m) for m in (10, 11, 12)] + [(year, m) for m in range(1, 10)]
        if all(ppt.get(k) is not None for k in months):
            totals[year] = sum(ppt[k] for k in months)
    return totals


def thom_gamma(values):
    """Thom (1958) approximation to the gamma MLE: alpha from A = ln(mean) - mean(ln x)."""
    mean = sum(values) / len(values)
    a = math.log(mean) - sum(math.log(v) for v in values) / len(values)
    alpha = (1 + math.sqrt(1 + 4 * a / 3)) / (4 * a)
    return alpha, mean / alpha


def gamma_cdf(x, alpha, beta):
    """Regularised lower incomplete gamma P(alpha, x/beta), by series or continued fraction."""
    z = x / beta
    if z <= 0:
        return 0.0
    if z < alpha + 1:
        term = total = 1 / alpha
        k = alpha
        while abs(term) > 1e-15 * abs(total):
            k += 1
            term *= z / k
            total += term
        return total * math.exp(-z + alpha * math.log(z) - math.lgamma(alpha))
    b, c, d = z + 1 - alpha, 1e300, 1 / (z + 1 - alpha)
    h = d
    for i in range(1, 500):
        an = -i * (i - alpha)
        b += 2
        d = an * d + b
        d = 1 / d if abs(d) > 1e-300 else 1e300
        c = b + an / c if abs(c) > 1e-300 else b + an * 1e300
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return 1 - math.exp(-z + alpha * math.log(z) - math.lgamma(alpha)) * h


def normal_quantile(p):
    """Acklam's rational approximation to the standard normal quantile (|error| < 1.2e-9)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    if p < 0.02425:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - 0.02425:
        return -normal_quantile(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="reuse the saved copy of the served file")
    record, digest = served(parser.parse_args().offline)
    column = {name: i for i, name in enumerate(record["fields"])}
    rows = {row[column["water_year"]]: row for row in record["rows"]}
    ppt = {year: row[column["ppt"]] for year, row in rows.items()}

    # 1. Served totals against the local v1.1 monthly table.
    local = local_water_years()
    totals = [{"water_year": y, "served_mm": ppt[y], "local_mm": round(v, 4), "difference_mm": ppt[y] - v}
              for y, v in sorted(local.items()) if y in ppt]
    worst_total = max(abs(t["difference_mm"]) for t in totals)

    # 2. The WMO normal and the percent anomalies.
    normal = sum(ppt[y] for y in WMO) / len(WMO)
    anomalies = [{"water_year": y, "served_pct": row[column["ppt_anom_pct_wmo"]],
                  "recomputed_pct": (ppt[y] - normal) / normal * 100} for y, row in sorted(rows.items())]
    worst_anomaly = max(abs(a["served_pct"] - a["recomputed_pct"]) for a in anomalies)

    # 3. SPI-12 from an independent gamma estimator.
    alpha, beta = thom_gamma([ppt[y] for y in WMO])
    spi = [{"water_year": y, "served": row[column["spi12"]],
            "recomputed": normal_quantile(min(max(gamma_cdf(ppt[y], alpha, beta), 1e-6), 1 - 1e-6))}
           for y, row in sorted(rows.items())]
    worst_spi = max(abs(s["served"] - s["recomputed"]) for s in spi)
    last = rows[max(rows)]

    checks = {
        "water_year_totals": {"years": [totals[0]["water_year"], totals[-1]["water_year"]], "compared": len(totals),
                              "max_abs_difference_mm": worst_total,
                              "status": "PASS" if worst_total <= TOTAL_TOL else "FAIL"},
        "wmo_normal": {"served_mm": record["norms_mm"]["wmo_1991_2020"], "recomputed_mm": normal,
                       "status": "PASS" if abs(normal - record["norms_mm"]["wmo_1991_2020"]) <= 0.01 else "FAIL"},
        "anomalies": {"compared": len(anomalies), "max_abs_difference_pct_points": worst_anomaly,
                      "status": "PASS" if worst_anomaly <= ANOMALY_TOL else "FAIL"},
        "spi12": {"method": "Thom (1958) gamma MLE approximation fitted on WY1991-2020", "alpha": alpha, "beta_mm": beta,
                  "compared": len(spi), "max_abs_difference": worst_spi,
                  "status": "PASS" if worst_spi <= SPI_TOL else "FAIL"},
        "latest_year": {"water_year": max(rows), "ppt_mm": ppt[max(rows)],
                        "anomaly_pct_served": last[column["ppt_anom_pct_wmo"]],
                        "spi12_served": last[column["spi12"]],
                        "spi12_recomputed": spi[-1]["recomputed"]},
    }
    result = {
        "basin_id": BASIN, "served_url": URL, "served_sha256": digest,
        "scope": "served drought record against local v1.1 monthly data and an independent SPI estimator",
        "checks": checks, "totals": totals, "anomalies": anomalies, "spi": spi,
        "not_checked": ["PDSI", "runoff q and its anomaly", "upstream SPI and anomalies",
                        "water year 1991 against local monthly data (needs October-December 1990)"],
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"basin_id": BASIN, "served_sha256": digest, "checks": checks}, indent=2))
    if any(c.get("status") == "FAIL" for c in checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
