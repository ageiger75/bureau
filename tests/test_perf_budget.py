"""Budget read from the planning workbook, and the XLSX reader beneath it.

The warehouse carries goals for a minority of markets — not for the largest ones. The
planning file carries all of them, and is the version the business commits to. Without it
most markets would show no gap at all, which is the most reassuring wrong answer this
product could give.

The fixture below builds a real .xlsx by hand, with the standard library only. That keeps
the test honest about what the reader must cope with, and keeps the repository free of a
spreadsheet dependency — the rule `AGENTS.md` set before this need arose.
"""

from __future__ import annotations

import zipfile

import pytest

from app.perf import budget as budget_module
from app.perf.budget import Budget, BudgetLine
from app.perf.xlsx import Workbook, WorkbookError, read_sheet

CONTENT_TYPES = (
    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    'content-types"><Default Extension="xml" ContentType="application/xml"/></Types>'
)

WORKBOOK = (
    '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/'
    'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/'
    '2006/relationships"><sheets><sheet name="DATA BASE" sheetId="1" r:id="rId1"/>'
    '</sheets></workbook>'
)

WORKBOOK_RELS = (
    '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
    'package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"'
    '/></Relationships>'
)

HEADERS = ["Brand", "Country", "Region", "Segment", "BUDGET 2026.JUL", "2025.JUL"]


def _sheet(rows):
    """Build a worksheet where text is inline and numbers are bare, as Excel writes them."""
    body = []
    for index, row in enumerate(rows, start=1):
        cells = []
        for position, value in enumerate(row):
            reference = "%s%d" % (chr(ord("A") + position), index)
            if isinstance(value, (int, float)):
                cells.append('<c r="%s"><v>%s</v></c>' % (reference, value))
            else:
                cells.append(
                    '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (reference, value)
                )
        body.append("<row r=\"%d\">%s</row>" % (index, "".join(cells)))
    return (
        '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main"><sheetData>%s</sheetData></worksheet>' % "".join(body)
    )


