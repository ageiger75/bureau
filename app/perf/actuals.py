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
from .xlsx import Workbook, read_sheet

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

#: Three layouts of the same rows, and the reader has to know all three because Finance
#: changed the export twice in one year without changing what it says. The first is the
#: original flash: merged headers, columns read by position. The second is the closing
#: file from August 2026 on — one sheet per month, `DATA AUGUST`, with a real header row.
#: The third is the CFO's own extract from the consolidation tool, `Sales Data Set MTD`,
#: which carries the same rows at published and constant rates side by side, and a sheet
#: by store beneath it. Which one a workbook is, is read from its sheets, never assumed.
LAYOUT_LEGACY = "positions"
LAYOUT_NAMED = "named columns"
LAYOUT_DATASET = "consolidation data set"

DATASET_MONTH_SHEET = "Sales Data Set MTD"
DATASET_YTD_SHEET = "Sales Data Set YTD"

#: The fiscal year opens in April. Needed here to rank the month sheets of one file.
FISCAL_OPENS = 4

MONTH_NAMES = ("JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
               "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER")

#: Le mois tel que l'écran le nomme. Les noms de feuilles ci-dessus restent ceux du fichier.
MONTH_LABELS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                "septembre", "octobre", "novembre", "décembre")

#: The channel as the newer layouts write it, to the code the older one used. The plan's
#: sixteen codes are the pivot; a name missing here is refused, not guessed.
CHANNEL_LABELS = {
    "retail": "RET",
    "e-business": "EBU",
    "market place": "MKTP",
    "web partners": "WEBP",
    "wholesale chains": "WHOCH",
    "wholesale independant accounts": "WHOIN",
    "wholesale independent accounts": "WHOIN",
    "wholesale spa": "WHOSP",
    "department stores": "DPT",
    "distributors": "DIS",
    "travel retail": "TRA",
    "tv channels": "TVC",
    "b2b": "B2B",
    "corporate gifts": "COPG",
    "cafe": "CAF",
    "café": "CAF",
    "spa": "SPA",
    "direct selling": "DDS",
    "digital direct selling": "DDS",
}

#: How the newer layouts name the basis, to the codes the older one carried.
BASIS_LABELS = {
    "sell in": SHIPPED,
    "sell out": SOLD,
    "total b2b": HOSPITALITY,
}

#: Market spellings the newer layouts use, to the plan's own. Aligned through the
#: consolidation entity, which is the one key all three files share, and kept explicit:
#: a market spelt three ways is three markets to a join, and two of them carry no plan.
FILE_MARKETS = {
    "CZEK REPUBLIC": "CZECH REPUBLIC",
    "NETHERLAND": "NETHERLANDS",
    "86 CHAMPS": "86CR",
    "MIDDLE EAST": "EXPORT MIDDLE EAST",
    "JAPAN MANAGEMENT UNIT": "JAPAN",
    "BRAZIL BUSINESS": "BRAZIL",
    "HONG KONG LOCAL": "HK",
    "HONG KONG DISTRIBUTORS": "HK DISTRIBUTORS",
    "TRAVEL RETAIL HONG KONG BUSINESS": "HK TR",
    "TRAVEL RETAIL LOI BUSINESS": "LOI TR",
    "EXPORT EUROPE": "LOI DISTRIBUTORS",
}


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

    __slots__ = ("lines", "faults", "path", "sheet", "year", "month")

    def __init__(self, lines, faults, path="", sheet="", year=None, month=None) -> None:
        self.lines = list(lines)
        self.faults = list(faults)
        self.path = path
        self.sheet = sheet
        #: The month this reading speaks for, when the file says. A screen once showed
        #: June's figures under an August heading because nothing checked: the amounts
        #: came from the file, the heading from the warehouse, and the file was old.
        self.year = year
        self.month = month

    @property
    def period(self) -> str:
        """`2026-08`, or empty when the file does not say which year — or which month."""
        if self.year and self.month:
            return "%04d-%02d" % (self.year, self.month)
        return ""

    @property
    def month_label(self) -> str:
        return MONTH_LABELS[self.month - 1] if self.month else ""

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

    def totals(self, bases: Sequence[str] = ()) -> "Dict[str, float]":
        """Actual, budget and last year over the bases named — all of them when none is.

        The whole point of this file is that its three columns describe one perimeter at
        one set of rates. Summing them here rather than assembling a total from somewhere
        else is not a convenience: any total built by intersecting this file with another
        source reintroduces exactly the perimeter difference the file was adopted to
        remove, and does it invisibly.
        """
        wanted = set(bases) or None
        actual = budget = last_year = 0.0
        counted = 0
        for line in self.lines:
            if wanted is not None and line.basis not in wanted:
                continue
            actual += line.actual
            budget += line.budget
            last_year += line.last_year
            counted += 1
        return {"actual": actual, "budget": budget, "last_year": last_year,
                "lines": float(counted)}

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


