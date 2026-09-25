"""Check the drought study against its own sources and the documented record."""
import json
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "PUBLISHED/data/atlas/drought-study"
HISTORY = ROOT / "PUBLISHED/data/atlas/climate-continuation/terraclimate-v1.1-history"
pytestmark = pytest.mark.skipif(not (OUT / "summary.json").exists(),
                                reason="drought study tables are R2-only; run build_drought_study.py")


def test_every_documented_year_is_found_in_the_data():
    summary = json.loads((OUT / "summary.json").read_text())
    for kind, years in (("dry", (2000, 2001, 2008, 2021)), ("wet", (1969, 1998))):
        for year in years:
            rows = [c for c in summary["documented"] if c["water_year"] == year]
            best = min(c["spi12"] for c in rows) if kind == "dry" else max(c["spi12"] for c in rows)
            assert (best <= -1.5) if kind == "dry" else (best >= 1.5), (year, best)


def test_water_year_total_matches_the_monthly_source():
    basin = "4120050220"
    record = json.loads((OUT / "basins" / f"{basin}.json").read_text())
    fields = {f: i for i, f in enumerate(record["fields"])}
    row = next(r for r in record["rows"] if r[fields["water_year"]] == 2021)
    total = duckdb.connect().execute("""
        SELECT sum(value) FROM read_parquet(?) WHERE basin_id=? AND variable='ppt'
          AND ((year=2020 AND month>=10) OR (year=2021 AND month<=9))
    """, [str(HISTORY / "year=*.parquet"), basin]).fetchone()[0]
    assert abs(row[fields["ppt"]] - total) < 1e-2
    assert [r[fields["water_year"]] for r in record["rows"]] == list(range(1961, 2026))


def test_trailing_norm_is_the_mean_of_the_previous_years():
    record = json.loads((OUT / "basins/4120050220.json").read_text())
    fields = {f: i for i, f in enumerate(record["fields"])}
    by_year = {r[fields["water_year"]]: r for r in record["rows"]}
    expected = sum(by_year[y][fields["ppt"]] for y in range(2011, 2021)) / 10
    assert abs(by_year[2021][fields["ppt_trailing_10"]] - expected) < 1e-2
    assert by_year[1970][fields["ppt_trailing_10"]] is None
    assert by_year[1971][fields["ppt_trailing_10"]] is not None


def test_spi_is_standardised_over_the_normal_period():
    con = duckdb.connect()
    mean, sd, n = con.execute("""
        SELECT avg(spi12), stddev_samp(spi12), count(*) FROM read_parquet(?)
        WHERE water_year BETWEEN 1991 AND 2020
    """, [str(OUT / "level07-wateryear.parquet")]).fetchone()
    assert n == 438 * 30
    assert abs(mean) < 0.1 and abs(sd - 1) < 0.1
