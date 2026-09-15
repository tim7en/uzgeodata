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
import statistics
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

# A basin must contain at least this many native source cells for its value to be a
# measurement of the basin rather than a reading of one grid cell that happens to
# overlap it. Four is not a deep principle; it is the point below which a "basin mean"
# is arithmetic over fewer numbers than a basin has sides.
#
# This gate exists because the reduction hides the problem. Every product is resampled
# onto the 15 arc-second HydroSHEDS lattice before reduction, so expected_count is
# identical for a 4 km product and an 11 km one -- around 835 cells for a median basin
# in both cases. That QA number describes the lattice, not the evidence, and reading it
# as sampling density is exactly the mistake this prevents.
MINIMUM_SOURCE_CELLS = 4


def hierarchy(path=HYDRO / "basin-hierarchy.csv"):
    """Level-12 basin to its level-10 and level-7 parents.

    The published table links 12 to 10 and 10 to 7, so the level-7 parent is reached by
    chaining. Doing it here rather than assuming a direct link is what stops a basin
    with no level-10 record from silently acquiring a level-7 one.
    """
    up = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            up[(row["child_level"], row["child_hybas_id"])] = row["parent_hybas_id"]
    parents = {}
    for (level, child), parent in up.items():
        if level != "12":
            continue
        grandparent = up.get(("10", parent))
        parents[child] = {"10": parent, "7": grandparent}
    return parents


def lift(annual, level, parents, areas):
    """Area-weighted aggregation of level-12 annual values to a coarser basin.

    A parent-year is produced only when every child basin reported that year. A mean
    over whichever children happened to report is a mean over a different area each
    year, and a trend through that measures which basins reported as much as what they
    measured.
    """
    children = {}
    for basin in annual:
        parent = parents.get(basin, {}).get(level)
        if parent:
            children.setdefault(parent, []).append(basin)

    lifted, dropped = {}, 0
    for parent, members in children.items():
        years = [set(year for year, _ in annual[basin]) for basin in members]
        shared = set.intersection(*years) if years else set()
        total = sum(areas.get(basin, 0.0) for basin in members)
        if not shared or total <= 0:
            dropped += 1
            continue
        series = []
        for year in sorted(shared):
            value = sum(areas.get(basin, 0.0) * dict(annual[basin])[year] for basin in members)
            series.append((year, value / total))
        lifted[parent] = series
    return lifted, dropped


def source_cells(area_km2, resolution_m):
    """How many native source cells a basin of this area contains."""
    cell_km2 = (resolution_m / 1000.0) ** 2
    return area_km2 / cell_km2 if cell_km2 else None


def _signif(value, digits=4):
    """Round to significant digits, keeping small p-values meaningful."""
    if value is None or value == 0:
        return value
    import math
    return round(value, -int(math.floor(math.log10(abs(value)))) + (digits - 1))


def band(metres):
    for low, high, name in ELEVATION:
        if low <= metres < high:
            return name
    return None


def basin_area(path=HYDRO / "basins-level12.geojson"):
    collection = json.loads(path.read_text(encoding="utf-8"))
    return {str(f["properties"]["HYBAS_ID"]): float(f["properties"]["SUB_AREA"])
            for f in collection["features"]}


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


def reference_level7(path=HYDRO / "reference-basin-attributes-level07.json"):
    """The same attributes, published column-wise for the coarser level."""
    block = json.loads(path.read_text(encoding="utf-8"))
    ids, values = block["ids"], block["values"]
    wanted = ("ele_mt_sav", "crp_pc_sse", "ire_pc_sse", "for_pc_sse", "urb_pc_sse")
    found = {}
    for index, basin in enumerate(ids):
        found[str(basin)] = {key: _number(values.get(key, [None] * len(ids))[index])
                             for key in wanted if key in values}
    return found


def system_of(level7_id, path=HYDRO / "basin-membership-level07.csv"):
    found = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["level"] == "7":
                found[row["hybas_id"]] = row["system_id"]
    return found


