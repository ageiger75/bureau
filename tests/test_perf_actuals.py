"""Finance's own actuals, read at the grain the plan is written in.

The figure at the top of this screen used to be derived from the warehouse and reconciled
against a published one, market by market, for weeks. This source carries the actual, last
year and the budget on one row, at one set of rates — so the variance becomes a subtraction
inside the source that decides, and every perimeter chased during that reconciliation stops
bearing on the headline.
"""

from __future__ import annotations

from app.perf import actuals


def test_the_maison_is_located_never_assumed():
    """The workbook lays its two sheets out differently, and a fixed column matched nothing
    on one of them — every row skipped, the total zero. A screen showing nothing looks
    exactly like a business doing nothing, which is the quiet kind of wrong."""
    rows = [
        ["", "", "", "", "L'Occitane en Provence", "x", "JAPAN", "APAC", "", "", "RET - Retail",
         "1", "2", "3.0", "4.0", "5.0"],
    ]
    assert actuals._locate_brand(rows, "L'Occitane en Provence") == 4

    shifted = [["", "", "", "", "", "L'Occitane en Provence", "JAPAN", "APAC", "", "",
                "RET - Retail", "1", "2", "3.0", "4.0", "5.0"]]
    assert actuals._locate_brand(shifted, "L'Occitane en Provence") == 5

    assert actuals._locate_brand(rows, "Another Maison") is None


def test_every_channel_of_the_plan_has_a_name_here():
    """Sixteen on each side, matched one to one. A channel appearing in the accounts and
    not in this table would be a hole in the screen, so it is refused rather than dropped:
    a hole that reports itself is worth more than a total that quietly narrows."""
    assert len(actuals.CHANNELS) == 16
    assert set(actuals.CHANNELS.values()) == {
        "b2b", "cafe", "copg", "dis", "direct selling", "dpt", "ecommerce", "marketplace",
        "retail", "spa", "tra", "tvc", "webp", "whoch", "whoin", "whosp",
    }


def test_the_three_bases_are_carried_never_collapsed():
    """This screen has always refused to mix sold and shipped in silence. This file is the
    first source that labels which is which, and hospitality — which nothing read before —
    arrives named rather than missing."""
    assert actuals.SOLD != actuals.SHIPPED != actuals.HOSPITALITY


def test_a_missing_file_reports_rather_than_raises():
    read = actuals.load("/nowhere/at/all.xlsx")
    assert not read.usable
    assert read.faults


def test_the_variance_column_is_the_one_at_budget_rates():
    """The published flash quotes the actual at real rates and computes its percentages on
    the actual at budget rates. Both are presented as constant-rate figures and only the
    percentages are.

    Dividing the quoted value by the quoted percentage therefore mixes two bases — and this
    repository did exactly that, concluded the planning workbook held a different budget
    several points away, and set out to find a perimeter that does not exist. The columns
    are named here so the next reader inherits the answer rather than the mistake.
    """
    assert actuals.ACTUAL_AT == 13
    assert actuals.LAST_YEAR_AT == 14
    assert actuals.BUDGET_AT == 15
    # The real-rate column sits at 11 and is deliberately not read for the variance.
    assert actuals.ACTUAL_AT != 11


def _unit(market, channel, actual, budget, reported=None):
    from app.perf.model import BusinessUnit, Drivers, Owner

    kwargs = {}
    if reported is not None:
        kwargs = {"reported_actual": reported[0], "reported_budget": reported[1]}
    return BusinessUnit(
        key="%s-%s" % (market, channel), label=market, market=market, region="EMEA",
        channel=channel, owner=Owner("A", "B", "c@d"),
        actual=Drivers.sales_only(actual), budget=Drivers.sales_only(budget),
        last_year=Drivers.sales_only(0.0), forecast_sales=0.0, **kwargs)


def test_a_unit_takes_both_sides_from_one_source_or_neither():
    """A reported actual against a warehouse plan would be a ratio across two perimeters —
    the exact fault this screen spent weeks measuring in the other direction."""
    reported = _unit("France", "retail", 900.0, 1000.0, reported=(980.0, 1000.0))
    warehouse = _unit("Spain", "retail", 900.0, 1000.0)

    assert reported.is_reported
    assert reported.sales_actual == 980.0 and reported.sales_budget == 1000.0
    assert reported.gap_vs_budget == -20.0
    assert not warehouse.is_reported
    assert warehouse.gap_vs_budget == -100.0


