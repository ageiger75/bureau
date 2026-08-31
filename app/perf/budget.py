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
from typing import Dict, List, Optional, Sequence, Tuple

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
    # Three lines, three businesses, one invoicing address. `HK` is the domestic market.
    # `HK DISTRIBUTORS` is an export business selling to distributors who resell. `HK TR`
    # is travel retail across Asia, sold in airports and billed from Hong Kong.
    #
    # Folded into one, a small market in steep decline sat inside a line several times
    # its size, made mostly of airport trade and barely moving: the fall was
    # arithmetically present in the total and impossible to see. Finance separates them
    # and always has — the country under its region, travel retail under a worldwide
    # heading. It was the cockpit that mixed them.
    "HK": "Hong Kong",
    "HK DISTRIBUTORS": "Hong Kong distributors",
    "HK TR": "Travel retail Asia",
    "LOI TR": "Travel retail international",
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


#: Segments the consolidation labels with an invoicing country while the business they
#: describe is not that country's. Travel retail is sold in airports across a region;
#: a distributor business is an export sold to someone who resells. Neither is the
#: domestic market, and neither answers the questions a domestic market answers.
TRAVEL_RETAIL_SEGMENT = "TRA"
DISTRIBUTOR_SEGMENT = "DIS"

#: Where selling to distributors is an export business rather than a corner of the local
#: market, named one country at a time. Not a rule over the segment: everywhere else the
#: plan already separates distributors as a channel of their market, and splitting the
#: market too would key a sell-in row to a plan line that does not exist — the tests said
#: so immediately, on Japan, which is exactly what they are for.
DISTRIBUTOR_MARKETS = {
    "Hong Kong": "Hong Kong distributors",
}

#: The entity that carries travel retail for no country in particular. Its country label
#: is a warehouse code rather than a place, and printing it on a screen asks the reader to
#: know an internal name to read a number.
INTERNATIONAL_TRAVEL_RETAIL = "Travel retail international"

#: Travel retail billed from Hong Kong is the Asian region's airport trade, not Hong
#: Kong's. Named for what it sells rather than for where the invoice is cut — a reader
#: who sees a country's name on a regional line will ask that country's question about it.
TRAVEL_RETAIL_NAMES = {
    "Hong Kong": "Travel retail Asia",
    "Loi Tr": INTERNATIONAL_TRAVEL_RETAIL,
}

#: What a travel-retail market is called once named. Tested for before renaming, because
#: the consolidation labels some of these rows with a country and others with the
#: travel-retail name itself — `HK` on one row and `HK TR` on the next, inside one entity.
#: The second kind is already named by the alias table, and prefixing it again produced
#: "Travel retail Travel retail Asia" on a live screen.
TRAVEL_RETAIL_PREFIX = "Travel retail"


def market_of(country: str, segment: str = "") -> str:
    """The market a consolidation row belongs to, not the country that invoices it.

    Three lines share Hong Kong's invoicing address and describe three businesses: the
    domestic market, an export business selling to distributors, and travel retail across
    Asia. Folded into one, a small market in steep decline sat inside a line several
    times its size, made mostly of airport trade and barely moving — the fall was
    arithmetically present in the total and impossible to see.

    Finance separates them and always has, so this is the file's reading as much as the
    warehouse's. It was the cockpit that mixed them, in an alias written here.
    """
    market = normalise_market(country)
    code = segment_code(segment)
    if code == TRAVEL_RETAIL_SEGMENT:
        # Case-insensitively: `normalise_market` title-cases anything it does not know,
        # so a name that arrives already spelled out comes back as "Travel Retail Asia".
        if market.lower().startswith(TRAVEL_RETAIL_PREFIX.lower()):
            return market
        return TRAVEL_RETAIL_NAMES.get(market, "%s %s" % (TRAVEL_RETAIL_PREFIX, market))
    if code == DISTRIBUTOR_SEGMENT and market in DISTRIBUTOR_MARKETS:
        return DISTRIBUTOR_MARKETS[market]
    return market


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

