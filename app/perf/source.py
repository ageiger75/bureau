"""The only module that knows where performance numbers come from.

Brief §35 Phase 6 asks for a clean seam between the data source and everything above it,
so that a warehouse can replace mock data without rewriting the application. That seam is
this file: the analytics engine, the routes and the templates never import `mock`.

When real data arrives, add a source that returns the same normalised `Dataset` and change
`current_source()`. Nothing above this line should need to move.
"""

from __future__ import annotations

from typing import List

from ..config import settings
from . import mock
from .kpi import Kpi
from .model import Dataset


#: The query anchors on the last complete month, so the screen must not say "MTD" — a
#: label that promises a month in progress while showing a month that has closed.
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
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
    return "%s %s sales" % (_MONTHS[month - 1], parts[0])


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

    def dataset(self) -> Dataset:
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

    def dataset(self) -> Dataset:
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

        period = str(rows[0].get("period") or "")
        return Dataset(
            period_label=_period_label(period),
            as_of=period,
            units=mapped.units,
        )

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