def test_the_screen_says_how_much_of_it_the_accounts_cover():
    """A cockpit half on one source and half on another is honest only if it says where the
    line falls — the share decides how much of the screen may be quoted in a meeting."""
    from app.perf.model import Dataset

    data = Dataset(period_label="Sales MTD", as_of="2026-07-31", units=[
        _unit("France", "retail", 900.0, 1000.0, reported=(900.0, 1000.0)),
        _unit("Spain", "retail", 100.0, 100.0),
    ])

    assert [u.market for u in data.reported] == ["France"]
    assert round(data.reported_share, 2) == 0.90
    assert data.units[0].figure_source == "the consolidation"
    assert data.units[1].figure_source == "the warehouse"


def test_several_published_rows_for_one_scope_are_summed_never_picked():
    """One market and channel can carry more than one row — two entities, or a channel sold
    and shipped. Choosing between them would show part of a business under a heading naming
    all of it."""
    read = actuals.Actuals([
        actuals.Line("China", "CHINA", "webp", actuals.SHIPPED, 100.0, 90.0, 120.0),
        actuals.Line("China", "CHINA", "webp", actuals.SOLD, 50.0, 40.0, 60.0),
    ], [])

    folded = actuals.by_scope(read)

    assert folded["China/webp"].actual == 150.0
    assert folded["China/webp"].budget == 180.0
    # Two bases under one heading is a fact about the business, and it is named.
    assert folded["China/webp"].basis == "MIXED"


# --- The series ----------------------------------------------------------------------


def _book(year, month, month_actual, ytd_actual, month_budget=0.0, ytd_budget=0.0):
    period = actuals.Period(year, month)
    line = actuals.Line("Somewhere", "EMEA", "retail", actuals.SOLD,
                        month_actual, 0.0, month_budget)
    cumulative = actuals.Line("Somewhere", "EMEA", "retail", actuals.SOLD,
                              ytd_actual, 0.0, ytd_budget)
    return actuals.Book(period, actuals.Actuals([line], []), actuals.Actuals([cumulative], []))


def test_the_fiscal_year_is_read_from_the_file_name():
    """April opens the year, so November 2025 belongs to FY26 and sits eighth in it. Read
    from the name rather than declared: a file filed under the wrong month would compare a
    cumulative total against the wrong predecessor and invent a restatement."""
    november = actuals.period_of("Sales by country and by channel 2025 11_RFx.xlsx")
    assert (november.year, november.month) == (2025, 11)
    assert november.fiscal_year == 2026
    assert november.fiscal_index == 8

    april = actuals.period_of("Sales by country and by channel 2025 04_RFx.xlsx")
    assert april.fiscal_index == 1
    assert actuals.period_of("Sales by country and by channel.xlsx") is None


def test_a_month_that_did_not_move_is_the_normal_state():
    """The whole instrument rests on one subtraction: inside a fiscal year, the cumulative
    of one month less the cumulative of the month before must equal the month itself. When
    it does, this reader reads the file correctly and nobody needs to confirm it."""
    series = actuals.Series([
        _book(2025, 4, 100.0, 100.0),
        _book(2025, 5, 120.0, 220.0),
        _book(2025, 6, 90.0, 310.0),
    ], [])
    drifts = series.drifts()
    assert len(drifts) == 3
    assert all(drift.is_clean for drift in drifts)
    assert series.restated() == []


def test_a_month_restated_after_publication_is_named_with_its_month():
    """A provision trued up at close, a reclassification applied backwards: the month was
    published at one figure and the next cumulative says another. That difference is
    decided rather than computed, which is exactly why no rule derived from the warehouse
    could have anticipated it — and why measuring it is worth more than deriving it."""
    series = actuals.Series([
        _book(2025, 4, 100.0, 100.0),
        _book(2025, 5, 120.0, 250.0),
    ], [])
    moved = series.restated()
    assert [drift.period.label for drift in moved] == ["2025-05"]
    assert moved[0].published == 120.0
    assert moved[0].implied == 150.0
    assert moved[0].actual_drift == 30.0


def test_a_month_whose_predecessor_is_absent_is_not_checked():
    """An absent check is not a passed one. A folder missing one month can still be read,
    and the months it cannot verify are left out of the count rather than reported clean."""
    series = actuals.Series([
        _book(2025, 4, 100.0, 100.0),
        _book(2025, 6, 90.0, 310.0),
    ], [])
    assert [drift.period.label for drift in series.drifts()] == ["2025-04"]


