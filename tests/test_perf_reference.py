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
