"""The KPI tracker read as a registry, and joined to warehouse readings.

Two failures are what these tests exist to prevent, and neither is visible on screen:
a target read where none was written, and a reading matched to the wrong row. Both produce
a confident verdict about a number nobody agreed.
"""

import zipfile
from xml.sax.saxutils import escape

import pytest

from app.perf import kpi as rules
from app.perf import kpi_registry, tracker
from app.perf.xlsx import WorkbookError


def write_workbook(path, sheets):
    """A real .xlsx on disk, written with the stdlib.

    The parsing tests below all start from rows in memory, which is the right place to
    exercise the rules — and is exactly how a typo in the file-opening path shipped once
    with a green suite. Everything between a path and those rows has to be walked at
    least once by something.
    """
    def column(index):
        name, index = "", index + 1
        while index:
            index, remainder = divmod(index - 1, 26)
            name = chr(ord("A") + remainder) + name
        return name

    def cell(row_at, col_at, value):
        ref = "%s%d" % (column(col_at), row_at + 1)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return '<c r="%s"><v>%s</v></c>' % (ref, value)
        return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (
            ref, escape(str(value)))

    parts, rels, book = [], [], []
    for number, (name, rows) in enumerate(sheets.items(), start=1):
        body = "".join(
            "<row r='%d'>%s</row>" % (
                at + 1,
                "".join(cell(at, col, value)
                        for col, value in enumerate(row) if value not in (None, "")),
            )
            for at, row in enumerate(rows)
        )
        parts.append(("xl/worksheets/sheet%d.xml" % number,
                      "<worksheetData xmlns='http://schemas.openxmlformats.org/"
                      "spreadsheetml/2006/main'><sheetData>%s</sheetData>"
                      "</worksheetData>".replace("worksheetData", "worksheet") % body))
        rels.append(
            '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet%d.xml"/>' % (number, number))
        book.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
                    % (escape(name), number, number))

    with zipfile.ZipFile(str(path), "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            "<workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main' "
            "xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/"
            "relationships'><sheets>%s</sheets></workbook>" % "".join(book))
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/"
            "relationships'>%s</Relationships>" % "".join(rels))
        for name, content in parts:
            archive.writestr(name, content)
    return path

HEADER = ["ID", "Niveau", "Propriétaire", "Périmètre", "Pilier", "KPI", "Définition",
          "Réel FY26"]


def sheet(*rows):
    return [HEADER] + [list(row) for row in rows]


# ------------------------------------------------------------------ reading a target


def test_a_target_is_read_from_the_comparison_that_states_it():
    """The operator carries the half that matters most: which way the KPI should move. A
    ceiling read as a floor inverts every verdict drawn from it."""
    assert tracker.read_target("Part des heroes ≥ 28,9 %") == (28.9, rules.UP, "%")
    assert tracker.read_target("Délai de réponse < 15 j") == (15.0, rules.DOWN, "days")
    assert tracker.read_target("Note moyenne > 4,6") == (4.6, rules.UP, "")
    assert tracker.read_target("UPT ≥ 3") == (3.0, rules.UP, "")


def test_a_definition_with_no_comparison_yields_no_target():
    """"Nombre de clients recrutés" states what is measured and not what is wanted. A
    reader that produced a number here would be inventing the commitment."""
    assert tracker.read_target("Nombre de clients recrutés sur la période") == (
        None, rules.UP, "")
    assert tracker.read_target("") == (None, rules.UP, "")


def test_a_loose_number_is_only_a_target_in_a_column_that_says_so():
    """A number inside a definition is as likely to be last year's, a threshold or a
    footnote. Only a column the sheet itself labels a target may be read bare."""
    assert tracker.read_target("Croissance de 5,3 % l'an dernier")[0] is None
    assert tracker.read_plain_target("5,3 %") == (5.3, rules.UP, "%")


def test_a_row_without_a_readable_target_is_counted_and_never_scored():
    """Scored against a target of nothing, it would read as catastrophically off — every
    month, forever, on a KPI nobody has actually set."""
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Marie", "LOEP", "Client", "Part des heroes",
         "Part du chiffre ≥ 28,9 %", 25.1],
        ["K2", "Groupe", "Marie", "LOEP", "Client", "Nouveaux clients",
         "Nombre de clients recrutés", 1_200_000.0],
    ))

    assert len(registry) == 2
    assert [entry.label for entry in registry.with_target] == ["Part des heroes"]
    assert [entry.label for entry in registry.without_target] == ["Nouveaux clients"]
    assert any("no target" in line for line in registry.refused)


def test_the_level_decides_priority_and_the_fy26_column_is_last_year():
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Marie", "LOEP", "Client", "Part des heroes", "≥ 28,9 %", 25.1],
        ["K2", "Fonction", "Luc", "LOEP", "Client", "Trafic retail", "≥ 100", 92.0],
    ))

    assert registry.entries[0].priority == rules.P1
    assert registry.entries[0].last_year == 25.1
    assert registry.entries[1].priority == rules.P3


