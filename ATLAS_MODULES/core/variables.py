"""The analytical variables this project is willing to answer for.

A question arrives as a concept -- precipitation, drought, vegetation -- and the
store answers in attribute ids. Something has to stand between them and decide which
product answers which concept, and that decision has to be made once, in the open,
rather than by whoever is writing the query. Otherwise a reader asking for
precipitation is offered TerraClimate, ERA5-Land, CHIRPS and GPM and picks by
accident, and two analyses of the same basin disagree for reasons neither records.

So this registry is deliberately opinionated. Each variable names one preferred
product, and says why that one. A fallback is listed where a second source could
answer the same question, and naming it as a fallback is itself the statement that
it is not the preferred answer.

What it is not: a catalogue of everything available. Fourteen variables are registered
because fourteen are published as dated regional series. A concept with no product
behind it is recorded as unavailable rather than quietly resolved to something
close, because the failure that matters here is answering the wrong question
confidently.

The identifiers are versioned (`uz:pre-monthly-v1`) so an analysis can cite the
product it used and a later change of source becomes a new version rather than a
silent substitution under the same name.
"""
from __future__ import annotations

# A concept is what a reader asks for; a variable is what the store can answer with.
# Several concepts may resolve to one variable -- "rainfall" and "precipitation" are
# the same measurement -- and a concept with no variable is not a gap in the registry
# but a gap in the data, recorded below.
CONCEPTS = {
    "precipitation": "uz:pre-monthly-v1",
    "rainfall": "uz:pre-monthly-v1",
    "evapotranspiration": "uz:aet-monthly-v1",
    "actual evapotranspiration": "uz:aet-monthly-v1",
    "potential evapotranspiration": "uz:pet-monthly-v1",
    "reference evapotranspiration": "uz:pet-monthly-v1",
    "soil moisture": "uz:soil-monthly-v1",
    "runoff": "uz:run-monthly-v1",
    "snow": "uz:snw-monthly-v1",
    "snow cover": "uz:snw-monthly-v1",
    "temperature": "uz:tmp-monthly-v1",
    "mean temperature": "uz:tmp-monthly-v1",
    "maximum temperature": "uz:tmx-monthly-v1",
    "minimum temperature": "uz:tmn-monthly-v1",
    "vapour pressure deficit": "uz:vpd-monthly-v1",
    "vpd": "uz:vpd-monthly-v1",
    "climate water deficit": "uz:cwd-monthly-v1",
    "water deficit": "uz:cwd-monthly-v1",
    "snow water equivalent": "uz:swe-monthly-v1",
    "swe": "uz:swe-monthly-v1",
    "terraclimate runoff": "uz:rtc-monthly-v1",
    "palmer drought severity index": "uz:pds-monthly-v1",
    "pdsi": "uz:pds-monthly-v1",
}

# Concepts a reader will reasonably ask for and this project cannot yet answer.
# Listed so the answer is "not published" rather than something approximate: the
# registry's value is as much in what it refuses as in what it resolves.
UNAVAILABLE = {
    "vegetation": "No NDVI or EVI series is published. Nothing here substitutes for it.",
    "ndvi": "No vegetation index is published as a regional dated series.",
    "land surface temperature": "Air temperature is published; land surface temperature is not, "
                                "and the two are different measurements.",
    "drought index": "Ambiguous: two are offered and they are not interchangeable. SPI is derived "
                     "on demand from published precipitation by products.spi(), with the gamma "
                     "fit stated; the Palmer index is published as TerraClimate's modelled "
                     "series (ask for 'palmer drought severity index'). SPEI is not offered.",
    "surface water": "Published as a long-term climatology, not as a dated monthly series.",
    "discharge": "No gauged or modelled discharge series is published; runoff is a land-surface "
                 "flux and is not the same quantity.",
}

