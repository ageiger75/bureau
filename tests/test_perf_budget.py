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


def test_a_sheet_declared_from_the_package_root_is_still_found(tmp_path):
    """Deux conventions coexistent pour ce chemin : relatif à la partie qui le déclare —
    « worksheets/sheet1.xml », ce qu'écrit Excel — et absolu depuis la racine du paquet,
    « /xl/worksheets/sheet1.xml », qu'écrivent d'autres outils. Préfixer les deux de la
    même façon donnait « xl/xl/… » : le classeur se lisait comme dépourvu de sa seule
    feuille, et l'annuaire disparaissait pour un slash.
    """
    path = tmp_path / "from-root.xlsx"
    rels = WORKBOOK_RELS.replace('Target="worksheets/sheet1.xml"',
                                 'Target="/xl/worksheets/sheet1.xml"')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("xl/workbook.xml", WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", _sheet([HEADERS]))

    assert read_sheet(path, "DATA BASE")[0][:2] == ["Brand", "Country"]


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
        ["Japan", "DIS - Distributors", "2025-07", "400000"],
        ["Japan", "DIS - Distributors", "2025-08", "300000"],
    ])

    assert cmd_reconcile([str(path)]) == 0
    assert "Utilisable" in capsys.readouterr().out


def test_a_rounding_difference_still_counts_as_agreement(tmp_path, against_spec):
    from app.cli import cmd_reconcile

    path = _candidate(tmp_path, [
        ["Japan", "DIS - Distributors", "2025-07", "400100"],
        ["Japan", "DIS - Distributors", "2025-08", "299500"],
    ])

    assert cmd_reconcile([str(path)]) == 0


def test_a_wrong_definition_is_refused_and_located(tmp_path, capsys, against_spec):
    """The point of the exercise. A total that lands by accident on one month cannot land
    on twelve, and the report says which one broke."""
    from app.cli import cmd_reconcile

    path = _candidate(tmp_path, [
        ["Japan", "DIS - Distributors", "2025-07", "400000"],
        ["Japan", "DIS - Distributors", "2025-08", "180000"],
    ])

    assert cmd_reconcile([str(path)]) == 1

    out = capsys.readouterr().out
    assert "2025-08" in out
    assert "En désaccord        1" in out


def test_the_biggest_gaps_come_first(tmp_path, capsys, against_spec):
    """A wrong definition shows up in money, not in cell counts: one large market off
    matters more than thirty small ones."""
    from app.cli import cmd_reconcile

    path = _candidate(tmp_path, [
        ["Japan", "DIS - Distributors", "2025-07", "399000"],
        ["Japan", "DIS - Distributors", "2025-08", "10000"],
    ])

    cmd_reconcile([str(path)])
    lines = [l for l in capsys.readouterr().out.splitlines() if "2025-0" in l]

    assert lines and "2025-08" in lines[0]


def test_cells_the_candidate_never_produced_are_named(tmp_path, capsys, against_spec):
    """Silence is the failure a percentage hides: a query covering two markets perfectly
    and missing thirty scores 100%."""
    from app.cli import cmd_reconcile

    path = _candidate(tmp_path, [
        ["Japan", "DIS - Distributors", "2025-07", "400000"],
    ])

    cmd_reconcile([str(path)])

    assert "Rien trouvé pour 1 cellules" in capsys.readouterr().out


def test_only_the_asked_perimeter_is_confronted(tmp_path, capsys, against_spec):
    """Retail is in the plan and is not sell-in. Counting it would flatter or damn the
    candidate for something it was never asked to produce."""
    from app.cli import cmd_reconcile

    path = _candidate(tmp_path, [
        ["Japan", "DIS - Distributors", "2025-07", "400000"],
        ["Japan", "DIS - Distributors", "2025-08", "300000"],
        ["Japan", "RET - Retail", "2025-07", "1"],
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
        ["JAPAN", "DIS - Distributors", "2025-07", "400000"],
        ["japan", "DIS - Distributors", "2025-08", "300000"],
    ])

    assert cmd_reconcile([str(path)]) == 0


