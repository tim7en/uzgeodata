"""Mann-Kendall and Sen's slope, with the two corrections that decide whether a trend map means anything.

The test itself is old and short. What separates a defensible trend map from a
decorative one is almost entirely what happens around it, and two things dominate.

**Serial correlation.** Mann-Kendall assumes independent observations. Climate and
vegetation series are not independent -- a wet year follows a wet year, NDVI in one
16-day window resembles the last -- and positive autocorrelation inflates the variance
of S, which deflates p. Applied naively to an autocorrelated series the test reports
significance that is not there, and it does so systematically rather than randomly, so
a map of "significant greening" can be substantially an artefact of persistence. The
Hamed and Rao (1998) variance correction is implemented here and applied by default.
Turning it off is possible and is recorded in the result, because a reader comparing
this with a paper that did not correct needs to know which they are looking at.

**Multiple testing.** Testing 7,445 basins at p < 0.05 yields about 372 significant
results when nothing whatever is happening. Any study that classifies thousands of
units into significant and non-significant categories and does not control for this is
reporting its own error rate as a finding. Benjamini-Hochberg false discovery rate
control is applied across each family of tests, and both the raw and adjusted verdicts
are returned so the difference is visible rather than asserted.

Sen's slope accompanies the test because Mann-Kendall says only whether a monotonic
trend exists, not how large it is, and a least-squares slope on a skewed or
outlier-prone series is not a robust answer to that question.

Validated against scipy: the tau this computes matches `scipy.stats.kendalltau` and the
slope matches `scipy.stats.theilslopes`, which is an independent implementation of the
same estimators rather than a restatement of this one.
"""
from __future__ import annotations
import math
import statistics

# Fewer than this many points and a monotonic test says almost nothing: the normal
# approximation to S is poor and a single outlier can carry the verdict.
MINIMUM_POINTS = 8

CLASSES = ("significant increase", "increase", "stable", "decrease", "significant decrease")


