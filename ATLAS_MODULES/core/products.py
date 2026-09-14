"""Layer 3: what the observations mean, rather than what they were.

An observation says 39 millimetres fell in this basin in March 2011. On its own that
answers nothing -- it is wet or dry only against what March usually brings here, and
"usually" has to be stated rather than assumed. These are the products that turn a
series into a statement: a normal, a departure from it, a trend, and a balance
between what arrived and what left.

Three rules run through all of them, and each one is a way a derived product can be
confidently wrong:

A gap is not a zero. Every function counts what it actually had and reports it, and
refuses to produce a figure resting on too little. A March anomaly computed from four
observed Marches is not comparable with one computed from twenty, and the difference
is invisible in the number itself.

A flux and a state do not aggregate alike. Precipitation over a season is a sum;
temperature over a season is a mean. The registry records which each variable is, so
nothing here has to guess, and asking for the sum of a state is refused rather than
answered.

A trend is a claim about the record, not about the world. Where the record thins
towards the present -- as the snow series does -- a trend through it measures the
sensor as much as the basin, so the caution travels with the result instead of being
left in a ledger nobody reads.
"""
from __future__ import annotations
import statistics

from . import query, variables

# A normal built on fewer than this many years is reported with the count rather than
# withheld, but nothing derived from it is offered as a departure: an anomaly against
# a baseline of three years says more about the baseline than about the month.
MINIMUM_BASELINE = 10


def _rows(store, variable, basins, start, end, connection):
    attribute = variables.attribute(variable)
    return attribute, query.observations(store, basins=basins, variables=[attribute],
                                         start=start, end=end, support="s",
                                         connection=connection)


def normals(store, variable, basins=None, start=None, end=None, connection=None):
    """The average each calendar month brings, and how many years stand behind it.

    This is the baseline everything else is measured against, so it carries its own
    support: twelve values, each with the count of years that actually contributed.
    """
    attribute, rows = _rows(store, variable, basins, start, end, connection)
    gathered = {}
    for basin, _, month_start, value, *_ in rows:
        if value is None:
            continue
        gathered.setdefault((basin, month_start.month), []).append(value)
    return {key: {"mean": statistics.fmean(values), "years": len(values)}
            for key, values in gathered.items()}


def anomalies(store, variable, basins=None, start=None, end=None,
              baseline=(None, None), connection=None):
    """Each month against what that month usually brings in that basin.

    The baseline is drawn from the whole record by default, never from the window
    being examined. That distinction is the difference between a measurement and a
    tautology: judging 2011 against a baseline built only from 2011 says that 2011 was
    normal, however extreme it was. Pass `baseline` to state a fixed reference period
    instead, which is what makes two analyses comparable.

    Returned as the departure and, where the spread allows it, as a standardised
    score. A standardised score over a baseline with almost no spread is enormous and
    meaningless, so it is withheld rather than reported: a desert month that is
    normally zero and once had a millimetre is not a ten-sigma event.
    """
    attribute, rows = _rows(store, variable, basins, start, end, connection)
    reference = rows if (start, end) == baseline else _rows(
        store, variable, basins, baseline[0], baseline[1], connection)[1]
    baseline_years = {}
    for basin, _, month_start, value, *_ in reference:
        if value is not None:
            baseline_years.setdefault((basin, month_start.month), []).append(value)

    out = []
    for basin, _, month_start, value, unit, *_ in rows:
        key = (basin, month_start.month)
        history = baseline_years.get(key, [])
        if value is None or len(history) < MINIMUM_BASELINE:
            out.append({"basin_id": basin, "month": month_start, "value": value,
                        "anomaly": None, "z": None, "baseline_years": len(history),
                        "withheld": "no value" if value is None else "baseline too short"})
            continue
        mean = statistics.fmean(history)
        spread = statistics.pstdev(history)
        out.append({
            "basin_id": basin, "month": month_start, "value": value, "unit": unit,
            "anomaly": value - mean, "baseline_years": len(history),
            "z": (value - mean) / spread if spread > 1e-9 else None,
            "withheld": None if spread > 1e-9 else "baseline has no spread",
        })
    return out