def _market(raw: str) -> str:
    """A market as the plan spells it, whatever this file's layout called it."""
    upper = " ".join(str(raw or "").split()).upper()
    return normalise_market(FILE_MARKETS.get(upper, upper))


def _sheet_for(names: Sequence[str], month: bool):
    """Which sheet carries the rows asked for, and in which layout. Empty when none does."""
    wanted = MONTH_SHEET if month else YTD_SHEET
    if wanted in names:
        return wanted, LAYOUT_LEGACY
    # The closing file keeps every month of the year side by side — `DATA APRIL`, `DATA
    # MAY`, … — and speaks for the latest one. Fiscal order, so August outranks April and
    # March outranks both.
    dated = []
    for name in names:
        upper = " ".join(name.split()).upper()
        if not upper.startswith("DATA "):
            continue
        is_ytd = upper.startswith("DATA YTD ")
        rest = (upper[len("DATA YTD "):] if is_ytd else upper[len("DATA "):]).strip()
        if rest in MONTH_NAMES and is_ytd is not month:
            calendar = MONTH_NAMES.index(rest) + 1
            fiscal = calendar - 3 if calendar >= FISCAL_OPENS else calendar + 9
            dated.append((fiscal, name))
    if dated:
        return max(dated)[1], LAYOUT_NAMED
    wanted = DATASET_MONTH_SHEET if month else DATASET_YTD_SHEET
    for name in names:
        if " ".join(name.split()).lower() == wanted.lower():
            return name, LAYOUT_DATASET
    return "", ""


def _header_row(rows: Sequence, *needed: str):
    """The first row carrying every name asked for, and where each sits."""
    for index, row in enumerate(rows):
        cells = {" ".join(str(cell).split()): at for at, cell in enumerate(row)
                 if isinstance(cell, str)}
        if all(name in cells for name in needed):
            return index, cells
    return None, {}


def _lines_legacy(rows: Sequence, brand: str):
    """The original flash: merged headers, columns known by position."""
    brand_at = _locate_brand(rows, brand)
    if brand_at is None:
        return [], ["%s introuvable — la colonne marque a bougé" % brand]
    lines: List[Line] = []
    unknown_channels = set()
    for row in rows:
        if len(row) <= BUDGET_AT:
            row = list(row) + [None] * (BUDGET_AT + 1 - len(row))
        if len(row) <= brand_at or str(row[brand_at] or "").strip() != brand:
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
        last_year = _number(row[LAST_YEAR_AT])
        # A row carrying only last year is a business that stopped — real to the
        # comparison against last year, and dropped for months before anyone noticed.
        if actual is None and budget is None and last_year is None:
            continue
        lines.append(Line(
            market=normalise_market(str(row[COUNTRY_AT] or "").strip()),
            region=str(row[REGION_AT] or "").strip(),
            channel=channel,
            basis=str(row[BASIS_AT] or "").strip(),
            actual=(actual or 0.0) * THOUSANDS,
            last_year=(last_year or 0.0) * THOUSANDS,
            budget=(budget or 0.0) * THOUSANDS,
        ))
    faults = []
    if unknown_channels:
        faults.append("canaux inconnus, non comptés : %s"
                      % ", ".join(sorted(unknown_channels)))
    return lines, faults