def _tied_groups(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [count for count in counts.values() if count > 1]


def kendall_s(values):
    """The S statistic: how many later values exceed earlier ones, less the reverse."""
    total = 0
    for i in range(len(values) - 1):
        for j in range(i + 1, len(values)):
            total += (values[j] > values[i]) - (values[j] < values[i])
    return total


def _variance(n, values):
    """Variance of S under the null, corrected for ties in the data."""
    base = n * (n - 1) * (2 * n + 5)
    for count in _tied_groups(values):
        base -= count * (count - 1) * (2 * count + 5)
    return base / 18.0


def autocorrelation(values, lag):
    """Lag-k autocorrelation of the series, about its own mean."""
    n = len(values)
    if lag >= n:
        return 0.0
    mean = statistics.fmean(values)
    denominator = sum((value - mean) ** 2 for value in values)
    if denominator == 0:
        return 0.0
    numerator = sum((values[i] - mean) * (values[i + lag] - mean) for i in range(n - lag))
    return numerator / denominator


def hamed_rao_factor(values, ranks=None):
    """Variance inflation from serial correlation, after Hamed and Rao (1998).

    Computed on the ranks of the detrended series, which is what the method specifies:
    the autocorrelation that matters to a rank-based test is the autocorrelation of the
    ranks, and leaving the trend in would measure the trend as if it were persistence.

    Returns 1.0 when nothing survives the significance screen, so an uncorrelated series
    is unchanged rather than nudged.
    """
    n = len(values)
    if n < MINIMUM_POINTS:
        return 1.0
    series = ranks if ranks is not None else _detrended_ranks(values)
    # Only autocorrelations that clear a rough significance bound contribute, which is
    # what stops the correction from being driven by noise at long lags.
    bound = 1.96 / math.sqrt(n)
    total = 0.0
    for lag in range(1, n - 1):
        rho = autocorrelation(series, lag)
        if abs(rho) <= bound:
            continue
        total += (n - lag) * (n - lag - 1) * (n - lag - 2) * rho
    if total == 0:
        return 1.0
    factor = 1 + (2 / (n * (n - 1) * (n - 2))) * total
    # A correction below one would claim independence buys significance; the method is
    # a correction for positive persistence and is floored accordingly.
    return max(factor, 1.0)


def _detrended_ranks(values):
    slope, intercept = sens_slope(values)[:2]
    residual = [value - (intercept + slope * index) for index, value in enumerate(values)]
    order = sorted(range(len(residual)), key=lambda i: residual[i])
    ranks = [0.0] * len(residual)
    for position, index in enumerate(order):
        ranks[index] = float(position + 1)
    return ranks


def sens_slope(values, times=None):
    """Median of all pairwise slopes, with the intercept that centres the fit.

    Robust to outliers in a way least squares is not, which matters for precipitation
    and for a vegetation index that occasionally records cloud rather than land.
    """
    times = list(range(len(values))) if times is None else list(times)
    slopes = [(values[j] - values[i]) / (times[j] - times[i])
              for i in range(len(values) - 1)
              for j in range(i + 1, len(values))
              if times[j] != times[i]]
    if not slopes:
        return 0.0, statistics.fmean(values) if values else 0.0, 0
    slope = statistics.median(slopes)
    intercept = statistics.median(values) - slope * statistics.median(times)
    return slope, intercept, len(slopes)


def mann_kendall(values, correct_autocorrelation=True, alpha=0.05):
    """Test for a monotonic trend, with the variance correction stated in the result.

    Returns the verdict and everything needed to check it: S, tau, z, p, the variance
    inflation applied, and the slope. Withheld rather than guessed where the series is
    too short to support the normal approximation.
    """
    values = [value for value in values if value is not None]
    n = len(values)
    if n < MINIMUM_POINTS:
        return {"n": n, "trend": None, "withheld": f"fewer than {MINIMUM_POINTS} points",
                "s": None, "tau": None, "p": None, "z": None, "slope": None,
                "variance_inflation": None, "autocorrelation_corrected": False}

    s = kendall_s(values)
    variance = _variance(n, values)
    inflation = hamed_rao_factor(values) if correct_autocorrelation else 1.0
    variance *= inflation

    if variance <= 0:
        return {"n": n, "trend": "stable", "withheld": "no variance in the series",
                "s": s, "tau": 0.0, "p": 1.0, "z": 0.0, "slope": 0.0,
                "variance_inflation": inflation,
                "autocorrelation_corrected": correct_autocorrelation}

    # Continuity correction: S is discrete and the normal approximation is applied to it.
    if s > 0:
        z = (s - 1) / math.sqrt(variance)
    elif s < 0:
        z = (s + 1) / math.sqrt(variance)
    else:
        z = 0.0
    p = 2 * (1 - _normal_cdf(abs(z)))

    denominator = math.sqrt(
        (n * (n - 1) / 2 - sum(c * (c - 1) / 2 for c in _tied_groups(values)))
        * (n * (n - 1) / 2))
    tau = s / denominator if denominator > 0 else 0.0
    slope, intercept, pairs = sens_slope(values)

    return {
        "n": n, "s": s, "tau": tau, "z": z, "p": p,
        "slope": slope, "intercept": intercept, "pairs": pairs,
        "variance_inflation": inflation,
        "autocorrelation_corrected": correct_autocorrelation,
        "trend": classify(p, slope, alpha),
        "withheld": None,
    }


def classify(p, slope, alpha=0.05):
    """The five-way verdict, with direction taken from the robust slope."""
    if slope == 0:
        return "stable"
    if p < alpha:
        return "significant increase" if slope > 0 else "significant decrease"
    return "increase" if slope > 0 else "decrease"


def benjamini_hochberg(p_values, alpha=0.05):
    """False discovery rate control across a family of tests.

    Returns the adjusted p-values in the original order and the rejection decisions.
    Testing thousands of units without this reports the error rate as a finding: at
    alpha 0.05 across 7,445 basins, about 372 come back significant when nothing is
    happening at all.
    """
    indexed = sorted((p, index) for index, p in enumerate(p_values) if p is not None)
    m = len(indexed)
    adjusted = [None] * len(p_values)
    if not m:
        return adjusted, [False] * len(p_values)

    previous = 1.0
    for rank in range(m, 0, -1):
        p, index = indexed[rank - 1]
        value = min(previous, p * m / rank)
        adjusted[index] = value
        previous = value
    return adjusted, [a is not None and a <= alpha for a in adjusted]


def _normal_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
