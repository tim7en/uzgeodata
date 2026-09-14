"""UzGeoData: the published basin record, as a library.

Until now the analysis layers were reachable only from a checkout of the repository,
with the 520 MB observation store on the same disk. That made the platform the source
of truth for its own analyses in principle and not in practice: a collaborator, a
notebook or an agent could read the web pages but could not ask the data a question.

This is the entry point that fixes that. `pip install uzgeodata`, then:

    import uzgeodata as uz

    data = uz.open()                       # the current published release, over HTTP
    data.release_id                         # what you are actually using
    data.series("4121289400", "precipitation", start="2020-01")
    data.spi("4121289400", window=3)

Nothing is downloaded wholesale. The published cube is Parquet partitioned by
variable and the host serves byte ranges, so a query for one basin reads the row
groups it touches and leaves the rest on the server.

Two things this module is careful about, because both are ways a published dataset
quietly misleads whoever reuses it:

**Which data.** Every dataset resolves to a named release and says so. Pin
`release=` to keep an analysis reproducible, or follow the pointer to track the
current one -- but never without knowing which you did. `uz.open()` records the id it
resolved, so a notebook can print what it used.

**What kind of data.** The cube is a read path, not the record. It carries no
revisions, run ids, coverage counts or missing reasons, so a value from it can be used
but not defended. Asking a cube-backed dataset for evidence raises rather than
returning nulls that look like an answer. The full record needs a checkout.
"""
from __future__ import annotations

from .dataset import Dataset, Unavailable, open  # noqa: A004 - `open` is the intended name
from .dataset import DEFAULT_HOST

__all__ = ["open", "Dataset", "Unavailable", "DEFAULT_HOST", "__version__"]
__version__ = "0.1.0"
