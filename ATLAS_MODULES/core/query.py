"""Ask the observation store a question.

The store has held the values for a while; what it has not had is a way to ask it
anything. A reader could fetch one basin as a file, and everything else -- several
basins, one variable, a window of years, a comparison across the region -- meant
reading the whole store and doing it by hand. That is the difference between a
publication layer and an analytical one, and it is this module.

Queries run through DuckDB over the Parquet partitions. Nothing is loaded into
Python that the question did not ask for, so a window of three variables over forty
basins reads three columns of two year files rather than 17.9 million rows.

Every view here encodes a rule the store already holds, because a query engine will
not apply them on its own and a wrong answer arrives looking exactly like a right
one:

* a superseded revision is not current, and `current` is written at publication time
  so asking for it costs nothing;
* one basin, one variable and one month is one value. A re-run under a corrected
  method does not supersede the earlier row -- the contract keeps both, as two
  measurements rather than a correction -- so a query that did not choose between
  them would return a month twice and every sum over it would be wrong by however
  many times the period had been re-extracted;
* a run that never finished is not evidence, so its rows are excluded by joining the
  run table rather than by trusting the row;
* a null is a month with no observation and never a zero, so nothing here coalesces;
* an upstream value already accounts for everything above the basin, so it can be
  read but never summed across basins -- `support` is a required argument rather
  than a default, so a caller states which question they are asking.
"""
from __future__ import annotations
import csv
import json
from pathlib import Path

DATED = "time_kind=observation"
UNDATED = ("time_kind=static", "time_kind=source_epoch", "time_kind=climatology")


def _duckdb():
    try:
        import duckdb
    except ImportError as error:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Querying the store needs duckdb: pip install duckdb") from error
    return duckdb


def run_ranking(store):
    """How each run ranks when two hold a current value for the same month."""
    path = Path(store) / "run.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as stream:
        return {row["run_id"]: (row.get("status") == "complete", row.get("started_at") or "")
                for row in csv.DictReader(stream)}


def completed_runs(store):
    """Runs the store's own table records as finished.

    A run writes its rows as it goes and its ledger only when it ends, so an
    extraction stopped halfway leaves real values behind that nothing has vouched
    for. They stay in the store -- the record of what happened is not edited -- and
    they stay out of analysis.
    """
    path = Path(store) / "run.csv"
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as stream:
        return {row["run_id"] for row in csv.DictReader(stream)
                if row.get("status") == "complete"}


def vouched(store):
    """Which years a finished extraction covered, per source release.

    The store names the run that *first* established a value. A later run that
    re-derives the identical number is a no-op, so an extraction interrupted and
    resumed leaves the interrupted run's id on rows the completed one also covered.
    Filtering on the run id alone would hide seven of ERA5 temperature's twenty
    years, and the query layer would then disagree with the published record about
    what the store contains.

    The ledger is the claim that matters: it states the span covered and whether the
    run finished, and it is written only on completion.
    """
    covered = {}
    for path in sorted(Path(store).glob("regional-*-ledger.json")):
        try:
            ledger = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        span = ledger.get("years")
        if not ledger.get("complete") or not span or not ledger.get("source"):
            continue
        release = f"{ledger['source']}@{ledger.get('asset')}"
        covered.setdefault(release, set()).update(range(span[0], span[1] + 1))
    return covered


