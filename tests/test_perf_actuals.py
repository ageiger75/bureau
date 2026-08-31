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


def test_the_variance_column_is_the_one_at_budget_rates():
    """The published flash quotes the actual at real rates and computes its percentages on
    the actual at budget rates. Both are presented as constant-rate figures and only the
    percentages are.

    Dividing the quoted value by the quoted percentage therefore mixes two bases — and this
    repository did exactly that, concluded the planning workbook held a different budget
    several points away, and set out to find a perimeter that does not exist. The columns
    are named here so the next reader inherits the answer rather than the mistake.
    """
    assert actuals.ACTUAL_AT == 13
    assert actuals.LAST_YEAR_AT == 14
    assert actuals.BUDGET_AT == 15
    # The real-rate column sits at 11 and is deliberately not read for the variance.
    assert actuals.ACTUAL_AT != 11


def _unit(market, channel, actual, budget, reported=None):
    from app.perf.model import BusinessUnit, Drivers, Owner

    kwargs = {}
    if reported is not None:
        kwargs = {"reported_actual": reported[0], "reported_budget": reported[1]}
    return BusinessUnit(
        key="%s-%s" % (market, channel), label=market, market=market, region="EMEA",
        channel=channel, owner=Owner("A", "B", "c@d"),
        actual=Drivers.sales_only(actual), budget=Drivers.sales_only(budget),
        last_year=Drivers.sales_only(0.0), forecast_sales=0.0, **kwargs)


def test_a_unit_takes_both_sides_from_one_source_or_neither():
    """A reported actual against a warehouse plan would be a ratio across two perimeters —
    the exact fault this screen spent weeks measuring in the other direction."""
    reported = _unit("France", "retail", 900.0, 1000.0, reported=(980.0, 1000.0))
    warehouse = _unit("Spain", "retail", 900.0, 1000.0)

    assert reported.is_reported
    assert reported.sales_actual == 980.0 and reported.sales_budget == 1000.0
    assert reported.gap_vs_budget == -20.0
    assert not warehouse.is_reported
    assert warehouse.gap_vs_budget == -100.0


def test_the_screen_says_how_much_of_it_the_accounts_cover():
    """A cockpit half on one source and half on another is honest only if it says where the
    line falls — the share decides how much of the screen may be quoted in a meeting."""
    from app.perf.model import Dataset

    data = Dataset(period_label="Sales MTD", as_of="2026-07-31", units=[
        _unit("France", "retail", 900.0, 1000.0, reported=(900.0, 1000.0)),
        _unit("Spain", "retail", 100.0, 100.0),
    ])

    assert [u.market for u in data.reported] == ["France"]
    assert round(data.reported_share, 2) == 0.90
    assert data.units[0].figure_source == "the accounts"
    assert data.units[1].figure_source == "the warehouse"


def test_several_published_rows_for_one_scope_are_summed_never_picked():
    """One market and channel can carry more than one row — two entities, or a channel sold
    and shipped. Choosing between them would show part of a business under a heading naming
    all of it."""
    read = actuals.Actuals([
        actuals.Line("China", "CHINA", "webp", actuals.SHIPPED, 100.0, 90.0, 120.0),
        actuals.Line("China", "CHINA", "webp", actuals.SOLD, 50.0, 40.0, 60.0),
    ], [])

    folded = actuals.by_scope(read)

    assert folded["China/webp"].actual == 150.0
    assert folded["China/webp"].budget == 180.0
    # Two bases under one heading is a fact about the business, and it is named.
    assert folded["China/webp"].basis == "MIXED"
