"""Le dernier reforecast de la Finance, lu comme un millésime. Ces tests gardent la
grammaire des colonnes telle que le fichier l'écrit (trois formes et deux irrégularités),
le partage réalisé / figé / prévision que le lecteur pose lui-même, la somme par périmètre
et ce qu'aucun périmètre ne porte. Tout est inventé."""

from __future__ import annotations

import zipfile

import pytest

from app.perf import reforecast as R
from app.perf.xlsx import WorkbookError
from tests.test_perf_budget import CONTENT_TYPES, _sheet

HEADERS = ["Entity", "Country", "Region", "Segment",
           "BUDGET - 2026 APR", "BUDGET- 2026 SEP", "2027.JAN - 2027 JAN",
           "REF2 - 2026 APR", "REF2 - SEPT FY27", "REF2 - 2027 JAN",
           "ACT - 2025 APR", "ACT - 2025 SEP", "ACT - 2026 JAN",
           "BUDGET - Q1", "REF2 - FY27"]

ROWS = [
    HEADERS,
    ["M_901 - Northland", "NORTHLAND", "NORTH", "RET - Retail", 100, 110, 120, 105, 100, 130, 90, 100, 110, 999, 999],
    ["M_902 - Northland", "NORTHLAND", "NORTH", "DIS - Distributors", 50, 50, 50, 60, 40, 45, 40, 40, 45, 1, 1],
    ["M_903 - Southland\xa0", "SOUTHLAND", "SOUTH", "WEBP - Web Partners", 10, 10, 10, 12, 8, 9, 10, 10, 10, 0, 0],
    ["M_904 - Other", "OTHER", "SOUTH", "DIS - Distributors", 5, 5, 5, 7, 7, 7, 4, 4, 4, 0, 0],
]


def workbook(path, sheets):
    """Un classeur à plusieurs feuilles, nommées comme la Finance les nomme."""
    names = list(sheets)
    book = ('<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships"><sheets>%s</sheets></workbook>'
            % "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (name, i + 1, i + 1)
                      for i, name in enumerate(names)))
    rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships">%s</Relationships>'
            % "".join('<Relationship Id="rId%d" Target="worksheets/sheet%d.xml" '
                      'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
                      % (i + 1, i + 1) for i in range(len(names))))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("xl/workbook.xml", book)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        for i, name in enumerate(names):
            archive.writestr("xl/worksheets/sheet%d.xml" % (i + 1), _sheet(sheets[name]))
    return path


@pytest.fixture
def vintage_path(tmp_path):
    return workbook(tmp_path / "reforecast.xlsx", {"DATA BASE": [HEADERS[:4]], "DATABASE REF2": ROWS})


def test_the_three_forms_of_a_month_and_the_two_irregularities_are_read():
    assert R.column_meaning("BUDGET - 2026 APR") == (R.BUDGET, "2026-04", "")
    assert R.column_meaning("BUDGET- 2026 SEP") == (R.BUDGET, "2026-09", "")
    assert R.column_meaning("REF2 - 2026 APR") == (R.FORECAST, "2026-04", "REF2")
    assert R.column_meaning("REF2- 2026 MAY") == (R.FORECAST, "2026-05", "REF2")
    assert R.column_meaning("REF2 - SEPT FY27") == (R.FORECAST, "2026-09", "REF2")
    assert R.column_meaning("REF2 - JAN FY27") == (R.FORECAST, "2027-01", "REF2")
    assert R.column_meaning("2027.JAN - 2027 JAN") == (R.BUDGET, "2027-01", "")
    assert R.column_meaning("ACT - 2025 APR") == (R.ACTUAL, "2025-04", "")
    # Les deux formes du classeur du plan passent aussi.
    assert R.column_meaning("BUDGET 2026.JUL") == (R.BUDGET, "2026-07", "")
    assert R.column_meaning("2025.JUL") == (R.ACTUAL, "2025-07", "")
    # Un trimestre, un total, un écart : pas un mois.
    assert R.column_meaning("BUDGET - Q1") is None
    assert R.column_meaning("REF2 - FY27") is None
    assert R.column_meaning("VAR REF2 vs BUDGET") is None


