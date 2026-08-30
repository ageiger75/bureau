"""Le lecteur du reforecast, éprouvé sur la forme réelle de la feuille."""
import pytest
from app.perf import reference
from app.perf.xlsx import WorkbookError


def sheet(rows):
    return [["", "Q1- ACTUAL"], ["", "ACTUAL", "BUDGET"]] + rows


def test_a_region_is_not_added_to_the_countries_inside_it():
    read = [("AMERICA", 100.0, 90.0), ("CANADA", 30.0, 25.0), ("USA", 70.0, 65.0)]
    leaves, skipped = reference._leaves(read)
    assert [n for n, _a, _b in leaves] == ["CANADA", "USA"]
    assert skipped == ["AMERICA"]


def test_a_country_that_is_its_own_unit_is_written_twice_and_counted_once():
    read = [("BRAZIL", 60.0, 55.0), ("BRAZIL", 60.0, 55.0)]
    leaves, skipped = reference._leaves(read)
    assert len(leaves) == 1


def test_the_grand_total_is_not_a_market():
    read = [("CANADA", 30.0, 25.0), ("USA", 70.0, 65.0), ("TOTAL", 100.0, 90.0)]
    leaves, _ = reference._leaves(read)
    assert [n for n, _a, _b in leaves] == ["CANADA", "USA"]


def test_a_total_placed_after_its_members_is_also_a_total():
    """One file, two conventions. The country sheet writes a business unit and then the
    countries inside it; the grey sheet closes each block with its own total instead. A
    reader that knows only the first counts the second block twice — which is how six
    million seven hundred thousand read as ten and a half.
    """
    read = [("CHINA", 2000.0, 0.0), ("HK BULK", 1260.4, 0.0),
            ("TOTAL BULK", 3260.4, 0.0), ("CAFE 86", 737.0, 0.0)]

    leaves, skipped = reference._leaves(read)

    assert [n for n, _a, _b in leaves] == ["CHINA", "HK BULK", "CAFE 86"]
    assert skipped == ["TOTAL BULK"]


def test_the_same_money_cut_twice_is_counted_once():
    """The grey sheet states its categories, totals them, then re-cuts the identical
    amount by channel underneath. A second view of the same money is not more money."""
    rows = [
        ["GREY & CLEANING"], ["", "ACTUAL"],
        ["CHINA", 2000.0], ["HK BULK", 1260.4], ["TOTAL BULK", 3260.4],
        ["CAFE 86", 737.0], ["TOTAL", 3997.4],
        ["RETAIL WEST", 498.0], ["RETAIL EAST", 3260.4], ["OTHER", 239.0],
        ["TOTAL", 3997.4],
    ]

    found = reference._cleaning_lines(rows, 3_997_400.0)

    assert sum(amount for _n, amount in found) == pytest.approx(3_997_400.0)
    assert [n for n, _a in found] == ["CHINA", "HK BULK", "CAFE 86"]


def test_a_market_the_cockpit_reads_under_another_name_is_not_invisible():
    """Le fichier montrait un trou de quinze millions, le total un trou de quatorze, et
    rien ne reliait les deux : dix-huit millions lus par le cockpit sous des noms que le
    fichier n'emploie pas ne figuraient dans aucune ligne du tableau."""
    ref = reference.Reference([reference.Line("Atlantis", 10_000.0, 9_000.0)])

    rows = reference.compare(ref, {"Lemuria": 8_800.0})

    assert sorted(rows) == [("Atlantis", 10_000.0, 0.0), ("Lemuria", 0.0, 8_800.0)]


def test_a_market_the_cockpit_reads_as_zero_stays_out_of_the_orphan_list():
    """Zéro n'est pas un nom orphelin : c'est un marché apparié qui n'a rien vendu."""
    ref = reference.Reference([reference.Line("Portugal", 100.0, 100.0)])

    rows = reference.compare(ref, {"Portugal": 100.0, "Finland": 0.0})

    assert [market for market, _t, _o in rows] == ["Portugal"]


def test_the_mainland_bulk_line_is_named_and_not_matched_on_the_word_bulk():
    """Le fichier écrit la Chine continentale `CHINA` tout court.

    Chercher le mot « bulk » n'en trouvait qu'une sur deux, et la commande annonçait
    alors deux sources en désaccord là où elles s'accordent de près.
    """
    from app.cli import _stated_bulk

    total, unknown = _stated_bulk([
        ("CHINA", 2_000_000.0), ("HK BULK", 1_260_000.0),
        ("TOTAL DAIGOU", 2_179_000.0), ("TOTAL JD- Group", 515_000.0),
        ("CAFE 86", 737_000.0),
    ])

    assert total == 3_260_000.0
    assert unknown == []


def test_a_cleaning_line_nobody_has_classified_is_returned_rather_than_guessed():
    from app.cli import _stated_bulk

    total, unknown = _stated_bulk([("CHINA", 2_000.0), ("TOTAL SOMETHING NEW", 900.0)])

    assert total == 2_000.0
    assert unknown == ["TOTAL SOMETHING NEW"]


def test_shanghai_is_folded_into_china_because_geography_says_so():
    folded = reference.rolled_up({"Shanghai": 8_882.0, "China": 44_585.0,
                                  "Hk Local": 26.0, "Hong Kong": 27_016.0})

    assert folded == {"China": 53_467.0, "Hong Kong": 27_042.0}


def test_a_name_on_one_side_and_an_equal_shortfall_on_the_other_are_paired():
    """Luxembourg à 177 et la Belgique courte de 177 : c'est le même argent."""
    rows = [("Belgium", 977.0, 800.0), ("France", 10_384.0, 10_581.0)]

    pairs = reference.offsetting([("Luxembourg", 177.0)], rows)

    assert pairs == [("Luxembourg", "Belgium", 177.0, reference.MISSING_HERE)]