def test_a_missing_candidate_file_is_refused_clearly(tmp_path, against_spec):
    from app.cli import cmd_reconcile

    assert cmd_reconcile([str(tmp_path / "absent.csv")]) == 2


# --------------------------------------------------- two bugs the spec file uncovered
#
# Both were found by someone writing a query against the exported specification, which is
# the only way they could have been found: neither shows up when the file is only ever
# written and never read back.


def test_an_actual_is_dated_by_the_month_it_belongs_to():
    """A budget line is labelled by the month it plans for and carries beside it the
    actual of the same month a year earlier. Exporting that actual under the plan's label
    dates April 2025 as April 2026 — a specification that misdates its own evidence, and
    whose reader has no way to notice."""
    assert budget_module.previous_year("2026-04") == "2025-04"
    assert budget_module.previous_year("2027-01") == "2026-01"


def test_a_malformed_period_is_left_alone_rather_than_mangled():
    assert budget_module.previous_year("") == ""
    assert budget_module.previous_year("nonsense") == "nonsense"


def test_the_exported_spec_carries_the_real_months(tmp_path, capsys, monkeypatch):
    from app.cli import cmd_budget
    from app.config import settings

    plan = Budget(
        [BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                    "2026-07", 500_000.0, 430_000.0)]
    )
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    target = tmp_path / "spec.csv"
    cmd_budget(["--spec", str(target)])

    written = target.read_text()

    assert "2025-07" in written
    assert "2026-07" not in written


def test_several_rows_for_one_cell_are_summed_not_overwritten():
    """A market × segment × month can carry several planning rows — a discount line
    beside a sales line. Keeping the last one made the workbook answer two different
    numbers for the same question, depending on whether the total or the lookup was
    asked."""
    plan = Budget(
        [
            BudgetLine("Japan", "APAC", "EBU - E-business", "ecommerce",
                       "2026-07", 3_000_000.0, 2_800_000.0),
            BudgetLine("Japan", "APAC", "EBU - E-business", "ecommerce",
                       "2026-07", -500_000.0, -400_000.0),
        ]
    )

    assert plan.budget_for("Japan", "ecommerce", "2026-07") == pytest.approx(2_500_000.0)
    assert plan.last_year_for("Japan", "ecommerce", "2026-07") == pytest.approx(2_400_000.0)


def test_the_lookup_and_the_total_agree():
    """The property the first version claimed and did not have. A workbook that answers
    differently depending on how it is asked cannot be a reconciliation target."""
    plan = Budget(
        [
            BudgetLine("Japan", "APAC", "EBU - E-business", "ecommerce",
                       "2026-07", 3_000_000.0, None),
            BudgetLine("Japan", "APAC", "EBU - E-business", "ecommerce",
                       "2026-07", -500_000.0, None),
        ]
    )

    assert plan.budget_for("Japan", "ecommerce", "2026-07") == pytest.approx(
        plan.total_budget("2026-07")
    )


def test_summing_absences_keeps_an_absence():
    """Absent plus absent is absent, not zero. A month nobody planned must not become a
    month planned at nothing."""
    plan = Budget(
        [
            BudgetLine("Japan", "APAC", "EBU - E-business", "ecommerce",
                       "2026-07", None, None),
            BudgetLine("Japan", "APAC", "EBU - E-business", "ecommerce",
                       "2026-07", None, None),
        ]
    )

    assert plan.budget_for("Japan", "ecommerce", "2026-07") is None


def test_a_cell_split_across_rows_is_confronted_as_one(tmp_path, monkeypatch):
    """The reconciliation had the mirror of the same bug: it expected one row and the
    candidate summed several, so a split cell could never agree."""
    from app.cli import cmd_reconcile
    from app.config import settings

    plan = Budget(
        [
            BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                       "2026-07", 500_000.0, 300_000.0),
            BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                       "2026-07", 100_000.0, 100_000.0),
        ]
    )
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    path = _candidate(tmp_path, [["Japan", "DIS - Distributors", "2025-07", "400000"]])

    assert cmd_reconcile([str(path)]) == 0