def test_a_renamed_header_is_a_named_absence_not_an_empty_registry():
    """The sheet is maintained by people. A column re-typed in capitals, or accented
    differently, must not silently empty the panel."""
    rows = [["id", "NIVEAU", "PROPRIÉTAIRE", "Perimetre", "Pilier", "kpi", "DEFINITION",
             "Reel FY26"],
            ["K1", "Groupe", "Marie", "LOEP", "Client", "Part des heroes", "≥ 28,9 %",
             25.1]]

    registry = tracker.tracker_from_rows(rows)

    assert len(registry) == 1
    assert registry.entries[0].owner == "Marie"


def test_a_sheet_with_no_kpi_column_refuses_rather_than_returning_nothing():
    """Empty and unreadable look identical on screen and mean opposite things."""
    registry = tracker.tracker_from_rows([["A", "B"], [1, 2]])

    assert len(registry) == 0
    assert registry.refused and "No header row" in registry.refused[0]


def test_an_open_point_makes_a_kpi_provisional():
    """Heroes reads 25.1% against a stated 28.9%, and the tracker's own open-points sheet
    says why it is still being argued. The variance shows; the challenge does not — nobody
    is sent to argue about a number the business is still defining."""
    points = tracker.read_open_points([
        ["KPI", "Point"],
        ["Part des heroes", "Le référentiel produit et le chiffre RGM ne désignent pas "
                            "les mêmes produits."],
    ])
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Marie", "LOEP", "Client", "Part des heroes", "≥ 28,9 %", 25.1],
    ), open_points=points)

    built = registry.entries[0].to_kpi([rules.Reading("2026-07", 25.1)])

    assert built.definition_status == rules.PROVISIONAL
    assert not built.can_be_challenged
    assert built.question() == ""
    assert "référentiel produit" in built.withheld_reason


# ------------------------------------------------------------------ the join


def rows_for(key, *values, scope="LOEP"):
    return [[scope, key, "2026-%02d" % (month + 4), value]
            for month, value in enumerate(values)]


def test_a_reading_is_matched_by_id_before_any_label():
    """An id is a claim and a label is a coincidence. Every id gets its chance before any
    alias is allowed to take a row — otherwise an alias can shadow the row that actually
    declared itself."""
    registry = tracker.tracker_from_rows(sheet(
        ["autre", "Groupe", "Marie", "LOEP", "Client", "NPS retail boutique", "≥ 74", 72.7],
        ["nps_retail", "Groupe", "Luc", "LOEP", "Client", "Un tout autre nom", "≥ 70", 71.0],
    ))

    matched, unmatched = kpi_registry.match(registry, ["nps_retail"])

    assert unmatched == []
    assert matched["nps_retail"].owner == "Luc"


def test_a_key_nothing_claims_is_named_rather_than_attached_to_a_near_miss():
    """Four KPIs contain the word "NPS". A screen that picks one of them is worse than a
    screen that says it cannot tell."""
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Marie", "LOEP", "Client", "NPS retail", "≥ 74", 72.7],
    ))

    matched, unmatched = kpi_registry.match(
        registry, ["nps_retail", "nps_ecommerce", "review_rating"])

    assert sorted(matched) == ["nps_retail"]
    assert sorted(unmatched) == ["nps_ecommerce", "review_rating"]


def test_the_join_scores_what_it_can_and_reports_what_it_cannot():
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Marie", "LOEP", "Client", "NPS retail", "≥ 74", 72.7],
        ["K2", "Groupe", "Marie", "LOEP", "Client", "Nouveaux clients",
         "Nombre recruté", 1_000.0],
        ["K3", "Groupe", "Luc", "LOEP", "Client", "Un KPI que rien n'alimente", "≥ 5", 4.0],
    ))
    rows = (rows_for("nps_retail", 71.0, 72.98)
            + rows_for("new_clients", 900.0, 950.0)
            + rows_for("refills_wob", 7.4, 7.6))

    report = kpi_registry.join_report(registry, rows)

    assert [item.label for item in report.kpis] == ["NPS retail"]
    assert report.without_target == ["Nouveaux clients"]
    assert report.unmatched_keys == ["refills_wob"]
    assert report.without_reading == 1


def test_only_the_scope_asked_for_is_read():
    """Market rows and the group roll-up share a table. Summing them would double every
    figure, and reading a market's as the group's would be worse."""
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Marie", "LOEP", "Client", "NPS retail", "≥ 74", 72.7],
    ))
    rows = rows_for("nps_retail", 71.0) + rows_for("nps_retail", 30.0, scope="Japan")

    report = kpi_registry.join_report(registry, rows)

    assert [reading.value for reading in report.kpis[0].readings] == [71.0]