def connect(store, geometry="reg-"):
    """A connection with the store's rules already expressed as views.

    `geometry` selects a geometry version prefix. The default is the regional
    release; the pilot's twenty basins carry their own and are not mixed in, because
    a value computed for one geometry is not a value for another.
    """
    store = Path(store)
    connection = _duckdb().connect()
    dated = (store / DATED / "*" / "part.parquet").as_posix()
    runs = sorted(completed_runs(store))
    # An empty list would make the SQL invalid, and an empty result is the honest
    # answer when no run has finished.
    allowed = ", ".join(f"'{run}'" for run in runs) or "''"

    # A row is evidence when the run that wrote it finished, or when a finished run
    # of the same release covered that year and merely found the value already there.
    pairs = [f"('{release}', {year})"
             for release, years in sorted(vouched(store).items()) for year in sorted(years)]
    vouched_sql = " OR (source_release_id, year) IN (%s)" % ", ".join(pairs) if pairs else ""

    # How the runs rank when two of them hold a current value for the same month: a
    # run that finished outranks one that did not, and among those, the later one.
    # The same rule the published atlas applies, so a query and the site cannot
    # disagree about which number is the current one.
    ranking = run_ranking(store)
    rows = ", ".join(f"('{run}', {int(complete)}, '{started}')"
                     for run, (complete, started) in sorted(ranking.items())) or "('', 0, '')"

    connection.execute(f"""
        CREATE VIEW dated_all AS
            SELECT * FROM read_parquet('{dated}', hive_partitioning = true);
        CREATE TABLE runs(run_id VARCHAR, complete INTEGER, started VARCHAR);
        INSERT INTO runs VALUES {rows};
        CREATE VIEW observations AS
            SELECT basin_id, attribute_id, year, month,
                   make_date(year, month, 1) AS month_start,
                   value, unit, spatial_support, coverage_fraction,
                   valid_count, expected_count, missing_reason,
                   source_release_id, recipe_version, run_id, geometry_version
            FROM dated_all d
            LEFT JOIN runs USING (run_id)
            WHERE current AND geometry_version LIKE '{geometry}%'
              AND (run_id IN ({allowed}){vouched_sql})
            QUALIFY row_number() OVER (
                PARTITION BY basin_id, attribute_id, spatial_support, year, month
                ORDER BY coalesce(complete, 0) DESC, coalesce(started, '') DESC, run_id DESC
            ) = 1;
    """)
    for kind in UNDATED:
        name = kind.split("=")[1]
        path = (store / kind / "part.parquet").as_posix()
        if not (store / kind / "part.parquet").exists():
            continue
        connection.execute(f"""
            CREATE VIEW {name} AS
                SELECT basin_id, attribute_id, value, unit, spatial_support,
                       temporal_statistic, valid_start, valid_end,
                       valid_count, expected_count, missing_reason,
                       source_release_id, recipe_version, run_id
                FROM read_parquet('{path}')
                WHERE current AND geometry_version LIKE '{geometry}%';
        """)
    return connection


def _in(column, values):
    if not values:
        return "TRUE", []
    marks = ", ".join("?" for _ in values)
    return f"{column} IN ({marks})", list(values)


def observations(store, basins=None, variables=None, start=None, end=None,
                 support="s", connection=None):
    """Monthly observations for these basins and variables, as tidy rows.

    `start` and `end` are inclusive months as "YYYY-MM". `support` is 's' for the
    basin itself or 'u' for everything draining through it; there is no default that
    mixes them, because the two answer different questions and adding them together
    answers neither.

    A month with no observation comes back with a null value and its reason, not
    omitted and not zero: the gaps are part of the record, and in the snow series
    they are the part a trend would otherwise be computed straight through.
    """
    own = connection is None
    connection = connection or connect(store)
    try:
        clauses, parameters = ["spatial_support = ?"], [support]
        for column, values in (("basin_id", basins), ("attribute_id", variables)):
            clause, extra = _in(column, values)
            clauses.append(clause)
            parameters.extend(extra)
        if start:
            clauses.append("month_start >= ?")
            parameters.append(f"{start}-01")
        if end:
            year, month = (int(part) for part in end.split("-"))
            clauses.append("month_start <= ?")
            parameters.append(f"{year}-{month:02d}-01")
        sql = f"""SELECT basin_id, attribute_id, month_start, value, unit,
                         valid_count, expected_count, missing_reason,
                         source_release_id, recipe_version
                  FROM observations WHERE {' AND '.join(clauses)}
                  ORDER BY basin_id, attribute_id, month_start"""
        return connection.execute(sql, parameters).fetchall()
    finally:
        if own:
            connection.close()


def available(store, connection=None, observed_span=False):
    """What the store can answer for: each variable, its span and its coverage."""
    own = connection is None
    connection = connection or connect(store)
    try:
        span_filter = "FILTER (WHERE value IS NOT NULL)" if observed_span else ""
        return connection.execute(f"""
            SELECT attribute_id, unit, spatial_support,
                   min(month_start) {span_filter} AS first_month, max(month_start) {span_filter} AS last_month,
                   count(DISTINCT basin_id) AS basins,
                   count(*) FILTER (WHERE value IS NOT NULL) AS observed,
                   count(*) FILTER (WHERE value IS NULL) AS missing
            FROM observations
            GROUP BY 1, 2, 3 ORDER BY 1, 3
        """).fetchall()
    finally:
        if own:
            connection.close()
