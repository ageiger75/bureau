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

    matched, unmatched, _ = kpi_registry.match(registry, ["nps_retail"])

    assert unmatched == []
    assert matched["nps_retail"].owner == "Luc"


def test_a_key_nothing_claims_is_named_rather_than_attached_to_a_near_miss():
    """Four KPIs contain the word "NPS". A screen that picks one of them is worse than a
    screen that says it cannot tell."""
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Marie", "LOEP", "Client", "NPS retail", "≥ 74", 72.7],
    ))

    matched, unmatched, _ = kpi_registry.match(
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
    assert [line.split(" (")[0] for line in report.without_target] == ["Nouveaux clients"]
    assert "no target" in report.without_target[0]
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


def test_the_group_reading_is_scored_against_the_group_target():
    """The sheet holds `Heroes WOB` twice — 30% for the group, 25% for a business unit.
    Matched on the name alone, a group reading of 25.1% is scored against whichever row
    the spreadsheet happened to sort first: against 25 it holds, against 30 it misses.
    The perimeter decides, never the order.
    """
    registry = tracker.tracker_from_rows(sheet(
        ["K9", "BU", "Luc", "Japan", "Client", "Heroes WOB", "≥ 25", 24.0],
        ["K1", "Groupe", "Marie", "LOEP", "Client", "Heroes WOB", "≥ 30", 25.1],
    ))

    matched, _, ambiguous = kpi_registry.match(registry, ["heroes_wob"])

    assert matched["heroes_wob"].target == 30.0
    assert matched["heroes_wob"].scope == "LOEP"
    # And the fact that two rows could have claimed it is reported, not hidden: the same
    # name carrying two targets is a question for whoever maintains the sheet.
    assert ambiguous == ["heroes_wob"]


def test_a_market_reading_takes_that_market_row():
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Marie", "LOEP", "Client", "Heroes WOB", "≥ 30", 25.1],
        ["K9", "BU", "Luc", "Japan", "Client", "Heroes WOB", "≥ 25", 24.0],
    ))

    matched, _, _ = kpi_registry.match(registry, ["heroes_wob"], scope="Japan")

    assert matched["heroes_wob"].target == 25.0


def test_a_bare_target_on_a_name_that_reads_as_a_ceiling_withholds_the_verdict():
    """"Discount ≥ 15" is what a bare 15 becomes in a reader that defaults to "higher is
    better". On a discount rate that scores every overshoot as good news. The figure is
    shown; the verdict is not, and the reason says which number is in doubt.
    """
    # A sheet with a column the tracker itself labels a target, which is the only place a
    # bare number may be read as one.
    header = HEADER + ["Cible FY27"]
    registry = tracker.tracker_from_rows([
        header,
        ["K1", "Groupe", "Marie", "LOEP", "Client", "Discount", "", 16.0, "15"],
        ["K2", "Groupe", "Marie", "LOEP", "Client", "Heroes WOB", "", 25.1, "30"],
    ])

    discount, heroes = registry.entries
    assert discount.reads_as_ceiling
    assert not heroes.reads_as_ceiling  # a bare floor on a name that is plainly a floor

    built = discount.to_kpi([rules.Reading("2026-07", 22.0)])
    assert built.definition_status == rules.PROVISIONAL
    assert built.question() == ""
    assert "keep down" in built.withheld_reason


def test_an_operator_settles_the_direction_and_nothing_is_assumed():
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Marie", "LOEP", "Client", "Turnover retail", "≤ 20", 22.0],
    ))

    entry = registry.entries[0]
    assert entry.direction == rules.DOWN
    assert not entry.direction_assumed
    assert entry.to_kpi([rules.Reading("2026-07", 25.0)]).can_be_challenged


# ------------------------------------------------- the sheet as it is actually written
#
# Column for column, arrows included. Everything above tests the rules; this tests that
# they are pointed at the right cells — which is the half that was wrong on the first run
# against the real file, with the suite green.

REAL = ["ID", "Niveau", "Propriétaire", "Périmètre", "Pilier", "KPI", "Définition / base",
        "Réel FY26", "Cible FY27", "Cible (num)", "Unité", "Sens", "Fréquence", "Source",
        "Déf.", "avr-26", "mai-26", "juin-26", "juil-26", "août-26", "sept-26", "oct-26",
        "nov-26", "déc-26", "janv-27", "févr-27", "mars-27", "Dernier réel",
        "Écart vs cible", "Statut"]