def seasonal(store, variable, basins=None, start=None, end=None, months=None,
             connection=None):
    """A season reduced the way the quantity allows: summed for a flux, averaged for a state.

    `months` is the season, defaulting to the whole year. A season missing any of its
    months yields no figure for a flux -- a summer total short of July is not a summer
    total -- while a state reports the mean of what was observed and says how much.
    """
    identifier = variables.resolve(variable)
    kind = variables.VARIABLES[identifier]["kind"]
    wanted = set(months or range(1, 13))
    attribute, rows = _rows(store, variable, basins, start, end, connection)

    gathered = {}
    for basin, _, month_start, value, *_ in rows:
        if month_start.month in wanted:
            gathered.setdefault((basin, month_start.year), []).append(value)

    out = []
    for (basin, year), values in sorted(gathered.items()):
        observed = [value for value in values if value is not None]
        whole = len(observed) == len(wanted)
        out.append({
            "basin_id": basin, "year": year, "kind": kind,
            "observed": len(observed), "expected": len(wanted),
            "total": sum(observed) if (kind == "flux" and whole) else None,
            "mean": statistics.fmean(observed) if observed else None,
            "withheld": None if whole else "the season is incomplete",
        })
    return out


def trend(store, variable, basins=None, start=None, end=None, months=None, connection=None):
    """Least-squares slope per year of the seasonal figure, with what qualifies it.

    The slope is arithmetic and always available; whether it means anything is not.
    Years missing from the record are counted, the registry's caution for the variable
    travels with the result, and a series that loses years towards the present is
    flagged, because a trend drawn through a thinning record is partly a trend in the
    record.
    """
    identifier = variables.resolve(variable)
    entry = variables.VARIABLES[identifier]
    seasons = seasonal(store, variable, basins, start, end, months, connection)

    gathered = {}
    for row in seasons:
        figure = row["total"] if row["kind"] == "flux" else row["mean"]
        if figure is not None and row["withheld"] is None:
            gathered.setdefault(row["basin_id"], []).append((row["year"], figure))

    out = []
    for basin, points in sorted(gathered.items()):
        years = [year for year, _ in points]
        if len(points) < 3:
            out.append({"basin_id": basin, "slope": None, "years": len(points),
                        "withheld": "too few complete years to fit a line"})
            continue
        mean_year = statistics.fmean(years)
        mean_value = statistics.fmean([value for _, value in points])
        spread = sum((year - mean_year) ** 2 for year in years)
        slope = sum((year - mean_year) * (value - mean_value) for year, value in points) / spread
        first, last = min(years), max(years)
        span = last - first + 1
        out.append({
            "basin_id": basin, "slope": slope, "per": "year", "unit": entry["unit"],
            "years": len(points), "span": [first, last],
            "gaps": span - len(points),
            "caution": entry.get("caution"),
            "thinning": len(points) < span,
        })
    return out


def water_balance(store, basins=None, start=None, end=None, connection=None):
    """Precipitation less actual evapotranspiration, month by month.

    The crudest useful balance and an honest one: both terms come from the same model
    on the same grid, which is why they may be differenced at all. It is not a
    catchment water balance -- nothing here routes water, accounts for storage or
    closes against a gauge -- so it is named for what it is, a climatic difference.
    """
    own = connection is None
    connection = connection or query.connect(store)
    try:
        rain = {(row[0], row[2]): row[3] for row in query.observations(
            store, basins=basins, variables=[variables.attribute("precipitation")],
            start=start, end=end, connection=connection)}
        lost = {(row[0], row[2]): row[3] for row in query.observations(
            store, basins=basins, variables=[variables.attribute("actual evapotranspiration")],
            start=start, end=end, connection=connection)}
        out = []
        for key in sorted(rain.keys() & lost.keys()):
            precipitation, evaporated = rain[key], lost[key]
            out.append({
                "basin_id": key[0], "month": key[1],
                "precipitation": precipitation, "evapotranspiration": evaporated,
                "balance": None if None in (precipitation, evaporated)
                           else precipitation - evaporated,
                "unit": "millimetres per month",
                "meaning": "climatic difference, not a routed catchment balance",
            })
        return out
    finally:
        if own:
            connection.close()