def test_the_spec_and_the_check_count_the_same_cells(tmp_path, capsys, monkeypatch):
    """They used to differ — the file wrote every planning row, the check summed them by
    key — so the same workbook announced 1 330 constraints and then expected 1 298. Both
    were defensible alone, which is the worst case: a reader comparing the two outputs
    concludes there is a bug and cannot tell which side has it."""
    from app.cli import cmd_budget, cmd_reconcile
    from app.config import settings

    plan = Budget(
        [
            BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                       "2026-07", 500_000.0, 300_000.0),
            BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                       "2026-07", 100_000.0, 100_000.0),
        ]
    )
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    target = tmp_path / "spec.csv"
    cmd_budget(["--spec", str(target)])
    announced = capsys.readouterr().out

    written = [l for l in target.read_text().strip().splitlines()[1:] if l.strip()]

    assert "Contraintes         1" in announced
    assert len(written) == 1
    # And the single written row carries the summed figure, not one of the two parts.
    assert "400000.00" in written[0]


# ------------------------------------------------------- the key the plan itself uses
#
# The plan designates its markets by a consolidation entity — M_103, M_105_TRA. That code
# is the plan's own answer to "which market does this revenue belong to". Reaching for a
# company code or a customer hierarchy instead is reaching for someone else's answer to
# the same question, and the two do not agree: eleven markets are billed by a hub and
# disappear entirely under a company-based attribution.


def test_the_entity_code_is_read_off_its_label():
    """The name after the dash drifts; the code in front of it is what consolidation
    keys on."""
    assert budget_module.entity_code("M_106_UNLOC - Far East") == "M_106_UNLOC"
    assert budget_module.entity_code("M_103 - OCC JAPAN - Total") == "M_103"
    assert budget_module.entity_code("") == ""


def test_the_spec_carries_the_join_key(tmp_path, monkeypatch):
    from app.cli import cmd_budget
    from app.config import settings

    plan = Budget([
        BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                   "2026-07", 500_000.0, 430_000.0, entity="M_103"),
    ])
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    target = tmp_path / "spec.csv"
    cmd_budget(["--spec", str(target)])

    lines = target.read_text().strip().splitlines()

    assert lines[0].startswith("entity,")
    assert lines[1].startswith("M_103,")


def test_a_candidate_can_join_on_the_entity_instead_of_the_market(tmp_path, capsys, monkeypatch):
    """A market name is typed by people and translated twice on the way here. The entity
    code is what the consolidation itself uses."""
    import csv

    from app.cli import cmd_reconcile
    from app.config import settings

    plan = Budget([
        BudgetLine("Hong Kong", "APAC", "TRA - Travel retail", "tra",
                   "2026-07", 500_000.0, 430_000.0, entity="M_105_TRA"),
    ])
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    path = tmp_path / "candidate.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entity", "segment", "period", "value"])
        # No market column at all: the entity carries the attribution on its own.
        writer.writerow(["M_105_TRA", "TRA - Travel retail", "2025-07", "430000"])

    assert cmd_reconcile([str(path)]) == 0
    assert "Jointes par entité  1" in capsys.readouterr().out


def test_a_candidate_without_an_entity_still_joins_on_the_market(tmp_path, monkeypatch):
    """The entity is a better key, not a required one."""
    import csv

    from app.cli import cmd_reconcile
    from app.config import settings

    plan = Budget([
        BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                   "2026-07", 500_000.0, 430_000.0, entity="M_103"),
    ])
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    path = tmp_path / "candidate.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["market", "segment", "period", "value"])
        writer.writerow(["Japan", "DIS - Distributors", "2025-07", "430000"])

    assert cmd_reconcile([str(path)]) == 0


def test_an_unknown_entity_falls_back_rather_than_vanishing(tmp_path, capsys, monkeypatch):
    """A candidate naming an entity the plan does not carry must not silently disappear
    into the unmatched pile without its market being tried."""
    import csv

    from app.cli import cmd_reconcile
    from app.config import settings

    plan = Budget([
        BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                   "2026-07", 500_000.0, 430_000.0, entity="M_103"),
    ])
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    path = tmp_path / "candidate.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entity", "market", "segment", "period", "value"])
        writer.writerow(["M_999_UNKNOWN", "Japan", "DIS - Distributors", "2025-07", "430000"])

    assert cmd_reconcile([str(path)]) == 0


