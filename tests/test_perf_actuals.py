"""Finance's own actuals, read at the grain the plan is written in.

The figure at the top of this screen used to be derived from the warehouse and reconciled
against a published one, market by market, for weeks. This source carries the actual, last
year and the budget on one row, at one set of rates — so the variance becomes a subtraction
inside the source that decides, and every perimeter chased during that reconciliation stops
bearing on the headline.
"""

from __future__ import annotations

from app.perf import actuals


def test_the_maison_is_located_never_assumed():
    """The workbook lays its two sheets out differently, and a fixed column matched nothing
    on one of them — every row skipped, the total zero. A screen showing nothing looks
    exactly like a business doing nothing, which is the quiet kind of wrong."""
    rows = [
        ["", "", "", "", "L'Occitane en Provence", "x", "JAPAN", "APAC", "", "", "RET - Retail",
         "1", "2", "3.0", "4.0", "5.0"],
    ]
    assert actuals._locate_brand(rows, "L'Occitane en Provence") == 4

    shifted = [["", "", "", "", "", "L'Occitane en Provence", "JAPAN", "APAC", "", "",
                "RET - Retail", "1", "2", "3.0", "4.0", "5.0"]]
    assert actuals._locate_brand(shifted, "L'Occitane en Provence") == 5

    assert actuals._locate_brand(rows, "Another Maison") is None


def test_every_channel_of_the_plan_has_a_name_here():
    """Sixteen on each side, matched one to one. A channel appearing in the accounts and
    not in this table would be a hole in the screen, so it is refused rather than dropped:
    a hole that reports itself is worth more than a total that quietly narrows."""
    assert len(actuals.CHANNELS) == 16
    assert set(actuals.CHANNELS.values()) == {
        "b2b", "cafe", "copg", "dis", "direct selling", "dpt", "ecommerce", "marketplace",
        "retail", "spa", "tra", "tvc", "webp", "whoch", "whoin", "whosp",
    }


def test_the_three_bases_are_carried_never_collapsed():
    """This screen has always refused to mix sold and shipped in silence. This file is the
    first source that labels which is which, and hospitality — which nothing read before —
    arrives named rather than missing."""
    assert actuals.SOLD != actuals.SHIPPED != actuals.HOSPITALITY


def test_a_missing_file_reports_rather_than_raises():
    read = actuals.load("/nowhere/at/all.xlsx")
    assert not read.usable
    assert read.faults