def accumulate(rows, window):
    """Running sums over `window` months, keyed by the month they end in.

    SPI is defined on accumulated precipitation, because a drought is a shortfall
    sustained over a period rather than a dry month. A window that reaches back before
    the record starts has nothing to accumulate and yields nothing, rather than a sum
    of the months that happen to exist.
    """
    series = {}
    for basin, _, month_start, value, *_ in rows:
        series.setdefault(basin, {})[(month_start.year, month_start.month)] = value

    out = {}
    for basin, months in series.items():
        ordered = sorted(months)
        for index in range(window - 1, len(ordered)):
            span = ordered[index - window + 1:index + 1]
            values = [months[key] for key in span]
            # Contiguity matters: a gap in the calendar is not a shorter window.
            first, last = span[0], span[-1]
            expected = (last[0] - first[0]) * 12 + (last[1] - first[1]) + 1
            if expected != window or any(value is None for value in values):
                continue
            out[(basin, last)] = sum(values)
    return out


def spi(store, basins=None, window=3, start=None, end=None, baseline=(None, None),
        connection=None):
    """Standardised Precipitation Index, fitted rather than approximated.

    A z-score of accumulated rainfall is the common shortcut and it is wrong in the
    place it matters: precipitation is bounded at zero and strongly skewed, so a
    normal assumption makes ordinary dry spells look extreme and extreme wet ones look
    ordinary. SPI is defined as the gamma fit transformed to a standard normal, and
    that is what this does -- a separate fit for each basin and each calendar month,
    because March and August are different distributions.

    Months of no rain are handled as the mixed distribution the definition requires:
    the probability of zero is carried alongside the gamma for the positive values,
    rather than a zero being fed to a fit that has no density there.

    Returned per month with the fit behind it. Where the baseline is too short to fit,
    the index is withheld: an SPI from six years is a number about six years.
    """
    import numpy
    from scipy import stats

    attribute = variables.attribute("precipitation")
    own = connection is None
    connection = connection or query.connect(store)
    try:
        window_rows = query.observations(store, basins=basins, variables=[attribute],
                                         start=start, end=end, connection=connection)
        reference = window_rows if (start, end) == baseline else query.observations(
            store, basins=basins, variables=[attribute],
            start=baseline[0], end=baseline[1], connection=connection)
    finally:
        if own:
            connection.close()

    totals = accumulate(window_rows, window)
    baseline_totals = accumulate(reference, window)

    samples = {}
    for (basin, (_, month)), total in baseline_totals.items():
        samples.setdefault((basin, month), []).append(total)

    out = []
    for (basin, (year, month)), total in sorted(totals.items()):
        history = samples.get((basin, month), [])
        positive = [value for value in history if value > 0]
        if len(history) < MINIMUM_BASELINE or len(positive) < 4:
            out.append({"basin_id": basin, "year": year, "month": month, "window": window,
                        "accumulation": total, "spi": None, "baseline_years": len(history),
                        "withheld": "too few years to fit a distribution"})
            continue

        # A sample with no spread has no distribution to fit. scipy does not say that:
        # it fails inside its solver with "f(a) and f(b) must have different signs",
        # which names nothing a reader could act on. A basin whose accumulations are
        # identical across the record -- a constant fill, or somewhere genuinely
        # unvarying -- is a basin SPI cannot describe, so it is withheld with the reason
        # rather than raising from three libraries down.
        if len(set(positive)) < 2:
            out.append({"basin_id": basin, "year": year, "month": month, "window": window,
                        "accumulation": total, "spi": None, "baseline_years": len(history),
                        "withheld": "the baseline has no spread, so no distribution fits"})
            continue

        # The mixed distribution: zeros are an atom, positives are gamma.
        zero_share = (len(history) - len(positive)) / len(history)
        shape, location, scale = stats.gamma.fit(positive, floc=0)
        if total <= 0:
            probability = zero_share / 2 if zero_share else 1e-6
        else:
            probability = zero_share + (1 - zero_share) * stats.gamma.cdf(
                total, shape, loc=location, scale=scale)
        probability = min(max(probability, 1e-6), 1 - 1e-6)
        out.append({
            "basin_id": basin, "year": year, "month": month, "window": window,
            "accumulation": total, "spi": float(stats.norm.ppf(probability)),
            "baseline_years": len(history), "dry_months_in_baseline": len(history) - len(positive),
            "withheld": None,
            "meaning": "Negative is drier than usual for this basin and calendar month; "
                       "below -1.5 is conventionally a marked shortfall. It describes "
                       "precipitation alone and is not a statement about water availability.",
        })
    return out