def test_the_reader_splits_the_year_itself_because_the_header_does_not(vintage_path):
    vintage = R.load(vintage_path)

    assert vintage.sheet == "DATABASE REF2" and vintage.vintage == "REF2" and vintage.number == 2
    assert vintage.fiscal_start == "2026-04" and vintage.periods[0] == "2026-04" and vintage.periods[-1] == "2027-03"
    # Deuxième reforecast : six mois réalisés, dont le sixième figé ; six en prévision.
    assert vintage.closed == ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
    assert vintage.frozen == "2026-09"
    assert vintage.ahead == ["2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03"]
    assert "avril à août réalisés" in vintage.split_sentence
    assert "septembre figé à la date du reforecast, pas le réel publié" in vintage.split_sentence
    assert "octobre à mars en prévision" in vintage.split_sentence
    assert vintage.ignored == ["BUDGET - Q1", "REF2 - FY27"] and vintage.faults == []
    # L'entité garde son code, l'espace insécable en moins ; le pays devient un marché.
    southland = [line for line in vintage.lines if line.market == "Southland"]
    assert southland and all(line.entity == "M_903" for line in southland)
    assert sorted(vintage.markets) == ["Northland", "Other", "Southland"]


def test_an_outlook_sums_the_year_its_three_pieces_and_the_two_halves(vintage_path):
    from app.perf.analytics import format_eur

    vintage = R.load(vintage_path)
    north = vintage.outlook("Nord", ["Northland"])

    assert north.usable and north.count == 6
    assert north.full_year == 480_000.0 and north.full_budget == 480_000.0 and north.gap == 0.0
    assert north.full_last_year == 425_000.0 and north.growth_label == "+12.9 %"
    assert north.closed == 165_000.0 and north.frozen == 140_000.0 and north.ahead == 175_000.0
    assert north.ahead_budget == 170_000.0 and north.ahead_last_year == 155_000.0
    assert north.ahead_growth_label == "+12.9 %" and north.ahead_plan_growth_label == "+9.7 %"
    assert north.first_half_label == "+13.0 %" and north.second_half_label == "+12.9 %"
    assert north.first_half_plan_label == "+14.8 %" and north.second_half_plan_label == "+9.7 %"
    assert north.halves_sentence.startswith("premier semestre +13.0 %, second semestre +12.9 %")
    assert "le plan disait +14.8 % puis +9.7 %" in north.halves_sentence
    assert north.sentence.startswith("%s attendus sur l'exercice, soit +%s contre le plan"
                                     % (format_eur(480_000.0), format_eur(0.0)))
    assert "octobre à mars en prévision, +12.9 % sur l'an dernier" in north.sentence

    # Le sell-in seul : les distributeurs, sous le plan.
    sell_in = vintage.outlook("Nord", ["Northland"], perimeter="sell-in")
    assert sell_in.count == 3 and sell_in.full_year == 145_000.0 and sell_in.gap == -5_000.0
    assert vintage.outlook("Personne", ["Nowhere"]).usable is False


def test_the_review_cuts_the_vintage_on_the_screens_perimeters_and_names_the_rest(vintage_path):
    known = {"Nord": {"markets": ["Northland"], "lead": ""},
             "Sud": {"markets": ["Southland"], "lead": ""},
             "Sans périmètre": {"markets": ["Other"], "lead": ""}}
    review = R.build(R.load(vintage_path), known)

    assert review.usable and [line.name for line in review.lines] == ["Nord", "Sud"]
    assert review.for_name("Nord").sell_in.full_year == 145_000.0
    assert review.for_name("Sud").all.full_year == 29_000.0 and review.for_name("Ouest") is None
    assert review.group.full_year == 530_000.0 and review.group_sell_in.full_year == 195_000.0
    assert review.unplaced == [("Other", 21_000.0)]
    assert review.unplaced_note.startswith("4 % de l'exercice au reforecast sur des lignes qu'aucun périmètre")
    assert review.unplaced_note.endswith(": Other")
    assert review.note.startswith("millésime REF2 de la Finance, exercice 2026-27 :")
    assert review.note.endswith("jamais à sa place")