def real_row(**over):
    row = {
        "ID": 2.0, "Niveau": "Maison", "Propriétaire": "Julie", "Périmètre": "LOEP",
        "Pilier": "3P Profit", "KPI": "Net sales hors cleaning",
        "Définition / base": "Périmètre healthy", "Réel FY26": "1 209",
        "Cible FY27": "1 259 (+4%)", "Cible (num)": 1259.0, "Unité": "M€", "Sens": "↑",
        "Fréquence": "Mensuel", "Source": "Finance / Revenue", "Déf.": "Verrouillé",
    }
    row.update(over)
    return [row.get(name) for name in REAL]


def test_the_numeric_target_column_wins_over_the_sentence_beside_it():
    """"1 259 (+4%)" is a sentence about a target. `Cible (num)` is the target."""
    registry = tracker.tracker_from_rows([REAL, real_row()])

    entry = registry.entries[0]
    assert entry.target == 1259.0
    assert entry.unit == "M€"
    assert entry.priority == rules.P1  # "Maison" is a board-level KPI
    assert entry.last_year == 1209.0  # read through the thin space


def test_the_arrow_column_settles_the_direction():
    """The sheet writes ↑ and ↓. A reader that does not understand the arrow is worse than
    one with no column at all: the cell is not empty, so nothing falls back to caution."""
    up = tracker.tracker_from_rows([REAL, real_row()]).entries[0]
    down = tracker.tracker_from_rows([REAL, real_row(
        KPI="Discount", **{"Sens": "↓", "Cible (num)": 15.0, "Unité": "%"})
    ]).entries[0]

    assert up.direction == rules.UP and not up.direction_assumed
    assert down.direction == rules.DOWN and not down.direction_assumed
    # And nothing is withheld: the sheet said which way it goes, so the verdict stands.
    assert down.to_kpi([rules.Reading("2026-07", 22.0)]).can_be_challenged
    assert down.to_kpi([rules.Reading("2026-07", 22.0)]).status == rules.ALERT


def test_the_sheets_own_months_are_read_where_the_warehouse_gives_nothing():
    """Two thirds of this tracker is KPIs no query can compute. The twelve columns beside
    the target are the only readings they have — and they are named as reported rather
    than measured, because a figure typed into a sheet is a different claim."""
    registry = tracker.tracker_from_rows([REAL, real_row(
        KPI="Engagement People", **{"Cible (num)": 80.0, "Unité": "score",
                                    "avr-26": 74.0, "mai-26": 76.0, "juin-26": None})])

    built = registry.entries[0].to_kpi()

    assert [(r.period, r.value) for r in built.readings] == [
        ("2026-04", 74.0), ("2026-05", 76.0)]
    assert "not measured" in built.source


def test_a_warehouse_reading_beats_the_sheets_own():
    """Measured beats typed, and the two are never merged."""
    registry = tracker.tracker_from_rows([REAL, real_row(**{"avr-26": 1000.0})])

    built = registry.entries[0].to_kpi([rules.Reading("2026-07", 1240.0)])

    assert [r.value for r in built.readings] == [1240.0]
    assert built.source == "Finance / Revenue"


def test_a_target_stated_in_words_is_no_target():
    """"> marché" is a real commitment and not a computable one. Counted, never scored:
    the alternative is inventing the market's growth rate and scoring against it."""
    registry = tracker.tracker_from_rows([REAL, real_row(
        KPI="Nouveaux clients", **{"Cible FY27": "> marché", "Cible (num)": None,
                                   "Réel FY26": "base"})])

    entry = registry.entries[0]
    assert not entry.has_target
    assert entry.last_year is None
    assert registry.without_target == [entry]


def test_the_definition_column_decides_whether_a_challenge_is_raised():
    settled = tracker.tracker_from_rows([REAL, real_row()]).entries[0]
    open_still = tracker.tracker_from_rows([REAL, real_row(**{"Déf.": "Provisoire"})
                                            ]).entries[0]

    assert settled.to_kpi([rules.Reading("2026-07", 1.0)]).can_be_challenged
    withheld = open_still.to_kpi([rules.Reading("2026-07", 1.0)])
    assert not withheld.can_be_challenged
    assert "not mark this definition as settled" in withheld.withheld_reason


