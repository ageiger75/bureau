"""The directory of who owns what.

Two things are being protected here at once. The first is the product: a market with no
named owner must stay blank rather than borrow a neighbour's name — putting a real person
in front of a question they do not own is worse than saying nothing.

The second is the repository. The directory is a list of real people and their real remit,
so it lives in a local file that git ignores, exactly as the planning workbook does. The
fixture below builds its own workbook with the standard library; no real name has ever
been committed here and none should be.
"""

from __future__ import annotations

import zipfile

import pytest

from app.perf import owners

SHEET = (
    '<?xml version="1.0"?>'
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    "<sheetData>%s</sheetData></worksheet>"
)


def _cell(ref, value):
    return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, value)


def _row(index, values):
    letters = "ABCDEFGH"
    cells = "".join(
        _cell("%s%d" % (letters[i], index), v) for i, v in enumerate(values) if v
    )
    return '<row r="%d">%s</row>' % (index, cells)


def directory_file(tmp_path, rows):
    """A directory workbook, built by hand, with invented people."""
    body = "".join(_row(i + 1, values) for i, values in enumerate(rows))
    path = tmp_path / "owners.xlsx"
    with zipfile.ZipFile(path, "w") as book:
        book.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
            'package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/>'
            "</Types>",
        )
        book.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
            'openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>',
        )
        book.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships"><sheets><sheet name="Directory" '
            'sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        book.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
            'openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>',
        )
        book.writestr("xl/worksheets/sheet1.xml", SHEET % body)
    return path


HEADER = ["BU", "Prénom", "Nom", "Poste", "Pays / Zone", "Type", "Manager", "Lieu"]


@pytest.fixture
def sample(tmp_path):
    return directory_file(
        tmp_path,
        [
            ["Annuaire"],
            HEADER,
            ["Japon", "Aiko", "TANAKA", "General Manager, Japan", "Japon",
             "Patron de BU", "", "Tokyo"],
            ["Greater China", "Wei", "ZHANG", "Managing Director, China",
             "Chine + Hong Kong", "Patron de BU", "", "Shanghai"],
            ["EMEA", "Luc", "MARTIN", "Managing Director EMEA", "EMEA (multi-pays)",
             "Patron de BU", "", "Paris"],
            ["EMEA", "Sofia", "ROSSI", "General Manager France", "France",
             "GM pays", "", "Paris"],
            ["EMEA", "Nils", "BERG", "General Manager Nordics", "Nordics",
             "GM pays", "", "Stockholm"],
        ],
    )


# --------------------------------------------------------------------- reading the file


def test_the_directory_is_read_from_the_file(sample):
    assert len(owners.load(sample)) == 5


def test_a_country_gm_owns_their_country(sample):
    assert owners.load(sample).owner_for("France", "GE COUNTRIES").name == "Sofia ROSSI"


def test_a_zone_that_lists_its_countries_is_expanded(sample):
    """`Chine + Hong Kong` names its members, so both resolve."""
    book = owners.load(sample)

    assert book.owner_for("China", "CHINA").name == "Wei ZHANG"
    assert book.owner_for("Hong Kong", "CHINA").name == "Wei ZHANG"


def test_a_named_grouping_is_never_expanded_from_a_guess(sample):
    """`Nordics` does not say which countries it contains. Deciding that Sweden is in it
    would be an assumption dressed as a fact, and the person named would be answering for
    a market the file never gave them."""
    book = owners.load(sample)
    entry = book.entry_for("Sweden", "GE COUNTRIES")

    assert entry is not None
    assert entry.name != "Nils BERG"


def test_an_unlisted_market_falls_to_its_bu_head(sample):
    """Not a guess: a BU head does own an unlisted market inside their own BU."""
    assert owners.load(sample).owner_for("Slovakia", "GE COUNTRIES").name == "Luc MARTIN"


def test_a_country_gm_outranks_the_bu_head_for_the_same_market(sample):
    """Both cover France. The question goes to whoever runs it day to day."""
    assert owners.load(sample).entry_for("France", "GE COUNTRIES").level == owners.COUNTRY_GM


def test_a_market_in_no_business_unit_stays_unowned(sample):
    book = owners.load(sample)

    assert book.entry_for("Nowhereland", "") is None
    assert book.owner_for("Nowhereland", "").name == ""
    assert book.is_named(book.owner_for("Nowhereland", "")) is False


def test_the_markets_with_nobody_are_listable(sample):
    book = owners.load(sample)

    assert book.unnamed_markets(["France", "Nowhereland"]) == ["Nowhereland"]


# ------------------------------------------------------------------ when there is no file


def test_no_directory_means_no_owners_rather_than_a_crash(monkeypatch, tmp_path):
    """The names live outside the repository, so a fresh clone has none. The cockpit
    still runs; it simply cannot say who to ask."""
    from app.config import settings

    owners.reset()
    monkeypatch.setattr(
        type(settings), "owners_path", property(lambda self: tmp_path / "absent.xlsx")
    )

    assert owners.owner_for("France", "GE COUNTRIES").name == ""
    owners.reset()


def test_a_malformed_directory_does_not_take_the_cockpit_down(monkeypatch, tmp_path):
    broken = tmp_path / "owners.xlsx"
    broken.write_bytes(b"not a workbook")

    from app.config import settings

    owners.reset()
    monkeypatch.setattr(type(settings), "owners_path", property(lambda self: broken))

    assert owners.owner_for("France", "GE COUNTRIES").name == ""
    owners.reset()


def test_a_file_without_the_expected_header_is_refused(tmp_path):
    wrong = directory_file(tmp_path, [["Nom", "Ville"], ["Someone", "Paris"]])

    with pytest.raises(ValueError):
        owners.load(wrong)
