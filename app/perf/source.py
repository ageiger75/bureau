"""The only module that knows where performance numbers come from.

Brief §35 Phase 6 asks for a clean seam between the data source and everything above it,
so that a warehouse can replace mock data without rewriting the application. That seam is
this file: the analytics engine, the routes and the templates never import `mock`.

When real data arrives, add a source that returns the same normalised `Dataset` and change
`current_source()`. Nothing above this line should need to move.
"""

from __future__ import annotations

from typing import List

import time

from ..config import settings
from ..util import now_iso
from . import mock
from .kpi import Kpi
from .model import Dataset


#: The query anchors on the last complete month, so the screen must not say "MTD" — a
#: label that promises a month in progress while showing a month that has closed.
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


#: How long a warehouse read stays good for. The underlying facts move once a day at
#: most, while the query takes minutes — so re-running it on every page load costs the
#: reader everything and buys nothing. The screen still carries the moment of the read, so
#: a cached figure is never passed off as a fresh one.
CACHE_SECONDS = 900

#: (dataset, read at). Module level rather than on the instance: `current_source()` builds
#: a new source per request, and a cache that dies with the request is not a cache.
_cached = None


def cache_clear() -> None:
    global _cached
    _cached = None


def read_at() -> str:
    """When the warehouse was read, to the minute. UTC, like every other stamp here."""
    return now_iso()[:16].replace("T", " ") + " UTC"


def _perimeter_note(budget, units=()) -> str:
    """What the headline figure leaves out, in the plan's own proportions.

    Two holes, and they compound. The warehouse only measures what the Maison sells to the
    end customer, so everything invoiced to a partner who resells is outside it. And the
    query itself may cover fewer channels than that — today it reads e-commerce and
    nothing else.

    The second hole is the one that misleads. A figure labelled as covering own retail and
    e-commerce, showing e-commerce alone, reads as a collapse rather than a subset. So the
    sentence is built from the channels actually present in the data, never from what the
    screen is one day meant to cover.

    Shares come from the file rather than from a constant: the mix changes every year, and
    a number written into a caveat is a caveat that quietly stops being true.
    """
    from .budget import perimeter_of
    from .model import ECOMMERCE, RETAIL

    channels = {unit.channel for unit in units}
    if channels == {ECOMMERCE}:
        covers = "E-commerce only"
    elif channels == {RETAIL}:
        covers = "Own retail only"
    elif channels:
        covers = "Own retail and e-commerce only"
    else:
        covers = ""

    total = 0.0
    measured = 0.0
    for line in budget.lines if budget else []:
        amount = line.budget or 0.0
        total += amount
        if perimeter_of(line.segment) != "own":
            continue
        if channels and line.channel not in channels:
            continue
        measured += amount

    if not covers:
        return ""
    if total <= 0:
        return covers + "."

    share = 100.0 * measured / total
    return (
        "%s — about %.0f%% of the plan. The rest is store sales and everything invoiced "
        "to partners who resell: wholesale, distributors, travel retail, marketplaces. "
        "No source measures it here yet."
        % (covers, share)
    )


def _period_label(period: str) -> str:
    """'2026-07' -> 'July 2026 sales'. Falls back to the raw value rather than guessing."""
    parts = period.split("-")
    if len(parts) != 2:
        return "Sales"
    try:
        month = int(parts[1])
    except ValueError:
        return "Sales"
    if not 1 <= month <= 12:
        return "Sales"
    # "Last complete month" is not decoration: read on the 27th, a screen headed "July"
    # looks like a month-old screen unless it says why July is the freshest month there is.
    return "%s %s sales · last complete month" % (_MONTHS[month - 1], parts[0])


class MockSource:
    """Invented data, clearly labelled as such everywhere it is shown."""

    name = "mock"
    label = "Mock data"
    #: Shown in the interface. A cockpit that looks authoritative while running on
    #: invented numbers is worse than no cockpit at all.
    caveat = (
        "Every figure on this screen is invented for demonstration. No real market, "
        "person or product appears here."
    )

    def dataset(self, refresh: bool = False) -> Dataset:
        return mock.dataset()

    def commitments(self) -> List["mock.MockCommitment"]:
        return mock.commitments()

    def client_kpis(self) -> List[Kpi]:
        return mock.client_kpis()