def _lines_from(rows: Sequence, brand: str, at: Dict[str, int], start: int,
                keys: Dict[str, str]):
    """Rows of the newer layouts, whose columns are known by name.

    `keys` says which header carries what: brand, region, market, basis, channel, actual,
    last_year, budget. Channel and basis arrive as labels and go through the two tables
    above; a label neither knows is refused and named.
    """
    lines: List[Line] = []
    unknown_channels = set()
    unknown_bases = set()
    width = max(at.values()) + 1
    for row in rows[start:]:
        if len(row) < width:
            # A trailing empty cell is not written at all; the row is short, not absent.
            row = list(row) + [None] * (width - len(row))
        if str(row[at[keys["brand"]]] or "").strip() != brand:
            continue
        label = " ".join(str(row[at[keys["channel"]]] or "").split()).lower()
        if not label:
            continue
        code = CHANNEL_LABELS.get(label)
        channel = CHANNELS.get(code or "")
        if channel is None:
            unknown_channels.add(label)
            continue
        actual = _number(row[at[keys["actual"]]])
        budget = _number(row[at[keys["budget"]]])
        last_year = _number(row[at[keys["last_year"]]])
        if actual is None and budget is None and last_year is None:
            continue
        basis_label = " ".join(str(row[at[keys["basis"]]] or "").split()).lower()
        basis = BASIS_LABELS.get(basis_label)
        if basis is None:
            unknown_bases.add(basis_label or "(vide)")
            basis = basis_label.upper()
        lines.append(Line(
            market=_market(row[at[keys["market"]]]),
            region=str(row[at[keys["region"]]] or "").strip(),
            channel=channel,
            basis=basis,
            actual=(actual or 0.0) * THOUSANDS,
            last_year=(last_year or 0.0) * THOUSANDS,
            budget=(budget or 0.0) * THOUSANDS,
        ))
    faults = []
    if unknown_channels:
        faults.append("canaux inconnus, non comptés : %s"
                      % ", ".join(sorted(unknown_channels)))
    if unknown_bases:
        faults.append("bases inconnues, gardées telles quelles : %s"
                      % ", ".join(sorted(unknown_bases)))
    return lines, faults


def _lines_named(rows: Sequence, brand: str):
    """The closing file from August 2026 on: one header row, columns by name."""
    index, at = _header_row(rows, "Brand", "Country", "Channel", "ACTUAL N", "BUDGET N")
    if index is None:
        return [], ["en-tête introuvable : Brand, Country, Channel, ACTUAL N, BUDGET N"]
    keys = {"brand": "Brand", "region": "Region", "market": "Country",
            "basis": "PCC - Parent", "channel": "Channel", "actual": "ACTUAL N",
            "last_year": "ACTUAL N-1", "budget": "BUDGET N"}
    missing = [name for name in keys.values() if name not in at]
    if missing:
        return [], ["colonnes manquantes : %s" % ", ".join(missing)]
    return _lines_from(rows, brand, at, index + 1, keys)


