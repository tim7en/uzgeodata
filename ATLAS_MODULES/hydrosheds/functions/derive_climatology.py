"""Derive HydroATLAS-shaped values from the dated observations already in the store.

The regional extraction produced real monthly observations. HydroATLAS attributes are
mostly climatologies — "January average", "annual total" — so the shapes it defines
can be computed from those observations by arithmetic, with no further extraction.

What comes out is a substitute, not a reproduction. A January normal computed over
2003-2022 from TerraClimate is an independent open-data estimate that happens to
carry the same name as the published attribute; it uses a different source and a
different period, and the contract keeps it under its own recipe version and its own
stated period so the two can never be mistaken for each other.

Each derived value carries how many periods actually contributed. Averaging twenty
Januaries and averaging the fourteen that were observed are different measurements,
and the second must say so rather than quietly presenting itself as the first.
"""
from __future__ import annotations

# Dated attribute in the store -> the variable name used in the recipes below.
INPUTS = {
    "uzgeodata.dated.v1.aet_mm_s": "aet",
    "uzgeodata.dated.v1.pet_mm_s": "pet",
    "uzgeodata.dated.v1.soil_mm_s": "soil",
    "uzgeodata.dated.v1.pre_mm_s": "pre",
    "uzgeodata.dated.v1.run_mm_s": "run",
    "uzgeodata.dated.v1.snw_pc_s": "snw",
}

# Which HydroATLAS column family each variable feeds, and how the annual figure is
# formed. These follow the reviewed climatology builders in `surrogates`.
MONTHLY = {
    "aet": ("aet_mm_s{:02d}", "aet_mm_syr", "total"),
    "pet": ("pet_mm_s{:02d}", "pet_mm_syr", "total"),
    "soil": ("swc_pc_s{:02d}", "swc_pc_syr", "mean"),
    "pre": ("pre_mm_s{:02d}", "pre_mm_syr", "total"),
    "snw": ("snw_pc_s{:02d}", "snw_pc_syr", "mean"),
}
MONTHS = range(1, 13)


def accumulate(rows, totals=None):
    """Sum each basin's dated values by variable and calendar month, one pass.

    Nulls are counted as periods that did not contribute, never as zeroes, which is
    what lets the derived value state its own denominator.
    """
    totals = {} if totals is None else totals
    for row in rows:
        variable = INPUTS.get(row["attribute_id"])
        if variable is None or row["month"] is None:
            continue
        key = (row["basin_id"], variable, row["month"])
        entry = totals.setdefault(key, {"sum": 0.0, "valid": 0, "expected": 0})
        entry["expected"] += 1
        if row["value"] is not None:
            entry["sum"] += row["value"]
            entry["valid"] += 1
    return totals


def normals(totals):
    """Mean of each calendar month across the years that carried a value."""
    out = {}
    for (basin, variable, month), entry in totals.items():
        value = entry["sum"] / entry["valid"] if entry["valid"] else None
        out.setdefault((basin, variable), {})[month] = {
            "value": value, "valid": entry["valid"], "expected": entry["expected"]}
    return out


def moisture_index(precipitation, potential):
    """Willmott and Feddema climate moisture index, bounded to -1..1.

    The same definition the pilot's climatology builder uses, applied to one basin
    rather than to a raster.
    """
    if precipitation is None or potential is None:
        return None
    if precipitation >= potential:
        return 1.0 - potential / precipitation if precipitation > 0 else None
    return precipitation / potential - 1.0 if potential > 0 else None


def _series(monthly):
    """The twelve monthly means, or None where a month never resolved."""
    return [monthly.get(month, {}).get("value") for month in MONTHS]


def _support(monthly):
    """The weakest and total support behind a set of months."""
    entries = [monthly.get(month, {}) for month in MONTHS]
    valid = [e.get("valid", 0) for e in entries]
    return min(valid) if valid else 0, max((e.get("expected", 0) for e in entries), default=0)


def derive(basin_normals):
    """Every HydroATLAS-shaped column derivable for one basin.

    Returns column -> (value, contributing periods, expected periods). A column whose
    inputs are incomplete yields None rather than a number computed from a gap.
    """
    results = {}
    for variable, (monthly_column, annual_column, kind) in MONTHLY.items():
        monthly = basin_normals.get(variable)
        if not monthly:
            continue
        low, expected = _support(monthly)
        for month in MONTHS:
            entry = monthly.get(month, {})
            results[monthly_column.format(month)] = (
                entry.get("value"), entry.get("valid", 0), entry.get("expected", 0))
        series = _series(monthly)
        if all(value is not None for value in series):
            total = sum(series)
            results[annual_column] = (total if kind == "total" else total / 12.0, low, expected)
        else:
            results[annual_column] = (None, low, expected)

    snow = basin_normals.get("snw")
    if snow:
        series = _series(snow)
        low, expected = _support(snow)
        results["snw_pc_smx"] = (max(series) if all(v is not None for v in series) else None,
                                 low, expected)

    runoff = basin_normals.get("run")
    if runoff:
        series = _series(runoff)
        low, expected = _support(runoff)
        results["run_mm_syr"] = (sum(series) if all(v is not None for v in series) else None,
                                 low, expected)

    # Moisture and aridity are ratios of precipitation to potential evapotranspiration,
    # so they exist only where both sides of the ratio do.
    rain, potential = basin_normals.get("pre"), basin_normals.get("pet")
    if rain and potential:
        low = min(_support(rain)[0], _support(potential)[0])
        expected = max(_support(rain)[1], _support(potential)[1])
        for month in MONTHS:
            results[f"cmi_ix_s{month:02d}"] = (
                moisture_index(rain.get(month, {}).get("value"),
                               potential.get(month, {}).get("value")), low, expected)
        wet, dry = _series(rain), _series(potential)
        if all(v is not None for v in wet + dry):
            annual_rain, annual_pet = sum(wet), sum(dry)
            results["cmi_ix_syr"] = (moisture_index(annual_rain, annual_pet), low, expected)
            results["ari_ix_sav"] = (annual_rain / annual_pet if annual_pet > 0 else None,
                                     low, expected)
        else:
            results["cmi_ix_syr"] = (None, low, expected)
            results["ari_ix_sav"] = (None, low, expected)
    return results