# --------------------------------------------------- two months that cannot be separated
#
# A cumulative fact with a snapshot missing in the middle cannot say what April did as
# opposed to May. Splitting them by a rule of thumb would be the one thing worth less than
# not having them: a figure invented to fill a column. Saying so, and confronting the pair
# with the plan's own two months added together, keeps the check honest and keeps the
# months out of the "missing" pile they do not belong in.


def _pair_plan():
    return Budget([
        BudgetLine("Hong Kong", "APAC", "TRA - Travel retail", "tra",
                   "2026-04", 0.0, 300_000.0, entity="M_105_TRA"),
        BudgetLine("Hong Kong", "APAC", "TRA - Travel retail", "tra",
                   "2026-05", 0.0, 200_000.0, entity="M_105_TRA"),
        BudgetLine("Hong Kong", "APAC", "TRA - Travel retail", "tra",
                   "2026-06", 0.0, 250_000.0, entity="M_105_TRA"),
    ])


def _combined_candidate(tmp_path, rows):
    import csv

    path = tmp_path / "candidate.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entity", "segment", "period", "value"])
        writer.writerows(rows)
    return path


@pytest.fixture
def pair(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: _pair_plan())


def test_a_range_of_months_is_read_as_the_months_it_covers():
    from app.cli import _months_in

    assert _months_in("2025-04..2025-05") == ["2025-04", "2025-05"]
    assert _months_in("2025-11..2026-01") == ["2025-11", "2025-12", "2026-01"]
    assert _months_in("2025-04") == ["2025-04"]


def test_a_malformed_range_is_left_alone(pair):
    from app.cli import _months_in

    assert _months_in("not..a..range") == ["not..a..range"]


def test_two_inseparable_months_are_checked_against_their_sum(tmp_path, capsys, pair):
    from app.cli import cmd_reconcile

    path = _combined_candidate(tmp_path, [
        ["M_105_TRA", "TRA - Travel retail", "2025-04..2025-05", "500000"],
        ["M_105_TRA", "TRA - Travel retail", "2025-06", "250000"],
    ])

    assert cmd_reconcile([str(path)]) == 0

    out = capsys.readouterr().out

    assert "Mois groupés        1 figures couvrant 2 mois, dont 1 d'accord" in out


def test_a_grouped_figure_that_disagrees_is_named(tmp_path, capsys, pair):
    from app.cli import cmd_reconcile

    path = _combined_candidate(tmp_path, [
        ["M_105_TRA", "TRA - Travel retail", "2025-04..2025-05", "100000"],
        ["M_105_TRA", "TRA - Travel retail", "2025-06", "250000"],
    ])

    assert cmd_reconcile([str(path)]) == 1

    out = capsys.readouterr().out

    assert "2025-04→2025-05" in out


def test_grouped_months_are_not_also_counted_as_missing(tmp_path, capsys, pair):
    """They were checked, jointly. Reporting them as absent as well would describe a gap
    that has just been closed, and understate a candidate that did its job."""
    from app.cli import cmd_reconcile

    path = _combined_candidate(tmp_path, [
        ["M_105_TRA", "TRA - Travel retail", "2025-04..2025-05", "500000"],
        ["M_105_TRA", "TRA - Travel retail", "2025-06", "250000"],
    ])

    cmd_reconcile([str(path)])

    assert "Absentes            0" in capsys.readouterr().out


def test_a_range_covering_nothing_expected_is_reported_not_silent(tmp_path, capsys, pair):
    from app.cli import cmd_reconcile

    path = _combined_candidate(tmp_path, [
        ["M_105_TRA", "TRA - Travel retail", "2024-01..2024-02", "500000"],
    ])

    cmd_reconcile([str(path)])

    assert "Groupes sans cible  1" in capsys.readouterr().out