def _measures(rows: Sequence, index: int, at: Dict[str, int]):
    """Which of the data set's `Sales` columns are the three the cockpit reads.

    The extract lays its measures out under two header lines above the column names: the
    rate (published or constant) and the scenario (`Actual 2027`, `Budget 2027`). The
    actual and last year are taken **at constant rate** — the same choice the positional
    layout makes, for the same reason: it is the basis every published percentage rests
    on. The budget has one rate only.
    """
    if index < 2:
        return {}, "les lignes de taux et de scénario manquent au-dessus de l'en-tête"
    rates = list(rows[index - 2])
    scenarios = rows[index - 1]
    header = rows[index]
    # The rate is written once over the columns it covers — a merged cell — so it is
    # carried forward until the next one is written.
    carried = ""
    for position in range(len(header)):
        if position < len(rates) and rates[position] not in (None, ""):
            carried = " ".join(str(rates[position]).split()).lower()
        rates[position:position + 1] = [carried] if position < len(rates) else []
        if position >= len(rates):
            rates.append(carried)
    found: Dict[str, int] = {}
    actual_years: Dict[int, int] = {}
    for position, cell in enumerate(header):
        if " ".join(str(cell or "").split()).lower() != "sales":
            continue
        rate = rates[position]
        scenario = " ".join(str(scenarios[position] if position < len(scenarios) else "")
                            .split()).lower()
        if scenario.startswith("budget") and "budget" not in found:
            found["budget"] = position
        if scenario.startswith("actual") and rate == "constant rate":
            try:
                year = int(scenario.split()[-1])
            except ValueError:
                continue
            actual_years[year] = position
    if len(actual_years) < 2 or "budget" not in found:
        return {}, ("colonnes de mesure introuvables : il faut Actual à taux constant sur "
                    "deux exercices et un Budget")
    years = sorted(actual_years)
    found["actual"] = actual_years[years[-1]]
    found["last_year"] = actual_years[years[-2]]
    return found, ""


def _lines_dataset(rows: Sequence, brand: str):
    """The CFO's extract: the same rows, at two rates, columns by name."""
    index, at = _header_row(rows, "Brand", "Entities", "PCC - Parent", "PCC - Lowest")
    if index is None:
        return [], ["en-tête introuvable : Brand, Entities, PCC - Parent, PCC - Lowest"]
    measures, why = _measures(rows, index, at)
    if why:
        return [], [why]
    keys = {"brand": "Brand", "region": "Management Unit - Parent",
            "market": "Management Unit - Lowest", "basis": "PCC - Parent",
            "channel": "PCC - Lowest", "actual": "actual", "last_year": "last_year",
            "budget": "budget"}
    missing = [name for name in ("Management Unit - Parent", "Management Unit - Lowest")
               if name not in at]
    if missing:
        return [], ["colonnes manquantes : %s" % ", ".join(missing)]
    at = dict(at)
    at.update(measures)
    return _lines_from(rows, brand, at, index + 1, keys)


def _dataset_period(rows: Sequence):
    """The month the CFO's extract declares: `Period 05 - August`, `Scenario FY27_ACT`."""
    month = year = None
    for row in rows[:12]:
        cells = [" ".join(str(cell).split()) for cell in row if cell not in (None, "")]
        for index, cell in enumerate(cells[:-1]):
            if cell.lower() == "period":
                name = cells[index + 1].split("-")[-1].strip().upper()
                if name in MONTH_NAMES:
                    month = MONTH_NAMES.index(name) + 1
            if cell.lower() == "scenario":
                text = cells[index + 1].upper()
                if text.startswith("FY") and text[2:4].isdigit():
                    year = 2000 + int(text[2:4])
    if month and year:
        # FY27 opens in April 2026: a month from April on belongs to the calendar year
        # before the fiscal label, the rest to the same year.
        year = year - 1 if month >= FISCAL_OPENS else year
    return year, month


def _period_for(path: str, found: str, layout: str, rows: Sequence):
    """(year, month) the sheet speaks for, from wherever the workbook writes it."""
    named = period_of(path)
    if layout == LAYOUT_DATASET:
        year, month = _dataset_period(rows)
        if month:
            return year or (named.year if named and named.month == month else None), month
    if layout == LAYOUT_NAMED:
        upper = " ".join(found.split()).upper()
        rest = upper[len("DATA YTD "):] if upper.startswith("DATA YTD ") else upper[len("DATA "):]
        if rest.strip() in MONTH_NAMES:
            month = MONTH_NAMES.index(rest.strip()) + 1
            if named and named.month == month:
                return named.year, month
            # The sheet names its month and nothing in the workbook names the year. A
            # closing file is published within weeks of its month, so the month is the
            # most recent one of that name already behind us.
            import datetime

            today = datetime.date.today()
            return (today.year if month < today.month else today.year - 1), month
    if named is not None:
        return named.year, named.month
    return None, None


