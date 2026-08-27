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


# ------------------------------------------------------- sell-in, and where it is not
#
# The warehouse measures what the Maison sells to the end customer. A large part of the
# plan is invoiced to someone who then resells it, and no sell-out query will ever
# reproduce those lines. Reading their absence as a shortfall would be a serious mistake,
# so the perimeter has to be nameable before anything is compared to anything.


def test_a_reseller_segment_is_sell_in():
    assert budget_module.perimeter_of("WHOIN - Wholesale indep") == "sell-in"
    assert budget_module.perimeter_of("DIS - Distributors") == "sell-in"


def test_an_operated_segment_is_own():
    assert budget_module.perimeter_of("RET - Retail") == "own"
    assert budget_module.perimeter_of("EBU - E-business") == "own"


def test_a_marketplace_store_is_sell_out_on_someone_elses_platform():
    """The correction that broke the binary split. A flagship the Maison operates on a
    marketplace sells to the end customer — that is sell-out, however little it looks
    like an own site. What it does not have is a funnel: the platform owns the traffic."""
    assert budget_module.perimeter_of("MKTP - Market place") == "platform"
    assert budget_module.is_sell_out("MKTP - Market place") is True


def test_a_platform_sale_is_not_counted_as_resold():
    """Placing it in sell-in would have hidden real sell-out revenue behind a caveat
    saying no source measures it — when the source measures it perfectly well."""
    assert budget_module.perimeter_of("MKTP - Market place") != "sell-in"


def test_what_the_sell_out_warehouse_can_account_for():
    assert budget_module.is_sell_out("RET - Retail") is True
    assert budget_module.is_sell_out("EBU - E-business") is True
    assert budget_module.is_sell_out("DIS - Distributors") is False


def test_an_unlisted_segment_falls_to_other_rather_than_being_guessed():
    """A new segment code appearing in next year's file must not be silently counted as
    sell-in because it looks a bit like wholesale."""
    assert budget_module.perimeter_of("XYZ - Something new") == "other"
    assert budget_module.perimeter_of("") == "other"


def test_the_exported_spec_is_last_year_not_the_plan(tmp_path, capsys, monkeypatch):
    """A query is validated against what the business invoiced, not against what it
    intended to invoice. A plan is allowed to be wrong; an actual is not."""
    from app.cli import cmd_budget
    from app.config import settings

    plan = Budget(
        [
            BudgetLine("Japan", "APAC", "WHOIN - Wholesale indep", "whoin",
                       "2026-07", 500_000.0, 430_000.0),
            BudgetLine("Japan", "APAC", "RET - Retail", "retail",
                       "2026-07", 900_000.0, 850_000.0),
        ]
    )
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    target = tmp_path / "spec.csv"
    assert cmd_budget(["--spec", str(target)]) == 0

    written = target.read_text().strip().splitlines()

    # One sell-in line only, carrying last year's figure — not the budget.
    assert len(written) == 2
    assert "430000.00" in written[1]
    assert "500000.00" not in written[1]


def test_the_spec_refuses_an_unknown_perimeter(tmp_path, monkeypatch):
    from app.cli import cmd_budget
    from app.config import settings

    plan = Budget(
        [BudgetLine("Japan", "APAC", "RET - Retail", "retail", "2026-07", 1.0, 1.0)]
    )
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    assert cmd_budget(["--spec", str(tmp_path / "x.csv"), "--perimeter", "wholesale"]) == 2


def test_revenue_with_no_plan_is_counted_and_named(capsys, monkeypatch):
    """It made two commands disagree by four million before it was visible. A channel
    that invoiced and that nobody planned for will be compared to nothing."""
    from app.cli import cmd_budget
    from app.config import settings

    plan = Budget(
        [
            BudgetLine("Japan", "APAC", "RET - Retail", "retail",
                       "2026-07", 900_000.0, 850_000.0),
            # Sold last year, planned for by nobody this year.
            BudgetLine("Japan", "APAC", "DDS - Digital Direct Selling", "dds",
                       "2026-07", None, 120_000.0),
        ]
    )
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    assert cmd_budget(["--segments"]) == 0

    out = capsys.readouterr().out
    assert "sans budget cette année" in out
    assert "120 000" in out


def test_web_partners_are_resellers():
    """Settled by the business, not by the code: e-retailers who buy stock to resell."""
    assert budget_module.perimeter_of("WEBP - Web Partners") == "sell-in"


def test_nothing_is_on_the_boundary_today():
    """Both open questions were answered. The mechanism stays; the list is empty."""
    assert budget_module.AMBIGUOUS_SEGMENTS == frozenset()


def test_an_unsettled_segment_would_still_be_declared(capsys, monkeypatch):
    """The question recurs — a marketplace can be run under either contract. The day one
    is, the code has to say it does not know rather than place it by resemblance."""
    from app.cli import cmd_budget
    from app.config import settings

    plan = Budget(
        [BudgetLine("Japan", "APAC", "MKTP - Market place", "mktp",
                    "2026-07", 500_000.0, 430_000.0)]
    )
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)
    monkeypatch.setattr(budget_module, "AMBIGUOUS_SEGMENTS", frozenset(("MKTP",)))

    cmd_budget(["--segments"])

    assert "Sur la frontière" in capsys.readouterr().out