def test_the_year_end_does_not_carry_into_the_next_april():
    """The cumulative resets in April, so April is checked against itself and never against
    the March before it. Getting this wrong would report a restatement every twelve months
    the size of a whole year."""
    series = actuals.Series([
        _book(2026, 3, 80.0, 900.0),
        _book(2026, 4, 110.0, 110.0),
    ], [])
    assert all(drift.is_clean for drift in series.drifts())


def test_two_files_claiming_one_month_are_both_refused(tmp_path):
    """The series exists to detect that a month changed. A series that quietly kept one of
    two versions of the same month would hide precisely what it is for."""
    (tmp_path / "Sales 2025 11.xlsx").write_bytes(b"")
    (tmp_path / "Sales 2025 11_v2.xlsx").write_bytes(b"")
    (tmp_path / "Sales unnamed month.xlsx").write_bytes(b"")
    read = actuals.series(str(tmp_path))
    assert read.books == []
    assert any("deux fichiers pour 2025-11" in fault for fault in read.faults)
    assert any("mois illisible" in fault for fault in read.faults)


def test_an_absent_folder_reports_rather_than_raises():
    read = actuals.series("/nowhere/at/all")
    assert not read.usable
    assert read.faults


# --- Three layouts of the same rows ----------------------------------------------------
#
# Finance changed the export twice in one year without changing what it says. The reader
# has to recognise each from the workbook itself, read the same three figures from each,
# and spell the markets the way the plan does whatever the file called them.

import zipfile

_CONTENT_TYPES = (
    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    'content-types"><Default Extension="xml" ContentType="application/xml"/></Types>'
)


def _cell(reference, value):
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return '<c r="%s"><v>%s</v></c>' % (reference, value)
    return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (reference, value)


def _sheet_xml(rows):
    body = []
    for index, row in enumerate(rows, start=1):
        cells = [_cell("%s%d" % (chr(ord("A") + position), index), value)
                 for position, value in enumerate(row)]
        body.append('<row r="%d">%s</row>' % (index, "".join(cells)))
    return ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main"><sheetData>%s</sheetData></worksheet>' % "".join(body))


def _workbook(path, sheets):
    """Write a workbook of several named sheets, the way Excel lays the package out."""
    names = list(sheets)
    workbook = ('<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships"><sheets>%s</sheets></workbook>'
                % "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (name, i, i)
                          for i, name in enumerate(names, start=1)))
    rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships">%s</Relationships>'
            % "".join('<Relationship Id="rId%d" Target="worksheets/sheet%d.xml" '
                      'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                      'relationships/worksheet"/>' % (i, i)
                      for i in range(1, len(names) + 1)))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        for i, name in enumerate(names, start=1):
            archive.writestr("xl/worksheets/sheet%d.xml" % i, _sheet_xml(sheets[name]))
    return str(path)


MAISON = "L'Occitane en Provence"
NAMED_HEADER = ["Brand", "Entities", "Region", "Country", "PCC - Parent", "Channel",
                "ACTUAL N", "ACTUAL N-1", "BUDGET N"]


def _named(rows):
    return [NAMED_HEADER] + rows


def test_the_closing_file_is_read_from_its_latest_month_sheet(tmp_path):
    """From August 2026 the file keeps one sheet per month, `DATA APRIL`, `DATA MAY`…, in
    an older shape for the earlier months, and speaks for the latest. The reader ranks
    the sheets in fiscal order and reads that one — August over April, and the year to
    date from its own sheet."""
    path = _workbook(tmp_path / "Sales by country  by channel August 26.xlsx", {
        "DATA APRIL ": [["Brand", "Country", "Channel", "ACTUAL N", "BUDGET N"],
                        [MAISON, "Northland", "Retail", 1.0, 1.0]],
        "DATA AUGUST": _named([
            [MAISON, "E001 - Northland", "GE COUNTRIES", "Northland", "Sell out", "Retail",
             120.0, 110.0, 100.0],
            [MAISON, "E001 - Northland", "GE COUNTRIES", "Northland", "Sell In",
             "Web partners", 30.0, 25.0, 40.0],
            ["Another Maison", "E002 - X", "GE COUNTRIES", "Northland", "Sell out", "Retail",
             999.0, 999.0, 999.0],
        ]),
        "DATA YTD AUGUST": _named([
            [MAISON, "E001 - Northland", "GE COUNTRIES", "Northland", "Sell out", "Retail",
             520.0, 480.0, 500.0],
        ]),
    })

    month = actuals.load(path, actuals.MONTH_SHEET)
    assert month.sheet == "DATA AUGUST"
    assert not month.faults
    assert (month.actual, month.last_year, month.budget) == (150_000.0, 135_000.0, 140_000.0)
    assert {line.basis for line in month.lines} == {actuals.SOLD, actuals.SHIPPED}
    assert {line.channel for line in month.lines} == {"retail", "webp"}

    ytd = actuals.load(path, actuals.YTD_SHEET)
    assert ytd.sheet == "DATA YTD AUGUST"
    assert ytd.actual == 520_000.0