def test_a_name_on_one_side_and_an_equal_excess_on_the_other_are_also_paired():
    """La forme qui manquait, et c'était la plus grosse ligne du tableau.

    `Other` vaut 4 826 et Hong Kong est excédentaire de 4 855 : le cockpit lit bien cet
    argent, rangé chez le voisin. Ne chercher que les manques trouvait un côté et
    laissait l'autre passer pour une anomalie séparée.
    """
    rows = [("Hong Kong", 22_187.0, 27_042.0)]

    pairs = reference.offsetting([("Other", 4_826.0)], rows)

    assert pairs == [("Other", "Hong Kong", 4_826.0, reference.FILED_ELSEWHERE)]


def test_a_difference_that_does_not_match_is_left_unpaired():
    rows = [("Belgium", 977.0, 800.0)]

    assert reference.offsetting([("Luxembourg", 900.0)], rows) == []


def test_a_store_total_that_is_the_only_carrier_of_its_country_is_not_a_double_count():
    """Le suffixe seul ne dit rien.

    Dans ces pays l'entité de base porte zéro retail et le total en est le seul porteur,
    exactement comme d'autres pays portent le leur sans suffixe. Crier sur la forme du nom
    revenait à alerter sur une convention saine, à chaque exécution.
    """
    from app.cli import _double_counted

    assert _double_counted({"M_110_STR_TOT": 80_973.0, "M_101_STR_TOT": 28_144.0}) == []


def test_a_country_carrying_both_a_total_and_its_detail_is_named():
    from app.cli import _double_counted

    found = _double_counted({"M_110_STR_TOT": 80_973.0, "M_110_UNLOC": 12_000.0})

    assert found == [("110", ["M_110_STR_TOT", "M_110_UNLOC"])]


def test_an_entity_carrying_nothing_never_raises_the_alarm():
    """Une entité à zéro coexiste avec le total sans rien doubler."""
    from app.cli import _double_counted

    assert _double_counted({"M_110_STR_TOT": 80_973.0, "M_110_UNLOC": 0.0}) == []


def test_a_customer_the_file_pulls_out_is_folded_into_the_entity_that_invoices_it():
    """`OTHER` est un client travel retail que la Finance isole, rangé chez les
    distributeurs européens parce que c'est un client et non une géographie.

    Déplié, il produisait deux constats qui s'annulaient : un marché excédentaire de
    4 855 et une ligne manquante de 4 826, dont aucun n'était réel.
    """
    ref = reference.Reference([
        reference.Line("Travel retail Asia", 16_794.0, 16_000.0),
        reference.Line("Other", 4_826.0, 4_800.0),
    ])

    rows = reference.compare(ref, {"Travel retail Asia": 21_620.0})

    assert rows == [("Travel retail Asia", 21_620.0, 21_620.0)]


def test_the_distributor_business_is_one_perimeter_under_two_names():
    """Lu une semaine comme un désaccord de périmètre, et ce n'en est pas un.

    L'unité Export couvre cinquante-cinq pays de distributeurs, et les deux sources en
    détachent le Moyen-Orient de la même façon, à l'euro près. Ce qui reste de chaque côté
    est donc le même commerce, et l'écart est un écart à expliquer.
    """
    ref = reference.Reference([
        reference.Line("Middle East", 3_378.0, 3_300.0),
        reference.Line("Loi Distributors", 10_079.0, 10_000.0),
    ])

    rows = reference.compare(ref, {"Middle East": 3_378.0, "Export": 8_767.0})

    assert sorted(rows) == [("Export", 10_079.0, 8_767.0),
                            ("Middle East", 3_378.0, 3_378.0)]


def test_a_euro_market_cannot_have_a_currency_gap():
    """No rate exists between two euro sides, so the gap is a finding, not a caveat."""
    rows = [("Austria", 4_000_000.0, 1_000_000.0)]
    found = reference.beyond_the_rates(rows)
    assert [(name, why) for name, _gap, _share, why in found] == [
        ("Austria", reference.NO_CURRENCY)]


def test_a_plausible_currency_move_is_not_a_finding():
    """Seven points against a rate set months ahead is the normal state of the world."""
    rows = [("Japan", 10_000_000.0, 9_300_000.0)]
    assert reference.beyond_the_rates(rows) == []


def test_a_gap_wider_than_a_rate_can_move_is_flagged():
    rows = [("Mexico", 5_000_000.0, 4_000_000.0)]
    found = reference.beyond_the_rates(rows)
    assert [(name, why) for name, _gap, _share, why in found] == [
        ("Mexico", reference.TOO_WIDE)]


def test_a_small_market_does_not_flag_on_a_wide_percentage():
    """A third of nothing is arithmetic, and printing it would bury the real lines."""
    rows = [("Portugal", 500_000.0, 300_000.0)]
    assert reference.beyond_the_rates(rows) == []


def test_a_market_read_on_one_side_only_is_left_to_the_unmatched_names():
    """Absent is not off by a hundred per cent, and it is already reported elsewhere."""
    rows = [("Nowhere", 9_000_000.0, 0.0), ("Elsewhere", 0.0, 9_000_000.0)]
    assert reference.beyond_the_rates(rows) == []


def test_the_widest_gap_is_read_first():
    rows = [("Mexico", 5_000_000.0, 4_000_000.0),
            ("China", 40_000_000.0, 30_000_000.0)]
    assert [name for name, _g, _s, _w in reference.beyond_the_rates(rows)] == [
        "China", "Mexico"]
