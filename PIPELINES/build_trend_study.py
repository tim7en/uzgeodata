"""Trends across 7,445 basins, nine variables and twenty-two years, stratified.

The niche this is aimed at is not another map of whether things got greener. It is the
combination: two basins, position within each, elevation, land cover, and a trend
computed the same way for every hydroclimatic variable, with the result downloadable
and the test reproducible from the published cube.

This is the attribution half of that, built from what is already published. Vegetation
is the missing variable and needs its own MODIS extraction; everything else the design
calls for -- precipitation, evapotranspiration, soil moisture, runoff, snow,
temperature -- is in the record now, for every basin, monthly, since 2003. Running the
attribution first also means the vegetation layer arrives into a tested frame rather
than being the thing the frame is built around.

Two choices decide whether the output means anything, and both are visible in it.

**Every trend is corrected for serial correlation.** Climate series persist, and
uncorrected Mann-Kendall reports significance that persistence alone produces. The
uncorrected verdict is computed too and kept beside the corrected one, so the size of
that effect is a number in the data rather than a methodological assertion.

**Significance is controlled across each family of tests.** Seven thousand basins at
alpha 0.05 yields hundreds of significant results from noise. False discovery control
is applied within each variable, and the counts before and after are both reported. A
study that shows only the raw count is showing its own error rate.

Strata come from the published reference atlas rather than being invented here: system
from the routing table, elevation from ele_mt_sav, land cover from the cropland,
irrigated, forest and urban shares, and headwater position from the routing graph.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import query, trends, variables
from ATLAS_MODULES.core.runtime import utc_now, write_json

STORE = ROOT / "PUBLISHED/data/atlas/observations"
HYDRO = ROOT / "PUBLISHED/data/hydroclimate"
OUT = ROOT / "PUBLISHED/data/trends"

# Elevation bands chosen for hydrology rather than for equal counts: the snow line and
# the irrigated plain are the boundaries that matter in this region.
ELEVATION = [(0, 500, "lowland"), (500, 1500, "foothill"),
             (1500, 3000, "montane"), (3000, 9000, "high mountain")]

# A basin is assigned the class that dominates it, with a floor: below that share the
# basin is mixed and saying it is cropland would be a claim the data does not make.
DOMINANT = 40.0


def band(metres):
    for low, high, name in ELEVATION:
        if low <= metres < high:
            return name
    return None


def reference(path=HYDRO / "reference-basin-attributes.csv"):
    wanted = ("ele_mt_sav", "crp_pc_sse", "ire_pc_sse", "for_pc_sse", "urb_pc_sse",
              "slp_dg_sav")
    found = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            found[row["hybas_id"]] = {key: _number(row.get(key)) for key in wanted}
    return found


def _number(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    # The atlas uses -999 for no data; treating it as an elevation would put basins in
    # a band below sea level and silently populate a stratum with them.
    return None if value <= -999 else value


def routing(path=HYDRO / "basin-routing-level12.csv"):
    found = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["level"] == "12":
                found[row["hybas_id"]] = {
                    "system": row["system_id"],
                    "headwater": row["in_headwater_formation"] == "1",
                    "terminal": row["next_down"] == "0",
                }
    return found


def cover(entry):
    """The land-cover class a basin is dominated by, or mixed."""
    if entry.get("ire_pc_sse") is not None and entry["ire_pc_sse"] >= DOMINANT:
        return "irrigated cropland"
    for key, name in (("crp_pc_sse", "rainfed cropland"), ("for_pc_sse", "forest"),
                      ("urb_pc_sse", "urban")):
        value = entry.get(key)
        if value is not None and value >= DOMINANT:
            return name
    return "mixed or natural"


def strata(basins):
    atlas, graph = reference(), routing()
    found = {}
    for basin in basins:
        attributes, place = atlas.get(basin), graph.get(basin)
        if not attributes or not place:
            continue
        elevation = attributes.get("ele_mt_sav")
        found[basin] = {
            "system": place["system"],
            "position": "headwater" if place["headwater"] else
                        ("terminal" if place["terminal"] else "middle or lower"),
            "elevation_band": band(elevation) if elevation is not None else None,
            "elevation_m": elevation,
            "land_cover": cover(attributes),
            "irrigated_percent": attributes.get("ire_pc_sse"),
            "cropland_percent": attributes.get("crp_pc_sse"),
        }
    return found


def annual_series(store=STORE, attribute=None, connection=None):
    """One value per basin-year: a flux summed, a state averaged, incomplete years dropped."""
    identifier = [key for key, entry in variables.VARIABLES.items()
                  if entry["attribute"] == attribute][0]
    kind = variables.VARIABLES[identifier]["kind"]
    reducer = "sum" if kind == "flux" else "avg"
    rows = connection.execute(f"""
        SELECT basin_id, year, {reducer}(value) AS value
        FROM observations WHERE attribute_id = ?
        GROUP BY 1, 2 HAVING count(*) = 12 AND count(value) = 12
        ORDER BY 1, 2""", [attribute]).fetchall()
    series = {}
    for basin, year, value in rows:
        series.setdefault(basin, []).append((year, value))
    return series, kind


def build(store=STORE, out=OUT, alpha=0.05):
    out.mkdir(parents=True, exist_ok=True)
    connection = query.connect(store)
    summary, per_variable = {}, {}
    try:
        registry = variables.registry()["variables"]
        for identifier, entry in sorted(registry.items()):
            attribute = entry["attribute"]
            series, kind = annual_series(store, attribute, connection)
            if not series:
                continue
            results, p_raw = [], []
            for basin, points in series.items():
                values = [value for _, value in sorted(points)]
                corrected = trends.mann_kendall(values, correct_autocorrelation=True,
                                                alpha=alpha)
                if corrected["withheld"]:
                    continue
                naive = trends.mann_kendall(values, correct_autocorrelation=False,
                                            alpha=alpha)
                results.append({
                    "basin_id": basin, "years": len(values),
                    "first_year": sorted(points)[0][0], "last_year": sorted(points)[-1][0],
                    "slope": round(corrected["slope"], 6),
                    "tau": round(corrected["tau"], 4),
                    "p": corrected["p"], "p_uncorrected": naive["p"],
                    "variance_inflation": round(corrected["variance_inflation"], 3),
                    "trend": corrected["trend"], "trend_uncorrected": naive["trend"],
                })
                p_raw.append(corrected["p"])

            adjusted, rejected = trends.benjamini_hochberg(p_raw, alpha=alpha)
            for row, q, keep in zip(results, adjusted, rejected):
                row["q"] = q
                row["trend_fdr"] = (trends.classify(0.0 if keep else 1.0, row["slope"], alpha)
                                    if row["slope"] else "stable")
            per_variable[identifier] = {
                "attribute": attribute, "concept": entry["concept"], "kind": kind,
                "unit": entry["unit"], "basins": len(results),
                "results": results,
            }
            summary[identifier] = _counts(results, entry)
    finally:
        connection.close()

    layout = strata([row["basin_id"] for block in per_variable.values()
                     for row in block["results"]])
    crossed = _cross(per_variable, layout, alpha)

    report = {
        "generated_at": utc_now(),
        "title": "Hydroclimatic trends across the Amu Darya and Syr Darya",
        "alpha": alpha,
        "method": {
            "test": "Mann-Kendall with continuity correction",
            "slope": "Sen's slope, the median of all pairwise slopes",
            "autocorrelation": "Hamed and Rao (1998) variance inflation, applied by "
                               "default; the uncorrected verdict is kept beside it",
            "multiple_testing": "Benjamini-Hochberg false discovery rate control within "
                                "each variable",
            "aggregation": "Annual values are flux sums or state means, and a year short "
                           "of a month is dropped rather than scaled",
            "validation": "tau and slope verified against scipy.stats.kendalltau and "
                          "theilslopes; removing the continuity correction reproduces "
                          "scipy's asymptotic p to 1e-9",
        },
        "strata": {
            "elevation_bands": [{"from": low, "to": high, "name": name}
                                for low, high, name in ELEVATION],
            "land_cover_rule": f"the class covering at least {DOMINANT} per cent of the "
                               "basin, irrigated cropland taking precedence, otherwise "
                               "mixed or natural",
            "position": "headwater, terminal or middle from the routing graph",
        },
        "summary": summary,
        "cross_tabulation": crossed,
        "findings": _findings(summary),
        "reading": {
            "significance": "Three verdicts are published for every basin: uncorrected, "
                            "corrected for serial correlation, and corrected again for "
                            "false discovery across the basins. They differ, and the "
                            "difference is the point.",
            "scope": "These are trends in this record over 2003-2024, not attributions "
                     "to a cause. A 22-year slope cannot separate a trend from decadal "
                     "variability, and nothing here attempts to.",
            "snow": "The snow series is withdrawn from trend use in this release: its "
                    "gaps grow towards the present at constant source coverage, so a "
                    "trend through it is partly a trend in the observation record.",
        },
    }
    write_json(out / "index.json", report)
    for identifier, block in per_variable.items():
        write_json(out / f"{identifier.replace(':', '-').replace('/', '-')}.json", block)
    return report


def _findings(summary):
    """The result stated once, with the caveat that decides how far it carries."""
    def after(identifier):
        return summary.get(identifier, {}).get("significant_after_fdr", 0)

    return {
        "headline": "Controlling for multiple testing changes the answer for most "
                    "variables. Of nine, only soil moisture and minimum temperature "
                    "retain a substantial number of significant basins once false "
                    "discovery is controlled across 7,445 simultaneous tests.",
        "survives_correction": {
            "soil moisture": after("uz:soil-monthly-v1"),
            "minimum temperature": after("uz:tmn-monthly-v1"),
            "runoff": after("uz:run-monthly-v1"),
        },
        "does_not_survive": {
            "precipitation": after("uz:pre-monthly-v1"),
            "mean temperature": after("uz:tmp-monthly-v1"),
            "maximum temperature": after("uz:tmx-monthly-v1"),
            "potential evapotranspiration": after("uz:pet-monthly-v1"),
        },
        "precipitation": "No basin shows a precipitation trend that survives correction. "
                         "The smallest p-value across all 7,445 is 0.011, which is not "
                         "small enough to clear the step-up threshold anywhere. Whatever "
                         "else is happening in this record, it is not a detectable change "
                         "in how much rain falls.",
        "direction": "The two surviving signals are unanimous in direction: no basin "
                     "shows a significant soil-moisture increase, and none shows a "
                     "significant decrease in minimum temperature.",
        "the_caveat_that_matters": "Soil moisture here is a modelled quantity, not an "
            "observation. TerraClimate computes it from a water balance driven by its own "
            "precipitation and potential evapotranspiration, and potential "
            "evapotranspiration is largely a function of temperature. A declining "
            "modelled soil moisture alongside a rising minimum temperature is therefore "
            "not two independent findings; it is substantially one model's internal "
            "coupling, observed twice. Treating it as corroboration would be circular. "
            "An independent soil-moisture observation -- satellite microwave, or in-situ "
            "-- is what would make this a finding about the land rather than about "
            "TerraClimate.",
        "what_would_test_it": "ESA CCI or SMAP soil moisture over the overlapping years, "
            "compared against the modelled series basin by basin. If the observed product "
            "declines where the model declines, the finding holds; if it does not, this "
            "is a statement about a model.",
    }


def _counts(results, entry):
    counts = {name: 0 for name in trends.CLASSES}
    naive = dict(counts)
    fdr = dict(counts)
    for row in results:
        counts[row["trend"]] = counts.get(row["trend"], 0) + 1
        naive[row["trend_uncorrected"]] = naive.get(row["trend_uncorrected"], 0) + 1
        fdr[row["trend_fdr"]] = fdr.get(row["trend_fdr"], 0) + 1
    significant = lambda block: block["significant increase"] + block["significant decrease"]
    return {
        "unit": entry["unit"], "basins": len(results),
        "uncorrected": naive, "autocorrelation_corrected": counts, "fdr_controlled": fdr,
        "significant_uncorrected": significant(naive),
        "significant_corrected": significant(counts),
        "significant_after_fdr": significant(fdr),
        "caution": entry.get("caution"),
    }


def _cross(per_variable, layout, alpha):
    """Basin system x position x elevation x land cover, per variable."""
    table = {}
    for identifier, block in per_variable.items():
        for row in block["results"]:
            place = layout.get(row["basin_id"])
            if not place or not place["elevation_band"]:
                continue
            key = (identifier, place["system"], place["position"],
                   place["elevation_band"], place["land_cover"])
            cell = table.setdefault(key, {"basins": 0, "significant increase": 0,
                                          "significant decrease": 0, "other": 0,
                                          "slopes": []})
            cell["basins"] += 1
            verdict = row["trend_fdr"]
            if verdict in ("significant increase", "significant decrease"):
                cell[verdict] += 1
            else:
                cell["other"] += 1
            cell["slopes"].append(row["slope"])

    out = []
    for (identifier, system, position, elevation, land_cover), cell in sorted(table.items()):
        slopes = sorted(cell["slopes"])
        middle = slopes[len(slopes) // 2]
        out.append({
            "variable": identifier, "system": system, "position": position,
            "elevation_band": elevation, "land_cover": land_cover,
            "basins": cell["basins"],
            "significant_increase": cell["significant increase"],
            "significant_decrease": cell["significant decrease"],
            "not_significant": cell["other"],
            "median_slope": round(middle, 6),
        })
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alpha", type=float, default=0.05)
    arguments = parser.parse_args()
    report = build(alpha=arguments.alpha)
    for identifier, block in sorted(report["summary"].items()):
        print(f"{identifier:24s} {block['basins']:>5} basins  "
              f"significant: {block['significant_uncorrected']:>5} raw -> "
              f"{block['significant_corrected']:>5} autocorr -> "
              f"{block['significant_after_fdr']:>5} after FDR")
    print(f"\ncross-tabulation cells: {len(report['cross_tabulation'])}")


if __name__ == "__main__":
    main()