def test_a_grouped_disagreement_is_not_called_usable(tmp_path, capsys, pair):
    """Caught by its own test: the verdict looked only at single months, so a candidate
    whose grouped figure was five times off was still told it reproduced everything. A
    check that passes what it just flagged is worse than no check."""
    from app.cli import cmd_reconcile

    path = _combined_candidate(tmp_path, [
        ["M_105_TRA", "TRA - Travel retail", "2025-04..2025-05", "100000"],
        ["M_105_TRA", "TRA - Travel retail", "2025-06", "250000"],
    ])

    assert cmd_reconcile([str(path)]) == 1
    assert "Utilisable" not in capsys.readouterr().out


def test_grouped_months_count_towards_the_rate(tmp_path, capsys, pair):
    """A rate that ignored them would flatter or damn a candidate for a limitation of the
    source rather than for its own work."""
    from app.cli import cmd_reconcile

    path = _combined_candidate(tmp_path, [
        ["M_105_TRA", "TRA - Travel retail", "2025-04..2025-05", "500000"],
        ["M_105_TRA", "TRA - Travel retail", "2025-06", "250000"],
    ])

    cmd_reconcile([str(path)])

    assert "Taux d'accord       100.0%" in capsys.readouterr().out


# ----------------------------------------------- une vérification qui se relance seule
#
# La mesure qui a fait passer le sell-in de « non mesuré » à « bêta » venait d'un script
# jetable sur une machine. Personne d'autre ne pouvait la refaire, et personne — pas même
# son auteur — ne pouvait dire six mois plus tard si elle tenait encore. C'est une
# affirmation, pas une garantie.


def test_la_verification_depuis_lentrepot_exige_la_requete(capsys, monkeypatch):
    from app.cli import cmd_reconcile
    from app.config import settings
    from app.perf import queries

    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(type(settings), "reads_warehouse", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: _pair_plan())
    monkeypatch.setattr(queries, "SELL_IN_HISTORY", "")

    assert cmd_reconcile(["--from-warehouse"]) == 2
    assert "SELL_IN_HISTORY" in capsys.readouterr().err


def test_la_verification_depuis_lentrepot_refuse_la_source_fictive(capsys, monkeypatch):
    from app.cli import cmd_reconcile
    from app.config import settings

    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: _pair_plan())

    assert cmd_reconcile(["--from-warehouse"]) == 2
    assert "snowflake" in capsys.readouterr().err


def test_la_verification_depuis_lentrepot_confronte_les_lignes_lues(monkeypatch, capsys):
    from app.cli import cmd_reconcile
    from app.config import settings
    from app.perf import queries, warehouse

    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(type(settings), "reads_warehouse", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: _pair_plan())
    monkeypatch.setattr(queries, "SELL_IN_HISTORY", "SELECT 1")
    monkeypatch.setattr(warehouse, "rows", lambda sql, params=None, label="": [
        {"entity": "M_105_TRA", "segment": "TRA - Travel retail",
         "period": "2025-04..2025-05", "value": 500_000.0},
        {"entity": "M_105_TRA", "segment": "TRA - Travel retail",
         "period": "2025-06", "value": 250_000.0},
    ])

    assert cmd_reconcile(["--from-warehouse"]) == 0

    out = capsys.readouterr().out

    assert "Lu dans l'entrepôt  2 lignes" in out
    assert "Utilisable" in out


def test_un_echec_de_lecture_ne_fait_pas_tomber_la_commande(monkeypatch, capsys):
    from app.cli import cmd_reconcile
    from app.config import settings
    from app.perf import queries, warehouse

    def boom(sql, params=None, label=""):
        raise RuntimeError("object does not exist")

    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(type(settings), "reads_warehouse", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: _pair_plan())
    monkeypatch.setattr(queries, "SELL_IN_HISTORY", "SELECT 1")
    monkeypatch.setattr(warehouse, "rows", boom)

    assert cmd_reconcile(["--from-warehouse"]) == 2
    assert "Lecture impossible" in capsys.readouterr().err