VARIABLES = {
    "uz:pre-monthly-v1": {
        "concept": "precipitation", "attribute": "uzgeodata.dated.v1.pre_mm_s",
        "unit": "millimetres per month", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "IDAHO_EPSCOR/TERRACLIMATE",
        "why": "Downscaled to about four kilometres, which matters where a level-12 basin sits "
               "in mountain terrain and a coarse cell would average a valley with a ridge.",
        "fallback": "ECMWF/ERA5_LAND/MONTHLY_AGGR",
        "fallback_cost": "About eleven kilometres, so a headwater basin may hold a single cell.",
        "kind": "flux",
    },
    "uz:aet-monthly-v1": {
        "concept": "actual evapotranspiration", "attribute": "uzgeodata.dated.v1.aet_mm_s",
        "unit": "millimetres per month", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "IDAHO_EPSCOR/TERRACLIMATE",
        "why": "Published on the same grid and water balance as precipitation and potential "
               "evapotranspiration, so the three can be differenced without crossing models.",
        "fallback": None, "kind": "flux",
    },
    "uz:pet-monthly-v1": {
        "concept": "potential evapotranspiration", "attribute": "uzgeodata.dated.v1.pet_mm_s",
        "unit": "millimetres per month", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "IDAHO_EPSCOR/TERRACLIMATE",
        "why": "Paired with actual evapotranspiration from one model, which is what makes their "
               "ratio a moisture index rather than a comparison of two conventions.",
        "fallback": None, "kind": "flux",
    },
    "uz:soil-monthly-v1": {
        "concept": "soil moisture", "attribute": "uzgeodata.dated.v1.soil_mm_s",
        "unit": "millimetres of soil moisture", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "IDAHO_EPSCOR/TERRACLIMATE",
        "why": "A modelled column store in millimetres. It is published as what it is and not "
               "relabelled as the percentage the atlas attribute holds.",
        "fallback": None, "kind": "state",
    },
    "uz:run-monthly-v1": {
        "concept": "runoff", "attribute": "uzgeodata.dated.v1.run_mm_s",
        "unit": "millimetres per month", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "ECMWF/ERA5_LAND/MONTHLY_AGGR",
        "why": "A land-surface model's runoff, kept as the answer because it was chosen first and "
               "the record's analyses use it. It is not discharge: it has not been routed and no "
               "gauge has been compared to it.",
        "fallback": "IDAHO_EPSCOR/TERRACLIMATE",
        "fallback_cost": "Published separately as uz:rtc-monthly-v1: a bucket model's surplus rather "
                         "than a land-surface scheme's, so the two differ in method, not only grid.",
        "kind": "flux",
    },
    "uz:snw-monthly-v1": {
        "concept": "snow cover", "attribute": "uzgeodata.dated.v1.snw_pc_s",
        "unit": "percent", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "frequency of snow-covered days in the month",
        "preferred": "MODIS/061/MYD10A1",
        "why": "Daily observations aggregated here, rather than the monthly product the atlas "
               "cites, so the count of contributing days is known per basin and month.",
        "fallback": None, "kind": "state",
        "caution": "Its gaps grow towards the present at constant source coverage, so the series "
                   "is published for inspection and withdrawn from trend analysis.",
    },
    "uz:tmp-monthly-v1": {
        "concept": "mean temperature", "attribute": "uzgeodata.dated.v1.tmp_dc_s",
        "unit": "degrees Celsius", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "ECMWF/ERA5_LAND/MONTHLY_AGGR",
        "why": "A true mean of hourly values. TerraClimate publishes only the daily extremes, "
               "and their midpoint is a different measurement that happens to carry the same name.",
        "fallback": "IDAHO_EPSCOR/TERRACLIMATE",
        "fallback_cost": "Finer at about four kilometres, but a midpoint of extremes rather than "
                         "a mean of hours, and about a degree warmer across this region.",
        "kind": "state",
    },
    "uz:tmx-monthly-v1": {
        "concept": "maximum temperature", "attribute": "uzgeodata.dated.v1.tmx_dc_s",
        "unit": "degrees Celsius", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "IDAHO_EPSCOR/TERRACLIMATE", "fallback": None, "kind": "state",
        "why": "The month's daily maxima. ERA5-Land publishes no daily extreme on this grid.",
    },
    "uz:tmn-monthly-v1": {
        "concept": "minimum temperature", "attribute": "uzgeodata.dated.v1.tmn_dc_s",
        "unit": "degrees Celsius", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "IDAHO_EPSCOR/TERRACLIMATE", "fallback": None, "kind": "state",
        "why": "The month's daily minima, paired with the maxima from the same model.",
    },
    # The rest of TerraClimate's water balance. All five are outputs of the model that
    # produces aet, pet and soil, so they agree with those by construction and none is a
    # second opinion on them.
    "uz:vpd-monthly-v1": {
        "concept": "vapour pressure deficit", "attribute": "uzgeodata.dated.v1.vpd_kp_s",
        "unit": "kilopascals", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "IDAHO_EPSCOR/TERRACLIMATE", "fallback": None, "kind": "state",
        "why": "Published on the same four-kilometre grid as the temperatures it depends on, "
               "rather than derived here from a humidity field this project does not hold.",
    },
    "uz:cwd-monthly-v1": {
        "concept": "climate water deficit", "attribute": "uzgeodata.dated.v1.cwd_mm_s",
        "unit": "millimetres per month", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "IDAHO_EPSCOR/TERRACLIMATE", "fallback": None, "kind": "flux",
        "why": "Demand the water balance could not meet: PET less AET inside one model, with soil "
               "storage accounted for, which the crude precipitation-less-AET balance is not.",
    },
    "uz:swe-monthly-v1": {
        "concept": "snow water equivalent", "attribute": "uzgeodata.dated.v1.swe_mm_s",
        "unit": "millimetres of snow water equivalent", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "IDAHO_EPSCOR/TERRACLIMATE", "fallback": None, "kind": "state",
        "why": "The water a snowpack holds, which snow cover cannot give: cover is extent only.",
        "caution": "Modelled from temperature and precipitation, not observed. It is not a "
                   "measurement to validate MODIS snow cover against, and in high terrain the "
                   "four-kilometre grid smooths the pack the melt actually comes from.",
    },
    "uz:rtc-monthly-v1": {
        "concept": "terraclimate runoff", "attribute": "uzgeodata.dated.v1.rtc_mm_s",
        "unit": "millimetres per month", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "IDAHO_EPSCOR/TERRACLIMATE", "fallback": None, "kind": "flux",
        "why": "A second runoff to set against ERA5-Land's, from a different model. Asking for "
               "'runoff' still resolves to ERA5-Land; this one has to be asked for by name.",
    },
    "uz:pds-monthly-v1": {
        "concept": "palmer drought severity index", "attribute": "uzgeodata.dated.v1.pds_ix_s",
        "unit": "index (dimensionless)", "cadence": "monthly", "coverage": [2003, 2024],
        "support": "basin, local", "aggregation": "area-weighted mean of the monthly field",
        "preferred": "IDAHO_EPSCOR/TERRACLIMATE", "fallback": None, "kind": "state",
        "why": "A published drought index beside the SPI derived here, computed by the source "
               "from its own water balance rather than from precipitation alone.",
        "caution": "An index already standardised by its source. Averaging it over basins or "
                   "months is descriptive; it is not re-standardised, and anomalies of it are "
                   "anomalies of an anomaly.",
    },
}


