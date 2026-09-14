"""A water flow diagram for the Amu Darya and Syr Darya, typed by how each flow is known.

Adapted from the Water Flow Diagram method (waterflowdiagram.ch), which draws a
municipality's water from abstraction through distribution, use and wastewater back to
the environment so stakeholders can see where it goes. Its published applications --
Bern, St Gallen, Tarapoto, Agadir -- are municipal, where one utility can account for
what it abstracted, delivered and lost.

Nothing at that resolution is published here. Withdrawal in this region is administered
by country and canal system, not by catchment, and Uzbek water is canal-delivered across
basin divides, so a national figure cannot be honestly split to level-12 basins by any
rule worth defending. Drawing it anyway would produce the familiar picture and invent
most of it.

So the scale is the basin system, and the diagram carries a second dimension the method
does not: every flow states how it is known.

    measured      This project's own record: 22 years of monthly precipitation,
                  evapotranspiration and runoff across 7,445 basins, and wastewater
                  volumes from a plant inventory. Reproducible from the published cube.
    administered  Published by the bodies that allocate the water -- ICWC and its Basin
                  Water Organizations. These are what was allocated and diverted, not an
                  independent measurement of what flowed, and the distinction matters
                  where a limit and an actual differ by a fifth.
    derived       Arithmetic on the two above, with the operation stated. A national
                  sectoral share applied to a national total is derived; the same share
                  applied to one basin would be invention, and is not drawn.
    unquantified  A flow the method expects and no source here supplies. Drawn as a gap
                  with its width unset rather than omitted, because a diagram that
                  silently drops distribution losses reads as a system without any.

The colouring follows that division. A reader can see at a glance which parts of this
picture are evidence and which are administrative record, which is the question a
reader of a Sankey diagram most often cannot answer and most needs to.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import query
from ATLAS_MODULES.core.runtime import utc_now, write_json

FLOW = ROOT / "PUBLISHED/data/water-flow"
STORE = ROOT / "PUBLISHED/data/atlas/observations"
HYDRO = ROOT / "PUBLISHED/data/hydroclimate"
OUT = FLOW / "regional-water-flow.json"

# mm over km2 -> km3
MM_KM2_TO_KM3 = 1e-6

BASIS = {
    "measured": {
        "label": "Measured",
        "colour": "#1b7f5a",
        "meaning": "This project's observation record or plant inventory. Reproducible "
                   "from the published release.",
    },
    "administered": {
        "label": "Administered",
        "colour": "#2b6cb0",
        "meaning": "Published by the bodies that allocate the water. What was allocated "
                   "and diverted, not an independent measurement of what flowed.",
    },
    "derived": {
        "label": "Derived",
        "colour": "#b7791f",
        "meaning": "Arithmetic on the above, with the operation stated on the flow.",
    },
    "unquantified": {
        "label": "Not quantified",
        "colour": "#9b2c2c",
        "meaning": "A flow the method expects and no source here supplies. Drawn as a "
                   "gap rather than omitted, so its absence is visible.",
    },
}


# Panel B carries nothing but ICWC figures, so colour there is free to say which
# country rather than how it is known -- the question a transboundary diagram is
# actually asked. Ordered upstream to downstream, which is the thing a reader needs to
# see: Kyrgyzstan and Tajikistan generate the flow, Kazakhstan receives what is left.
COUNTRY = {
    "kyrgyzstan":   {"label": "Kyrgyzstan",   "colour": "#7c3aed", "position": "headwater"},
    "tajikistan":   {"label": "Tajikistan",   "colour": "#0891b2", "position": "headwater"},
    "uzbekistan":   {"label": "Uzbekistan",   "colour": "#16a34a", "position": "midstream"},
    "turkmenistan": {"label": "Turkmenistan", "colour": "#ea580c", "position": "midstream"},
    "kazakhstan":   {"label": "Kazakhstan",   "colour": "#2563eb", "position": "downstream"},
    "terminal":     {"label": "Aral Sea",     "colour": "#64748b", "position": "terminal"},
}


def basin_areas(path=HYDRO / "basins-level12.geojson"):
    collection = json.loads(path.read_text(encoding="utf-8"))
    return {str(f["properties"]["HYBAS_ID"]): float(f["properties"]["SUB_AREA"])
            for f in collection["features"]}


def measured_fluxes(store=STORE, areas=None):
    """Regional mean annual volumes for the fluxes the record carries.

    Area-weighted from monthly basin means, and only from years where all twelve
    months are present: a year short of a month is not an annual total, which is the
    same rule the seasonal products apply.
    """
    areas = areas or basin_areas()
    connection = query.connect(store)
    try:
        connection.execute("CREATE OR REPLACE TABLE basin_area (basin_id VARCHAR, area_km2 DOUBLE)")
        connection.executemany("INSERT INTO basin_area VALUES (?, ?)", list(areas.items()))
        rows = connection.execute("""
            WITH annual AS (
              SELECT basin_id,
                     regexp_extract(attribute_id, '([^.]+)$', 1) AS variable,
                     year, sum(value) AS mm
              FROM observations
              WHERE attribute_id IN ('uzgeodata.dated.v1.pre_mm_s',
                                     'uzgeodata.dated.v1.aet_mm_s',
                                     'uzgeodata.dated.v1.run_mm_s')
              GROUP BY 1, 2, 3 HAVING count(*) = 12
            ), volumes AS (
              SELECT variable, year, sum(mm * area_km2 * ?) AS km3
              FROM annual JOIN basin_area USING (basin_id) GROUP BY 1, 2
            )
            SELECT variable, avg(km3), min(year), max(year), count(*)
            FROM volumes GROUP BY 1""", [MM_KM2_TO_KM3]).fetchall()
    finally:
        connection.close()
    return {variable: {"km3_per_year": round(value, 1), "years": [first, last],
                       "complete_years": count}
            for variable, value, first, last, count in rows}


def wastewater(path=HYDRO / "wastewater-plants-transboundary.csv"):
    """The one urban flow this region publishes in volume."""
    plants = [row for row in csv.DictReader(path.open(encoding="utf-8"))
              if row.get("wastewater_discharge_m3_d", "").strip()]
    daily = sum(float(row["wastewater_discharge_m3_d"]) for row in plants)
    served = sum(float(row["population_served"]) for row in plants
                 if row.get("population_served", "").strip())
    levels = {}
    for row in plants:
        levels[row["treatment_level"]] = levels.get(row["treatment_level"], 0) + 1
    return {
        "plants": len(plants),
        "km3_per_year": round(daily * 365 / 1e9, 4),
        "m3_per_day": round(daily),
        "population_served": int(served),
        "litres_per_person_day": round(daily / served * 1000, 1) if served else None,
        "treatment_levels": levels,
        "basins": len({row["hybas_id_level12"] for row in plants if row["hybas_id_level12"]}),
    }


def administered(path=FLOW / "regional-withdrawals.csv"):
    return {row["figure_id"]: row for row in csv.DictReader(path.open(encoding="utf-8"))}


def number(entry):
    return float(entry["value"])


def build(store=STORE):
    fluxes = measured_fluxes(store)
    plants = wastewater()
    figures = administered()
    sources = json.loads((FLOW / "sources.json").read_text(encoding="utf-8"))

    rain = fluxes["pre_mm_s"]["km3_per_year"]
    evaporated = fluxes["aet_mm_s"]["km3_per_year"]
    runoff = fluxes["run_mm_s"]["km3_per_year"]
    surplus = round(rain - evaporated, 1)

    amu = number(figures["icwc-amu-actual-2022"])
    syr = number(figures["icwc-syr-actual-2022"])
    diverted = round(amu + syr, 2)

    uzbek = number(figures["icwc-amu-uz-2022"])
    shares = {row["sector"]: number(row) for row in figures.values()
              if row["component"] == "sector_share"}

    nodes, links = [], []

    def node(key, label, note=None):
        nodes.append({"id": key, "label": label, "note": note})
        return key

    def link(source, target, value, basis, label, note=None, operation=None, country=None):
        links.append({"source": source, "target": target,
                      "value": None if value is None else round(value, 3),
                      "unit": "km3/yr", "basis": basis, "label": label,
                      "note": note, "operation": operation, "country": country})

    # --- the measured natural balance -------------------------------------------
    node("precipitation", "Precipitation",
         f"Area-weighted over 965,725 km2 from {fluxes['pre_mm_s']['years'][0]}-"
         f"{fluxes['pre_mm_s']['years'][1]}")
    node("evapotranspiration", "Evapotranspiration", "Returned to atmosphere")
    node("surplus", "Climatic surplus", "Precipitation less evapotranspiration")
    link("precipitation", "evapotranspiration", evaporated, "measured",
         "Evapotranspiration", "TerraClimate actual evapotranspiration, 22 complete years")
    link("precipitation", "surplus", surplus, "derived",
         "Climatic surplus", "Not a renewable-resource figure: it neither routes water "
         "nor accounts for storage, glacier melt or inflow from outside the domain",
         operation="precipitation - evapotranspiration")

    # --- what the administering bodies divert ------------------------------------
    node("amu", "Amu Darya diversion", "ICWC/BWO, 2022 hydrological year")
    node("syr", "Syr Darya diversion", "ICWC/BWO, 2022 hydrological year")
    link("surplus", "amu", amu, "administered", "Amu Darya diverted",
         "44.26 of a 55.23 limit, 80 per cent")
    link("surplus", "syr", syr, "administered", "Syr Darya diverted",
         "86 per cent of the established limit")

    # Whatever the surplus holds beyond the diversion is not "available water": it is
    # the part of the difference this diagram cannot account for, and says so.
    node("unaccounted", "Not accounted for",
         "The difference between the climatic surplus and recorded diversion. It "
         "includes river outflow, wetland and delta losses, aquifer recharge, and the "
         "mismatch between two models on different grids. It is not spare water.")
    link("surplus", "unaccounted", round(surplus - diverted, 2), "derived",
         "Unaccounted difference",
         "A residual, not a resource. The runoff series puts the land-surface flux at "
         f"{runoff} km3/yr, well above the surplus, which is how visible the model "
         "mismatch is at this scale.",
         operation="climatic surplus - recorded diversion")

    # --- countries, and where the rivers actually end ----------------------------
    # The earlier draft drew the Syr Darya as a terminal sink, which is wrong twice
    # over: the 13.83 km3 is withdrawal "up to entry point to the Shardara reservoir"
    # and so excludes Kazakhstan entirely, and the river continues past it to the
    # Northern Aral. A transboundary diagram that stops at the last upstream user
    # describes the dispute from one bank.
    for key, code in (("tj", "tajikistan"), ("tm", "turkmenistan"), ("uz", "uzbekistan")):
        entry = figures[f"icwc-amu-{key}-2022"]
        node(f"amu-{key}", COUNTRY[code]["label"], entry["note"])
        link("amu", f"amu-{key}", number(entry), "administered",
             COUNTRY[code]["label"], entry["note"], country=code)

    node("syr-upstream", "Withdrawn above Chardara",
         "Kyrgyzstan, Tajikistan and Uzbekistan. The published 2022 total is bounded at "
         "the Shardara reservoir and is not split by country; the country figures "
         "available are 2026 limits, tabulated separately rather than drawn at a width "
         "that would imply they are the same year.")
    link("syr", "syr-upstream", number(figures["icwc-syr-above-chardara-2022"]),
         "administered", "Withdrawn above Chardara",
         "Excludes Kazakhstan, which lies downstream of the reservoir", country="uzbekistan")

    node("syr-kz", COUNTRY["kazakhstan"]["label"],
         "Downstream of Chardara. Its withdrawal is outside the 13.83 km3 above, and is "
         "published as a limit rather than an actual.")
    link("syr", "syr-kz", None, "unquantified", "Kazakhstan, downstream",
         "The 2022 actual for Kazakhstan below Chardara is not published. Its 2026 limit "
         "is 1.369 km3/yr. Drawn as a gap because the diagram cannot honestly give it a "
         "width.", country="kazakhstan")

    # Terminal flows: what is left of two rivers that once fed a sea.
    north = number(figures["icwc-syr-north-aral-2022"])
    large = number(figures["icwc-large-aral-2022"])
    node("north-aral", "Northern Aral Sea", "Fed by the Syr Darya below Chardara")
    node("large-aral", "Large Aral Sea",
         "Inflow in 2022 came entirely from drainage canals, not from river discharge")
    link("syr-kz", "north-aral", north, "administered", "To the Northern Aral",
         "0.82 km3 in 2022, per Kazakhstan's water authorities", country="terminal")

    delta = number(figures["icwc-amu-delta-2022"])
    node("amu-delta", "Amu Darya delta")
    link("amu-uz", "amu-delta", delta, "administered", "To the delta",
         "2.055 km3 reached the delta in 2022", country="terminal")
    link("amu-delta", "large-aral", large, "administered", "To the Large Aral",
         "0.5035 km3, down from 0.65 in 2021, and sourced entirely from drainage canals "
         "rather than river discharge", country="terminal")

    # --- sectors, at the only scale the shares support ---------------------------
    node("uz-use", "Uzbekistan sectoral use",
         "Sectoral shares are national and are applied here to what remains of the "
         "country's Amu Darya diversion after the delta")
    link("amu-uz", "uz-use", round(uzbek - delta, 3), "administered", "To sectoral use",
         "The country's Amu Darya diversion less what reached the delta")
    remaining = uzbek - delta
    for sector, share in sorted(shares.items(), key=lambda item: -item[1]):
        pretty = sector.replace("_", " ").title()
        node(f"sector-{sector}", pretty)
        link("uz-use", f"sector-{sector}", remaining * share / 100, "derived", pretty,
             f"National share of {share} per cent applied to what remains of the "
             "country's Amu Darya diversion. The share is national; the diversion is one "
             "basin. Treat the split as indicative of proportion, not as a basin "
             "measurement.",
             operation=f"{remaining:.3f} km3 x {share}%")

    # --- returns ------------------------------------------------------------------
    node("wastewater", "Treated wastewater",
         f"{plants['plants']} plants, {plants['population_served']:,} people served")
    link("sector-municipal", "wastewater", plants["km3_per_year"], "measured",
         "Treated wastewater return",
         f"{plants['m3_per_day']:,} m3/d across {plants['plants']} plants in "
         f"{plants['basins']} basins, {plants['litres_per_person_day']} L/person/day. "
         "The one urban flow published in volume here.")

    drainage = number(figures["uz-drainage-reuse"])
    node("drainage", "Collector-drainage reuse", "National figure")
    link("sector-agriculture", "drainage", drainage, "administered",
         "Collector-drainage reuse", "Reused collector and drainage water, nationally")

    node("environment", "Returned to rivers and the delta")
    link("wastewater", "environment", plants["km3_per_year"], "measured",
         "Discharged to rivers", "Outfalls located to level-12 basins")
    link("drainage", "environment", drainage, "administered", "Returned via drains")

    # --- what the method expects and nothing here supplies ------------------------
    for key, label, why in (
        ("gap-losses", "Distribution losses",
         "Central to the method and often the largest single finding in its published "
         "applications. No baseline is published for this region: the 2023 national "
         "plan targets a 10 per cent reduction without stating what from."),
        ("gap-groundwater", "Groundwater abstraction",
         "The method separates surface from groundwater sources. National usable "
         "groundwater is given as 0.5 km3/yr against an estimated 27.6 km3/yr yield, "
         "but abstraction is not published at any scale this diagram can use."),
        ("gap-untreated", "Untreated wastewater",
         "The inventory carries 53 plants and the volume they treat. What is generated "
         "and never reaches a plant is the quantity the method most wants and no source "
         "here reports."),
    ):
        node(key, label, why)
        link("uz-use", key, None, "unquantified", label, why)

    report = {
        "generated_at": utc_now(),
        "title": "Where the region's water goes",
        "scope": "Amu Darya and Syr Darya basins, 965,725 km2, 7,445 level-12 basins",
        "method": sources["method_reference"],
        "basis_legend": BASIS,
        "country_legend": COUNTRY,
        "nodes": nodes,
        "links": links,
        "measured": {"fluxes_km3_per_year": fluxes, "wastewater": plants},
        "administered_year": 2022,
        "sources": sources["sources"],
        "reuse": sources["reuse"],
        "reading": {
            "scale": "Basin systems, not municipalities. Withdrawal here is administered "
                     "by country and canal system while the record is organised by "
                     "catchment, and canal delivery crosses basin divides, so a national "
                     "figure cannot be honestly disaggregated to a basin.",
            "years": "The measured fluxes are 22-year means; the administered figures are "
                     "the 2022 hydrological year. They are drawn together because that is "
                     "what is published, and the mismatch is stated rather than hidden by "
                     "averaging one to the other.",
            "closure": "This diagram does not close, and is not made to. Precipitation "
                       "less evapotranspiration leaves a surplus larger than the recorded "
                       "diversion, while the runoff series exceeds that surplus outright: "
                       "two models on different grids disagree, and forcing the arrows to "
                       "balance would hide exactly the thing worth seeing.",
            "colour": "Colour is how a flow is known, not what kind of water it is. That "
                      "is the division this region's data makes necessary and it is the "
                      "question a reader of a Sankey usually cannot answer.",
        },
    }
    write_json(OUT, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    arguments = parser.parse_args()
    report = build()
    summary = {k: v for k, v in report.items() if k not in ("nodes", "links", "sources")}
    summary["nodes"] = len(report["nodes"])
    summary["links"] = len(report["links"])
    print(json.dumps(summary, indent=2, ensure_ascii=False)[:2600])


if __name__ == "__main__":
    main()