def test_the_warehouse_suffix_joins_to_a_plan_that_omits_it(tmp_path, capsys, monkeypatch):
    """The workbook types the same entity two ways: bare `M_101` for most of them,
    suffixed `M_102_UNLOC` for a few. The consolidation always writes the suffixed
    form, so an exact match alone loses five markets — France, Germany, Hong Kong,
    New Zealand and the United States, 165 cells of real revenue. The suffix is an
    alias rather than a rule in the query: how a spreadsheet was typed is not
    something SQL should have to know.
    """
    import csv

    from app.cli import cmd_reconcile
    from app.config import settings

    plan = Budget([
        BudgetLine("France", "EMEA", "DIS - Distributors", "dis",
                   "2026-07", 300_000.0, 250_000.0, entity="M_101"),
    ])
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    path = tmp_path / "candidate.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entity", "segment", "period", "value"])
        writer.writerow(["M_101_UNLOC", "DIS - Distributors", "2025-07", "250000"])

    assert cmd_reconcile([str(path)]) == 0
    out = capsys.readouterr().out
    assert "Jointes par entité  1" in out
    assert "Absentes            0" in out


def test_the_plans_own_spelling_wins_over_the_alias(tmp_path, capsys, monkeypatch):
    """An alias must never shadow a line the plan actually wrote. Where both forms
    exist they are different markets, and quietly merging them would invent revenue."""
    import csv

    from app.cli import cmd_reconcile
    from app.config import settings

    plan = Budget([
        BudgetLine("Australia", "APAC", "DPT - Department Stores", "dpt",
                   "2026-07", 90_000.0, 80_000.0, entity="M_102_UNLOC"),
        BudgetLine("Elsewhere", "APAC", "DPT - Department Stores", "dpt",
                   "2026-07", 10_000.0, 5_000.0, entity="M_102"),
    ])
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    path = tmp_path / "candidate.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entity", "segment", "period", "value"])
        writer.writerow(["M_102_UNLOC", "DPT - Department Stores", "2025-07", "80000"])

    assert cmd_reconcile([str(path)]) == 1  # the other cell is still missing
    out = capsys.readouterr().out
    # Matched Australia on its own spelling, not merged into Elsewhere.
    assert "D'accord            1" in out
    assert "En désaccord        0" in out


def test_two_entities_on_one_market_are_added_before_being_confronted(
    tmp_path, capsys, monkeypatch
):
    """China is billed by two entities. A ranged figure from either one, compared alone
    against the market's whole cell, looks short by exactly the other's revenue — and the
    second entry then finds those cells already spent and is reported as having no target.
    That invented a multi-million divergence out of two entities that both reconcile
    exactly. They are summed first, and the label says the figure took more than one.
    """
    import csv

    from app.cli import cmd_reconcile
    from app.config import settings

    plan = Budget([
        BudgetLine("China", "CHINA", "WEBP - Web Partners", "webp",
                   "2026-04", 0.0, 1_500_000.0, entity="M_104"),
        BudgetLine("China", "CHINA", "WEBP - Web Partners", "webp",
                   "2026-05", 0.0, 3_000_000.0, entity="M_104"),
        BudgetLine("China", "CHINA", "WEBP - Web Partners", "webp",
                   "2026-04", 0.0, 1_500_000.0, entity="M_106_JDCOM"),
        BudgetLine("China", "CHINA", "WEBP - Web Partners", "webp",
                   "2026-05", 0.0, 1_500_000.0, entity="M_106_JDCOM"),
    ])
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    path = tmp_path / "candidate.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entity", "segment", "period", "value"])
        # The same market and the same inseparable pair, reached by two entities.
        writer.writerow(["M_104", "WEBP - Web Partners", "2025-04..2025-05", "4500000"])
        writer.writerow(["M_106_JDCOM", "WEBP - Web Partners", "2025-04..2025-05", "3000000"])

    exit_code = cmd_reconcile([str(path)])
    out = capsys.readouterr().out

    # 4.5m + 3m against a 7.5m market cell: one figure that agrees, not two that fail.
    assert "dont 1 d'accord" in out
    assert "sans cible" not in out
    assert exit_code == 0


