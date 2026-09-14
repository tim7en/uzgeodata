"""How much the diagram moves, and what actually moves it.

The published applications of this method run sensitivity analysis on an engineered
system: vary the loss rate, the connection rate, the treatment capacity, and see what
the diagram looks like in 2048. That works because a utility has measured all of those
and can defend a range for each.

Here almost none of it is measured, so varying it would be varying assumptions and
calling the spread a result. What *is* measured is the supply side -- twenty-two years
of precipitation and evapotranspiration across 7,445 basins -- and that turns out to be
where the sensitivity lives anyway. Diversion is set by allocation and moves little
between years; what arrives varies by a factor of three.

So this computes two things and keeps them apart:

**Observed sensitivity.** The year-by-year climatic surplus against the recorded
diversion. No assumption enters: it is the measured record on one side and the
administering bodies' own figure on the other. This is the finding.

**Scenario arithmetic.** What the states' own legal commitments would do to that ratio.
An earlier draft used 10 and 20 per cent because they were tidy numbers, which made the
analysis unfalsifiable against anything a government had actually promised. The headline
case is now Uzbekistan's irrigation efficiency target -- 0.63 to 0.73 by 2030, adopted in
УП-6024 -- because a delivery efficiency converts arithmetically into a withdrawal
reduction in a way an area or a canal length does not. It is still arithmetic and not a
model: no mechanism, cost or delivery risk is represented.

What is deliberately not modelled: distribution losses, groundwater substitution and
connection rates -- the three levers the method's own applications pull hardest. No
baseline is published for any of them here, so a scenario over them would be a picture
of an assumption.
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
from ATLAS_MODULES.core import query
from ATLAS_MODULES.core.runtime import utc_now, write_json

FLOW = ROOT / "PUBLISHED/data/water-flow"
STORE = ROOT / "PUBLISHED/data/atlas/observations"
HYDRO = ROOT / "PUBLISHED/data/hydroclimate"
OUT = FLOW / "regional-water-flow-sensitivity.json"

MM_KM2_TO_KM3 = 1e-6
STRESS = 0.8   # diversion at four fifths of the surplus: no comfortable margin left


def annual_balance(store=STORE):
    """Region-wide precipitation, evapotranspiration and their difference, per year."""
    collection = json.loads((HYDRO / "basins-level12.geojson").read_text(encoding="utf-8"))
    areas = [(str(f["properties"]["HYBAS_ID"]), float(f["properties"]["SUB_AREA"]))
             for f in collection["features"]]
    connection = query.connect(store)
    try:
        connection.execute("CREATE OR REPLACE TABLE basin_area (basin_id VARCHAR, area_km2 DOUBLE)")
        connection.executemany("INSERT INTO basin_area VALUES (?, ?)", areas)
        rows = connection.execute("""
            WITH annual AS (
              SELECT basin_id, regexp_extract(attribute_id, '([^.]+)$', 1) AS v,
                     year, sum(value) AS mm
              FROM observations
              WHERE attribute_id IN ('uzgeodata.dated.v1.pre_mm_s',
                                     'uzgeodata.dated.v1.aet_mm_s')
              GROUP BY 1, 2, 3 HAVING count(*) = 12
            )
            SELECT year,
                   sum(CASE WHEN v = 'pre_mm_s' THEN mm * area_km2 * ? END),
                   sum(CASE WHEN v = 'aet_mm_s' THEN mm * area_km2 * ? END)
            FROM annual JOIN basin_area USING (basin_id)
            GROUP BY 1 ORDER BY 1""", [MM_KM2_TO_KM3, MM_KM2_TO_KM3]).fetchall()
    finally:
        connection.close()
    return [{"year": year, "precipitation": round(p, 1), "evapotranspiration": round(a, 1),
             "surplus": round(p - a, 1)} for year, p, a in rows]


def slope(years, values):
    mean_x, mean_y = statistics.fmean(years), statistics.fmean(values)
    spread = sum((x - mean_x) ** 2 for x in years)
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(years, values)) / spread


def figures(path=FLOW / "regional-withdrawals.csv"):
    return {row["figure_id"]: row for row in csv.DictReader(path.open(encoding="utf-8"))}


def build(store=STORE):
    balance = annual_balance(store)
    entries = figures()
    diversion = round(float(entries["icwc-amu-actual-2022"]["value"])
                      + float(entries["icwc-syr-actual-2022"]["value"]), 2)
    agriculture = float(entries["uz-share-agriculture"]["value"]) / 100

    years = [row["year"] for row in balance]
    surplus = [row["surplus"] for row in balance]
    for row in balance:
        row["diversion_share"] = round(diversion / row["surplus"], 3)
        row["stressed"] = row["diversion_share"] >= STRESS
        row["exceeded"] = row["diversion_share"] > 1.0

    half = len(balance) // 2
    early = statistics.fmean(surplus[:half])
    late = statistics.fmean(surplus[half:])

    observed = {
        "years": [years[0], years[-1]],
        "diversion_km3": diversion,
        "diversion_note": "The 2022 hydrological year, held constant across every year "
                          "because allocation is what it is set at, not what the weather "
                          "delivered. ICWC publishes limits and actuals by year; only one "
                          "year is transcribed here, and extending that is the first thing "
                          "worth doing.",
        "surplus_km3": {
            "mean": round(statistics.fmean(surplus), 1),
            "sd": round(statistics.pstdev(surplus), 1),
            "min": {"year": years[surplus.index(min(surplus))], "value": min(surplus)},
            "max": {"year": years[surplus.index(max(surplus))], "value": max(surplus)},
            "range_factor": round(max(surplus) / min(surplus), 2),
        },
        "share_of_surplus": {
            "wettest_year": round(diversion / max(surplus), 3),
            "driest_year": round(diversion / min(surplus), 3),
        },
        "stressed_years": [row["year"] for row in balance if row["stressed"]],
        "exceeded_years": [row["year"] for row in balance if row["exceeded"]],
        "trend_km3_per_year": {
            "precipitation": round(slope(years, [r["precipitation"] for r in balance]), 2),
            "evapotranspiration": round(slope(years, [r["evapotranspiration"] for r in balance]), 2),
            "surplus": round(slope(years, surplus), 2),
        },
        "halves_km3": {"first": round(early, 1), "second": round(late, 1),
                       "change_percent": round((late - early) / early * 100, 1)},
        "annual": balance,
    }

    # Scenario arithmetic, taken from the states' own legal instruments rather than from
    # round numbers. An earlier draft used 10 and 20 per cent because they were tidy;
    # that made the analysis unfalsifiable against anything a government had actually
    # committed to. These are commitments in law, with the act cited.
    targets = {row["target_id"]: row for row in csv.DictReader(
        (FLOW / "national-targets.csv").open(encoding="utf-8"))}
    efficiency = targets["uz-irrigation-efficiency"]
    baseline_kpd, target_kpd = float(efficiency["baseline"]), float(efficiency["target"])
    # Delivering the same water to the same fields at a higher delivery efficiency needs
    # proportionally less withdrawn. This is the conversion the efficiency target makes
    # possible and that an area or a length target does not.
    policy_cut = 1 - baseline_kpd / target_kpd

    scenarios = []
    for cut, label, note in (
        (0.0, "As recorded", "The 2022 diversion, unchanged."),
        (policy_cut,
         f"Uzbekistan meets its efficiency target (КПД {baseline_kpd}→{target_kpd})",
         f"УП-6024 commits Uzbekistan to raising irrigation system efficiency from "
         f"{baseline_kpd} to {target_kpd} by 2030. Delivering the same water to the same "
         f"fields at that efficiency requires {policy_cut:.1%} less withdrawal. This is "
         f"the state's own commitment, converted arithmetically; no mechanism, cost or "
         f"delivery risk is represented."),
        (0.20, "A fifth less agricultural withdrawal",
         "Beyond any current commitment, shown to indicate what order of change would be "
         "needed to clear the dry-year threshold rather than merely approach it."),
    ):
        saved = diversion * agriculture * cut
        adjusted = diversion - saved
        stressed = [row["year"] for row in balance if adjusted / row["surplus"] >= STRESS]
        scenarios.append({
            "label": label, "reduction": cut, "note": note,
            "diversion_km3": round(adjusted, 2),
            "water_freed_km3": round(saved, 2),
            "stressed_years": len(stressed),
            "exceeded_years": len([r for r in balance if adjusted > r["surplus"]]),
            "driest_year_share": round(adjusted / min(surplus), 3),
            "basis": "derived",
        })

    report = {
        "generated_at": utc_now(),
        "title": "What moves the diagram",
        "stress_threshold": STRESS,
        "stress_meaning": "Diversion at four fifths of the climatic surplus. Not a "
                          "regulatory threshold and not a forecast; a line drawn to count "
                          "how often the margin is thin.",
        "observed": observed,
        "scenarios": scenarios,
        "policy_targets": {
            "note": "Taken from the states' own legal instruments. Only two of the five "
                    "riparian states publish numeric water-saving targets, and only one "
                    "of those two states it as a delivery efficiency, which is the form "
                    "that converts directly into a withdrawal figure. Kazakhstan states "
                    "its as a volume, which is directly comparable. The three remaining "
                    "states are recorded as having strategies without located numbers, "
                    "because an absence of published targets is itself comparable "
                    "information about a shared river.",
            "uzbekistan_efficiency_implies_reduction": round(policy_cut, 4),
            "targets": list(targets.values()),
        },
        "not_modelled": {
            "distribution_losses": "No baseline is published for this region. The method's "
                                   "own applications usually find this the largest single "
                                   "lever, and it cannot be evaluated here.",
            "groundwater_substitution": "Abstraction is not published at a usable scale, so "
                                        "substituting groundwater for surface water cannot "
                                        "be represented.",
            "connection_rates": "Not published. The wastewater inventory gives what 53 "
                                "plants treat, not what share of generated wastewater "
                                "reaches them.",
        },
        "caution": "A twenty-two year slope is a statement about this record, not an "
                   "attribution to climate change. Decadal variability alone can produce a "
                   "decline of this size, and nothing here separates the two. What does not "
                   "depend on that question is the operational finding: in the later half "
                   "of the record the margin between what arrives and what is taken is "
                   "repeatedly thin, whatever is causing it.",
    }
    write_json(OUT, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    report = build()
    observed = report["observed"]
    print(f"surplus {observed['surplus_km3']['mean']} km3/yr mean, "
          f"sd {observed['surplus_km3']['sd']}, "
          f"{observed['surplus_km3']['min']['value']} ({observed['surplus_km3']['min']['year']}) "
          f"to {observed['surplus_km3']['max']['value']} ({observed['surplus_km3']['max']['year']})")
    print(f"diversion is {observed['share_of_surplus']['wettest_year']:.0%} of the surplus in "
          f"the wettest year and {observed['share_of_surplus']['driest_year']:.0%} in the driest")
    print(f"stressed years: {observed['stressed_years']}")
    print(f"exceeded years: {observed['exceeded_years']}")
    for entry in report["scenarios"]:
        print(f"  {entry['label']:38s} frees {entry['water_freed_km3']:5.2f} km3  "
              f"stressed years {entry['stressed_years']:2d}  exceeded {entry['exceeded_years']}")


if __name__ == "__main__":
    main()