def test_the_cfo_data_set_reads_the_constant_rate_columns(tmp_path):
    """The CFO's extract carries each actual twice — at published rate and at constant
    rate — under a merged header that is written once over the columns it covers. The
    cockpit reads the constant-rate pair, the basis every published percentage rests on,
    and the budget, which has one rate only."""
    blank = [None, None]
    rows = [
        [None, None, "SAL_RE_015 - Sales Data Set"],
        [None, "Scenario", "FY27_ACT - Actual 2027"],
        [None, "Period", "05 - August"],
        blank + [None] * 6 + ["Published rate", None, "Constant rate", None, "Published rate"],
        blank + [None] * 6 + ["Actual 2027", "Actual 2026", "Actual 2027", "Actual 2026",
                              "Budget 2027"],
        blank + ["Brand", "Entities", "Management Unit - Parent", "Management Unit - Lowest",
                 "PCC - Parent", "PCC - Lowest", "Sales", "Sales", "Sales", "Sales", "Sales"],
        blank + [None] * 6 + ["Actual 2027", "Actual 2026", "Actual 2027", "Actual 2026",
                              "Budget 2027"],
        blank + [None] * 6 + ["Sales"] * 5,
        blank + [MAISON, "E001 - Northland", "Greater Europe", "Northland", "Sell out",
                 "Retail", 999.0, 999.0, 120.0, 110.0, 100.0],
        blank + [MAISON, "E001 - Northland", "Greater Europe", "Northland", "Total B2B",
                 "Corporate Gifts", 999.0, 999.0, 5.0, 4.0, 6.0],
    ]
    path = _workbook(tmp_path / "OCC FS DATA SET 2026_08.xlsx", {
        "Sales Data Set MTD": rows, "Sales Data by Store MTD": [["ignored"]],
        "Sales Data Set YTD": rows,
    })

    month = actuals.load(path, actuals.MONTH_SHEET)
    assert month.sheet == "Sales Data Set MTD"
    assert not month.faults
    assert (month.actual, month.last_year, month.budget) == (125_000.0, 114_000.0, 106_000.0)
    assert month.by_basis() == {actuals.SOLD: 120_000.0, actuals.HOSPITALITY: 5_000.0}
    assert actuals.load(path, actuals.YTD_SHEET).sheet == "Sales Data Set YTD"


def test_markets_are_spelt_as_the_plan_spells_them_whatever_the_file_called_them(tmp_path):
    """Three files, three spellings, one plan. Aligned through the consolidation entity
    and kept explicit: a market spelt its own way joins no plan line, and a market that
    joins no plan line shows as a business with no commitment."""
    path = _workbook(tmp_path / "August 26.xlsx", {"DATA AUGUST": _named([
        [MAISON, "E035", "GE COUNTRIES", "Czek Republic", "Sell out", "Retail", 1.0, 1.0, 1.0],
        [MAISON, "E010", "GE COUNTRIES", "Netherland", "Sell out", "Retail", 1.0, 1.0, 1.0],
        [MAISON, "E086", "GE COUNTRIES", "86 Champs", "Sell out", "Cafe", 1.0, 1.0, 1.0],
        [MAISON, "E098", "GE DISTRIBUTORS", "MIDDLE EAST", "Sell In", "Distributors",
         1.0, 1.0, 1.0],
        [MAISON, "E007", "APAC", "HK TR", "Sell In", "Travel Retail", 1.0, 1.0, 1.0],
        [MAISON, "E004", "N.AMERICA", "USA", "Sell out", "E-Business", 1.0, 1.0, 1.0],
        [MAISON, "E007", "CHINA", "CHINA CROSS BORDER", "Sell In", "Web partners",
         1.0, 1.0, 1.0],
    ])})

    assert actuals.load(path).markets() == [
        "86Cr", "China", "Czech Republic", "Middle East", "Netherlands",
        "Travel retail Asia", "United States",
    ]
    # The CFO's own spellings reach the same names.
    for theirs, ours in (("Japan Management Unit", "Japan"), ("Brazil business", "Brazil"),
                         ("Hong Kong Local", "Hong Kong"),
                         ("Hong Kong Distributors", "Hong Kong distributors"),
                         ("Travel Retail LOI Business", "Travel retail international"),
                         ("Export Europe", "Loi Distributors"),
                         ("China Cross border", "China")):
        assert actuals._market(theirs) == ours, theirs