def test_a_single_entity_figure_is_not_labelled_as_shared(tmp_path, capsys, monkeypatch):
    """The `+n` suffix must mean something. One entity, no suffix."""
    import csv

    from app.cli import cmd_reconcile
    from app.config import settings

    plan = Budget([
        BudgetLine("Japan", "JAPAN", "DIS - Distributors", "dis",
                   "2026-04", 0.0, 100_000.0, entity="M_103"),
        BudgetLine("Japan", "JAPAN", "DIS - Distributors", "dis",
                   "2026-05", 0.0, 200_000.0, entity="M_103"),
    ])
    monkeypatch.setattr(type(settings), "has_budget_file", property(lambda self: True))
    monkeypatch.setattr(budget_module, "load", lambda path: plan)

    path = tmp_path / "candidate.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entity", "segment", "period", "value"])
        writer.writerow(["M_103", "DIS - Distributors", "2025-04..2025-05", "300000"])

    assert cmd_reconcile([str(path)]) == 0
    out = capsys.readouterr().out
    assert "dont 1 d'accord" in out
    assert "+1" not in out


def test_hospitality_is_a_third_block_not_a_corner_of_sell_in():
    """The group budget closes on three blocks — sell-out, sell-in, and this. A hotel does
    not resell: it puts the product in the room. Recognition follows the invoice as it does
    for sell-in, but no partner carries a margin downstream, so the questions differ — room
    counts and contract renewals, not sell-through and stock cover. Folded into sell-in it
    would be asked the wrong question; left in `other` it is not asked at all."""
    from app.perf.budget import perimeter_of

    assert perimeter_of("B2B - Hospitality") == "b2b"
    assert perimeter_of("COPG - Corporate Gifts") == "b2b"
    assert perimeter_of("DIS - Distributors") == "sell-in"
    assert perimeter_of("RET - Retail") == "own"
    # QVC is genuinely sell-in and already covered: a TV channel buys to resell.
    assert perimeter_of("TVC - TV Channels") == "sell-in"


def test_travel_retail_is_not_the_country_it_is_invoiced_from():
    """Hong Kong le marché et le travel retail de Hong Kong sont deux commerces qui
    partagent une adresse de facturation.

    Repliés ensemble, un petit marché en fort recul se retrouvait dans une ligne
    plusieurs fois plus grosse, faite surtout d'aéroports et qui ne bougeait presque
    pas : la chute était
    arithmétiquement présente dans le total et impossible à voir.
    """
    from app.perf.budget import market_of

    # Une adresse de facturation, trois commerces : le marché domestique, un export
    # vendu à des distributeurs qui revendent, et le travel retail de toute l'Asie.
    assert market_of("Hong Kong", "TRA") == "Travel retail Asia"
    assert market_of("Hong Kong", "DIS") == "Hong Kong distributors"
    assert market_of("Hong Kong", "") == "Hong Kong"
    assert market_of("Hong Kong", "RET") == "Hong Kong"
    # Et pas une règle sur le segment. Ailleurs le plan sépare déjà les distributeurs
    # comme un canal de leur marché ; découper aussi le marché clé la ligne de sell-in
    # sur un plan qui n'existe pas.
    assert market_of("Japan", "DIS") == "Japan"
    # L'entité qui porte le travel retail d'aucun pays en particulier. Son libellé de pays
    # est un code d'entrepôt, et l'imprimer demanderait au lecteur de connaître un nom
    # interne pour lire un chiffre.
    assert market_of("Loi Tr", "TRA") == "Travel retail international"


def test_a_row_already_named_travel_retail_is_not_renamed_twice():
    """Une même entité étiquette ses lignes de deux façons : `HK` sur l'une, `HK TR` sur
    la suivante. La seconde est déjà nommée par la table d'alias, et la préfixer encore
    a produit « Travel retail Travel retail Asia » sur un écran en service.
    """
    from app.perf.budget import market_of

    assert market_of("HK TR", "TRA") == "Travel retail Asia"
    assert market_of("LOI TR", "TRA") == "Travel retail international"
    assert market_of("Travel retail Asia", "TRA") == "Travel Retail Asia"


