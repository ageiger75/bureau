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
#: What the file separates out of its own total: bulk, daigou, the café business. Read
#: and printed, never assigned to markets — whether a daigou flow belongs to Hong Kong or
#: to China is a judgement the file does not make, and this reader making it would put a
#: number under a heading nobody chose.
CLEANING_SHEET = "CLEANING"

#: Perimeters the two sources do not cut the same way, and that no rename would reconcile.
#: `(what the cockpit calls it, what the file calls it, why they will not line up)`.
#:
#: Kept as a mechanism, empty today. The one pair that lived here — the distributor
#: business under two names — turned out to be the same perimeter after all, and is folded
#: below. The mechanism stays because the question recurs: two organisations cutting one
#: business differently is the normal state, and printing such a pair side by side is
#: better than netting it or than an alias written on resemblance of size.
DIFFERENT_CUT: Tuple[Tuple[str, Tuple[str, ...], str], ...] = ()

#: Markets the consolidation splits finer than the file does, and where geography settles
#: it rather than resemblance. Shanghai is in China and Hk Local is in Hong Kong; nobody
#: has to confirm that. Anything needing a judgement stays out of this table and is
#: reported as an unmatched name instead.
ROLLUP: Dict[str, str] = {
    "Shanghai": "China",
    "Hk Local": "Hong Kong",
}

#: Lines the file names for itself that the consolidation invoices from one entity, and
#: that therefore have to be folded before the two are compared. `(file line, market)`.
#:
#: `OTHER` is a travel-retail customer large enough that Finance pulls it out on its own
#: line, and files it beside the European distributors because it is a customer rather
#: than a geography. The consolidation has no such line: the money sits inside Hong Kong's
#: travel-retail entity with the rest. Two facts agree on it — `M_007_TRA` carries 4 826k€
#: more than the file's `HK TR`, and `OTHER` is 4 826k€ — and the business reads it the
#: same way. Unfolded, it produced two findings that cancelled: a market over by 4 855 and
#: a line missing by 4 826, neither of them real.
#:
#: It folds into travel retail and not into the country. Hong Kong's invoicing address is
#: shared by three businesses — the domestic market, an export business selling to
#: distributors, and travel retail across Asia — and `OTHER` belongs to the third.
REFERENCE_ROLLUP: Dict[str, str] = {
    "Other": "Travel retail Asia",
    # The distributor business, under the name the consolidation gives it. Read as a
    # perimeter mismatch for a week and it is not one: the Export business unit covers
    # fifty-five distributor countries across Latin America, Africa, Europe, Central Asia
    # and the Middle East, and both sources carve the Middle East out of it the same way —
    # `EXPORT MIDDLE EAST` in the file, `M_098_UNLOC_REG2` in the consolidation, agreeing
    # to the euro. What is left on each side is therefore the same business, and the
    # 1 312k€ between them is a difference to explain rather than a perimeter to argue
    # about. The name kept is the one the business itself uses for the unit.
    "Loi Distributors": "Export",
}

#: The cleaning lines the warehouse's bulk flag actually covers, spelled as the file
#: spells them. Named rather than matched on the word "bulk": the file writes the mainland
#: line as plain `CHINA`, so a substring test found one of the two and reported that the
#: two sources disagreed when they agree to within 140 k€.
BULK_LINES = frozenset(("CHINA", "HK BULK"))