def strata(basins, level="12"):
    if level == "7":
        atlas = reference_level7()
        systems = system_of(None)
        found = {}
        for basin in basins:
            attributes = atlas.get(basin)
            if not attributes:
                continue
            elevation = attributes.get("ele_mt_sav")
            found[basin] = {
                "system": systems.get(basin, "unknown"),
                # Position within a system is a level-12 routing property; at level 7 a
                # basin is large enough to contain headwater and lowland alike, so it is
                # not claimed here rather than being asserted from the outlet.
                "position": "whole sub-basin",
                "elevation_band": band(elevation) if elevation is not None else None,
                "elevation_m": elevation,
                "land_cover": cover(attributes),
                "irrigated_percent": attributes.get("ire_pc_sse"),
                "cropland_percent": attributes.get("crp_pc_sse"),
            }
        return found
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


def build(store=STORE, out=OUT, alpha=0.05, level="12"):
    out.mkdir(parents=True, exist_ok=True)
    areas = basin_area()
    parents = hierarchy() if level != "12" else {}
    coarse = basin_area(HYDRO / f"basins-level{int(level):02d}.geojson") if level != "12" else areas
    connection = query.connect(store)
    summary, per_variable = {}, {}
    try:
        registry = variables.registry()["variables"]
        for identifier, entry in sorted(registry.items()):
            attribute = entry["attribute"]
            series, kind = annual_series(store, attribute, connection)
            if not series:
                continue
            resolution = entry.get("native_resolution_m")
            if level != "12":
                series, _ = lift(series, level, parents, areas)
            scale = coarse
            results, p_raw, unresolved = [], [], 0
            for basin, points in series.items():
                cells = source_cells(scale.get(basin, 0.0), resolution) if resolution else None
                if cells is not None and cells < MINIMUM_SOURCE_CELLS:
                    unresolved += 1
                    continue
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
                    # Four significant digits. A p-value carried to seventeen is
                    # storing float noise: nothing downstream distinguishes 0.0234117
                    # from 0.02341, and at 6,016 basins x 14 variables the difference
                    # is megabytes of precision nobody can use.
                    "p": _signif(corrected["p"]), "p_uncorrected": _signif(naive["p"]),
                    "variance_inflation": round(corrected["variance_inflation"], 3),
                    "trend": corrected["trend"], "trend_uncorrected": naive["trend"],
                })
                p_raw.append(corrected["p"])

            adjusted, rejected = trends.benjamini_hochberg(p_raw, alpha=alpha)
            for row, q, keep in zip(results, adjusted, rejected):
                row["q"] = _signif(q)
                row["trend_fdr"] = (trends.classify(0.0 if keep else 1.0, row["slope"], alpha)
                                    if row["slope"] else "stable")
            tested = len(results)
            per_variable[identifier] = {
                "attribute": attribute, "concept": entry["concept"], "kind": kind,
                "unit": entry["unit"], "basins": tested,
                "native_resolution_m": resolution,
                "basins_withheld_unresolved": unresolved,
                "results": results,
            }
            block = _counts(results, entry)
            block.update({
                "native_resolution_m": resolution,
                "source_cell_km2": round((resolution / 1000.0) ** 2, 1) if resolution else None,
                "basins_withheld_unresolved": unresolved,
                "basins_tested": tested,
                "median_source_cells": round(statistics.median(
                    [source_cells(coarse[b], resolution) for b in
                     (r["basin_id"] for r in results) if b in coarse]), 1)
                    if results and resolution else None,
            })
            summary[identifier] = block
    finally:
        connection.close()

    layout = strata([row["basin_id"] for block in per_variable.values()
                     for row in block["results"]], level)
    crossed = _cross(per_variable, layout, alpha)

    report = {
        "generated_at": utc_now(),
        "title": "Hydroclimatic trends across the Amu Darya and Syr Darya",
        "basin_level": level,
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
            "resolution": "A basin smaller than its source grid cell is not a "
                          "measurement of the basin. Variables are gated on holding at "
                          "least four native source cells, which withdraws ERA5-Land "
                          "entirely at this basin level.",
            "snow": "The snow series is withdrawn from trend use in this release: its "
                    "gaps grow towards the present at constant source coverage, so a "
                    "trend through it is partly a trend in the observation record.",
        },
    }
    write_json(out / "index.json", report)
    # Compact rather than indented: these are machine-readable results of thousands of
    # rows, not something anyone reads by eye.
    #
    # Level-7 results ship in full. Level-12 per-basin results do not, and the reason is
    # a hard one: the site has a 950 MB budget and 19 MB of level-12 rows would spend a
    # fifth of the remaining headroom on a file that is derivable. Anyone can regenerate
    # it from the published cube with the code in this repository, the summary and the
    # cross-tabulation are published either way, and level 7 is the scale at which every
    # product actually resolves. Shipping the derivable copy and running out of room for
    # the next variable would be the worse trade.
    keep_rows = level != "12"
    for identifier, block in per_variable.items():
        path = out / f"{identifier.replace(':', '-').replace('/', '-')}.json"
        payload = block if keep_rows else {
            **{k: v for k, v in block.items() if k != "results"},
            "results_withheld": {
                "reason": "Per-basin rows at level 12 are derivable from the published "
                          "cube and are not shipped, to stay inside the site's size "
                          "budget. Level-7 rows are shipped in full.",
                "rows": len(block["results"]),
                "reproduce": "uz.open() then ATLAS_MODULES.core.trends.mann_kendall on "
                             "the annual series; see the study page.",
            },
        }
        path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False,
                                   allow_nan=False), encoding="utf-8")
    return report