#: Sold to a business that does not resell it: hotels put the product in the room, a
#: company gives it away. A third block, not a corner of sell-in — the plan itself reads
#: the business that way, and the group budget closes on the three: sell-out, sell-in,
#: and this. Recognition follows the invoice, as with sell-in, but nothing downstream is
#: a resale and no partner has a margin on it, so the questions differ: room counts and
#: contract renewals rather than sell-through and stock cover.
B2B_SEGMENTS = frozenset(("B2B", "COPG"))

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


#: Plan rows that are a roll-up rather than a market. There is nobody to challenge about
#: "Other", and letting it into a ranking pushes out a market someone can actually be
#: asked about — the same reason the screen keeps "Rest of World" out of its fires.
#:
#: A name is a weak key and this list is a maintenance cost. It is still the honest option:
#: the workbook carries no column saying which of its rows are totals, so the alternative
#: is to infer it from size or from a naming pattern, and both would eventually swallow a
#: real market. An explicit list is wrong loudly rather than quietly.
#: Header names under which a workbook may name the Maison a line belongs to. Read only to
#: report what was summed — never to filter, because choosing a brand silently would be the
#: same fault in the other direction.
BRAND_COLUMNS = frozenset(("brand", "brand code", "marque", "maison"))

AGGREGATE_MARKETS = frozenset(("Other", "Others", "Rest of World", "ROW"))


def is_aggregate_market(market: str) -> bool:
    return (market or "").strip().lower() in {m.lower() for m in AGGREGATE_MARKETS}


def perimeter_of(segment: str) -> str:
    """`own`, `platform`, `sell-in`, `b2b`, or `other`. Never a guess: unlisted codes fall
    to `other` rather than being placed by resemblance."""
    code = segment_code(segment)
    if code in OWN_SEGMENTS:
        return "own"
    if code in PLATFORM_SEGMENTS:
        return "platform"
    if code in SELL_IN_SEGMENTS:
        return "sell-in"
    if code in B2B_SEGMENTS:
        return "b2b"
    return "other"


def is_sell_out(segment: str) -> bool:
    return segment_code(segment) in SELL_OUT_SEGMENTS


def segment_code(segment: str) -> str:
    """`EBU - E-business` -> `EBU`."""
    return (segment or "").split("-", 1)[0].strip().upper()


def entity_code(entity: str) -> str:
    """`M_106_UNLOC - Far East` -> `M_106_UNLOC`.

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
        #: The consolidation entity the plan attributes this line to — `M_103`, `M_105`.
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

    def __init__(self, lines: List[BudgetLine], brands: Optional[Sequence[str]] = None
                 ) -> None:
        self.lines = lines
        #: The Maisons the workbook named, if it named any. Empty means the column was
        #: absent, which is not the same as one brand — and the difference matters enough
        #: to keep the two states apart rather than defaulting.
        self.brands = sorted(set(brands or ()))
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

    def channels(self) -> List[str]:
        return sorted({line.channel for line in self.lines if line.channel})

    def scopes(self) -> List[Tuple[str, str]]:
        """Every `(market, channel)` the plan actually carries, in reading order.

        Not the product of the two lists. A market that sells through four channels has
        four scopes and not eleven, and handing someone the full grid would invite a
        judgement on business that does not exist.
        """
        return sorted({(line.market, line.channel) for line in self.lines if line.channel})

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

    # The house sells several Maisons, and two of them trade in the same country under
    # names a reader will shorten to the same word. Nothing in this reader has ever looked
    # at a brand, so a workbook carrying two of them would be summed into one plan in
    # silence — and a plan is the denominator of every variance on this screen. Found by
    # reading a published comment about one Maison onto the other's figure.
    #
    # Not an error: a single-brand workbook is the normal case and a multi-brand one may be
    # deliberate. What is refused is not knowing, so the brands are carried out and the
    # command says what it summed.
    brand_at = None
    for position, name in enumerate(header):
        if name.strip().lower() in BRAND_COLUMNS:
            brand_at = position
            break

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
    brands_seen = set()
    for row in rows[1:]:
        def cell(position: int):
            return row[position] if position < len(row) else None

        country = cell(country_at)
        if not country:
            continue
        market = normalise_market(str(country))
        if brand_at is not None:
            named = str(cell(brand_at) or "").strip()
            if named:
                brands_seen.add(named)
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
    return Budget(lines, brands_seen)
