"""Budget and last year, read from the planning workbook rather than the warehouse.

The warehouse carries goals for a minority of markets — not for the largest ones — while
the planning file carries all of them, and is the version the business actually commits
to. Where the two overlap they agree; where they differ, the file is the reference.

That is not a workaround. A budget is a decision, not a measurement: it belongs with the
other governance artefacts, alongside KPI targets and definitions. The warehouse supplies
what happened; this file supplies what was promised.

Values in the sheet are thousands of euros in group currency. They are converted once,
here, so nothing downstream has to remember the unit.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .xlsx import Workbook, WorkbookError

#: The normalised sheet. The other sheets are pivots built from it.
SHEET = "DATA BASE"

THOUSANDS = 1000.0

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

#: `BUDGET 2026.JUL` and its last-year twin `2025.JUL`. Quarter and full-year columns are
#: ignored: the cockpit reads months and adds them up itself.
BUDGET_COLUMN = re.compile(r"^BUDGET\s+(\d{4})\.([A-Z]{3})$")
ACTUAL_COLUMN = re.compile(r"^(\d{4})\.([A-Z]{3})$")

#: Planning segments mapped to the cockpit's driver models. Anything unmapped keeps its
#: own name and carries no driver breakdown — which is the honest default.
SEGMENT_CHANNEL = {
    "EBU": "ecommerce",
    "RET": "retail",
}

#: Market names differ between the planning file and the warehouse. Kept explicit and
#: editable rather than guessed: a silent mismatch would drop a market from the cockpit
#: without anyone noticing.
MARKET_ALIASES = {
    "USA": "United States",
    "UK": "United Kingdom",
    "HK": "Hong Kong",
    "HK DISTRIBUTORS": "Hong Kong",
    "HK TR": "Hong Kong",
    "CHINA CROSS BORDER": "China",
    "NEW ZEALAND": "New Zealand",
    "CZECH REPUBLIC": "Czech Republic",
    "EXPORT MIDDLE EAST": "Middle East",
}


def normalise_market(name: str) -> str:
    """Planning-file market name in the form the rest of the cockpit uses."""
    raw = (name or "").strip()
    if raw in MARKET_ALIASES:
        return MARKET_ALIASES[raw]
    return raw.title()


def segment_code(segment: str) -> str:
    """`EBU - E-business` -> `EBU`."""
    return (segment or "").split("-", 1)[0].strip().upper()


def channel_of(segment: str) -> str:
    return SEGMENT_CHANNEL.get(segment_code(segment), segment_code(segment).lower())


def _period(year: str, month: str) -> Optional[str]:
    number = MONTHS.get(month)
    return None if number is None else "%s-%02d" % (year, number)


class BudgetLine:
    __slots__ = ("market", "region", "segment", "channel", "period", "budget", "last_year")

    def __init__(
        self,
        market: str,
        region: str,
        segment: str,
        channel: str,
        period: str,
        budget: Optional[float],
        last_year: Optional[float],
    ) -> None:
        self.market = market
        self.region = region
        self.segment = segment
        self.channel = channel
        self.period = period
        self.budget = budget
        self.last_year = last_year


class Budget:
    """Every budget line of a fiscal year, addressable by market, channel and period."""

    def __init__(self, lines: List[BudgetLine]) -> None:
        self.lines = lines
        self._index: Dict[Tuple[str, str, str], BudgetLine] = {}
        for line in lines:
            # One planning row per market × segment, so the key cannot collide. If it ever
            # does, the later row wins and the totals below would reveal it.
            self._index[(line.market, line.channel, line.period)] = line

    def line(self, market: str, channel: str, period: str) -> Optional[BudgetLine]:
        return self._index.get((market, channel, period))

    def budget_for(self, market: str, channel: str, period: str) -> Optional[float]:
        found = self.line(market, channel, period)
        return found.budget if found else None

    def last_year_for(self, market: str, channel: str, period: str) -> Optional[float]:
        found = self.line(market, channel, period)
        return found.last_year if found else None

    def markets(self) -> List[str]:
        return sorted({line.market for line in self.lines})

    def periods(self) -> List[str]:
        return sorted({line.period for line in self.lines})

    def total_budget(self, period: str) -> float:
        return sum(l.budget or 0.0 for l in self.lines if l.period == period)

    def total_last_year(self, period: str) -> float:
        return sum(l.last_year or 0.0 for l in self.lines if l.period == period)


def load(path) -> Budget:
    """Read the planning workbook. Raises rather than returning an empty budget.

    An empty budget would make every market look exactly on plan, which is the most
    reassuring wrong answer this product could give.
    """
    with Workbook(path) as workbook:
        rows = list(workbook.rows(SHEET))

    if not rows:
        raise WorkbookError("Sheet %r is empty." % SHEET)

    header = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    try:
        country_at = header.index("Country")
        region_at = header.index("Region")
        segment_at = header.index("Segment")
    except ValueError as exc:
        raise WorkbookError(
            "Sheet %r must have Country, Region and Segment columns. Found: %s"
            % (SHEET, ", ".join(h for h in header if h))
        ) from exc

    budget_at: Dict[str, int] = {}
    actual_at: Dict[str, int] = {}
    for position, name in enumerate(header):
        budgeted = BUDGET_COLUMN.match(name)
        if budgeted:
            period = _period(budgeted.group(1), budgeted.group(2))
            if period:
                budget_at[period] = position
            continue
        actual = ACTUAL_COLUMN.match(name)
        if actual:
            period = _period(actual.group(1), actual.group(2))
            if period:
                actual_at[period] = position

    if not budget_at:
        raise WorkbookError("No monthly budget column found in %r." % SHEET)

    lines: List[BudgetLine] = []
    for row in rows[1:]:
        def cell(position: int):
            return row[position] if position < len(row) else None

        country = cell(country_at)
        if not country:
            continue
        market = normalise_market(str(country))
        region = str(cell(region_at) or "").strip()
        segment = str(cell(segment_at) or "").strip()
        channel = channel_of(segment)

        for period, position in budget_at.items():
            budget = cell(position)
            # Last year is the same month one year earlier, in its own column.
            year, month = period.split("-")
            twin = "%d-%s" % (int(year) - 1, month)
            last_year = cell(actual_at[twin]) if twin in actual_at else None

            if budget is None and last_year is None:
                continue
            lines.append(
                BudgetLine(
                    market=market,
                    region=region,
                    segment=segment,
                    channel=channel,
                    period=period,
                    budget=float(budget) * THOUSANDS if isinstance(budget, float) else None,
                    last_year=float(last_year) * THOUSANDS
                    if isinstance(last_year, float)
                    else None,
                )
            )
    return Budget(lines)
