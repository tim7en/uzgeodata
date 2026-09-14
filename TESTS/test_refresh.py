"""Refreshing has to be safe to attempt and honest about what it would do.

Two failures matter here. The first is publishing after a fetch that did not finish,
which would put a basin API describing months the monthly record does not have. The
second is running the rebuild steps out of order, which would do the same thing more
quietly: climatologies are derived from the dated series, upstream figures from the
local ones, and everything published from both.
"""
import pytest

from PIPELINES import refresh_regional_record as refresh


def test_the_rebuild_runs_in_dependency_order():
    labels = [entry[0] for entry in refresh.PUBLISH]
    scripts = [entry[1][0] for entry in refresh.PUBLISH]
    order = {name: index for index, name in enumerate(scripts)}

    derive = order["PIPELINES/derive_regional_substitutes.py"]
    upstream = order["PIPELINES/accumulate_upstream_annuals.py"]
    history = order["PIPELINES/build_basin_history.py"]
    api = order["PIPELINES/build_basin_api.py"]
    coverage = order["PIPELINES/build_regional_coverage.py"]

    assert derive < upstream, "upstream figures accumulate the derived local ones"
    assert upstream < api, "the API publishes what upstream produced"
    assert history < api or api < history, "both read the store; either order is sound"
    assert derive < coverage and upstream < coverage, "coverage counts what was derived"
    assert len(labels) == len(set(labels)), "each step is named once"


def test_a_failed_fetch_publishes_nothing(monkeypatch):
    """The state a partial extraction leaves is exactly what the store records and
    refuses to present. Publishing over it would present it anyway."""
    attempted = []

    def fake_run(command, dry_run=False):
        attempted.append(command[0])
        return "extract_regional_monthly" not in command[0]

    monkeypatch.setattr(refresh, "run", fake_run)
    monkeypatch.setattr(refresh, "missing_years",
                        lambda **kwargs: {"terraclimate": {"stored_to": "2022-12",
                                                           "years_to_fetch": [2023]}})

    outcome = refresh.extend("2023-12")
    assert outcome["ok"] is False
    assert outcome["failed_at"].startswith("fetch")
    assert not any("build_basin_api" in name for name in attempted), "nothing was republished"


def test_a_failed_rebuild_stops_rather_than_continuing(monkeypatch):
    attempted = []

    def fake_run(command, dry_run=False):
        attempted.append(command[0])
        return "accumulate_upstream_annuals" not in command[0]

    monkeypatch.setattr(refresh, "run", fake_run)
    outcome = refresh.publish(span=(2003, 2024))
    assert outcome["ok"] is False
    assert "upstream" in outcome["failed_at"]
    assert not any("build_basin_api" in name for name in attempted), \
        "the API is not rebuilt over a failed accumulation"


def test_a_source_already_current_is_not_refetched(monkeypatch):
    monkeypatch.setattr(refresh, "missing_years",
                        lambda **kwargs: {"terraclimate": {"stored_to": "2024-12",
                                                           "years_to_fetch": []}})
    monkeypatch.setattr(refresh, "publish", lambda dry_run=False: {"ok": True})
    ran = []
    monkeypatch.setattr(refresh, "run", lambda command, dry_run=False: ran.append(command) or True)

    outcome = refresh.extend("2024-12")
    assert outcome["ok"] and outcome["fetched"] == []
    assert not ran, "an hour of Earth Engine is not spent re-fetching what is stored"


def test_checking_writes_nothing_and_needs_no_credentials(monkeypatch, tmp_path):
    """A check must be safe to run at any time, including while a fetch is running."""
    monkeypatch.setattr(refresh, "stored_extent", lambda store=None: {})
    monkeypatch.setattr(refresh, "missing_years", lambda **kwargs: {})
    report = refresh.check(probe=False)
    assert "source" not in report, "no probe means no network"
    assert report["registry"]["variables"] > 0
    assert report["registry"]["unavailable"], "the check reports what cannot be refreshed too"


