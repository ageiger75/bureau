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
#: Planning segments to the channel vocabulary the warehouse rows land on. Both sides have
#: to reach the same word or a channel joins to no budget line at all — which the cockpit
#: reports honestly, and which is still a market missing from the ranking.
SEGMENT_CHANNEL = {
    "EBU": "ecommerce",
    "RET": "retail",
    "MKTP": "marketplace",
    "SPA": "spa",
    "CAF": "cafe",
    "DDS": "direct selling",
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


#: Three ways revenue reaches the Maison, not two. The binary split — ours or resold —
#: broke on the first real question: a Tmall flagship operated by the Maison sells to the
#: end customer, so it is sell-out, but it happens on a platform that is not our site and
#: has no funnel we can read. Collapsing that into either bucket loses something true.

#: Sold by the Maison, on the Maison's own site or in its own stores. Sell-out, and the
#: only case where the whole funnel — visits, conversion, basket — can be measured.
OWN_SEGMENTS = frozenset(("RET", "EBU", "CAF", "SPA"))

#: Sold by the Maison to the end customer, on someone else's platform. Still sell-out: the
#: revenue is recognised when the shopper buys. But the platform owns the traffic, so
#: there is no funnel behind the number — which is why these markets can show real sales
#: and no conversion at all, and why that is not a fault to repair.
PLATFORM_SEGMENTS = frozenset(("MKTP",))

#: Invoiced to a partner who then resells. Sell-in: the revenue is recognised when the
#: Maison ships, not when a shopper buys, and no sell-out source will ever show it.
SELL_IN_SEGMENTS = frozenset(
    ("WEBP", "TRA", "DIS", "DPT", "WHOCH", "WHOIN", "TVC", "WHOSP")
)

#: Segments whose model the code cannot read off the segment name, and which nobody has
#: settled yet. Empty today: marketplaces were confirmed as stores the Maison operates,
#: and Web Partners as e-retailers who buy to resell.
#:
#: Kept as a mechanism rather than deleted, because the question recurs. A marketplace can
#: be run under either contract, and the day one is, the code must say it does not know
#: instead of placing it by resemblance to its neighbours.
AMBIGUOUS_SEGMENTS = frozenset()

#: Everything the sell-out warehouse can account for, however it reached the shopper.
SELL_OUT_SEGMENTS = OWN_SEGMENTS | PLATFORM_SEGMENTS


def perimeter_of(segment: str) -> str:
    """`own`, `platform`, `sell-in`, or `other`. Never a guess: unlisted codes fall to
    `other` rather than being placed by resemblance."""
    code = segment_code(segment)
    if code in OWN_SEGMENTS:
        return "own"
    if code in PLATFORM_SEGMENTS:
        return "platform"
    if code in SELL_IN_SEGMENTS:
        return "sell-in"
    return "other"


def is_sell_out(segment: str) -> bool:
    return segment_code(segment) in SELL_OUT_SEGMENTS


def segment_code(segment: str) -> str:
    """`EBU - E-business` -> `EBU`."""
    return (segment or "").split("-", 1)[0].strip().upper()


def entity_code(entity: str) -> str:
    """`M_007_UNLOC - Far East` -> `M_007_UNLOC`.

    The label after the dash is a human name that drifts; the code in front of it is what
    the consolidation actually keys on.
    """
    return (entity or "").split("-", 1)[0].strip().upper()


def channel_of(segment: str) -> str:
    return SEGMENT_CHANNEL.get(segment_code(segment), segment_code(segment).lower())


def previous_year(period: str) -> str:
    """`2026-04` -> `2025-04`.

    A budget line is labelled by the month it plans for, and carries beside it the actual
    of the same month a year earlier. Exporting that actual under the plan's label says a
    figure from April 2025 belongs to April 2026 — a specification that misdates its own
    evidence, and the reader has no way to notice.
    """
    parts = (period or "").split("-")
    if len(parts) != 2:
        return period
    try:
        return "%d-%s" % (int(parts[0]) - 1, parts[1])
    except ValueError:
        return period


def _period(year: str, month: str) -> Optional[str]:
    number = MONTHS.get(month)
    return None if number is None else "%s-%02d" % (year, number)


class BudgetLine:
    __slots__ = (
        "market", "region", "segment", "channel", "period", "budget", "last_year",
        "entity",
    )

    def __init__(
        self,
        market: str,
        region: str,
        segment: str,
        channel: str,
        period: str,
        budget: Optional[float],
        last_year: Optional[float],
        entity: str = "",
    ) -> None:
        self.market = market
        self.region = region
        self.segment = segment
        self.channel = channel
        self.period = period
        self.budget = budget
        self.last_year = last_year
        #: The consolidation entity the plan attributes this line to — `M_024`, `M_098`.
        #: It is the plan's own answer to "which market does this revenue belong to", and
        #: therefore the join key for anything that has to reproduce the plan. Reaching for
        #: a company or a customer hierarchy instead is reaching for someone else's answer
        #: to the same question, and the two do not agree.
        self.entity = entity


def _add(first: Optional[float], second: Optional[float]) -> Optional[float]:
    """Sum two figures, where absent plus absent stays absent.

    Treating a missing figure as zero here would turn a month nobody planned into a month
    planned at nothing, which the rest of the cockpit spends its time refusing to do.
    """
    if first is None:
        return second
    if second is None:
        return first
    return first + second


class Budget:
    """Every budget line of a fiscal year, addressable by market, channel and period."""

    def __init__(self, lines: List[BudgetLine]) -> None:
        self.lines = lines
        self._index: Dict[Tuple[str, str, str], BudgetLine] = {}
        for line in lines:
            # Collisions happen, and they are not duplicates: a market × segment × month
            # can carry several planning rows — a discount line beside a sales line. The
            # first version of this kept the last row and said the totals would reveal it.
            # They did not: `total_budget` summed every row while `line()` returned one,
            # so the same workbook answered two different numbers depending on which was
            # asked. Summing is what the plan itself means.
            key = (line.market, line.channel, line.period)
            existing = self._index.get(key)
            if existing is None:
                self._index[key] = BudgetLine(
                    market=line.market,
                    region=line.region,
                    segment=line.segment,
                    channel=line.channel,
                    period=line.period,
                    budget=line.budget,
                    last_year=line.last_year,
                    entity=line.entity,
                )
                continue
            existing.budget = _add(existing.budget, line.budget)
            existing.last_year = _add(existing.last_year, line.last_year)

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

    # Optional: older versions of the workbook did not carry it, and its absence costs the
    # join key rather than the whole read.
    entity_at = header.index("Entity") if "Entity" in header else None

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
        entity = entity_code(str(cell(entity_at) or "")) if entity_at is not None else ""

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
                    entity=entity,
                )
            )
    return Budget(lines)
