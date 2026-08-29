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
    ref = reference.Reference([reference.Line("Loi Distributors", 10_000.0, 9_000.0)])

    rows = reference.compare(ref, {"Export": 8_800.0})

    assert sorted(rows) == [("Export", 0.0, 8_800.0),
                            ("Loi Distributors", 10_000.0, 0.0)]


def test_a_market_the_cockpit_reads_as_zero_stays_out_of_the_orphan_list():
    """Zéro n'est pas un nom orphelin : c'est un marché apparié qui n'a rien vendu."""
    ref = reference.Reference([reference.Line("Portugal", 100.0, 100.0)])

    rows = reference.compare(ref, {"Portugal": 100.0, "Finland": 0.0})

    assert [market for market, _t, _o in rows] == ["Portugal"]
