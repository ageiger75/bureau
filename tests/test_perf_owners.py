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


def directory_file(tmp_path, rows, lookup=None, name="owners.xlsx"):
    """A directory workbook, built by hand, with invented people.

    Optionally carries a second sheet in the shape of the country lookup, which is the
    form the real directory took once it stopped needing to be interpreted.
    """
    body = "".join(_row(i + 1, values) for i, values in enumerate(rows))
    lookup_body = (
        "".join(_row(i + 1, values) for i, values in enumerate(lookup)) if lookup else ""
    )
    path = tmp_path / name
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
            'officeDocument/2006/relationships"><sheets><sheet name="Responsables" '
            'sheetId="1" r:id="rId1"/>'
            + ('<sheet name="Recherche par pays" sheetId="2" r:id="rId2"/>' if lookup else "")
            + "</sheets></workbook>",
        )
        book.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
            'openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            + (
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/worksheet" '
                'Target="worksheets/sheet2.xml"/>'
                if lookup
                else ""
            )
            + "</Relationships>",
        )
        book.writestr("xl/worksheets/sheet1.xml", SHEET % body)
        if lookup:
            book.writestr("xl/worksheets/sheet2.xml", SHEET % lookup_body)
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


# ------------------------------------------------------------ the country lookup shape
#
# The directory's better form: one row per market, naming its BU, its BU head and its GM.
# It removes this module's judgement entirely — nothing to split, expand or infer — so it
# is preferred wherever a workbook carries one.

LEADERS_HEADER = ["BU", "Niveau", "Prénom", "Nom", "Poste", "Pays couverts", "Statut"]
LOOKUP_HEADER = [
    "Pays / entité marché",
    "BU",
    "Responsable BU (MD)",
    "Responsable pays / cluster (GM)",
    "Responsable local complémentaire",
    "Commentaire",
]


@pytest.fixture
def looked_up(tmp_path):
    return directory_file(
        tmp_path,
        rows=[
            LEADERS_HEADER,
            ["EMEA", "MD", "Luc", "MARTIN", "Managing Director EMEA", "France", ""],
            ["EMEA", "GM", "Sofia", "ROSSI", "Managing Director France", "France", ""],
            ["Travel Retail", "MD", "Ines", "COSTA", "Managing Director Global TR",
             "Monde, canal Travel Retail", ""],
            ["Travel Retail", "GM", "Otto", "BRANDT", "General Manager TR EMEAA",
             "Europe, canal Travel Retail", ""],
        ],
        lookup=[
            LOOKUP_HEADER,
            ["France", "EMEA", "Luc MARTIN", "Sofia ROSSI", "", ""],
            ["Slovaquie", "EMEA", "Luc MARTIN", "", "", "Sans GM"],
            ["Thaïlande", "EMEA", "Luc MARTIN", "Sofia ROSSI", "Nok SRISAI", "Cluster"],
        ],
        name="lookup.xlsx",
    )


def test_the_market_answers_through_its_md_and_not_its_country_gm(looked_up):
    """The rule this test used to hold was the opposite, and it was wrong. This screen has
    one reader, and the people who answer to him are his MDs. Naming the country GM on the
    card proposed a conversation he does not hold, over the head of the person who does —
    politely, at every reading, with nothing to signal it."""
    assert owners.load(looked_up).owner_for("France", "GE COUNTRIES").name == "Luc MARTIN"


def test_a_market_with_no_gm_answers_to_its_bu_head(looked_up):
    """Stated by the file itself, not inferred: the GM column is simply empty."""
    assert owners.load(looked_up).owner_for("Slovakia", "GE COUNTRIES").name == "Luc MARTIN"


def test_nothing_stands_above_an_md_but_the_reader(looked_up):
    """Escalation had an object while the card named a country GM. Now that it names the
    MD, the next step up is the reader himself — and a screen that offers to escalate to
    its own reader is describing his job back to him."""
    owner = owners.load(looked_up).owner_for("France", "GE COUNTRIES")

    assert owner.escalates_to == ""


def test_a_bu_head_escalates_to_nobody(looked_up):
    assert owners.load(looked_up).owner_for("Slovakia", "GE COUNTRIES").escalates_to == ""


def test_the_person_on_the_ground_is_named_beside_the_owner_not_instead(looked_up):
    """The question goes to the MD who answers for the number; the detail stays with
    whoever runs the market day to day. Collapsing the two loses one of them — and which
    of the two is lost was the whole defect."""
    book = owners.load(looked_up)
    owner = book.owner_for("Thailand", "APAC")

    assert owner.name == "Luc MARTIN"
    # Le second nom utile ici est celui juste sous le MD — la personne qu'il amènerait.
    assert owner.local_lead == "Sofia ROSSI"
    # Et là où aucun GM ne s'interpose, le MD répond seul : pas de second nom inventé.
    assert book.owner_for("Slovakia", "GE COUNTRIES").local_lead == ""


def test_job_titles_come_from_the_leaders_sheet(looked_up):
    """The lookup names people but not their titles. "Managing Director EMEA" is a remit
    the reader recognises; "Managing Director" alone is a label."""
    assert owners.load(looked_up).owner_for("France", "GE").role == "Managing Director EMEA"


def test_a_business_unit_owning_no_country_still_has_a_head(looked_up):
    """Travel Retail runs a channel worldwide, so no country row routes to it. Its head is
    on the leaders sheet, and the two sheets are read together for exactly this case."""
    owner = owners.load(looked_up).owner_for("Anywhere", "WW TR")

    assert owner.name == "Ines COSTA"


def test_a_regional_travel_retail_gm_never_claims_a_country(looked_up):
    """Their remit is a continent within a channel, not a market. Routing France to the
    TR EMEAA GM would hand them a question about a business they do not run."""
    book = owners.load(looked_up)

    assert "BRANDT" not in book.owner_for("France", "GE COUNTRIES").name


def test_a_first_name_is_never_mistaken_for_a_surname(looked_up):
    """`nom` is a substring of `prénom`. A loose column match named everyone twice by
    their first name, which is the kind of bug that survives a reading."""
    owner = owners.load(looked_up).owner_for("Anywhere", "WW TR")

    first, _, last = owner.name.partition(" ")
    assert first != last


def test_the_czech_republic_is_named_as_the_rest_of_the_cockpit_names_it(tmp_path):
    """L'annuaire traduisait « République tchèque » en « Czechia » quand le plan et
    l'entrepôt disent « Czech Republic ». Le pays était dans le fichier, avec son MD, et
    il ressortait « sans périmètre » — une absence de jointure déguisée en absence de
    réponse."""
    book = directory_file(
        tmp_path,
        rows=[LEADERS_HEADER,
              ["EMEA", "MD", "Luc", "MARTIN", "Managing Director EMEA", "France", ""]],
        lookup=[LOOKUP_HEADER,
                ["République tchèque", "EMEA", "Luc MARTIN", "", "", ""]],
        name="lookup.xlsx",
    )

    assert owners.load(book).owner_for("Czech Republic", "GE COUNTRIES").name == "Luc MARTIN"