def load(path: str, sheet: str = MONTH_SHEET, brand: str = BRAND) -> Actuals:
    """Read one sheet of the published file, in whichever layout the workbook uses.

    `sheet` names the rows wanted — the month, or the year to date — in the original
    layout's words; a workbook laid out differently is read from the sheet that carries
    the same rows there. Rows of another Maison are skipped rather than summed, and a row
    whose channel is not in the table is refused rather than dropped: a channel appearing
    in the accounts and not here is a hole in the screen, and a hole that reports itself is
    worth more than one that quietly narrows a total.
    """
    try:
        with Workbook(path) as book:
            names = book.sheet_names
    except Exception as exc:  # noqa: BLE001 — the message matters more than the type
        return Actuals([], ["%s" % exc], path, sheet)

    month = sheet != YTD_SHEET
    if sheet in names:
        found, layout = sheet, LAYOUT_LEGACY
    else:
        found, layout = _sheet_for(names, month)
    if not found:
        return Actuals([], ["aucune feuille %s reconnue — feuilles : %s"
                            % ("du mois" if month else "de l'exercice à date",
                               ", ".join(names))], path, sheet)
    try:
        rows = read_sheet(path, found)
    except Exception as exc:  # noqa: BLE001
        return Actuals([], ["%s" % exc], path, found)

    if layout == LAYOUT_LEGACY:
        lines, faults = _lines_legacy(rows, brand)
    elif layout == LAYOUT_NAMED:
        lines, faults = _lines_named(rows, brand)
    else:
        lines, faults = _lines_dataset(rows, brand)
    if not lines:
        faults.append("aucune ligne %s dans %r" % (brand, found))
    year, month = _period_for(path, found, layout, rows)
    return Actuals(lines, faults, path, found, year=year, month=month)


def by_scope(read: "Actuals") -> Dict[str, "Line"]:
    """`market/channel` → the published line, folded where a market splits a channel.

    The file can carry several rows for one market and channel — different entities, or
    the same channel on two bases — and the plan carries one. They are summed rather than
    picked between: a screen that silently chose a row would show part of a business under
    a heading naming all of it.
    """
    folded: Dict[str, Line] = {}
    for line in read.lines:
        key = "%s/%s" % (line.market, line.channel)
        held = folded.get(key)
        if held is None:
            folded[key] = Line(line.market, line.region, line.channel, line.basis,
                               line.actual, line.last_year, line.budget)
            continue
        held.actual += line.actual
        held.last_year += line.last_year
        held.budget += line.budget
        if held.basis != line.basis:
            # Two bases under one heading is a fact about the business, not a fault: a
            # market may sell a channel and ship it. Named so nothing reads it as one.
            held.basis = "MIXED"
    return folded


def current(month: bool = True) -> "Actuals":
    """The published file as it sits on disk right now, or an empty reading.

    Absent, the screen falls back to the warehouse exactly as before — degraded, never
    wrong. The one thing it must not do is show a variance from one source under a label
    naming the other.
    """
    from ..config import settings

    path = str(settings.actuals_path)
    return load(path, MONTH_SHEET if month else YTD_SHEET)


