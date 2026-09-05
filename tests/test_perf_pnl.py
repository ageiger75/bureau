"""La contribution réalisée à date par périmètre, au compte de gestion.

Ces tests gardent les trois règles du fichier : un seul exercice de change est lu ; l'écriture
centrale est nommée à part et hors de tout total ; ce qui a été écarté est dit, jamais
soustrait deux fois. Toutes les valeurs sont inventées.
"""

from __future__ import annotations

from app.perf import pnl as P
from app.perf.analytics import format_eur

HEADER = ("exchange_year,snapshot_date,mois_cumules,region,ventes_keur,produits_keur,"
          "autres_ppl_keur,distribution_keur,marketing_keur,administratif_keur,autres_keur,"
          "contribution_keur,budget_ventes_keur,budget_produits_keur,budget_autres_ppl_keur,"
          "budget_distribution_keur,budget_marketing_keur,budget_administratif_keur,"
          "budget_autres_keur,budget_contribution_keur,dpl308_exclu_keur,exclusion\n")


def _row(year, date, months, region, sales, costs, contribution, bsales, bcontribution,
         excluded=0.0, exclusion=""):
    return '%s,%s,%d,%s,%s,%s,0,%s,0,0,0,%s,%s,0,0,0,0,0,0,%s,%s,"%s"\n' % (
        year, date, months, region, sales, costs[0], costs[1], contribution, bsales,
        bcontribution, excluded, exclusion)


NOTE = "DPL308 sur FRANCE x DISTRIBUTORS, hors budget et récurrent chaque mois"

FILE = HEADER + "".join([
    # L'exercice précédent, entier : jamais lu en niveau avec le suivant.
    _row("FY2026", "2026-03-01", 12, "JAPAN", 100000, (-14000, -60000), 26000, 98000, 25000),
    # Deux instantanés de l'exercice en cours : le dernier est lu, l'autre est connu.
    _row("FY2027", "2026-05-01", 2, "JAPAN", 15000, (-3000, -10000), 2000, 16000, 2500),
    _row("FY2027", "2026-06-01", 3, "JAPAN", 23548.87, (-4683.18, -15017.96), 3847.73, 24826.95, 4000),
    _row("FY2027", "2026-06-01", 3, "BRAZIL", 20000, (-3000, -19000), -2000, 20100, -500),
    _row("FY2027", "2026-06-01", 3, "GREAT.EU. EXCL SPACE", 100000, (-20000, -70000), 10000, 104000, 12000),
    _row("FY2027", "2026-06-01", 3, "SPACE", 25000, (-5000, -23000), -3000, 24000, 1000),
    _row("FY2027", "2026-06-01", 3, "FRANCE TOTAL", 35000, (-7000, -22000), 6000, 36000, 5000, 3200, NOTE),
    _row("FY2027", "2026-06-01", 3, "WW TRAVEL RETAIL", 45000, (-10000, -21000), 14000, 39000, 11000),
    _row("FY2027", "2026-06-01", 3, "INT COST", 0, (0, 0), 22876, 0, 0),
])

NAMES = ["Greater China", "North America", "APAC", "EMEA", "Japan", "Brazil"]


def _statement(tmp_path, text=FILE):
    path = tmp_path / "pnl_bu.csv"
    path.write_text(text, encoding="utf-8")
    return P.load(str(path))


def test_only_the_last_snapshot_of_the_last_exchange_year_is_read(tmp_path):
    statement = _statement(tmp_path)

    assert statement.usable
    assert statement.snapshot.exchange_year == "FY2027"
    assert statement.snapshot.date == "2026-06-01" and statement.snapshot.months == 3
    assert statement.snapshot.through == "juin 2026"
    assert statement.snapshot.period_label == "avril à juin 2026"
    assert statement.previous.date == "2026-05-01"
    assert [line.region for line in statement.lines] == [
        "JAPAN", "BRAZIL", "GREAT.EU. EXCL SPACE", "SPACE", "FRANCE TOTAL", "WW TRAVEL RETAIL"]
    assert any("2 exercices de change" in fault for fault in statement.faults)


def test_amounts_are_thousands_and_the_contribution_is_read_not_recomputed(tmp_path):
    japan = _statement(tmp_path).perimeter("Japan")

    assert abs(japan.sales - 23_548_870.0) < 1e-6
    assert abs(japan.contribution - 3_847_730.0) < 1e-6
    assert abs(japan.costs["distribution"] + 15_017_960.0) < 1e-6
    assert japan.rate_label == "16.3 %"
    assert japan.sales_index_label == "94.9 %"
    assert abs(japan.gap - (3_847_730.0 - 4_000_000.0)) < 1e-6


def test_three_regions_of_the_file_make_the_emea_of_the_screen(tmp_path):
    emea = _statement(tmp_path).perimeter("EMEA")

    assert emea.sales == 160_000_000.0
    assert emea.contribution == 13_000_000.0
    assert emea.budget_contribution == 18_000_000.0
    # L'exclusion remonte avec son montant, déjà retiré : rien n'est soustrait deux fois.
    assert emea.excluded == 3_200_000.0
    assert emea.exclusion == NOTE


def test_the_central_entry_is_named_apart_and_never_in_a_total(tmp_path):
    statement = _statement(tmp_path)

    assert [line.region for line in statement.central] == ["INT COST"]
    assert statement.total.contribution == sum(line.contribution for line in statement.lines)
    assert all(line.region != "INT COST" for line in statement.lines)
    review = P.build(statement, NAMES)
    assert "INT COST %s" % format_eur(22_876_000.0) in review.central_note
    assert "tenue à part" in review.central_note
    assert all(line.region != "INT COST" for line in review.perimeters + review.others)


def test_the_review_places_the_regions_on_the_screens_perimeters(tmp_path):
    review = P.build(_statement(tmp_path), NAMES)

    assert review.usable
    assert [line.region for line in review.perimeters] == ["EMEA", "Japan", "Brazil"]
    assert [line.region for line in review.others] == ["Travel Retail"]
    assert review.for_name("Brazil").gap == -1_500_000.0
    assert review.absent[0].startswith("2 exercices de change")
    assert "sans ligne au compte de gestion : Greater China, North America, APAC" in review.absent
    assert review.title == "Contribution à fin juin 2026"
    assert review.excluded_note.startswith("%s écartés du compte de gestion" % format_eur(3_200_000.0))
    assert NOTE in review.excluded_note


def test_without_the_file_the_review_names_it():
    review = P.build(None, NAMES)

    assert not review.usable
    assert review.absent == ["var/pnl_bu.csv absent : la contribution réalisée par BU n'est pas lue"]


def test_a_missing_column_is_a_fault_not_a_crash(tmp_path):
    statement = _statement(tmp_path, "exchange_year,region\nFY2027,JAPAN\n")

    assert not statement.usable and "colonnes manquantes" in statement.faults[0]
    assert not P.load(str(tmp_path / "nulle-part.csv")).usable