def test_a_missing_value_is_not_read_as_zero():
    """A KPI that was not measured and one that measured nothing are different facts, and
    only one of them is a finding."""
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Marie", "LOEP", "Client", "NPS retail", "≥ 74", 72.7],
    ))
    rows = [["LOEP", "nps_retail", "2026-06", None],
            ["LOEP", "nps_retail", "2026-07", 72.98]]

    report = kpi_registry.join_report(registry, rows)

    assert [reading.value for reading in report.kpis[0].readings] == [72.98]


def test_a_kpi_at_target_raises_nothing():
    """The whole point of the panel: when it holds, it is counted, not shown."""
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Marie", "LOEP", "Client", "NPS retail", "≥ 70", 72.7],
    ))

    built = kpi_registry.join(registry, rows_for("nps_retail", 72.98))

    assert built[0].status == rules.ON_TRACK
    assert rules.needing_attention(built) == []


def test_a_ceiling_kpi_above_its_target_is_the_alert_not_the_good_news():
    """"Lower is better" is not decoration. Read as a floor, a response time of 30 days
    against a ceiling of 15 comes out as a triumph."""
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Luc", "LOEP", "Client", "Délai de réponse", "< 15 j", 12.0],
    ))

    built = kpi_registry.join(registry, [["LOEP", "K1", "2026-07", 30.0]])

    assert built[0].direction == rules.DOWN
    assert built[0].status == rules.ALERT
    assert rules.needing_attention(built) == built


# ------------------------------------------------------------------ the file itself


def test_a_real_workbook_is_read_end_to_end(tmp_path):
    """Every step between a path on disk and a scored KPI, walked once.

    The rules above are tested on rows in memory, which is where they belong — and that
    is precisely how a property called as a method reached the terminal with a green
    suite behind it. A registry that raises on open is indistinguishable, from the
    screen, from a registry that is empty.
    """
    path = write_workbook(tmp_path / "suivi.xlsx", {
        "LISEZ-MOI": [["Ce classeur suit les KPI FY27."]],
        "KPI FY27": [
            HEADER,
            ["K1", "Groupe", "Marie", "LOEP", "Client", "NPS retail", "≥ 74", 72.7],
            ["K2", "Groupe", "Marie", "LOEP", "Client", "Part des heroes", "≥ 28,9 %",
             25.1],
            ["K3", "Fonction", "Luc", "LOEP", "Client", "Nouveaux clients",
             "Nombre recruté", 1_000.0],
        ],
        "POINTS OUVERTS": [
            ["KPI", "Point"],
            ["Part des heroes",
             "Le référentiel produit et le chiffre RGM ne désignent pas les mêmes "
             "produits."],
        ],
    })

    registry = tracker.read_tracker(path)

    assert len(registry) == 3
    assert [entry.label for entry in registry.without_target] == ["Nouveaux clients"]
    assert registry.open_points  # the third sheet was found and read

    built = kpi_registry.join(registry, rows_for("nps_retail", 71.0, 72.98))

    assert [item.label for item in built] == ["NPS retail"]
    # 72.98 against 74 is 1.4% short: inside the tracker's own watch band, so it is
    # shown and not raised as an alert. The distinction is the panel's whole value.
    assert built[0].status == rules.WATCH
    assert built[0].owner == "Marie"

    # And the open point reached the KPI it names, through the file rather than a fixture.
    heroes = kpi_registry.join(registry, rows_for("heroes_wob", 25.1))
    assert heroes[0].definition_status == rules.PROVISIONAL


def test_a_workbook_with_no_kpi_sheet_says_which_sheets_it_found(tmp_path):
    """Refusing by name, so the next step is obvious. "No KPI sheet" with nothing else
    sends someone to look at a file they cannot see from here."""
    path = write_workbook(tmp_path / "autre.xlsx", {
        "Budget": [["A", "B"]],
        "Notes": [["C"]],
    })

    with pytest.raises(WorkbookError) as raised:
        tracker.read_tracker(path)

    assert "Budget" in str(raised.value) and "Notes" in str(raised.value)


def test_a_kpi_sheet_under_another_name_is_still_found(tmp_path):
    """The sheet is named by people. Never by position, though: a sheet added in front
    would silently redirect the whole registry to the wrong table."""
    path = write_workbook(tmp_path / "suivi.xlsx", {
        "Garde": [["Sommaire"]],
        "KPI FY28 (v2)": [
            HEADER,
            ["K1", "Groupe", "Marie", "LOEP", "Client", "NPS retail", "≥ 74", 72.7],
        ],
    })

    registry = tracker.read_tracker(path)

    assert [entry.label for entry in registry.entries] == ["NPS retail"]
