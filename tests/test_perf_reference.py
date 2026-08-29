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