def test_without_the_file_the_review_names_what_it_expects():
    review = R.build(None, {"Nord": {"markets": ["Northland"]}})
    assert not review.usable and review.lines == []
    assert review.absent == ["var/reforecast.xlsx absent : le dernier reforecast de la Finance n'est pas lu"]


def test_a_workbook_without_the_sheet_or_without_reforecast_months_is_refused(tmp_path):
    with pytest.raises(WorkbookError) as refused:
        R.load(workbook(tmp_path / "plan.xlsx", {"DATA BASE": ROWS}))
    assert "DATABASE" in str(refused.value) and "DATA BASE" in str(refused.value)

    plain = [["Entity", "Country", "Region", "Segment", "BUDGET - 2026 APR", "ACT - 2025 APR"],
             ["M_901 - Northland", "NORTHLAND", "NORTH", "RET - Retail", 100, 90]]
    with pytest.raises(WorkbookError) as refused:
        R.load(workbook(tmp_path / "ref.xlsx", {"DATABASE REF2": plain}))
    assert "Aucune colonne de reforecast" in str(refused.value)


def test_a_vintage_without_a_number_keeps_everything_as_forecast_and_says_so(tmp_path):
    rows = [["Entity", "Country", "Region", "Segment", "BUDGET - 2026 APR", "REF - 2026 APR", "ACT - 2025 APR"],
            ["M_901 - Northland", "NORTHLAND", "NORTH", "RET - Retail", 100, 105, 90]]
    vintage = R.load(workbook(tmp_path / "ref.xlsx", {"DATABASE REF": rows}))
    assert vintage.number is None and vintage.closed == [] and vintage.frozen == ""
    assert len(vintage.ahead) == 12
    assert any("millésime sans numéro" in fault for fault in vintage.faults)


# --------------------------------------------------------------------------- le terminal


def test_the_command_prints_the_split_the_perimeters_and_the_structure(vintage_path, monkeypatch, capsys):
    import shutil

    from app import cli
    from app.config import settings
    from app.perf import page as page_module

    assert cli.cmd_reforecast([]) == 2
    assert "absent" in capsys.readouterr().err

    shutil.copy(vintage_path, settings.reforecast_path)
    known = {"Nord": {"markets": ["Northland"], "lead": ""}, "Sud": {"markets": ["Southland"], "lead": ""}}
    monkeypatch.setattr(page_module, "perimeters", lambda directory, month: known)
    try:
        assert cli.cmd_reforecast([]) == 0
        out = capsys.readouterr().out
        assert "millésime REF2 de la Finance" in out and "septembre figé" in out
        assert "Nord" in out and "Groupe" in out and "+12.9 %" in out
        assert "aucun périmètre de l'écran ne porte : Other" in out
        assert cli.cmd_reforecast(["--structure"]) == 0
        out = capsys.readouterr().out
        lines = [line.strip() for line in out.splitlines()]
        assert any(line.startswith("REF2 - SEPT FY27") and line.endswith("reforecast 2026-09 · REF2")
                   for line in lines)
        assert any(line.startswith("BUDGET - Q1") and line.endswith("ignorée (pas un mois)") for line in lines)
        assert any(line.startswith("Entity") and line.endswith("clé") for line in lines)
        assert cli.cmd_reforecast(["--markets"]) == 0
        assert "Other" in capsys.readouterr().out
    finally:
        settings.reforecast_path.unlink()