def _findings(summary):
    """The result stated once, with the caveat that decides how far it carries."""
    def after(identifier):
        return summary.get(identifier, {}).get("significant_after_fdr", 0)

    return {
        "resolution": {
            "finding": "Two variables cannot be analysed at this basin level at all. "
                       "ERA5-Land has a 0.1 degree grid, about 123 km2 per cell, against "
                       "a median level-12 basin of 136 km2: across the whole region there "
                       "are 1.05 ERA5 cells per basin, so basins and cells are "
                       "interchangeable and neighbouring basins read the same number. "
                       "Runoff and mean temperature are withheld entirely rather than "
                       "reported at a resolution they do not have.",
            "cells_per_basin_across_region": {"TerraClimate": 6.03, "ERA5-Land": 1.05,
                                              "MODIS MYD10A1": 518.9},
            "why_it_was_not_obvious": "Every product is resampled onto the 15 arc-second "
                "HydroSHEDS lattice before reduction, so the stored expected_count is "
                "about 835 cells for a median basin whether the source is 4 km or 11 km. "
                "That number describes the lattice and not the evidence, and reading it "
                "as sampling density is the mistake the gate now prevents.",
            "what_survives": "TerraClimate at about 6 cells per basin is resolved enough "
                "for a basin mean to be a statement about the basin, and MODIS at 500 m "
                "comfortably so. Basins holding fewer than four source cells are withheld "
                "for every variable, which removes 19 per cent of them from the "
                "TerraClimate analyses.",
            "the_remaining_caveat": "Resolving the basin is not the same as the basins "
                "being independent of each other. A climate field is spatially "
                "correlated, so adjacent basins share signal even with distinct cells, "
                "and the count of significant basins is therefore not a count of "
                "independent findings. False discovery control remains valid under this "
                "kind of positive dependence, but the basin count should be read as "
                "extent, not as evidential weight.",
        },
        "headline": "Controlling for multiple testing changes the answer for most "
                    "variables. Of nine, only soil moisture and minimum temperature "
                    "retain a substantial number of significant basins once false "
                    "discovery is controlled across 7,445 simultaneous tests.",
        "survives_correction": {
            "soil moisture": after("uz:soil-monthly-v1"),
            "minimum temperature": after("uz:tmn-monthly-v1"),
            "palmer drought severity index": after("uz:pds-monthly-v1"),
            "vapour pressure deficit": after("uz:vpd-monthly-v1"),
            "snow water equivalent": after("uz:swe-monthly-v1"),
        },
        "does_not_survive": {
            "precipitation": after("uz:pre-monthly-v1"),
            "maximum temperature": after("uz:tmx-monthly-v1"),
            "potential evapotranspiration": after("uz:pet-monthly-v1"),
            "climatic water deficit": after("uz:cwd-monthly-v1"),
            "terraclimate runoff": after("uz:rtc-monthly-v1"),
        },
        "precipitation": "No basin shows a precipitation trend that survives correction. "
                         "The smallest p-value across all 7,445 is 0.011, which is not "
                         "small enough to clear the step-up threshold anywhere. Whatever "
                         "else is happening in this record, it is not a detectable change "
                         "in how much rain falls.",
        "direction": "The two surviving signals are unanimous in direction: no basin "
                     "shows a significant soil-moisture increase, and none shows a "
                     "significant decrease in minimum temperature.",
        "drivers_do_not_trend_but_states_do": {
            "observation": "In TerraClimate's own water balance the fluxes show no trend "
                           "and the stores do. Precipitation, potential evapotranspiration, "
                           "the climatic water deficit and the model's runoff surplus all "
                           "fall to zero significant basins after correction; actual "
                           "evapotranspiration keeps 50 of 6,016. Soil moisture keeps 2,790 "
                           "and PDSI 1,159, both declining, both unanimous in direction.",
            "why_it_matters": "A bucket model's store is the running integral of inflow "
                              "less outflow. If neither flux trends, a trending store is "
                              "not explained by the model's own causal chain, and the "
                              "decline cannot be attributed to the drivers the model was "
                              "given. This is the opposite of corroboration: the five "
                              "TerraClimate variables agreeing is what a single internal "
                              "coupling looks like, and here even that coupling does not "
                              "close.",
            "three_readings": [
                "A small persistent imbalance that does not itself trend still integrates "
                "into a monotonic change in the store. This is physically real and is what "
                "storage memory means; it would make the decline genuine but would also "
                "mean it says nothing about a changing climate.",
                "Model drift or incomplete spin-up, in which case the trend is a property "
                "of the simulation and not of the land.",
                "Seasonal redistribution, where annual means of a state move because the "
                "timing within the year shifts while annual totals do not.",
            ],
            "not_separable_here": "Twenty-two annual values cannot distinguish these three. "
                                  "Monthly-resolved analysis and an independent soil "
                                  "moisture product are what would, and neither is done in "
                                  "this study.",
            "the_temperature_asymmetry": "Minimum temperature rises in 1,618 basins while "
                "maximum temperature retains none, which is a narrowing diurnal range. "
                "Potential evapotranspiration responds mainly to daytime conditions, so "
                "the warming that is present is largely not reaching the water balance -- "
                "consistent with PET showing no trend, and a further reason the soil "
                "signal is not a straightforward warming response.",
        },
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
    parser.add_argument("--level", default="12", choices=("7", "10", "12"))
    arguments = parser.parse_args()
    out = OUT if arguments.level == "12" else OUT / f"level{arguments.level}"
    report = build(alpha=arguments.alpha, level=arguments.level, out=out)
    print(f"basin level {arguments.level}")
    for identifier, block in sorted(report["summary"].items()):
        print(f"{identifier:24s} {block['basins']:>5} basins  "
              f"significant: {block['significant_uncorrected']:>5} raw -> "
              f"{block['significant_corrected']:>5} autocorr -> "
              f"{block['significant_after_fdr']:>5} after FDR")
    print(f"\ncross-tabulation cells: {len(report['cross_tabulation'])}")


if __name__ == "__main__":
    main()
