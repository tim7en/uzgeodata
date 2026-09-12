"""The stage 5 acceptance gate, as tests.

Round-trip a frozen snapshot, append a correction without losing the value it
replaces, preserve nulls, keep monthly observations apart from monthly
climatologies, and refuse a changed unit, geometry or period inside an
unversioned series.
"""
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ATLAS_MODULES.core import observations
from ATLAS_MODULES.core.observations import ContractError
from PIPELINES.stage_pilot_observations import STORE, build_rows, latest_run

CLIMATOLOGY = dict(
    basin_id="4120380180", geometry_version="geom-1", basin_level=12,
    attribute_id="hydrosheds.basinatlas.v1.pre_mm_s07", recipe_version="terraclimate@abc",
    mode="annual_extension", spatial_support="s", time_kind="climatology", month=7,
    temporal_statistic="monthly_climatological_mean",
    valid_start="1991-01-01", valid_end="2021-01-01",
    value=12.5, unit="millimetres per month", source_release_id="terraclimate@abc", run_id="run-1")


def make(**overrides):
    return observations.build(**{**CLIMATOLOGY, **overrides})


def require_local_store():
    if os.environ.get('UZGEODATA_SKIP_LOCAL_STORE') == '1':
        pytest.skip('local observation-store audit is running separately')
    if not observations.partition_files(STORE):
        pytest.skip('raw observation partitions are not distributed in a Git checkout')


@pytest.fixture(scope="module")
def staged():
    """The undated partitions only. The store also holds a dated series of millions
    of rows, and reading it whole to check the pilot would cost gigabytes."""
    require_local_store()
    rows = []
    for kind in ("static", "source_epoch", "climatology"):
        rows.extend(observations.read_partitions(STORE / f"time_kind={kind}"))
    assert rows, "the pilot observations are published"
    return rows


@pytest.fixture(scope="module")
def manifest():
    return json.loads((STORE / "manifest.json").read_text(encoding="utf-8"))


def _is_dated(entry):
    """A dated run publishes into the uzgeodata.dated namespace and reports per-year
    completeness. Runs that publish an epoch snapshot are a different shape and are
    checked elsewhere."""
    named = entry.get("attributes") or [entry.get("attribute_id")]
    return any((name or "").startswith("uzgeodata.dated.") for name in named)