def test_the_perimeter_column_separates_five_rows_of_the_same_name():
    """`Nouveaux clients` appears at LOEP, EMEA, NA and twice for China, with different
    targets and different units. The group reading must take the group's row."""
    rows = [REAL,
            real_row(KPI="Nouveaux clients", **{"Périmètre": "LOEP", "Niveau": "Maison",
                                                "Cible (num)": None,
                                                "Cible FY27": "> marché"}),
            real_row(KPI="Nouveaux clients", **{"Périmètre": "EMEA", "Niveau": "BU",
                                                "Cible (num)": 4.0, "Unité": "%"}),
            real_row(KPI="Nouveaux clients", **{"Périmètre": "NA", "Niveau": "BU",
                                                "Cible (num)": 722.0,
                                                "Unité": "k clients"})]
    registry = tracker.tracker_from_rows(rows)

    group, _, _ = kpi_registry.match(registry, ["new_clients"])
    assert group["new_clients"].scope == "LOEP"

    america, _, _ = kpi_registry.match(registry, ["new_clients"], scope="NA")
    assert america["new_clients"].target == 722.0


def test_the_warehouse_hands_back_dictionaries_and_they_are_read_by_name():
    """`warehouse.rows` returns one dict per row, keyed by column name; the disk cache and
    these tests hand back sequences. A positional read of a mapping does not fail here —
    it fails two minutes into a query, on the one machine that has the data.
    """
    registry = tracker.tracker_from_rows(sheet(
        ["K1", "Groupe", "Marie", "LOEP", "Client", "NPS retail", "≥ 74", 72.7],
    ))
    as_dicts = [
        {"SCOPE": "LOEP", "KPI_KEY": "nps_retail", "PERIOD": "2026-06", "VALUE": 71.0},
        {"scope": "LOEP", "kpi_key": "nps_retail", "period": "2026-07", "value": 72.98},
        {"scope": "Japan", "kpi_key": "nps_retail", "period": "2026-07", "value": 30.0},
    ]

    built = kpi_registry.join(registry, as_dicts)

    assert [reading.value for reading in built[0].readings] == [71.0, 72.98]


def test_the_labels_this_tracker_actually_uses_are_claimed():
    """Written against the real sheet: `Traffic` alone, `Reviews sur relances`,
    `Net sales hors cleaning`, `Same-store sales Groupe`. An alias list is only worth
    what the file it is pointed at says."""
    registry = tracker.tracker_from_rows(sheet(
        ["1", "Maison", "Julie", "LOEP", "3P", "Net sales hors cleaning", "≥ 1259", 1209.0],
        ["2", "Maison", "Julie", "LOEP", "3P", "Same-store sales Groupe", "≥ 4,5", 3.0],
        ["3", "Maison", "Julie", "LOEP", "Client", "Traffic", "≥ 2", 1.0],
        ["4", "Maison", "Julie", "LOEP", "Client", "Reviews sur relances", "≥ 4,6", 4.5],
        ["5", "Maison", "Julie", "LOEP", "Client", "Heroes WOB", "≥ 30", 28.9],
        ["6", "Maison", "Julie", "LOEP", "Client", "Refills", "≥ 5,3", 5.0],
    ))

    matched, unmatched, _ = kpi_registry.match(registry, [
        "net_sales", "same_store_sales", "retail_traffic", "review_rating",
        "heroes_wob", "refills_wob", "nps_retail",
    ])

    assert sorted(matched) == ["heroes_wob", "net_sales", "refills_wob",
                               "retail_traffic", "review_rating", "same_store_sales"]
    assert matched["retail_traffic"].label == "Traffic"
    assert matched["review_rating"].label == "Reviews sur relances"
    # The sheet carries "NPS Global" and no row per survey family, so this stays unclaimed
    # rather than being attached to a KPI that measures something else.
    assert unmatched == ["nps_retail"]