#: The rest of what the file separates, which no flag here can reproduce. Daigou is not
#: marked in the warehouse, the JD group is invoiced rather than sold, and the café is an
#: entity. Named so that a line matching neither list is reported instead of being
#: silently counted as one or the other.
OTHER_CLEANING = frozenset(("TOTAL DAIGOU", "TOTAL JD- GROUP", "CAFE 86"))

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

    __slots__ = ("lines", "total_actual", "total_budget", "skipped",
                 "total_ex_cleaning", "cleaning")

    def __init__(self, lines: Sequence[Line], total_actual: float = 0.0,
                 total_budget: float = 0.0, skipped: Sequence[str] = (),
                 total_ex_cleaning: float = 0.0,
                 cleaning: Sequence[Tuple[str, float]] = ()) -> None:
        self.lines = list(lines)
        #: Read from the summary sheet rather than summed from the lines: the two are
        #: produced by different pivots, and a total this reader computed itself would
        #: agree with itself while disagreeing with the file.
        self.total_actual = total_actual
        self.total_budget = total_budget
        #: Roll-up rows passed over, named so nobody wonders where a region went.
        self.skipped = list(skipped)
        #: The same quarter without the cleaning business, which the file separates for
        #: itself. Read rather than derived: the two totals sit side by side on the
        #: summary sheet, and a difference this reader computed would be a guess at which
        #: of them the cockpit's perimeter matches.
        self.total_ex_cleaning = total_ex_cleaning
        #: `(name, amount)` for what the file holds outside its clean perimeter. Shown so
        #: a market's gap can be read against it: a country short by two million with two
        #: million of bulk sitting in this list is a different finding from one short by
        #: two million with nothing here.
        self.cleaning = list(cleaning)

    def by_market(self) -> Dict[str, Line]:
        return {line.market: line for line in self.lines}


def _number(value) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def read_rows(path) -> List[Tuple[str, float, float]]:
    """The country sheet as written, before any subtotal is removed.

    For looking at the file's own hierarchy rather than at what this reader made of it.
    Whether Hong Kong sits inside the file's China grouping is a question about the
    spreadsheet, and the spreadsheet is the only place that can answer it.
    """
    with Workbook(path) as book:
        rows = list(book.rows(COUNTRY_SHEET))
    read = []
    for row in rows:
        name = str(row[0] or "").strip() if row else ""
        if not name:
            continue
        actual = _number(row[1] if len(row) > 1 else None)
        budget = _number(row[2] if len(row) > 2 else None)
        if actual is None or budget is None:
            continue
        read.append((name, actual * THOUSANDS, budget * THOUSANDS))
    return read


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
        cleaning_rows = list(book.rows(CLEANING_SHEET)) if CLEANING_SHEET in names else []

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

    total_actual, total_budget, ex_cleaning = 0.0, 0.0, 0.0
    for row in totals:
        if len(row) > 2 and str(row[0] or "").strip().upper() == "Q1":
            total_actual = (_number(row[1]) or 0.0) * MILLIONS
            total_budget = (_number(row[2]) or 0.0) * MILLIONS
            # The summary sheet repeats the quarter without cleaning, further along the
            # same row. Column seven by the file's own layout.
            ex_cleaning = (_number(row[7] if len(row) > 7 else None) or 0.0) * MILLIONS
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
    cleaning = _cleaning_lines(cleaning_rows, total_actual - ex_cleaning)
    return Reference(lines, total_actual, total_budget, skipped, ex_cleaning, cleaning)


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

        # Forward: the country sheet writes a business unit and then its countries.
        run = 0.0
        forward = False
        for ahead in range(index + 1, len(read)):
            run += read[ahead][1]
            if abs(run - actual) <= SUBTOTAL_TOLERANCE:
                forward = True
                break
        # Backward: the grey sheet does the opposite, closing each block with its own
        # total. One file, two conventions, and a reader that knows only one of them
        # counts a block twice — which is how the same six million read as ten.
        back = 0.0
        backward = False
        for behind in range(len(leaves) - 1, -1, -1):
            back += leaves[behind][1]
            if abs(back - actual) <= SUBTOTAL_TOLERANCE:
                backward = True
                break

        if forward or backward:
            skipped.append(name)
            if backward:
                # The rows it summed are its members and stay; the sum itself goes.
                pass
        else:
            leaves.append(read[index])
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


