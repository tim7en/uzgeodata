"""A trend map is a pile of hypothesis tests, and the tests are where it goes wrong.

These check the statistics against independent implementations where one exists, and
check the two corrections that decide whether a map of "significant" anything means
what it says: the variance inflation from serial correlation, and false discovery
control across thousands of simultaneous tests. Both failures produce a plausible map.
"""
import math
import random

import pytest

from ATLAS_MODULES.core import trends


def test_the_s_statistic_is_maximal_for_a_monotonic_series():
    values = list(range(10))
    assert trends.kendall_s(values) == 10 * 9 // 2
    assert trends.kendall_s(values[::-1]) == -(10 * 9 // 2)
    assert trends.kendall_s([5] * 10) == 0


def test_tau_matches_scipy():
    """scipy's kendalltau is an independent implementation of the same coefficient."""
    stats = pytest.importorskip("scipy.stats")
    random.seed(11)
    for _ in range(6):
        values = [random.gauss(0, 1) + 0.15 * index for index in range(24)]
        mine = trends.mann_kendall(values, correct_autocorrelation=False)
        theirs = stats.kendalltau(list(range(len(values))), values)
        assert mine["tau"] == pytest.approx(theirs.statistic, abs=1e-9)


def test_p_matches_scipy_asymptotic_up_to_the_continuity_correction():
    """Compared against the same approximation, which is the only fair comparison.

    scipy's default `kendalltau` uses the exact distribution at this n; this uses the
    normal approximation with a continuity correction, as Mann-Kendall conventionally
    does. Those disagree in the far tail by construction and neither is wrong, so the
    comparison is made against scipy's asymptotic method. The residual difference is
    the continuity correction alone, which makes this test slightly the more
    conservative of the two -- verified below by removing it and matching exactly.
    """
    stats = pytest.importorskip("scipy.stats")
    random.seed(12)
    for signal in (0.0, 0.02, 0.05, 0.1, 0.3):
        values = [random.gauss(0, 1) + signal * index for index in range(30)]
        mine = trends.mann_kendall(values, correct_autocorrelation=False)
        theirs = stats.kendalltau(list(range(len(values))), values, method="asymptotic")
        assert (mine["p"] < 0.05) == (theirs.pvalue < 0.05),             f"verdicts disagree at signal {signal}"
        assert mine["p"] == pytest.approx(theirs.pvalue, rel=0.20),             f"p disagrees at signal {signal} by more than the continuity correction"
        assert mine["p"] >= theirs.pvalue * 0.999,             "the continuity correction should never make this test less conservative"


def test_removing_the_continuity_correction_reproduces_scipy_exactly():
    """Pins down that the only difference is the correction, not the implementation."""
    stats = pytest.importorskip("scipy.stats")
    random.seed(31)
    values = [random.gauss(0, 1) + 0.1 * index for index in range(30)]
    n = len(values)
    s = trends.kendall_s(values)
    variance = n * (n - 1) * (2 * n + 5) / 18
    z = s / math.sqrt(variance)                       # no continuity correction
    p = 2 * (1 - trends._normal_cdf(abs(z)))
    theirs = stats.kendalltau(list(range(n)), values, method="asymptotic")
    assert p == pytest.approx(theirs.pvalue, rel=1e-9)


def test_sens_slope_matches_scipy_theilslopes():
    stats = pytest.importorskip("scipy.stats")
    random.seed(13)
    values = [3 + 0.4 * index + random.gauss(0, 1) for index in range(25)]
    slope, intercept, _ = trends.sens_slope(values)
    theirs = stats.theilslopes(values, list(range(len(values))))
    assert slope == pytest.approx(theirs.slope, abs=1e-9)


def test_sens_slope_survives_an_outlier_that_moves_least_squares():
    """The reason a robust slope is used: one bad observation should not carry a trend."""
    clean = [1.0 * index for index in range(20)]
    spiked = list(clean)
    spiked[3] = 500.0                      # a cloud, a sensor fault, a typo
    honest, _, _ = trends.sens_slope(clean)
    robust, _, _ = trends.sens_slope(spiked)
    mean_x = statistics_mean(range(20))
    mean_y = statistics_mean(spiked)
    least_squares = (sum((x - mean_x) * (y - mean_y) for x, y in zip(range(20), spiked))
                     / sum((x - mean_x) ** 2 for x in range(20)))
    assert robust == pytest.approx(honest, abs=0.2), "the median pairwise slope holds"
    assert abs(least_squares - honest) > 1.0, "least squares does not"


def statistics_mean(values):
    values = list(values)
    return sum(values) / len(values)


def test_autocorrelation_inflates_the_variance_and_the_correction_catches_it():
    """The failure that makes a trend map wrong in one direction.

    A strongly persistent series with no trend at all produces runs that look like
    trends. Uncorrected, the test reports significance far more often than alpha; the
    Hamed-Rao correction is what stops a map of persistence being published as a map of
    change.
    """
    random.seed(7)
    false_positives_raw = false_positives_corrected = 0
    trials = 120
    for _ in range(trials):
        # AR(1) with strong persistence, zero trend by construction.
        series, value = [], 0.0
        for _ in range(30):
            value = 0.8 * value + random.gauss(0, 1)
            series.append(value)
        if trends.mann_kendall(series, correct_autocorrelation=False)["p"] < 0.05:
            false_positives_raw += 1
        if trends.mann_kendall(series, correct_autocorrelation=True)["p"] < 0.05:
            false_positives_corrected += 1

    assert false_positives_raw > trials * 0.12, \
        "an autocorrelated series should fool the uncorrected test well above alpha"
    assert false_positives_corrected < false_positives_raw, \
        "the correction must reduce it"


def test_the_correction_leaves_an_independent_series_alone():
    random.seed(8)
    values = [random.gauss(0, 1) for _ in range(30)]
    assert trends.hamed_rao_factor(values) == pytest.approx(1.0, abs=0.35), \
        "white noise should not be inflated much"


def test_a_real_trend_survives_the_correction():
    """The correction must not simply suppress everything."""
    random.seed(9)
    values = [0.5 * index + random.gauss(0, 1) for index in range(30)]
    result = trends.mann_kendall(values)
    assert result["trend"] == "significant increase"
    assert result["slope"] == pytest.approx(0.5, abs=0.15)


def test_false_discovery_control_removes_the_noise_a_naive_map_would_publish():
    """Testing thousands of units at 0.05 finds hundreds of trends in pure noise."""
    random.seed(10)
    units = 2000
    p_values = []
    for _ in range(units):
        series = [random.gauss(0, 1) for _ in range(22)]
        p_values.append(trends.mann_kendall(series, correct_autocorrelation=False)["p"])

    naive = sum(1 for p in p_values if p < 0.05)
    _, rejected = trends.benjamini_hochberg(p_values, alpha=0.05)
    controlled = sum(rejected)

    assert naive > units * 0.02, "the naive count picks up the expected false positives"
    assert controlled < naive / 4, "FDR control removes most of what was never there"


def test_false_discovery_control_keeps_real_signal():
    random.seed(14)
    p_values = []
    for index in range(400):
        trend = 0.4 if index < 80 else 0.0      # a fifth of the units really do move
        series = [trend * step + random.gauss(0, 1) for step in range(22)]
        p_values.append(trends.mann_kendall(series, correct_autocorrelation=False)["p"])
    _, rejected = trends.benjamini_hochberg(p_values, alpha=0.05)
    found = sum(rejected[:80])
    assert found > 55, "most of the genuine trends survive the correction"
    assert sum(rejected[80:]) < 25, "and few of the null units are admitted"


def test_a_short_series_is_withheld_rather_than_tested():
    result = trends.mann_kendall([1, 2, 3, 4])
    assert result["trend"] is None
    assert "fewer than" in result["withheld"]


def test_a_flat_series_is_stable_and_says_why():
    result = trends.mann_kendall([7.0] * 20)
    assert result["trend"] == "stable"
    assert result["p"] == 1.0


def test_the_result_records_whether_it_was_corrected():
    values = [0.3 * index for index in range(20)]
    assert trends.mann_kendall(values)["autocorrelation_corrected"] is True
    assert trends.mann_kendall(values, correct_autocorrelation=False)[
        "autocorrelation_corrected"] is False


def test_classification_takes_direction_from_the_robust_slope():
    assert trends.classify(0.01, 1.5) == "significant increase"
    assert trends.classify(0.01, -1.5) == "significant decrease"
    assert trends.classify(0.40, 1.5) == "increase"
    assert trends.classify(0.40, -1.5) == "decrease"
    assert trends.classify(0.01, 0.0) == "stable"


def test_false_discovery_control_matches_statsmodels():
    """An independent implementation of the same step-up procedure.

    Worth pinning because the procedure is easy to get subtly wrong -- Bonferroni
    reasoning says the smallest p must clear alpha/m, which is not what BH requires,
    and a wrong implementation here would silently change every published count.
    """
    multitest = pytest.importorskip("statsmodels.stats.multitest")
    random.seed(3)
    p_values = ([random.betavariate(0.3, 4) for _ in range(500)]
                + [random.random() for _ in range(1500)])
    mine_adjusted, mine_rejected = trends.benjamini_hochberg(p_values, alpha=0.05)
    theirs_rejected, theirs_adjusted, _, _ = multitest.multipletests(
        p_values, alpha=0.05, method="fdr_bh")

    assert sum(mine_rejected) == sum(theirs_rejected)
    assert list(mine_rejected) == list(theirs_rejected)
    for mine, theirs in zip(mine_adjusted, theirs_adjusted):
        assert mine == pytest.approx(theirs, abs=1e-12)