# ------------------------------------------------- turning a claim into a measurement
#
# "The sell-in data is not clean" is an assertion. Against twelve months of known actuals
# per market and segment it becomes a measurement — and a query that reproduces them is
# usable whatever the state of the semantic layer above it.


def _spec_plan():
    return Budget(
        [
            BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                       "2026-07", 500_000.0, 400_000.0),
            BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                       "2026-08", 500_000.0, 300_000.0),
            BudgetLine("Japan", "APAC", "RET - Retail", "retail",
                       "2026-07", 900_000.0, 850_000.0),
        ]
    )


def _candidate(tmp_path, rows):
    import csv

    path = tmp_path / "candidate.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["market", "segment", "period", "value"])
        writer.writerows(rows)
    return path


@pytest.fixture
def against_spec(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: _spec_plan())


def test_a_candidate_that_reproduces_the_actuals_is_accepted(
    tmp_path, capsys, against_spec
):
    from app.cli import cmd_reconcile

    path = _candidate(tmp_path, [
        ["Japan", "DIS - Distributors", "2026-07", "400000"],
        ["Japan", "DIS - Distributors", "2026-08", "300000"],
    ])

    assert cmd_reconcile([str(path)]) == 0
    assert "Utilisable" in capsys.readouterr().out


def test_a_rounding_difference_still_counts_as_agreement(tmp_path, against_spec):
    from app.cli import cmd_reconcile

    path = _candidate(tmp_path, [
        ["Japan", "DIS - Distributors", "2026-07", "400100"],
        ["Japan", "DIS - Distributors", "2026-08", "299500"],
    ])

    assert cmd_reconcile([str(path)]) == 0


def test_a_wrong_definition_is_refused_and_located(tmp_path, capsys, against_spec):
    """The point of the exercise. A total that lands by accident on one month cannot land
    on twelve, and the report says which one broke."""
    from app.cli import cmd_reconcile

    path = _candidate(tmp_path, [
        ["Japan", "DIS - Distributors", "2026-07", "400000"],
        ["Japan", "DIS - Distributors", "2026-08", "180000"],
    ])

    assert cmd_reconcile([str(path)]) == 1

    out = capsys.readouterr().out
    assert "2026-08" in out
    assert "En désaccord        1" in out


def test_the_biggest_gaps_come_first(tmp_path, capsys, against_spec):
    """A wrong definition shows up in money, not in cell counts: one large market off
    matters more than thirty small ones."""
    from app.cli import cmd_reconcile

    path = _candidate(tmp_path, [
        ["Japan", "DIS - Distributors", "2026-07", "399000"],
        ["Japan", "DIS - Distributors", "2026-08", "10000"],
    ])

    cmd_reconcile([str(path)])
    lines = [l for l in capsys.readouterr().out.splitlines() if "2026-0" in l]

    assert lines and "2026-08" in lines[0]


def test_cells_the_candidate_never_produced_are_named(tmp_path, capsys, against_spec):
    """Silence is the failure a percentage hides: a query covering two markets perfectly
    and missing thirty scores 100%."""
    from app.cli import cmd_reconcile

    path = _candidate(tmp_path, [
        ["Japan", "DIS - Distributors", "2026-07", "400000"],
    ])

    cmd_reconcile([str(path)])

    assert "Rien trouvé pour 1 cellules" in capsys.readouterr().out


def test_only_the_asked_perimeter_is_confronted(tmp_path, capsys, against_spec):
    """Retail is in the plan and is not sell-in. Counting it would flatter or damn the
    candidate for something it was never asked to produce."""
    from app.cli import cmd_reconcile

    path = _candidate(tmp_path, [
        ["Japan", "DIS - Distributors", "2026-07", "400000"],
        ["Japan", "DIS - Distributors", "2026-08", "300000"],
        ["Japan", "RET - Retail", "2026-07", "1"],
    ])

    cmd_reconcile([str(path)])
    out = capsys.readouterr().out

    assert "Cellules attendues  2" in out
    assert "Hors périmètre      1" in out


def test_market_names_are_normalised_before_confronting(tmp_path, against_spec):
    """The warehouse says one thing, the planning file another. A name mismatch would
    read as a missing market and send everyone after the wrong problem."""
    from app.cli import cmd_reconcile

    path = _candidate(tmp_path, [
        ["JAPAN", "DIS - Distributors", "2026-07", "400000"],
        ["japan", "DIS - Distributors", "2026-08", "300000"],
    ])

    assert cmd_reconcile([str(path)]) == 0


def test_a_missing_candidate_file_is_refused_clearly(tmp_path, against_spec):
    from app.cli import cmd_reconcile

    assert cmd_reconcile([str(tmp_path / "absent.csv")]) == 2
