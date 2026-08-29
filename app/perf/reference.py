"""The quarter's closed actuals, read from Finance's own reforecast file.

A cockpit that cannot be checked against the figures the Maison actually reports is a
cockpit nobody has to believe. This reads one thing out of the reforecast workbook — the
quarter that has closed — and hands it back so the screen's own total can be set beside
it, market by market.

Two rules, and both matter more than the comparison itself:

1. **Only the closed quarter is read.** The later columns of a reforecast are a new
   opinion about the rest of the year, and the plan on this screen is the budget. Reading
   them would silently replace the commitment with a revision of it — and the whole point
   of measuring against a plan is that the plan does not move when the year gets hard.
2. **The rates are not the same.** The reforecast is stated at budget rates; the warehouse
   reports what was invoiced. Every line will differ by whatever the currency did, and a
   comparison that does not say so reads a foreign-exchange move as a data fault.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .budget import normalise_market
from .xlsx import Workbook, WorkbookError

#: The sheet holding one row per country with the closed quarter beside its budget.
COUNTRY_SHEET = "BY QUARTER BY COUNTRY"
TOTAL_SHEET = "OVERALL BY QUARTER"

#: How close a roll-up has to be to the rows under it to count as their sum. A cent on
#: figures in the hundreds of millions: this is spotting a subtotal, not tolerating a
#: discrepancy.
SUBTOTAL_TOLERANCE = 0.01

#: The file states thousands of euros per country and millions on the summary sheet.
THOUSANDS = 1_000.0
MILLIONS = 1_000_000.0


class Line:
    """One market's closed quarter, as Finance reports it."""

    __slots__ = ("market", "actual", "budget")

    def __init__(self, market: str, actual: float, budget: float) -> None:
        self.market = market
        self.actual = actual
        self.budget = budget

    @property
    def gap(self) -> float:
        return self.actual - self.budget


class Reference:
    """The closed quarter, by market and in total."""

    __slots__ = ("lines", "total_actual", "total_budget", "skipped")

    def __init__(self, lines: Sequence[Line], total_actual: float = 0.0,
                 total_budget: float = 0.0, skipped: Sequence[str] = ()) -> None:
        self.lines = list(lines)
        #: Read from the summary sheet rather than summed from the lines: the two are
        #: produced by different pivots, and a total this reader computed itself would
        #: agree with itself while disagreeing with the file.
        self.total_actual = total_actual
        self.total_budget = total_budget
        #: Roll-up rows passed over, named so nobody wonders where a region went.
        self.skipped = list(skipped)

    def by_market(self) -> Dict[str, Line]:
        return {line.market: line for line in self.lines}


def _number(value) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def read_reference(path) -> Reference:
    """Read the closed quarter out of a reforecast workbook."""
    with Workbook(path) as book:
        names = book.sheet_names
        if COUNTRY_SHEET not in names:
            raise WorkbookError(
                "No '%s' sheet in this workbook. Sheets present: %s"
                % (COUNTRY_SHEET, ", ".join(names))
            )
        rows = list(book.rows(COUNTRY_SHEET))
        totals = list(book.rows(TOTAL_SHEET)) if TOTAL_SHEET in names else []

    read = []
    for row in rows:
        name = str(row[0] or "").strip() if row else ""
        if not name:
            continue
        actual = _number(row[1] if len(row) > 1 else None)
        budget = _number(row[2] if len(row) > 2 else None)
        if actual is None or budget is None:
            continue
        read.append((name, actual, budget))

    leaves, skipped = _leaves(read)
    # Summed per market after normalising, not one line per source row. The file writes
    # China twice — the mainland and cross-border — and Hong Kong three times, and every
    # one of them normalises to the same market the cockpit knows. Compared row by row,
    # each fragment was set against the market's whole figure, so one market produced
    # three findings and none of them was true.
    per_market: Dict[str, Tuple[float, float]] = {}
    for name, actual, budget in leaves:
        market = normalise_market(name)
        had = per_market.get(market, (0.0, 0.0))
        per_market[market] = (had[0] + actual * THOUSANDS, had[1] + budget * THOUSANDS)
    lines = [
        Line(market, values[0], values[1])
        for market, values in sorted(per_market.items())
    ]

    total_actual, total_budget = 0.0, 0.0
    for row in totals:
        if len(row) > 2 and str(row[0] or "").strip().upper() == "Q1":
            total_actual = (_number(row[1]) or 0.0) * MILLIONS
            total_budget = (_number(row[2]) or 0.0) * MILLIONS
            break

    # Checked against the figure the file states for itself, on a different sheet built by
    # a different pivot. A reader that agrees only with its own sum agrees with nothing —
    # and this one has already been wrong twice, once counting a region alongside the
    # countries inside it and once counting the grand total as a country.
    summed = sum(line.actual for line in lines)
    if total_actual and abs(summed - total_actual) > MILLIONS * 0.01:
        raise WorkbookError(
            "The markets read add up to %.3f M€ and the file states %.3f M€ for the same "
            "quarter. Something is being counted twice or not at all; refusing to compare "
            "against a total this reader cannot reproduce."
            % (summed / MILLIONS, total_actual / MILLIONS)
        )
    return Reference(lines, total_actual, total_budget, skipped)


def _leaves(read: Sequence[Tuple[str, float, float]]):
    """Split a hierarchical column into the rows that are figures and those that are sums.

    The sheet writes a business unit and then the countries inside it, in one column, with
    no marker saying which is which — and a country that happens to be its own unit is
    written twice, identically. Adding a region to the markets it contains double-counts
    the file; a name list would work until Finance renames one.

    So a row is a subtotal when the rows that follow it add up to it. Arithmetic rather
    than vocabulary, and it is checked afterwards against the total the file states for
    itself: a reader that agrees only with its own sum agrees with nothing.
    """
    leaves, skipped, index = [], [], 0
    while index < len(read):
        name, actual, _budget = read[index]
        run = 0.0
        for ahead in range(index + 1, len(read)):
            run += read[ahead][1]
            if abs(run - actual) <= SUBTOTAL_TOLERANCE:
                skipped.append(name)
                break
        else:
            leaves.append(read[index])
            index += 1
            continue
        index += 1

    # The grand total closes the column and has nothing after it to sum against, so the
    # pass above keeps it as a figure — and the file then reads as exactly twice itself.
    # It is spotted the other way round: the one row equal to the sum of all the others.
    whole = sum(item[1] for item in leaves)
    for position, item in enumerate(leaves):
        if abs(item[1] * 2 - whole) <= SUBTOTAL_TOLERANCE:
            skipped.append(item[0])
            leaves.pop(position)
            break
    return leaves, skipped


def compare(reference: Reference, ours: Dict[str, float]) -> List[Tuple[str, float, float]]:
    """`(market, theirs, ours)` per market, largest absolute difference first.

    A market the reference names and the cockpit does not returns `ours = 0.0` rather than
    being dropped: a market missing from our side is the finding, and skipping it would
    hide exactly the fault this comparison exists to catch.
    """
    found = [
        (line.market, line.actual, ours.get(line.market, 0.0))
        for line in reference.lines
    ]
    return sorted(found, key=lambda item: -abs(item[1] - item[2]))
