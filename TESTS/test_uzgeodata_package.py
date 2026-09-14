"""The public API is the boundary where this project stops being able to correct you.

Inside the repository a wrong assumption gets caught by a contract, a ledger or a
test. Past `import uzgeodata` there is only what the API says and what it refuses, so
these check the refusals: that a dataset always knows which release answered, and that
the fast read path is never mistaken for the citable record.
"""
import json

import pytest

from ATLAS_MODULES.core import releases

pytest.importorskip("duckdb")
uz = pytest.importorskip("uzgeodata")


def VALUE(year, month):
    """The fixture's own formula, so an expectation cannot drift from the data."""
    return 10.0 + month + ((year * 7) % 11)


@pytest.fixture
def published(tmp_path):
    """A minimal published tree: a cube of one variable, and a promoted release."""
    import duckdb

    folder = tmp_path / "cube" / "variable=pre_mm_s"
    folder.mkdir(parents=True)
    connection = duckdb.connect()
    connection.execute(f"""
        COPY (SELECT '4120000001' AS basin_id,
                     'uzgeodata.dated.v1.pre_mm_s' AS attribute_id,
                     year, month,
                     CAST(10.0 + month + ((year * 7) % 11) AS DOUBLE) AS value,
                     'millimetres per month' AS unit
              FROM range(2003, 2025) t(year), range(1, 13) m(month))
        TO '{(folder / "data_0.parquet").as_posix()}' (FORMAT PARQUET)
    """)
    connection.close()
    (tmp_path / "cube" / "index.json").write_text(
        json.dumps({"rows": 264, "months": ["2003-01", "2024-12"]}), encoding="utf-8")

    record = releases.cut(tmp_path, [folder / "data_0.parquet", tmp_path / "cube/index.json"],
                          base=tmp_path, rows=264, span=["2003-01", "2024-12"])
    releases.promote(tmp_path, record["release_id"])
    return tmp_path


def test_a_dataset_always_knows_which_release_answered(published):
    data = uz.open(published)
    assert data.release_id.startswith("uz-")
    assert data.span == ("2003-01", "2024-12")
    described = data.describe()
    assert described["release_id"] == data.release_id
    assert described["rows"] == 264
    data.close()


def test_a_release_can_be_pinned_so_an_analysis_stays_reproducible(published):
    first = uz.open(published).release_id
    # A later release supersedes it, but the pinned id keeps resolving to the original.
    later = releases.cut(published, [published / "cube/index.json"], base=published,
                         supersedes=first)
    releases.promote(published, later["release_id"])

    assert uz.open(published).release_id == later["release_id"], "unpinned follows the pointer"
    assert uz.open(published, release=first).release_id == first, "pinned stays put"


def test_a_cube_backed_dataset_refuses_to_supply_evidence(published):
    """The distinction the whole API exists to hold: usable is not defensible."""
    data = uz.open(published)
    assert not data.backed_by_record
    rows = data.series("4120000001", "precipitation", start="2010-01", end="2010-03")
    assert len(rows) == 3
    assert rows[0]["value"] == pytest.approx(VALUE(2010, 1)), "the cube returns what it stores"
    assert [row["month"].month for row in rows] == [1, 2, 3], "ordered, oldest first"
    assert "valid_count" not in rows[0], "the cube carries no coverage, so it reports none"

    with pytest.raises(uz.Unavailable, match="carries no revisions"):
        data.evidence("4120000001", "precipitation")
    data.close()


def test_the_description_says_which_kind_of_source_answered(published):
    data = uz.open(published)
    assert data.describe()["backed_by"] == "published cube"
    assert "cannot be defended" in data.describe()["evidence"]
    data.close()


def test_verification_is_refused_rather_than_faked_for_a_remote_source():
    data = uz.Dataset(base="https://example.invalid/data/atlas",
                      release={"release_id": "uz-x", "span": None}, remote=True)
    with pytest.raises(uz.Unavailable, match="over HTTP"):
        data.verify()


def test_a_local_dataset_verifies_against_its_own_manifest(published):
    data = uz.open(published)
    assert data.verify() == []
    (published / "cube/index.json").write_text("{}", encoding="utf-8")
    assert data.verify(), "an edited artefact stops verifying"
    data.close()


def test_an_unregistered_concept_is_refused_with_what_can_be_asked(published):
    from ATLAS_MODULES.core import variables

    data = uz.open(published)
    with pytest.raises(variables.Unavailable):
        data.series("4120000001", "vegetation")
    data.close()


def test_derived_products_run_against_the_cube(published):
    """Layer 3 works on a remote read path, not only on a checkout."""
    pytest.importorskip("scipy")
    data = uz.open(published)
    entries = [row for row in data.spi("4120000001", window=3) if row["withheld"] is None]
    assert entries, "twenty-two years of a cube is enough to fit"
    assert all(-5 < row["spi"] < 5 for row in entries)
    data.close()
