"""Resolving a release, and answering questions against it.

The work here is mostly refusals and bookkeeping. The querying is DuckDB reading
Parquet; what needs care is making sure a caller always knows which release answered
and what kind of answer it was.

A dataset is backed either by the published cube -- fast, remote, evidence-free -- or
by a full observation store in a checkout. The two answer the same questions with the
same shapes, so analysis code moves between them unchanged, and they differ in exactly
one respect: the store can defend a value and the cube cannot. That difference is
enforced rather than documented, because a null where evidence should be is
indistinguishable from evidence that says nothing.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

DEFAULT_HOST = "https://uzgeodata.uz"
ATLAS = "data/atlas"

# Columns the analysis layers expect from the `observations` view. The cube carries the
# first five and cannot carry the rest; they are selected as NULL so the shapes match,
# and every path that would let a caller mistake those nulls for evidence raises.
EVIDENCE = ("valid_count", "expected_count", "missing_reason", "source_release_id",
            "recipe_version")


class Unavailable(RuntimeError):
    """A question this dataset cannot answer, and the reason it cannot."""


def _fetch(url):
    with urlopen(url, timeout=60) as response:  # noqa: S310 - fixed https host
        return json.loads(response.read().decode("utf-8"))


def open(source=None, release=None, connection=None):  # noqa: A001 - module-level name
    """A dataset for the published record.

    `source` is a host (the default, reading the published cube over HTTP) or a path to
    a checkout's `PUBLISHED/data/atlas`. `release` pins a release id; omitting it
    follows the pointer to whatever is current, which the dataset then records so an
    analysis can report what it actually used.
    """
    source = source or DEFAULT_HOST
    text = str(source)
    if text.startswith(("http://", "https://")):
        return Dataset.remote(text.rstrip("/"), release, connection)
    return Dataset.local(Path(source), release, connection)


class Dataset:
    """One release, and the questions it can answer."""

    def __init__(self, *, base, release, remote, store=None, connection=None):
        self._base = base
        self._release = release
        self._remote = remote
        self._store = store
        self._connection = connection

    # ---- construction -----------------------------------------------------------

    @classmethod
    def remote(cls, host, release=None, connection=None):
        root = f"{host}/{ATLAS}"
        record = _fetch(f"{root}/releases/{release}.json") if release else None
        if record is None:
            pointer = _fetch(f"{root}/latest.json")
            record = _fetch(f"{root}/{pointer['path']}")
        return cls(base=root, release=record, remote=True, connection=connection)

    @classmethod
    def local(cls, path, release=None, connection=None):
        from ATLAS_MODULES.core import releases

        path = Path(path)
        record = releases.read(path, release)
        store = path / "observations"
        from ATLAS_MODULES.core import observations as contract

        has_store = bool(contract.partition_files(store))
        return cls(base=path.as_posix(), release=record, remote=False,
                   store=store if has_store else None, connection=connection)

    # ---- identity ---------------------------------------------------------------

    @property
    def release_id(self):
        """Which release answered. Print this in anything you intend to reproduce."""
        return self._release["release_id"]

    @property
    def span(self):
        return tuple(self._release.get("span") or ())

    @property
    def rows(self):
        return self._release.get("rows")

    @property
    def backed_by_record(self):
        """True when this dataset can defend a value, not merely report it."""
        return self._store is not None

    def __repr__(self):
        kind = "record" if self.backed_by_record else "cube"
        return (f"<uzgeodata {self.release_id} {kind} "
                f"{'-'.join(self.span) if self.span else 'unknown span'}>")

    def describe(self):
        """What this dataset is, in a form worth pasting into a method section."""
        return {
            "release_id": self.release_id,
            "cut_at": self._release.get("cut_at"),
            "commit": self._release.get("commit"),
            "span": list(self.span),
            "rows": self.rows,
            "source": self._base,
            "backed_by": "observation record" if self.backed_by_record else "published cube",
            "evidence": ("Values can be traced to the run and coverage behind them."
                         if self.backed_by_record else
                         "The cube is a read path: no revisions, run ids, coverage counts "
                         "or missing reasons. Cite the release id; a value cannot be "
                         "defended from this source alone."),
        }

    def variables(self):
        """The registry: one preferred product per concept, and what is refused."""
        registry = self._release.get("registry")
        if registry:
            return registry
        from ATLAS_MODULES.core import variables

        return variables.registry()

    def verify(self):
        """Check the artefacts against the release manifest. Local sources only."""
        if self._remote:
            raise Unavailable(
                "verification compares files on disk against the release manifest, and "
                "this dataset reads them over HTTP. Clone the published tree, or fetch "
                "the release record and check the digests yourself.")
        from ATLAS_MODULES.core import releases

        return releases.check(Path(self._base), self.release_id)

    # ---- querying ---------------------------------------------------------------

    def _connect(self):
        if self._connection is not None:
            return self._connection, False
        import duckdb

        if not self._remote:
            from ATLAS_MODULES.core import query

            if self._store is None:
                self._connection = _cube_view(duckdb.connect(), f"{self._base}/cube")
            else:
                self._connection = query.connect(self._store)
            return self._connection, False
        connection = duckdb.connect()
        connection.execute("INSTALL httpfs; LOAD httpfs;")
        self._connection = _cube_view(connection, f"{self._base}/cube")
        return self._connection, False

    def series(self, basin, concept, start=None, end=None):
        """One basin's monthly series for a concept, oldest first.

        Returns dicts rather than tuples: a positional row invites the caller to index
        the wrong column, and this is the boundary where that stops being catchable.
        """
        from ATLAS_MODULES.core import query, variables

        attribute = variables.attribute(concept)
        connection, _ = self._connect()
        rows = query.observations(self._store or self._base, basins=[str(basin)],
                                  variables=[attribute], start=start, end=end,
                                  connection=connection)
        out = []
        for row in rows:
            entry = {"basin_id": row[0], "attribute_id": row[1], "month": row[2],
                     "value": row[3], "unit": row[4]}
            if self.backed_by_record:
                entry.update({"valid_count": row[5], "expected_count": row[6],
                              "missing_reason": row[7], "source_release_id": row[8],
                              "recipe_version": row[9]})
            out.append(entry)
        return out

    def evidence(self, basin, concept, start=None, end=None):
        """The same series with what stands behind each value.

        Raises on a cube-backed dataset rather than returning nulls in the evidence
        columns. Nulls there would read as "no coverage recorded" when the truth is
        "this source does not carry coverage", and those are different claims.
        """
        if not self.backed_by_record:
            raise Unavailable(
                "this dataset reads the published cube, which carries no revisions, run "
                "ids, coverage counts or missing reasons. Evidence needs the observation "
                "record: open a checkout's PUBLISHED/data/atlas instead.")
        return self.series(basin, concept, start, end)

    def spi(self, basin, window=3, start=None, end=None, baseline=(None, None)):
        """Standardised Precipitation Index: a gamma fit, not a z-score."""
        from ATLAS_MODULES.core import products

        connection, _ = self._connect()
        return products.spi(self._store or self._base, basins=[str(basin)], window=window,
                            start=start, end=end, baseline=baseline, connection=connection)

    def anomalies(self, basin, concept, start=None, end=None, baseline=(None, None)):
        """Each month against what that month usually brings in that basin."""
        from ATLAS_MODULES.core import products

        connection, _ = self._connect()
        return products.anomalies(self._store or self._base, concept, basins=[str(basin)],
                                  start=start, end=end, baseline=baseline,
                                  connection=connection)

    def seasonal(self, basin, concept, months=None, start=None, end=None):
        """A season summed for a flux, averaged for a state, withheld if incomplete."""
        from ATLAS_MODULES.core import products

        connection, _ = self._connect()
        return products.seasonal(self._store or self._base, concept, basins=[str(basin)],
                                 start=start, end=end, months=months, connection=connection)

    def trend(self, basin, concept, months=None, start=None, end=None):
        """Slope per year, with the gaps and cautions that qualify it."""
        from ATLAS_MODULES.core import products

        connection, _ = self._connect()
        return products.trend(self._store or self._base, concept, basins=[str(basin)],
                              start=start, end=end, months=months, connection=connection)

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _cube_view(connection, cube):
    """An `observations` view over the cube, shaped like the record's.

    The analysis layers query a view with a fixed set of columns. The cube carries the
    measurements and none of the evidence, so the evidence columns are selected as NULL
    to keep the shape -- and `Dataset.evidence` refuses rather than handing those nulls
    to a caller who would read them as findings.
    """
    nulls = ", ".join(f"NULL AS {name}" for name in EVIDENCE)
    connection.execute(f"""
        CREATE OR REPLACE VIEW observations AS
        SELECT basin_id, attribute_id,
               make_date(year, month, 1) AS month_start,
               -- Cast rather than trust the file: a cube written with DECIMAL values
               -- reaches the fitting code as Decimal, and scipy rejects it with a type
               -- error that says nothing about where it came from. The record writes
               -- doubles; this makes the library independent of that staying true.
               CAST(value AS DOUBLE) AS value, unit, {nulls},
               's' AS spatial_support, year, month
        FROM read_parquet('{cube}/variable=*/*.parquet', hive_partitioning = true)
    """)
    return connection