# --- Twelve months of it -------------------------------------------------------------
#
# One file answers "where are we against the plan". A folder of them answers two questions
# no single file can, and both are worth more to the data teams than to the screen.
#
# The first is whether this reader reads the file correctly, and it is self-checking:
# inside a fiscal year, the year-to-date sheet of one month less the year-to-date sheet of
# the month before must equal the periodic sheet of that month, to the euro. Twelve files
# give eleven independent checks that cost nothing and need nobody's confirmation.
#
# The second is restatement, and it is the reason to keep the whole series rather than the
# latest file. When those two disagree, a month has been changed after it was published —
# a provision trued up, a reclassification applied backwards, an entity moved. That is
# precisely the class of difference that no rule derived from the warehouse can anticipate,
# because it is decided rather than computed. Measured here, it stops being a mystery and
# becomes a list with dates on it.

import os
import re

#: The published files name their month at the end of the stem: `... 2025 11_RFx.xlsx`.
#: Read rather than assumed, and the last match wins — a folder name or a version suffix
#: can carry digits too, and a file filed under the wrong month is worse than one skipped.
PERIOD_IN_NAME = re.compile(r"(20\d\d)[ _\-.]?(0[1-9]|1[0-2])(?!\d)")


class Period:
    """The month a published file speaks for, and where it sits in the fiscal year."""

    __slots__ = ("year", "month", "path")

    def __init__(self, year: int, month: int, path: str = "") -> None:
        self.year = year
        self.month = month
        self.path = path

    @property
    def fiscal_year(self) -> int:
        """FY26 runs April 2025 to March 2026 — the house's own convention."""
        return self.year + 1 if self.month >= FISCAL_OPENS else self.year

    @property
    def fiscal_index(self) -> int:
        """1 in April, 12 in March. The position the year-to-date accumulates to."""
        return self.month - 3 if self.month >= FISCAL_OPENS else self.month + 9

    @property
    def label(self) -> str:
        return "%04d-%02d" % (self.year, self.month)

    def __repr__(self) -> str:  # pragma: no cover — diagnostics only
        return "Period(%s)" % self.label


class Book:
    """One published file, both of its sheets."""

    __slots__ = ("period", "month", "ytd")

    def __init__(self, period: "Period", month: "Actuals", ytd: "Actuals") -> None:
        self.period = period
        self.month = month
        self.ytd = ytd

    @property
    def usable(self) -> bool:
        return self.month.usable and self.ytd.usable


class Drift:
    """What one month was published as, and what the next month's year-to-date says it was.

    Held as a class rather than a tuple because the interesting field is the smallest one:
    a difference of zero is the normal state and the reason to trust everything else.
    """

    __slots__ = ("period", "published", "implied", "budget_published", "budget_implied")

    def __init__(self, period, published, implied, budget_published, budget_implied):
        self.period = period
        self.published = published
        self.implied = implied
        self.budget_published = budget_published
        self.budget_implied = budget_implied

    @property
    def actual_drift(self) -> float:
        return self.implied - self.published

    @property
    def budget_drift(self) -> float:
        return self.budget_implied - self.budget_published

    @property
    def is_clean(self) -> bool:
        """Within a euro on both terms. Rounding lives in the file, not in the business."""
        return abs(self.actual_drift) < 1.0 and abs(self.budget_drift) < 1.0