class Unavailable(LookupError):
    """A concept this project does not answer for, and the reason it does not."""


def resolve(concept):
    """The analytical variable that answers a concept.

    Raises rather than guessing. A caller asking for vegetation gets told there is no
    vegetation series, which is a useful answer; being handed something adjacent
    because it was the nearest match is not.
    """
    key = str(concept).strip().lower()
    if key in CONCEPTS:
        return CONCEPTS[key]
    if key in VARIABLES:
        return key
    if key in UNAVAILABLE:
        raise Unavailable(f"{concept}: {UNAVAILABLE[key]}")
    raise Unavailable(f"{concept}: no analytical variable is registered under that name. "
                      f"Registered concepts: {', '.join(sorted(CONCEPTS))}.")


def attribute(concept):
    """The store's attribute id for a concept, ready to query with."""
    return VARIABLES[resolve(concept)]["attribute"]


def describe(identifier):
    """One variable, with the source behind it and the reason it was preferred."""
    return {"id": identifier, **VARIABLES[identifier]}


def registry(coverage=None, observed_through=None):
    """Everything registered, with what is deliberately not, for publication."""
    entries = {key: describe(key) for key in sorted(VARIABLES)}
    if coverage is not None:
        for key, entry in entries.items():
            measured = coverage.get(entry["attribute"])
            if measured is None:
                raise ValueError(f"{key}: registered variable is missing from the cube")
            entry["coverage"] = list(measured)
            if observed_through is not None:
                entry["observed_through"] = observed_through.get(entry["attribute"])
    return {
        "version": 1,
        "note": "One preferred product per concept, chosen once and in the open. A fallback is "
                "named where a second source could answer, and naming it as a fallback says it "
                "is not the preferred answer.",
        "variables": entries,
        "concepts": dict(sorted(CONCEPTS.items())),
        "unavailable": dict(sorted(UNAVAILABLE.items())),
    }