def test_the_plan_asks_only_for_years_that_are_missing(monkeypatch):
    monkeypatch.setattr(refresh, "stored_extent", lambda store=refresh.STORE: {
        "uzgeodata.dated.v1.pre_mm_s": {"last": "2022-12"},
        "uzgeodata.dated.v1.aet_mm_s": {"last": "2022-12"},
        "uzgeodata.dated.v1.pet_mm_s": {"last": "2022-12"},
        "uzgeodata.dated.v1.soil_mm_s": {"last": "2022-12"},
    })
    plan = refresh.missing_years(through="2024-06")
    terra = plan["terraclimate"]
    assert terra["stored_to"] == "2022-12"
    assert terra["years_to_fetch"] == [2022, 2023, 2024], \
        "the stored year is refetched because it may be partial; later years are new"

    assert refresh.missing_years(through="2022-12")["terraclimate"]["years_to_fetch"] == [], \
        "asking for what is already held fetches nothing"


def test_a_source_with_nothing_stored_is_reported_rather_than_assumed(monkeypatch):
    monkeypatch.setattr(refresh, "stored_extent", lambda store=refresh.STORE: {})
    plan = refresh.missing_years(through="2024-12")
    assert all(entry["stored_to"] is None for entry in plan.values())
    assert all("note" in entry for entry in plan.values())


def test_new_months_in_the_same_year_are_fetched(monkeypatch):
    monkeypatch.setattr(refresh, "stored_extent", lambda store=refresh.STORE: {
        "uzgeodata.dated.v1.run_mm_s": {"last": "2026-03"}})
    plan = refresh.missing_years(through="2026-08")
    assert plan["era5_runoff"]["years_to_fetch"] == [2026]


def test_extension_bypasses_stale_year_checkpoints(monkeypatch):
    monkeypatch.setattr(refresh, "missing_years", lambda **kwargs: {
        "era5_runoff": {"stored_to": "2026-03", "years_to_fetch": [2026]}})
    issued = []
    monkeypatch.setattr(refresh, "run", lambda command, dry_run=False: issued.append(command) or True)
    monkeypatch.setattr(refresh, "publish", lambda *args: {"ok": True})
    assert refresh.extend("2026-08")["ok"]
    assert "--refresh-cache" in issued[0]


def test_an_absent_source_never_becomes_a_successful_noop(monkeypatch):
    monkeypatch.setattr(refresh, "missing_years", lambda **kwargs: {"era5_runoff": {"stored_to": None}})
    monkeypatch.setattr(refresh, "publish", lambda *args: pytest.fail("must not publish an absent source"))
    assert not refresh.extend("2026-08")["ok"]


def test_the_published_window_follows_the_store_not_a_constant(monkeypatch):
    """Both publishers default to 2003-2022. That was right while the record ended
    there and silently wrong the moment it did not: the store would hold 2024 and
    every published file would agree with every other about a record two years old."""
    monkeypatch.setattr(refresh, "stored_extent", lambda store=refresh.STORE: {
        "uzgeodata.dated.v1.pre_mm_s": {"first": "2003-01", "last": "2024-12"},
        "uzgeodata.dated.v1.snw_pc_s": {"first": "2003-01", "last": "2023-06"},
    })
    assert refresh.stored_span() == (2003, 2024), "the widest window any variable reaches"

    issued = []
    monkeypatch.setattr(refresh, "run", lambda command, dry_run=False: issued.append(command) or True)
    outcome = refresh.publish()

    assert outcome["published_span"] == "2003-2024"
    windowed = [c for c in issued if "--years" in c]
    assert {c[0] for c in windowed} == {"PIPELINES/derive_regional_substitutes.py",
                                        "PIPELINES/build_basin_history.py"}
    assert all(c[c.index("--years") + 1] == "2003-2024" for c in windowed)
    assert not any("--years" in c for c in issued
                   if c[0].endswith(("build_basin_api.py", "build_regional_coverage.py"))),         "a step that takes no window is not handed one"


def test_an_empty_store_publishes_without_inventing_a_window(monkeypatch):
    monkeypatch.setattr(refresh, "stored_extent", lambda store=refresh.STORE: {})
    issued = []
    monkeypatch.setattr(refresh, "run", lambda command, dry_run=False: issued.append(command) or True)
    outcome = refresh.publish()
    assert outcome["published_span"] is None
    assert not any("--years" in command for command in issued)
