import numpy as np
import pytest

from PIPELINES import seasonal_forecast_seas5 as seas5


def test_quantile_mapping_removes_a_multiplicative_bias():
    rng = np.random.default_rng(1)
    observed = rng.gamma(4, 10, size=24)
    # A model that rains twice as much as the observations, with the same shape.
    hindcast = rng.gamma(4, 20, size=(24, 25))
    mapped = seas5.quantile_map(hindcast[3], hindcast.ravel(), observed)
    assert abs(np.median(mapped) - np.median(observed)) < 0.25 * np.median(observed)
    assert mapped.min() >= observed.min() and mapped.max() <= observed.max()


def test_tercile_probabilities_and_percentiles():
    pool = np.arange(300.0)
    assert seas5.tercile_probabilities(np.full(51, -1.0), pool) == (1.0, 0.0, 0.0)
    below, near, above = seas5.tercile_probabilities(np.arange(0, 300, 6.0), pool)
    assert abs(below + near + above - 1) < 1e-9 and 0.25 < below < 0.4
    # Ties count half: every pool value equal to the member sits at the middle.
    assert seas5.midrank_percentile([5.0], np.full(9, 5.0))[0] == pytest.approx(0.5)


def test_skill_tells_a_skilful_forecast_from_a_random_one():
    rng = np.random.default_rng(7)
    observed = rng.normal(size=24)
    skilful = observed[:, None] + rng.normal(scale=0.5, size=(24, 25))
    random = rng.normal(size=(24, 25))
    good, bad = seas5.skill(skilful, observed), seas5.skill(random, observed)
    assert good["correlation"] > 0.7 and good["rpss"] > 0.1 and good["roc_below"] > 0.8 and good["useful"]
    assert bad["useful"] is False and bad["rpss"] < good["rpss"]


def test_forecast_statement_is_in_observed_terms_and_flags_a_dry_season():
    rng = np.random.default_rng(3)
    observed = rng.gamma(5, 20, size=24)
    hindcast = rng.gamma(5, 40, size=(24, 25))
    dry = np.quantile(hindcast, 0.05) * np.ones(51)
    statement = seas5.forecast_statement(dry, hindcast, observed, extensive=True)
    assert statement["probabilities"]["below"] == 1.0
    assert statement["dry_probability"] == 1.0
    assert statement["median"] < statement["normal"] and statement["anomaly_percent"] < 0


def test_windows_start_after_the_start_month_and_wrap_the_year():
    windows = {w["id"]: w for w in seas5.windows(9)}
    assert windows["next3"]["label"] == "Oct–Dec"
    assert windows["season5"]["label"] == "Oct–Feb"
    assert seas5.target_month(2026, 9, 5) == (2027, 1)
    assert seas5.target_month(2026, 12, 1) == (2026, 12)


def test_one_degree_cells_reduce_to_basins_by_overlap(tmp_path, monkeypatch):
    import geopandas as gpd
    from shapely.geometry import box
    from PIPELINES import extract_regional_climate_grids as grids
    monkeypatch.setattr(grids, "CACHE", tmp_path)
    frame = gpd.GeoDataFrame({"basin_id": ["a", "b"]},
                             geometry=[box(60.0, 40.0, 61.0, 41.0), box(60.5, 40.0, 61.5, 41.0)])
    lat, lon = np.array([41.0, 40.0]), np.array([60.0, 61.0, 62.0])
    # Cells centred on whole degrees: basin a straddles the 60 and 61 cells; b lies wholly
    # in the 61 cell. Each spans the two latitude rows equally.
    field = np.array([[0.0, 0.0, 0.0], [10.0, 20.0, 40.0]])[None]
    field = np.repeat(field, 2, axis=0)
    values = seas5.grid_to_basins(field, lat, lon, frame)
    assert values.shape == (2, 2)
    assert values[0, 0] == pytest.approx(7.5, abs=0.2)
    assert values[0, 1] == pytest.approx(10.0, abs=0.2)