def test_a_market_drilldown_names_what_exists_instead_of_rendering_nothing():
    """Un marché mal orthographié et un marché absent du plan se ressemblent trop.

    Le drapeau était accepté et ignoré en silence : la commande imprimait le total du
    groupe, et le lecteur croyait regarder un marché. Un drapeau ignoré sans un mot est
    pire qu'un drapeau refusé.
    """
    import io
    import contextlib

    from app.cli import _print_planned_market
    from app.perf.budget import Budget, BudgetLine

    plan = Budget([BudgetLine(market="France", region="EMEA", segment="RET - Retail",
                              channel="retail", period="2026-04", budget=100.0,
                              last_year=90.0, entity="M_101")])

    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code = _print_planned_market(plan, "Atlantide")

    assert code == 2
    assert "France" in err.getvalue()


def test_a_market_drilldown_shows_each_channel_month_by_month():
    """Une sortie de canal planifiée se lit dans la forme de la série, pas dans un total.

    Un canal plein en début d'année et vide à la fin dit une fermeture programmée ; le
    même canal plat dit que le plan ne la porte pas — et l'écran montrerait alors un
    marché en échec sur ce qu'on lui a demandé de faire.
    """
    import io
    import contextlib

    from app.cli import _print_planned_market
    from app.perf.budget import Budget, BudgetLine

    def line(channel, period, amount):
        return BudgetLine(market="France", region="EMEA", segment="X", channel=channel,
                          period=period, budget=amount, last_year=amount, entity="M_101")

    plan = Budget([
        line("retail", "2026-04", 100.0), line("retail", "2026-05", 110.0),
        line("dis", "2026-04", 50.0), line("dis", "2026-05", 0.0),
    ])

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = _print_planned_market(plan, "France")

    printed = out.getvalue()
    assert code == 0
    assert "dis" in printed and "retail" in printed
    assert "2026-04" in printed and "2026-05" in printed


def test_the_plan_lists_the_pairs_it_carries_not_the_grid():
    """A market selling through two channels has two scopes, never every channel.

    The list leaves this machine for someone who must judge each pair, so a grid would
    ask them to rule on business that does not exist.
    """
    plan = Budget([
        BudgetLine("France", "EMEA", "RET", "retail", "2026-04", 10.0, 9.0),
        BudgetLine("France", "EMEA", "EBU", "ecommerce", "2026-04", 20.0, 19.0),
        BudgetLine("Japan", "APAC", "RET", "retail", "2026-04", 30.0, 29.0),
        BudgetLine("Japan", "APAC", "RET", "retail", "2026-05", 31.0, 30.0),
    ])
    assert plan.scopes() == [
        ("France", "ecommerce"), ("France", "retail"), ("Japan", "retail")]
    assert plan.channels() == ["ecommerce", "retail"]


def test_the_plan_totals_by_region_over_chosen_periods():
    """A variance has two terms, and this exposes the one nobody checks."""
    plan = Budget([
        BudgetLine("France", "EMEA", "RET", "retail", "2026-04", 10.0, 9.0),
        BudgetLine("France", "EMEA", "EBU", "ecommerce", "2026-04", 20.0, 19.0),
        BudgetLine("Japan", "APAC", "RET", "retail", "2026-04", 30.0, 29.0),
        BudgetLine("Japan", "APAC", "RET", "retail", "2026-05", 31.0, 30.0),
    ])
    one = {}
    for line in plan.lines:
        if line.period == "2026-04":
            one[line.region] = one.get(line.region, 0.0) + (line.budget or 0.0)
    assert one == {"EMEA": 30.0, "APAC": 30.0}


def test_the_plan_says_which_maisons_it_summed():
    """Two Maisons trade in the same country under names a reader shortens the same way.
    Nothing here filters on brand, so a workbook carrying two would be summed in silence —
    and a plan is the denominator of every variance on the screen."""
    plan = Budget([BudgetLine("Brazil", "BRAZIL", "RET", "retail", "2026-04", 10.0, 9.0)],
                  brands=["L'Occitane en Provence", "L'Occitane au Brésil"])
    assert plan.brands == ["L'Occitane au Brésil", "L'Occitane en Provence"]

    quiet = Budget([BudgetLine("Brazil", "BRAZIL", "RET", "retail", "2026-04", 10.0, 9.0)])
    assert quiet.brands == []