def test_a_channel_the_table_does_not_know_is_refused_and_named(tmp_path):
    path = _workbook(tmp_path / "August 26.xlsx", {"DATA AUGUST": _named([
        [MAISON, "E001", "GE COUNTRIES", "Northland", "Sell out", "Retail", 1.0, 1.0, 1.0],
        [MAISON, "E001", "GE COUNTRIES", "Northland", "Sell out", "Drones", 1.0, 1.0, 1.0],
    ])})
    read = actuals.load(path)

    assert len(read.lines) == 1
    assert read.faults == ["canaux inconnus, non comptés : drones"]


def test_a_workbook_with_no_recognised_sheet_says_which_sheets_it_has(tmp_path):
    path = _workbook(tmp_path / "other.xlsx", {"Summary": [["x"]], "Notes": [["y"]]})
    read = actuals.load(path)

    assert not read.lines
    assert read.faults[0].startswith("aucune feuille du mois reconnue — feuilles : Summary, Notes")


def test_a_row_carrying_only_last_year_is_kept(tmp_path):
    """A business that stopped has a last year and nothing else. Dropping the row left the
    comparison against last year half a million short of the figure the flash published
    beside it — found on May, and true of every month before."""
    path = _workbook(tmp_path / "August 26.xlsx", {"DATA AUGUST": _named([
        [MAISON, "E001", "GE COUNTRIES", "Northland", "Sell out", "Retail", 100.0, 90.0, 95.0],
        [MAISON, "E001", "GE COUNTRIES", "Northland", "Sell In", "Department Stores",
         None, 12.0, None],
    ])})
    read = actuals.load(path)

    assert len(read.lines) == 2
    assert read.last_year == 102_000.0
    assert read.actual == 100_000.0


def test_the_month_is_read_from_a_name_that_writes_it_in_words():
    august = actuals.period_of("Sales by country  by channel August 26.xlsx")
    assert (august.year, august.month) == (2026, 8)
    assert august.fiscal_index == 5
    march = actuals.period_of("Sales by country by channel march 2027.xlsx")
    assert (march.year, march.month) == (2027, 3)
    # Digits still win where both are written.
    both = actuals.period_of("Sales April 2026_05.xlsx")
    assert (both.year, both.month) == (2026, 5)


def test_the_reading_declares_the_month_it_speaks_for(tmp_path):
    """June's figures once sat under an August heading because nothing compared the two.
    Each layout says its month somewhere — the sheet name, the Period cell, the file
    name — and the reading carries it."""
    named = _workbook(tmp_path / "Sales by country by channel August 26.xlsx", {
        "DATA AUGUST": _named([[MAISON, "E001", "GE COUNTRIES", "Northland", "Sell out",
                                "Retail", 1.0, 1.0, 1.0]])})
    read = actuals.load(named)
    assert (read.year, read.month, read.period) == (2026, 8, "2026-08")
    assert read.month_label == "August"

    legacy = actuals.load(str(tmp_path / "nowhere 2026 05.xlsx"))
    assert legacy.month is None  # a missing file declares nothing


def test_the_cfo_extract_declares_its_month_from_its_own_cells(tmp_path):
    blank = [None, None]
    rows = [
        [None, None, "SAL_RE_015 - Sales Data Set"],
        [None, "Scenario", "FY27_ACT - Actual 2027"],
        [None, "Period", "05 - August"],
        blank + [None] * 6 + ["Published rate", None, "Constant rate", None, "Published rate"],
        blank + [None] * 6 + ["Actual 2027", "Actual 2026", "Actual 2027", "Actual 2026",
                              "Budget 2027"],
        blank + ["Brand", "Entities", "Management Unit - Parent", "Management Unit - Lowest",
                 "PCC - Parent", "PCC - Lowest", "Sales", "Sales", "Sales", "Sales", "Sales"],
        blank + [MAISON, "E001", "Greater Europe", "Northland", "Sell out", "Retail",
                 9.0, 9.0, 1.0, 1.0, 1.0],
    ]
    path = _workbook(tmp_path / "extract.xlsx", {"Sales Data Set MTD": rows})
    read = actuals.load(path)

    assert (read.year, read.month) == (2026, 8)
    # FY27 opens in April 2026: a January would belong to 2027.
    assert actuals._dataset_period([[None, "Scenario", "FY27_ACT"], [None, "Period", "10 - January"]]) == (2027, 1)