@pytest.fixture
def workbook_path(tmp_path):
    path = tmp_path / "budget.xlsx"
    rows = [
        HEADERS,
        ["L'Occitane", "JAPAN", "JAPAN", "EBU - E-business", 1861.7, 1620.0],
        ["L'Occitane", "JAPAN", "JAPAN", "RET - Retail", 5148.0, 5360.0],
        ["L'Occitane", "USA", "N.AMERICA", "EBU - E-business", 1850.0, 1640.0],
        ["L'Occitane", "UK", "GE COUNTRIES", "EBU - E-business", 730.0, 1090.0],
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("xl/workbook.xml", WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr("xl/worksheets/sheet1.xml", _sheet(rows))
    return path


# --------------------------------------------------------------------------- reader


def test_the_reader_finds_sheets_by_name(workbook_path):
    with Workbook(workbook_path) as book:
        assert book.sheet_names == ["DATA BASE"]


def test_the_reader_returns_text_and_numbers(workbook_path):
    rows = read_sheet(workbook_path, "DATA BASE")

    assert rows[0][:4] == ["Brand", "Country", "Region", "Segment"]
    assert rows[1][4] == pytest.approx(1861.7)


def test_an_unknown_sheet_names_the_ones_that_exist(workbook_path):
    with pytest.raises(WorkbookError) as refused:
        read_sheet(workbook_path, "Sheet1")

    assert "DATA BASE" in str(refused.value)


def test_a_file_that_is_not_a_workbook_is_refused(tmp_path):
    fake = tmp_path / "not-a-workbook.xlsx"
    fake.write_text("this is not a zip archive")

    with pytest.raises(WorkbookError):
        read_sheet(fake, "DATA BASE")


# --------------------------------------------------------------------------- budget


def test_thousands_are_converted_once(workbook_path):
    """The sheet is in thousands. Converting here means nothing downstream has to know."""
    loaded = budget_module.load(workbook_path)

    assert loaded.budget_for("Japan", "ecommerce", "2026-07") == pytest.approx(1_861_700)


def test_last_year_is_the_same_month_a_year_earlier(workbook_path):
    loaded = budget_module.load(workbook_path)

    assert loaded.last_year_for("Japan", "ecommerce", "2026-07") == pytest.approx(1_620_000)


def test_planning_segments_map_to_the_cockpit_channels(workbook_path):
    loaded = budget_module.load(workbook_path)

    assert loaded.budget_for("Japan", "retail", "2026-07") == pytest.approx(5_148_000)


def test_market_names_are_translated_not_guessed(workbook_path):
    """A silent mismatch would drop a market from the cockpit with nobody noticing."""
    loaded = budget_module.load(workbook_path)

    assert "United States" in loaded.markets()
    assert "United Kingdom" in loaded.markets()
    assert "Usa" not in loaded.markets()


def test_the_markets_the_warehouse_misses_are_the_point(workbook_path):
    """The largest e-commerce markets have no goal in the warehouse. They have one here."""
    loaded = budget_module.load(workbook_path)

    assert loaded.budget_for("United States", "ecommerce", "2026-07") == pytest.approx(1_850_000)
    assert loaded.budget_for("United Kingdom", "ecommerce", "2026-07") == pytest.approx(730_000)


def test_an_unknown_market_returns_nothing_rather_than_zero(workbook_path):
    """Zero would read as "on plan". Absent reads as absent."""
    loaded = budget_module.load(workbook_path)

    assert loaded.budget_for("Atlantis", "ecommerce", "2026-07") is None


def test_a_workbook_without_budget_columns_is_refused(tmp_path):
    """An empty budget would make every market look exactly on plan."""
    path = tmp_path / "wrong.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("xl/workbook.xml", WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            _sheet([["Brand", "Country", "Region", "Segment"], ["x", "JAPAN", "JAPAN", "RET"]]),
        )

    with pytest.raises(WorkbookError):
        budget_module.load(path)


# ----------------------------------------------------------- reading the file by hand
#
# `manage.py budget` exists to answer one question before the warehouse is ever reached:
# does the planning file cover the markets whose sales we are about to read? A workbook
# that is unreadable, or silently missing a month, is better found here than in front of
# a screen that looks calm.


def test_the_command_refuses_clearly_when_the_file_is_absent(capsys, monkeypatch):
    from app.cli import cmd_budget
    from app.config import settings

    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: False))

    assert cmd_budget([]) == 2
    assert "Classeur absent" in capsys.readouterr().err


def test_the_command_reports_what_the_file_covers(capsys, monkeypatch):
    from app.cli import cmd_budget
    from app.config import settings
    from app.perf import budget as budget_module

    plan = Budget(
        [
            BudgetLine("Japan", "APAC", "EBU", "ecommerce", "2026-07", 1_861_700.0, 1_622_900.0),
            BudgetLine("France", "EMEA", "RET", "retail", "2026-08", 900_000.0, 850_000.0),
        ]
    )
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    assert cmd_budget([]) == 0

    out = capsys.readouterr().out
    assert "Marchés             2" in out
    assert "2026-07" in out and "2026-08" in out


def test_an_empty_cell_prints_a_dash_rather_than_a_zero(capsys, monkeypatch):
    """A zero shown where a number is missing is the exact lie the cockpit avoids."""
    from app.cli import cmd_budget
    from app.config import settings
    from app.perf import budget as budget_module

    plan = Budget(
        [BudgetLine("Japan", "APAC", "EBU", "ecommerce", "2026-07", 1_861_700.0, None)]
    )
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    cmd_budget(["--period", "2026-07"])

    assert "—" in capsys.readouterr().out


def test_an_unknown_period_is_refused_rather_than_shown_empty(monkeypatch):
    from app.cli import cmd_budget
    from app.config import settings
    from app.perf import budget as budget_module

    plan = Budget(
        [BudgetLine("Japan", "APAC", "EBU", "ecommerce", "2026-07", 1_861_700.0, 1_622_900.0)]
    )
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    assert cmd_budget(["--period", "2026-12"]) == 2