@pytest.fixture(scope="module")
def ledgers():
    """Every regional run that has published a dated series into the store."""
    found = {}
    for path in sorted(STORE.glob("regional-*-ledger.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        if _is_dated(entry):
            found[path.name] = entry
    return found


@pytest.fixture(scope="module")
def landcover_ledger():
    path = STORE / "regional-landcover-ledger.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@pytest.fixture(scope="module")
def snow_ledger():
    return json.loads((STORE / "regional-snow-ledger.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def totals():
    require_local_store()
    return observations.summarise(STORE)


@pytest.fixture(scope="module")
def one_dated_year():
    require_local_store()
    return observations.read_partitions(STORE / "time_kind=observation" / "year=2003")


def test_the_staged_pilot_invents_no_observation_year(staged, manifest, totals):
    """The HydroATLAS run contributes no dated value, however many the store holds."""
    batch, _ = latest_run()
    pilot = [row for row in staged if row["run_id"] == batch["run_id"]]
    assert manifest["rows"] == totals["rows"]
    assert manifest["staged_from_this_run"] == len(pilot)
    assert all(row["year"] is None for row in pilot), "this run holds no dated observations"
    assert {row["time_kind"] for row in pilot} == {"static", "source_epoch", "climatology"}
    assert manifest["by_mode"]["reference_import"] == manifest["basins"] * 281


def test_a_monthly_climatology_is_not_a_dated_month():
    climatology = make()
    assert climatology["year"] is None and climatology["month"] == 7
    with pytest.raises(ContractError, match="carries no year"):
        make(year=2026)
    with pytest.raises(ContractError, match="requires its year"):
        make(time_kind="observation", year=None)

    # July 2026 and a July climatology are different observations, never the same row.
    dated = make(time_kind="observation", year=2026, valid_start="2026-07-01",
                 valid_end="2026-08-01", temporal_statistic="monthly_mean")
    assert dated["observation_id"] != climatology["observation_id"]
    assert observations.partition(dated) != observations.partition(climatology)


def test_a_class_code_is_never_stored_as_a_calendar_month(staged):
    with pytest.raises(ContractError, match="dimension code"):
        make(time_kind="source_epoch", month=1, valid_start=None, valid_end=None)
    with pytest.raises(ContractError, match="not a calendar month"):
        make(month=13)

    def months(column):
        return {row["month"] for row in staged
                if row["attribute_id"].endswith(column) and row["mode"] == "annual_extension"}
    assert months("glc_pc_s01") == {None}, "land-cover class 1 is not January"
    assert months("snw_pc_s01") == {1}, "a January snow climatology keeps its month"


def test_a_missing_value_keeps_its_reason_and_never_becomes_a_zero(staged):
    with pytest.raises(ContractError, match="requires a missing_reason"):
        make(value=None)
    with pytest.raises(ContractError, match="is not missing"):
        make(value=0.0, missing_reason="not measured")
    assert make(value=0.0)["value"] == 0.0, "a measured zero is a value"

    missing = [row for row in staged if row["value"] is None]
    assert missing, "the pilot carries published missing values"
    assert all(row["missing_reason"] for row in missing)
    assert all(row["value"] != 0 for row in missing)


def test_a_correction_supersedes_without_losing_the_earlier_value():
    first = make(value=12.5)
    corrected = make(value=13.25, revision=2, supersedes=observations.row_key(first), run_id="run-2")
    stored = observations.append([first], [corrected])

    assert len(stored) == 2, "the superseded value stays in the store"
    assert [row["value"] for row in stored] == [12.5, 13.25]
    current = observations.latest(stored)
    assert [row["value"] for row in current] == [13.25]
    assert current[0]["revision"] == 2

    with pytest.raises(ContractError, match="not in the store"):
        observations.append([], [corrected])
    with pytest.raises(ContractError, match="supersedes nothing"):
        make(revision=1, supersedes=observations.row_key(first))


def test_a_published_row_cannot_be_rewritten_in_place():
    first = make(value=12.5)
    with pytest.raises(ContractError, match="already published with different content"):
        observations.append([first], [make(value=99.0)])
    # Re-staging identical frozen evidence is a no-op, so a rebuild changes nothing.
    assert observations.append([first], [make()]) == [first]


def test_an_unversioned_series_cannot_change_its_unit_or_period():
    metres = make(unit="metres", value=1.0)
    with pytest.raises(ContractError, match="unit changes"):
        observations.append([metres], [make(unit="feet", value=3.28, basin_id="4120380350")])

    # The same change is acceptable once the recipe that made it is versioned.
    versioned = make(unit="feet", value=3.28, recipe_version="terraclimate@def",
                     basin_id="4120380350")
    assert len(observations.append([metres], [versioned])) == 2

    with pytest.raises(ContractError, match="valid_start changes"):
        observations.append([metres], [make(unit="metres", value=2.0, valid_start="1961-01-01",
                                            basin_id="4120380350")])


def test_a_dated_series_may_hold_many_periods():
    dated = [make(time_kind="observation", year=2026, month=month,
                  valid_start=f"2026-{month:02d}-01", valid_end=f"2026-{month + 1:02d}-01",
                  temporal_statistic="monthly_mean", value=float(month)) for month in (7, 8)]
    stored = observations.append([], dated)
    assert len(stored) == 2
    assert not observations.series_conflicts(stored), "months are observations, not a drifting series"
    with pytest.raises(ContractError, match="must lie after"):
        make(time_kind="observation", year=2026, valid_start="2026-08-01", valid_end="2026-08-01")


def test_the_store_round_trips_through_its_partitions(tmp_path):
    rows = observations.append([], [
        make(),
        make(value=None, missing_reason="source masked", basin_id="4120380350"),
        make(value=0.0, basin_id="4120382970"),
        # A dated extraction is a different method from a climatology, so it carries
        # its own recipe version rather than drifting inside the climatological one.
        make(time_kind="observation", year=2026, valid_start="2026-07-01",
             valid_end="2026-08-01", temporal_statistic="monthly_mean",
             recipe_version="terraclimate-dated@abc", basin_id="4120383080"),
    ])
    observations.write_partitions(tmp_path, rows)
    restored = observations.read_partitions(tmp_path)

    assert sorted(restored, key=observations.sort_key) == sorted(rows, key=observations.sort_key)
    values = {row["basin_id"]: row["value"] for row in restored}
    assert values["4120380350"] is None and values["4120382970"] == 0.0, "a null survives as a null"


def test_a_partition_is_replaced_atomically_not_rewritten_in_place(tmp_path):
    """A regional run writes for hours while the portal serves the same files. A
    reader must see the old partition or the new one, never half of either."""
    first = observations.append([], [make(value=1.0)])
    observations.write_partitions(tmp_path, first)
    partition = tmp_path / "time_kind=climatology" / "part.parquet"
    original = partition.read_bytes()

    second = observations.append(first, [make(value=2.0, basin_id="4120380350")])
    observations.write_partitions(tmp_path, second)
    assert partition.read_bytes() != original, "the partition was replaced"
    assert not list(tmp_path.rglob("*.tmp")), "no temporary is left behind"

    # A temporary that does survive a crash is not mistaken for data.
    stray = partition.with_name(partition.name + ".tmp")
    stray.write_text("observation_id,revision\nbroken,1\n", encoding="utf-8")
    assert len(observations.read_partitions(tmp_path)) == len(second)


def dated(year, month, basin, value=50.0):
    return make(time_kind="observation", year=year, month=month, basin_id=basin,
                valid_start=f"{year}-{month:02d}-01",
                valid_end=f"{year}-{month + 1:02d}-01" if month < 12 else f"{year + 1}-01-01",
                temporal_statistic="monthly_mean", recipe_version="dated@abc", value=value)


def test_a_scoped_append_touches_only_the_partitions_it_writes(tmp_path):
    """A store holding a dated series is too large to read whole on every publish."""
    observations.append_partitioned(tmp_path, [make(value=1.0), dated(2003, 1, "4120380180")])
    climatology = tmp_path / "time_kind=climatology" / "part.parquet"
    first_year = tmp_path / "time_kind=observation" / "year=2003" / "part.parquet"
    assert climatology.is_file() and first_year.is_file()
    untouched = first_year.read_bytes()

    added, touched = observations.append_partitioned(tmp_path, [dated(2004, 1, "4120380180")])
    assert added == 1
    assert touched == [observations.partition(dated(2004, 1, "4120380180"))]
    assert first_year.read_bytes() == untouched, "2003 was neither read nor rewritten"
    assert len(observations.read_partitions(tmp_path)) == 3


def test_a_scoped_append_still_refuses_to_rewrite_a_published_row(tmp_path):
    observations.append_partitioned(tmp_path, [dated(2003, 1, "4120380180", value=50.0)])
    with pytest.raises(ContractError, match="already published with different content"):
        observations.append_partitioned(tmp_path, [dated(2003, 1, "4120380180", value=99.0)])
    # Re-staging the identical row remains a no-op.
    added, _ = observations.append_partitioned(tmp_path, [dated(2003, 1, "4120380180", value=50.0)])
    assert added == 0


def test_a_rerun_is_stamped_as_a_revision_rather_than_refused(tmp_path):
    """Completing a partial run changes the upstream totals it had already published."""
    observations.append_partitioned(tmp_path, [make(value=1.0), make(value=2.0, spatial_support="u")])

    # The local value is unchanged by the basins the second run adds; the upstream
    # one is not, because it now accumulates over the basins that were missing.
    rerun = [make(value=1.0, run_id="run-2"), make(value=2.75, spatial_support="u", run_id="run-2")]
    stamped = observations.as_revisions(tmp_path, rerun)
    assert [row["revision"] for row in stamped] == [1, 2]
    assert stamped[1]["supersedes"] == observations.row_key(make(value=2.0, spatial_support="u"))

    added, _ = observations.append_partitioned(tmp_path, stamped)
    assert added == 1, "the confirmed value is a no-op; only the corrected one is added"
    current = observations.latest(observations.read_partitions(tmp_path))
    assert sorted(row["value"] for row in current) == [1.0, 2.75]
    assert len(observations.read_partitions(tmp_path)) == 3, "the superseded value stays"


def test_stamping_a_revision_leaves_an_unseen_observation_at_its_first(tmp_path):
    observations.append_partitioned(tmp_path, [make(value=1.0)])
    fresh = make(value=9.0, basin_id="4120380350", run_id="run-2")
    stamped = observations.as_revisions(tmp_path, [fresh])
    assert stamped[0]["revision"] == 1 and stamped[0]["supersedes"] is None
    assert observations.append_partitioned(tmp_path, stamped)[0] == 1


def test_a_third_run_supersedes_the_revision_standing_not_the_first(tmp_path):
    observations.append_partitioned(tmp_path, [make(value=1.0)])
    second = observations.as_revisions(tmp_path, [make(value=2.0, run_id="run-2")])
    observations.append_partitioned(tmp_path, second)
    third = observations.as_revisions(tmp_path, [make(value=3.0, run_id="run-3")])

    assert third[0]["revision"] == 3
    assert third[0]["supersedes"] == observations.row_key(second[0])
    observations.append_partitioned(tmp_path, third)
    assert [row["value"] for row in observations.latest(observations.read_partitions(tmp_path))] == [3.0]


def test_the_whole_store_is_verified_without_being_held_in_memory(tmp_path):
    observations.append_partitioned(tmp_path, [dated(2003, 1, "4120380180"),
                                               dated(2004, 1, "4120380180")])
    assert observations.verify_partitions(tmp_path) == []

    # A unit that drifts between two partitions is invisible to either write alone.
    drifted = dict(dated(2005, 1, "4120380180"))
    drifted["unit"] = "millimetres"
    drifted["observation_id"] = observations.observation_id(drifted)
    observations.write_partitions(tmp_path, [drifted])
    problems = observations.verify_partitions(tmp_path)
    assert problems and "unit changes" in problems[0], "the cross-partition check catches it"


def test_counts_are_summarised_a_partition_at_a_time(tmp_path):
    observations.append_partitioned(tmp_path, [
        make(value=1.0),
        make(value=None, missing_reason="source masked", basin_id="4120380350"),
        dated(2003, 1, "4120380180"), dated(2003, 2, "4120380180"), dated(2004, 1, "4120380180"),
    ])
    totals = observations.summarise(tmp_path)
    assert totals["rows"] == 5 and totals["current_rows"] == 5
    assert totals["by_time_kind"] == {"climatology": 2, "observation": 3}
    assert totals["dated_observations"] == 3
    assert totals["missing_values"] == 1
    assert totals["by_mode"] == {"annual_extension": 5}
    assert len(totals["attributes"]) == 1
    assert totals == observations.summarise(tmp_path), "summarising changes nothing"
    assert totals == observations.summarise(tmp_path, cache=False), "the cache agrees with a full read"


def test_an_unchanged_partition_is_not_read_again(tmp_path, monkeypatch):
    """Publishing touches a few partitions; counting the rest again costs more than
    writing them did."""
    observations.append_partitioned(tmp_path, [make(value=1.0), dated(2003, 1, "4120380180")])
    observations.summarise(tmp_path)
    assert (tmp_path / observations.SUMMARY_CACHE).is_file()

    read = []
    original = observations._read_file
    monkeypatch.setattr(observations, "_read_file", lambda path: read.append(path) or original(path))

    observations.summarise(tmp_path)
    assert read == [], "nothing changed, nothing re-read"

    observations.append_partitioned(tmp_path, [dated(2004, 1, "4120380180")])
    read.clear()
    totals = observations.summarise(tmp_path)
    assert len(read) == 1 and "year=2004" in str(read[0]), "only the changed partition is read"
    assert totals["rows"] == 3


def test_a_changed_partition_invalidates_its_own_cache_entry(tmp_path):
    observations.append_partitioned(tmp_path, [dated(2003, 1, "4120380180", value=50.0)])
    assert observations.summarise(tmp_path)["rows"] == 1

    # Rewrite the partition behind the cache's back, as a crash or a manual edit would.
    partition = tmp_path / "time_kind=observation" / "year=2003" / "part.parquet"
    observations.write_partitions(tmp_path, [dated(2003, 1, "4120380180", value=50.0),
                                             dated(2003, 2, "4120380180", value=60.0)])
    assert partition.stat().st_size > 0
    assert observations.summarise(tmp_path)["rows"] == 2, "size and mtime caught the change"


def test_a_corrupt_cache_is_ignored_rather_than_trusted(tmp_path):
    observations.append_partitioned(tmp_path, [dated(2003, 1, "4120380180")])
    (tmp_path / observations.SUMMARY_CACHE).write_text("{not json", encoding="utf-8")
    assert observations.summarise(tmp_path)["rows"] == 1


def test_a_superseded_row_is_stored_but_not_counted_as_current(tmp_path):
    first = dated(2003, 1, "4120380180", value=50.0)
    observations.append_partitioned(tmp_path, [first])
    corrected = observations.build(**{**{k: v for k, v in first.items()
                                         if k not in ("observation_id", "revision", "supersedes")},
                                      "value": 55.0, "revision": 2,
                                      "supersedes": observations.row_key(first)})
    observations.append_partitioned(tmp_path, [corrected])
    totals = observations.summarise(tmp_path)
    assert totals["rows"] == 2, "the superseded value is kept"
    assert totals["current_rows"] == 1, "but only the correction is current"


def test_the_published_store_round_trips_and_matches_its_run(staged):
    batch, lock = latest_run()
    rebuilt, _ = build_rows(batch, lock)
    pilot = [row for row in staged if row["run_id"] == batch["run_id"]]
    assert len(rebuilt) == len(pilot)
    assert {observations.row_key(row) for row in rebuilt} == {observations.row_key(row) for row in pilot}
    assert not observations.series_conflicts(staged), "sources coexist without drifting"


def test_the_whole_store_holds_no_series_conflict():
    """Checked across every partition, which the scoped writes cannot see alone."""
    require_local_store()
    assert observations.verify_partitions(STORE) == []


def test_the_dated_series_covers_the_region_for_twenty_years(manifest, totals, ledgers, one_dated_year):
    """Every dated attribute is accounted for by a run that produced it.

    Written against the ledgers present rather than against one source, so adding a
    dated family extends the store without rewriting what this asserts.
    """
    assert ledgers, "a dated series is published"
    for name, entry in ledgers.items():
        assert entry["complete"] and not entry["failures"], name
        assert entry["stored_rows"] == entry["expected_rows"], name
        assert entry["basins"] == 7445 and entry["years"] == [2003, 2022], name

    claimed = {a for entry in ledgers.values() for a in entry.get("attributes", [entry.get("attribute_id")])}
    assert set(manifest["dated_attributes"]) == claimed, "no dated attribute without a run behind it"
    assert totals["dated_observations"] == manifest["dated_observations"]
    pilot_dated = 20 * 20 * 12  # the pilot snow series, under its own geometry
    assert totals["dated_observations"] == sum(e["stored_rows"] for e in ledgers.values()) + pilot_dated

    regional_version = next(iter(ledgers.values()))["geometry_version"]
    regional = [r for r in one_dated_year if r["geometry_version"] == regional_version]
    pilot = [r for r in one_dated_year if r["geometry_version"] != regional_version]
    assert len({r["basin_id"] for r in regional}) == 7445
    assert len({r["basin_id"] for r in pilot}) == 20, "the pilot series is not overwritten"
    assert {r["month"] for r in regional} == set(range(1, 13))

    # A dated month carries the month it covers, and every value its QA denominator.
    for row in one_dated_year:
        assert row["valid_start"][:7] == f"{row['year']:04d}-{row['month']:02d}"
        assert row["temporal_statistic"] == "monthly_mean"
        assert row["expected_count"] and row["valid_count"] <= row["expected_count"]
        assert row["value"] is not None or row["missing_reason"], "a null says why"


def test_each_dated_attribute_keeps_one_unit_across_the_region(one_dated_year):
    """Several variables now share a partition; none may borrow another's unit."""
    units = {}
    for row in one_dated_year:
        units.setdefault(row["attribute_id"], set()).add(row["unit"])
    for attribute, found in units.items():
        assert len(found) == 1, f"{attribute} is stored in {found}"
    assert len(units) >= 1


def test_the_climatology_it_was_derived_alongside_still_stands(staged):
    climatology = {row["attribute_id"] for row in staged if row["time_kind"] == "climatology"}
    assert "uzgeodata.dated.v1.snw_pc_s" not in climatology
    assert any(a.endswith("snw_pc_s01") for a in climatology), "the January climatology still stands"


def test_a_dated_month_is_partitioned_by_its_year(ledgers, one_dated_year):
    for year in range(2003, 2023):
        # Either format: the store is read through the contract, not through a suffix.
        assert observations.partition_files(STORE / "time_kind=observation" / f"year={year}")
    assert {row["year"] for row in one_dated_year} == {2003}
    regional = sum(entry["stored_rows"] // len(range(2003, 2023)) for entry in ledgers.values())
    assert len(one_dated_year) == regional + 20 * 12, "one year of every source, plus the pilot"


def test_the_ledger_reports_the_availability_a_trend_would_confound(snow_ledger):
    """Null months are not stable across the record. A snow trend computed without
    them can be a trend in what the sensor delivered."""
    ledger = snow_ledger
    availability = ledger["availability"]["by_year"]
    assert set(availability) == {str(year) for year in range(2003, 2023)}
    assert availability["2022"]["null_months"] > availability["2003"]["null_months"] * 2
    assert "not stable across the record" in ledger["availability"]["meaning"]

    images = {year: sum(counts) for year, counts in ledger["source_images"].items()}
    assert min(images.values()) > 340, "daily coverage is constant, so it is not the cause"

    support = ledger["basin_support"]
    assert support["basins"] == 7445 and support["basins_without_a_cell"] == 0
    assert support["basins_at_or_below"]["100"] > 0, "the thin tail is published, not hidden"


def test_qa_denominators_must_agree_with_their_coverage():
    assert make(valid_count=900, expected_count=947, coverage_fraction=900 / 947)
    with pytest.raises(ContractError, match="exceeds expected_count"):
        make(valid_count=1000, expected_count=947, coverage_fraction=1.0)
    with pytest.raises(ContractError, match="disagrees with its own QA denominators"):
        make(valid_count=100, expected_count=947, coverage_fraction=1.0)
    with pytest.raises(ContractError, match="outside 0..1"):
        make(coverage_fraction=1.4)


def test_provenance_is_required_on_every_row(staged):
    for field in ("attribute_id", "geometry_version", "recipe_version", "source_release_id", "run_id"):
        with pytest.raises(ContractError, match=f"{field} is required"):
            make(**{field: None})
    releases = {row["source_release_id"] for row in staged}
    published = {line.split(",")[0] for line in
                 (STORE / "source_release.csv").read_text(encoding="utf-8").splitlines()[1:]}
    assert releases <= published, "every observation points at a published source release"


def test_the_land_cover_block_covers_the_region_on_both_supports(landcover_ledger):
    """Fifty-one attributes from one adapter, for the basin and for everything above it."""
    if landcover_ledger is None:
        pytest.skip("the land-cover run has not been published")
    assert landcover_ledger["complete"] and not landcover_ledger["failures"]
    assert landcover_ledger["basins_extracted"] == 7445
    assert len(landcover_ledger["attributes"]) == 51
    assert landcover_ledger["rows"] == 51 * 7445
    assert landcover_ledger["without_value"] == 0

    published = set(landcover_ledger["attributes"])
    assert {f"glc_pc_s{t:02d}" for t in range(1, 23)} <= published, "every class, local support"
    assert {f"glc_pc_u{t:02d}" for t in range(1, 23)} <= published, "every class, upstream"
    assert {"for_pc_sse", "for_pc_use", "crp_pc_sse", "glc_cl_smj"} <= published
    assert "2015" == landcover_ledger["epoch"], "an epoch snapshot, not a current state"
    assert "not a 2026 state" in landcover_ledger["epoch_note"]


def test_land_cover_class_shares_account_for_the_whole_basin():
    """Percentages that do not sum to a whole basin mean the crosswalk lost a class."""
    require_local_store()
    rows = [r for r in observations.read_partitions(STORE / "time_kind=source_epoch")
            if r["recipe_version"].startswith("copernicus_lc_regional")]
    if not rows:
        pytest.skip("the land-cover run has not been published")
    shares = {}
    for row in rows:
        column = row["attribute_id"].split(".")[-1]
        if column.startswith("glc_pc_s") and column[8:].isdigit():
            shares.setdefault(row["basin_id"], []).append(row["value"] or 0.0)
    assert len(shares) == 7445
    totals = [sum(v) for v in shares.values()]
    assert all(len(v) == 22 for v in shares.values()), "all twenty-two classes present"
    assert min(totals) > 95 and max(totals) < 105, f"class shares span {min(totals)}..{max(totals)}"