class Series:
    """A folder of published files, in order, with what reading them found."""

    __slots__ = ("books", "faults", "folder")

    def __init__(self, books, faults, folder="") -> None:
        self.books = list(books)
        self.faults = list(faults)
        self.folder = folder

    @property
    def usable(self) -> bool:
        return bool(self.books) and all(book.usable for book in self.books)

    def fiscal_years(self) -> List[int]:
        return sorted({book.period.fiscal_year for book in self.books})

    def drifts(self) -> List["Drift"]:
        """Every month the series can check, whether or not it moved.

        A month is checkable when the file before it in its own fiscal year is present, or
        when it is April and the year-to-date is the month itself. Months whose predecessor
        is missing are silently uncheckable rather than reported clean — an absent check is
        not a passed one.
        """
        by_year: Dict[int, Dict[int, Book]] = {}
        for book in self.books:
            by_year.setdefault(book.period.fiscal_year, {})[book.period.fiscal_index] = book

        found: List[Drift] = []
        for _, months in sorted(by_year.items()):
            for index, book in sorted(months.items()):
                if index == 1:
                    before_actual = before_budget = 0.0
                else:
                    earlier = months.get(index - 1)
                    if earlier is None:
                        continue
                    before_actual = earlier.ytd.actual
                    before_budget = earlier.ytd.budget
                found.append(Drift(
                    period=book.period,
                    published=book.month.actual,
                    implied=book.ytd.actual - before_actual,
                    budget_published=book.month.budget,
                    budget_implied=book.ytd.budget - before_budget,
                ))
        return found

    def restated(self) -> List["Drift"]:
        return [drift for drift in self.drifts() if not drift.is_clean]

    def by_market(self) -> Dict[str, List["Period"]]:
        """Which months each market appears in — a market that stops appearing is news."""
        seen: Dict[str, List[Period]] = {}
        for book in self.books:
            for market in book.month.markets():
                seen.setdefault(market, []).append(book.period)
        return seen


#: The closing file writes its month in words and its year in two digits: `August 26`.
MONTH_IN_NAME = re.compile(r"\b(%s)\b[ _\-.]*(20\d\d|\d\d)\b" % "|".join(MONTH_NAMES),
                           re.IGNORECASE)


def period_of(name: str) -> Optional["Period"]:
    """The month a file name speaks for, or nothing if it does not say."""
    stem = os.path.splitext(os.path.basename(name))[0]
    matches = PERIOD_IN_NAME.findall(stem)
    if matches:
        year, month = matches[-1]
        return Period(int(year), int(month), name)
    worded = MONTH_IN_NAME.findall(stem)
    if worded:
        month_name, year = worded[-1]
        year = int(year) if len(year) == 4 else 2000 + int(year)
        return Period(year, MONTH_NAMES.index(month_name.upper()) + 1, name)
    return None


def series(folder: str, brand: str = BRAND) -> "Series":
    """Read every published file in a folder, ordered by the month each speaks for.

    Files that do not name a month are refused rather than guessed at, and two files
    claiming the same month are both refused: the series exists to detect restatement, and
    a series that quietly kept one of two versions would hide exactly what it is for.
    """
    try:
        names = sorted(os.listdir(folder))
    except OSError as exc:  # noqa: BLE001 — the message matters more than the type
        return Series([], ["%s" % exc], folder)

    faults: List[str] = []
    claimed: Dict[str, List[str]] = {}
    candidates: List[Period] = []
    for name in names:
        if not name.lower().endswith((".xlsx", ".xlsm")) or name.startswith("~$"):
            continue
        period = period_of(name)
        if period is None:
            faults.append("mois illisible dans le nom, fichier ignoré : %s" % name)
            continue
        period.path = os.path.join(folder, name)
        claimed.setdefault(period.label, []).append(name)
        candidates.append(period)

    doubled = {label for label, names_ in claimed.items() if len(names_) > 1}
    for label in sorted(doubled):
        faults.append("deux fichiers pour %s : %s — aucun retenu"
                      % (label, ", ".join(sorted(claimed[label]))))

    books: List[Book] = []
    for period in sorted(candidates, key=lambda p: (p.year, p.month)):
        if period.label in doubled:
            continue
        month = load(period.path, MONTH_SHEET, brand)
        ytd = load(period.path, YTD_SHEET, brand)
        faults.extend("%s — %s" % (os.path.basename(period.path), fault)
                      for fault in month.faults + ytd.faults)
        books.append(Book(period, month, ytd))

    if not books:
        faults.append("aucun fichier publié lisible dans %s" % folder)
    return Series(books, faults, folder)


def current_series() -> "Series":
    """The folder of published files as it sits on disk right now."""
    from ..config import settings

    return series(str(settings.actuals_folder))
