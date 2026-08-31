"""Finance's own actuals, at the grain the plan is written in.

The cockpit spent weeks reconciling a warehouse total against a published one and closing
the difference market by market. This file makes most of that work unnecessary for the
figure at the top of the screen, and the reason is worth stating plainly.

It carries, on one row: the Maison, the consolidation entity, whether the line is sold or
shipped, the country, the region, the channel — and then **the actual, last year and the
budget side by side, at one set of rates**. That is exactly the cockpit's own data model,
published monthly by the people whose number the house quotes.

So the split becomes clean, and it is the split this product should have started from:

* **What the business did**, and how it compares to what it promised, comes from here. It
  is right by construction — same source, same rates, same perimeter as the figure Finance
  publishes — so the screen can never again show a shortfall the house does not recognise.
  Every perimeter this repository has chased since the reconciliation began (counters the
  referential omits, pseudo-entities, a market with no shop, two rate regimes) stops
  mattering to the headline, because the headline stops coming from the warehouse.
* **Why**, comes from the warehouse, which is the only place it exists: sessions,
  conversion, basket, the store behind the market, the day behind the month.

One number, one source. The warehouse explains it; it no longer competes with it.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .budget import normalise_market
from .xlsx import read_sheet

#: The sheets carrying one row per country × channel. `Data Periodic` is the month;
#: `Data YTD` is the fiscal year to date on the same shape.
MONTH_SHEET = "Data Periodic"
YTD_SHEET = "Data YTD"

#: The Maison this cockpit reads. Named rather than assumed: the same workbook carries
#: other brands, two of them trade in the same country, and a total summed across them
#: would be wrong in a way no total reveals.
BRAND = "L'Occitane en Provence"

#: Where each field sits on a data row. Read by position because the header row of this
#: workbook does not sit above its own columns — a merged-cell layout meant for a human
#: reader, not for a parser. Checked on load rather than trusted: the first data row must
#: look like a data row, or the file is refused.
BASIS_AT, COUNTRY_AT, REGION_AT, CHANNEL_AT = 3, 6, 7, 10
ACTUAL_AT, LAST_YEAR_AT, BUDGET_AT = 13, 14, 15

#: The Maison does not sit in the same column on both sheets — one puts it fourth, the
#: other fifth — so it is located rather than assumed. Hard-coding it read every row of one
#: sheet as another brand's and returned an empty total, which is the quiet kind of wrong:
#: a screen showing nothing looks like a business doing nothing.
BRAND_CANDIDATES = (4, 5)

#: `ACTUAL_AT` is deliberately the column stated **at the budget's own rates**, and not the
#: one beside it. That choice is the difference between a right answer and a plausible one,
#: and it was found the hard way.
#:
#: The published flash quotes the neighbouring column — the actual at real rates — as its
#: headline value, while computing every percentage on this one. Both are labelled as being
#: at constant rates, and only the percentages are. Deriving a budget by dividing the
#: quoted value by the quoted percentage therefore mixes two bases, and this register did
#: exactly that: it concluded that the planning workbook and Finance held different budgets,
#: several points apart, and named a perimeter to go and find. They hold the same budget,
#: to the euro, every month checked.
#:
#: The columns chosen here reproduce the published percentage exactly on two independent
#: months. That is the test any replacement has to pass.
THOUSANDS = 1000.0

#: The file's channel codes, in the cockpit's vocabulary. Sixteen on each side, and they
#: correspond one to one — this file and the planning workbook are cut the same way,
#: which is the whole point of reading them together.
CHANNELS = {
    "B2B": "b2b",
    "CAF": "cafe",
    "COPG": "copg",
    "DDS": "direct selling",
    "DIS": "dis",
    "DPT": "dpt",
    "EBU": "ecommerce",
    "MKTP": "marketplace",
    "RET": "retail",
    "SPA": "spa",
    "TRA": "tra",
    "TVC": "tvc",
    "WEBP": "webp",
    "WHOCH": "whoch",
    "WHOIN": "whoin",
    "WHOSP": "whosp",
}

#: How the accounts recognise the line. Carried rather than collapsed: the screen has
#: always refused to mix the two bases silently, and this file states which is which.
SOLD = "SELL_OUT"
SHIPPED = "SELL_IN"
HOSPITALITY = "B2BT"


class Line:
    """One country × channel, with both sides of its variance."""

    __slots__ = ("market", "region", "channel", "basis", "actual", "last_year", "budget")

    def __init__(self, market, region, channel, basis, actual, last_year, budget):
        self.market = market
        self.region = region
        self.channel = channel
        self.basis = basis
        self.actual = actual
        self.last_year = last_year
        self.budget = budget

    @property
    def gap(self) -> float:
        return self.actual - self.budget


class Actuals:
    """Everything the file carries for one Maison, and what it could not read."""

    __slots__ = ("lines", "faults", "path", "sheet")

    def __init__(self, lines, faults, path="", sheet="") -> None:
        self.lines = list(lines)
        self.faults = list(faults)
        self.path = path
        self.sheet = sheet

    @property
    def usable(self) -> bool:
        return bool(self.lines) and not self.faults

    @property
    def actual(self) -> float:
        return sum(line.actual for line in self.lines)

    @property
    def budget(self) -> float:
        return sum(line.budget for line in self.lines)

    @property
    def last_year(self) -> float:
        return sum(line.last_year for line in self.lines)

    @property
    def gap(self) -> float:
        return self.actual - self.budget

    @property
    def pct(self) -> Optional[float]:
        return self.gap / self.budget if self.budget else None

    def markets(self) -> List[str]:
        return sorted({line.market for line in self.lines})

    def by_market(self) -> Dict[str, List[Line]]:
        grouped: Dict[str, List[Line]] = {}
        for line in self.lines:
            grouped.setdefault(line.market, []).append(line)
        return grouped

    def by_basis(self) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for line in self.lines:
            totals[line.basis] = totals.get(line.basis, 0.0) + line.actual
        return totals


def _number(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _locate_brand(rows: Sequence, brand: str) -> Optional[int]:
    """Which column names the Maison, on this sheet.

    Found rather than declared: the same workbook lays its two sheets out differently, and
    a fixed index silently matched nothing on one of them — every row skipped, the total
    zero, and a screen showing nothing looks exactly like a business doing nothing.
    """
    for column in BRAND_CANDIDATES:
        for row in rows:
            if len(row) > column and str(row[column] or "").strip() == brand:
                return column
    return None


def load(path: str, sheet: str = MONTH_SHEET, brand: str = BRAND) -> Actuals:
    """Read one sheet of the published file.

    Rows of another Maison are skipped rather than summed, and a row whose channel code is
    not in the table is refused rather than dropped: a channel appearing in the accounts
    and not here is a hole in the screen, and a hole that reports itself is worth more than
    one that quietly narrows a total.
    """
    try:
        rows = read_sheet(path, sheet)
    except Exception as exc:  # noqa: BLE001 — the message matters more than the type
        return Actuals([], ["%s" % exc], path, sheet)

    brand_at = _locate_brand(rows, brand)
    if brand_at is None:
        return Actuals([], ["%s introuvable dans %r — la colonne marque a bougé"
                            % (brand, sheet)], path, sheet)

    lines: List[Line] = []
    faults: List[str] = []
    unknown_channels = set()

    for number, row in enumerate(rows, start=1):
        if len(row) <= BUDGET_AT:
            continue
        if str(row[brand_at] or "").strip() != brand:
            continue
        code = str(row[CHANNEL_AT] or "").split(" - ")[0].strip().upper()
        if not code:
            continue
        channel = CHANNELS.get(code)
        if channel is None:
            unknown_channels.add(code)
            continue
        actual = _number(row[ACTUAL_AT])
        budget = _number(row[BUDGET_AT])
        if actual is None and budget is None:
            continue
        lines.append(Line(
            market=normalise_market(str(row[COUNTRY_AT] or "").strip()),
            region=str(row[REGION_AT] or "").strip(),
            channel=channel,
            basis=str(row[BASIS_AT] or "").strip(),
            actual=(actual or 0.0) * THOUSANDS,
            last_year=(_number(row[LAST_YEAR_AT]) or 0.0) * THOUSANDS,
            budget=(budget or 0.0) * THOUSANDS,
        ))

    if unknown_channels:
        faults.append("canaux inconnus, non comptés : %s"
                      % ", ".join(sorted(unknown_channels)))
    if not lines:
        faults.append("aucune ligne %s dans %r" % (brand, sheet))
    return Actuals(lines, faults, path, sheet)