class SnowflakeSource:
    """Real figures, read from the warehouse through a named CLI connection.

    Deliberately incomplete: it refuses to serve anything until the queries in
    `queries.py` are written against the real schema. Returning empty lists instead would
    render a calm-looking cockpit on a business that has problems — the most expensive
    failure available to this product.
    """

    name = "snowflake"
    label = "Snowflake"
    caveat = ""

    def __init__(self) -> None:
        #: Filled by `dataset()`. Where the planning file and the warehouse disagree, and
        #: which markets have no named owner — both worth saying out loud on the screen.
        self.conflicts = []
        self.markets_without_owner = []
        #: What the headline figure leaves out, in the plan's own proportions. Computed
        #: from the file rather than written down, so it stays true when the file changes.
        self.perimeter_note = ""

    def _refuse_if_unwritten(self, *names: str) -> None:
        from . import queries

        missing = [n for n in names if not queries.ALL.get(n, "").strip()]
        if missing:
            raise NotImplementedError(
                "These queries are not written yet: %s. See app/perf/queries.py — it "
                "describes exactly what each must return." % ", ".join(missing)
            )

    def _budget(self):
        """The planning workbook, or a refusal.

        Not optional. Without it almost every market arrives with no commitment to be
        measured against, so nothing is a gap, nothing is a win, and the screen renders
        calm — the failure this whole module is arranged to avoid. Better to say the file
        is missing than to show a business with no problems.
        """
        from . import budget as budget_module

        if not settings.has_budget_file:
            raise NotImplementedError(
                "The planning workbook is missing. The warehouse supplies actuals; the "
                "budget comes from the file, because the targets in Snowflake are not "
                "always filled in. Copy it to %s and restart."
                % settings.budget_path
            )
        return budget_module.load(settings.budget_path)

    def dataset(self, refresh: bool = False) -> Dataset:
        global _cached

        if not refresh and _cached is not None:
            dataset, stored_at, conflicts, unnamed, note = _cached
            if time.time() - stored_at < CACHE_SECONDS:
                self.conflicts = conflicts
                self.markets_without_owner = unnamed
                self.perimeter_note = note
                return dataset

        self._refuse_if_unwritten("SALES_AND_DRIVERS")

        from . import mapping, queries, warehouse

        # Before the network, not after: a missing local file is not worth a round trip to
        # the warehouse, and the refusal is clearer when nothing has been read yet.
        budget = self._budget()

        rows = warehouse.rows(queries.SALES_AND_DRIVERS)
        if not rows:
            raise NotImplementedError(
                "The query ran and returned nothing. An empty cockpit and a healthy "
                "business look identical, so this refuses rather than renders."
            )

        mapped = mapping.units_from_rows(rows, budget=budget)
        # Kept on the source, not on the dataset: they describe the plumbing, not the
        # business, and the screen shows them where it shows the caveat.
        self.conflicts = mapped.conflicts
        self.markets_without_owner = mapped.markets_without_owner
        self.perimeter_note = _perimeter_note(budget, mapped.units)

        period = str(rows[0].get("period") or "")
        built = Dataset(
            period_label=_period_label(period),
            # The moment of the read, not the period — and to the minute, because the
            # warehouse is not yet stable within a day. Sell-out facts are still being
            # reprocessed on recent months, so the same query run hours apart returns
            # different figures for some markets. Two screens that disagree are a
            # scandal; two screens stamped an hour apart are a fact about the pipeline.
            as_of=read_at(),
            units=mapped.units,
        )
        _cached = (
            built,
            time.time(),
            self.conflicts,
            self.markets_without_owner,
            self.perimeter_note,
        )
        return built

    def commitments(self) -> List["mock.MockCommitment"]:
        self._refuse_if_unwritten("COMMITMENTS")
        raise NotImplementedError("Commitment mapping not written yet.")

    def client_kpis(self) -> List[Kpi]:
        self._refuse_if_unwritten("KPI_READINGS")
        raise NotImplementedError("KPI mapping not written yet.")


def current_source():
    """The active source.

    Mock unless the environment asks otherwise, and it has to ask twice — a source name
    and a connection name. A warehouse is never reached by default.
    """
    if settings.reads_warehouse:
        return SnowflakeSource()
    return MockSource()