def _cleaning_lines(rows, expected: float) -> List[Tuple[str, float]]:
    """The categories outside the clean perimeter, counted once.

    The sheet cuts the same money twice — by category, then by channel — one block under
    the other with nothing between them. Read straight through, it comes to ten million
    where the file says six point seven: every euro counted twice, and a reader would have
    taken the sum for a bigger hole than exists.

    So the reading stops the moment the categories add up to what the summary sheet says
    is outside the perimeter. The second cut is the same money seen differently, and a
    second view is not more money.
    """
    read = []
    for row in rows:
        name = str(row[0] or "").strip() if row else ""
        amount = _number(row[1] if len(row) > 1 else None)
        if name and amount is not None:
            read.append((name, amount, amount))

    leaves, _skipped = _leaves(read)
    found, running = [], 0.0
    for name, amount, _budget in leaves:
        found.append((name, amount * THOUSANDS))
        running += amount * THOUSANDS
        if expected and abs(running - expected) <= SUBTOTAL_TOLERANCE * THOUSANDS:
            break
    return found


def rolled_up(ours: Dict[str, float]) -> Dict[str, float]:
    """The cockpit's markets, folded into the names the file uses where geography says so.

    Applied before comparing, because the alternative is a table where China is short by
    fifteen million and Shanghai appears eight million out of nowhere — two findings, one
    of them false, about one country.
    """
    folded: Dict[str, float] = {}
    for market, amount in ours.items():
        name = ROLLUP.get(market, market)
        folded[name] = folded.get(name, 0.0) + amount
    return folded


#: What an offsetting pair means, which is not the same thing in both directions.
MISSING_HERE = "missing"
FILED_ELSEWHERE = "filed"


def offsetting(orphans: Sequence[Tuple[str, float]],
               rows: Sequence[Tuple[str, float, float]],
               tolerance: float = 0.02) -> List[Tuple[str, str, float, str]]:
    """`(orphan, market, amount, kind)` where an unmatched name and a market's difference
    are the same money.

    Two directions, and they are different findings. A market **short** by the orphan's
    amount means the cockpit does not read that money at all under any name — Luxembourg
    at 177 k€ against a Belgium short by 177. A market **over** by it means the cockpit
    does read it and files it under the neighbour: the file's `Other` is 4 826 k€ and
    Hong Kong is over by 4 855, because Hong Kong's travel-retail entity carries both and
    the file splits them.

    Looking only for shortfalls found the first kind and missed the second, which was the
    one that mattered — an anomaly on each side of the table, cancelling to the euro, read
    as two problems for a week.
    """
    found = []
    for name, amount in orphans:
        if not amount:
            continue
        for market, ref_amount, our_amount in rows:
            if market == name or not ref_amount:
                continue
            difference = ref_amount - our_amount
            if difference > 0 and abs(difference - amount) <= tolerance * amount:
                found.append((name, market, amount, MISSING_HERE))
                break
            if difference < 0 and abs(-difference - amount) <= tolerance * amount:
                found.append((name, market, amount, FILED_ELSEWHERE))
                break
    return found


def compare(reference: Reference, ours: Dict[str, float]) -> List[Tuple[str, float, float]]:
    """`(market, theirs, ours)` per market, largest absolute difference first.

    A market the reference names and the cockpit does not returns `ours = 0.0` rather than
    being dropped: a market missing from our side is the finding, and skipping it would
    hide exactly the fault this comparison exists to catch.

    And the same in the other direction, which is the half this was missing. Iterating the
    reference alone made a market the cockpit reads under a name the file does not use
    disappear from the table while still sitting in the cockpit's total — so the file
    showed a hole of fifteen million, the total showed a hole of fourteen, and nothing
    on the screen connected the two. Eighteen million were being compared to nothing.
    """
    #: Folded first, so a line the file separates and the consolidation does not is never
    #: compared against a market that does not exist on our side.
    theirs: Dict[str, float] = {}
    for line in reference.lines:
        name = REFERENCE_ROLLUP.get(line.market, line.market)
        theirs[name] = theirs.get(name, 0.0) + line.actual
    named = set(theirs)
    found = [(market, amount, ours.get(market, 0.0))
             for market, amount in theirs.items()]
    found.extend(
        (market, 0.0, amount)
        for market, amount in ours.items()
        if market not in named and amount
    )
    return sorted(found, key=lambda item: -abs(item[1] - item[2]))