def test_an_annual_amount_is_never_scored_against_one_month():
    """`Net sales hors cleaning ≥ 1 259 M€` is what the Maison intends to sell over
    twelve months. Set against one month of sales it reads as a miss of ninety-four
    percent — every month, until the year ends — and it would sit at the top of a panel
    whose whole job is to show only what is genuinely off.

    The cockpit already measures euros against the monthly plan, market by market. This
    panel is for the signals that lead them.
    """
    registry = tracker.tracker_from_rows([REAL,
        real_row(),  # Net sales hors cleaning, 1259 M€
        real_row(KPI="Refills", **{"Cible (num)": 5.3, "Unité": "%"}),
    ])

    amount, rate = registry.entries
    assert amount.is_amount and amount.scorable
    assert "year's total" in amount.scorable
    assert not rate.is_amount and rate.scorable == ""

    report = kpi_registry.join_report(registry, rows_for("refills_wob", 7.4)
                                      + rows_for("net_sales", 78_000_000.0))

    assert [item.label for item in report.kpis] == ["Refills"]
    assert any("Net sales" in line for line in report.without_target)
    # And the one that can be judged is judged: 7.4% against 5.3% holds.
    assert report.kpis[0].status == rules.ON_TRACK


def test_a_ranking_is_a_level_and_stays_scorable():
    """`EMV ranking ≤ 10` is a position, not a quantity. Rank 12 in July is rank 12,
    whatever the month — nothing about it is a year's worth."""
    registry = tracker.tracker_from_rows([REAL, real_row(
        KPI="EMV ranking", **{"Cible (num)": 10.0, "Unité": "Rang", "Sens": "↓"})])

    entry = registry.entries[0]
    assert not entry.is_amount and entry.scorable == ""
    built = entry.to_kpi([rules.Reading("2026-07", 12.0)])
    assert built.status == rules.ALERT


# ---------------------------------------------------- what the real join actually printed
#
# Both of these reached the terminal saying "On track", which is the direction that costs
# the most: a panel built to show only what is off, showing something wrong as fine.


def test_an_amount_is_never_scored_against_a_growth_target():
    """`Brand.com` carries a target of 10.2% — a growth rate. The warehouse returns the
    euros sold. Matched on the name they look like one measure; they are two, and the
    join printed "6 847 662% — on track".
    """
    registry = tracker.tracker_from_rows([REAL, real_row(
        KPI="Brand.com", **{"Cible (num)": 10.2, "Unité": "%"})])

    report = kpi_registry.join_report(
        registry, [{"scope": "LOEP", "kpi_key": "brand_com_sales",
                    "period": "2026-07", "value": 6_847_662.1}])

    assert report.kpis == []
    assert "not the same measure" in report.without_target[0]


def test_the_same_key_is_scored_when_the_units_do_agree():
    """The refusal is about the pair, not about the key: an amount against an amount is
    exactly what this should judge, once a year's readings exist to judge."""
    registry = tracker.tracker_from_rows([REAL, real_row(
        KPI="Brand.com", **{"Cible (num)": 27.2, "Unité": "M€"})])

    entry = registry.entries[0]
    assert kpi_registry._units_agree("brand_com_sales", entry) == ""
    # And it is still held back, for the other reason: a year's target, one month's reading.
    assert "year's total" in entry.scorable


def test_a_group_reading_is_refused_when_the_group_has_no_row():
    """`Brand.com` exists for EMEA and not for the Maison. Falling back to it scored a
    group reading against one region's commitment — the precise error the perimeter was
    introduced to stop, arriving through the back door of an empty group list.
    """
    registry = tracker.tracker_from_rows([REAL,
        real_row(KPI="Brand.com", **{"Niveau": "BU", "Périmètre": "EMEA",
                                     "Cible (num)": 10.2, "Unité": "%"}),
        real_row(KPI="Brand.com", **{"Niveau": "BU", "Périmètre": "APAC",
                                     "Cible (num)": 8.0, "Unité": "%"})])

    matched, unmatched, _ = kpi_registry.match(registry, ["brand_com_sales"])

    assert matched == {}
    assert unmatched == ["brand_com_sales"]

    # And EMEA's own reading still finds EMEA's row.
    scoped, _, _ = kpi_registry.match(registry, ["brand_com_sales"], scope="EMEA")
    assert scoped["brand_com_sales"].scope == "EMEA"
