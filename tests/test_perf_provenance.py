"""How settled each figure is, and whether the screen says so.

The cockpit is being read before the data behind it is finished. That is the right call —
waiting for a complete warehouse would mean waiting a year — but it creates one specific
danger, and this file exists to close it: a screen where a checked number and an unchecked
one look identical.
"""

from __future__ import annotations

from app.perf import provenance
from app.perf.budget import Budget, BudgetLine


def test_every_measure_declares_a_state():
    """A measure added without one is a measure whose author did not ask the question."""
    for key, item in provenance.REGISTER.items():
        assert item.maturity in (provenance.VALIDATED, provenance.BETA, provenance.ABSENT)
        assert item.key == key
        assert item.label.strip()
        assert item.note.strip()


def test_anything_unsettled_says_what_would_settle_it():
    """A beta or absent measure with nothing to confirm is a measure nobody owns."""
    for item in provenance.unsettled():
        assert item.to_confirm.strip(), item.key


def test_what_is_missing_outranks_what_is_merely_unconfirmed():
    """A wrong number can be argued with. An absent one cannot: nothing on a screen says
    'the thing you are not seeing'."""
    states = [item.maturity for item in provenance.unsettled()]

    assert states == sorted(states, key=lambda s: provenance.ORDER[s])


def test_the_plan_is_the_one_thing_that_reconciles():
    """It is checked against the consolidated pack, so a disagreement is a bug, not a
    discussion. Nothing else on the screen has that standing yet."""
    assert provenance.REGISTER["sales_budget"].maturity == provenance.VALIDATED


def test_a_measure_is_promoted_only_when_something_attests_to_it():
    """Sell-in stopped being absent the day it reconciled with the plan's own actuals, and
    not a day earlier. Promotion is edited by hand for exactly this reason: a query being
    written is not evidence that it is right."""
    sell_in = provenance.REGISTER["sell_in"]

    assert sell_in.maturity == provenance.BETA
    assert "reconcile" in sell_in.note
    assert sell_in.to_confirm.strip()


def test_nothing_is_validated_on_the_strength_of_working():
    """Only the plan carries that standing, because it is checked against a pack the
    organisation publishes. Everything else is at best beta."""
    validated = [m.key for m in provenance.REGISTER.values() if m.is_settled]

    assert validated == ["sales_budget"]


# ------------------------------------------------------- the caveat on the big number


class _Unit:
    """Just enough of a business unit for the caveat: it only reads the channel."""

    def __init__(self, channel):
        self.channel = channel


def _plan(retail=0.0, ecommerce=0.0, resold=0.0):
    lines = []
    if retail:
        lines.append(BudgetLine("Japan", "APAC", "RET - Retail", "retail",
                                "2026-07", retail, None))
    if ecommerce:
        lines.append(BudgetLine("Japan", "APAC", "EBU - E-business", "ecommerce",
                                "2026-07", ecommerce, None))
    if resold:
        lines.append(BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                                "2026-07", resold, None))
    return Budget(lines)


def test_the_caveat_describes_the_channels_actually_present():
    """The failure this replaces: a screen carrying e-commerce alone, labelled as covering
    stores too. The reader takes a subset for a collapse — which is exactly what happened
    the first time the real screen was opened."""
    from app.perf.source import _perimeter_note

    note = _perimeter_note(
        _plan(retail=600.0, ecommerce=100.0, resold=300.0),
        units=[_Unit("ecommerce")],
    )

    assert note.startswith("E-commerce only")
    assert "retail" not in note.split(".")[0].lower()


def test_the_share_counts_only_what_the_screen_can_see():
    """Own e-commerce is 100 of a 1000 plan, so the figure covers 10% — not the 70% that
    own channels represent, because stores are not in this data."""
    from app.perf.source import _perimeter_note

    note = _perimeter_note(
        _plan(retail=600.0, ecommerce=100.0, resold=300.0),
        units=[_Unit("ecommerce")],
    )

    assert "10%" in note


def test_the_share_is_read_from_the_file_not_written_into_the_code():
    """A number hard-coded into a caveat is a caveat that quietly stops being true. The
    mix changes every year; the sentence has to change with it."""
    from app.perf.source import _perimeter_note

    small = _perimeter_note(_plan(ecommerce=100.0, resold=900.0), [_Unit("ecommerce")])
    large = _perimeter_note(_plan(ecommerce=700.0, resold=300.0), [_Unit("ecommerce")])

    assert "10%" in small
    assert "70%" in large


def test_both_own_channels_present_says_so():
    from app.perf.source import _perimeter_note

    note = _perimeter_note(
        _plan(retail=600.0, ecommerce=100.0, resold=300.0),
        units=[_Unit("retail"), _Unit("ecommerce")],
    )

    assert note.startswith("E-commerce and store sales only")
    assert "70%" in note


def test_a_channel_on_screen_is_never_listed_among_the_things_not_measured():
    """The contradiction this replaces: the sentence named its covered channels from what
    was on screen and its excluded ones from a fixed list, so the day stores arrived it
    announced "own retail and e-commerce only" and then put "store sales" among the things
    no source measures. A caveat that contradicts itself costs more than no caveat."""
    from app.perf.source import _perimeter_note

    note = _perimeter_note(
        _plan(retail=600.0, ecommerce=100.0, resold=300.0),
        units=[_Unit("retail"), _Unit("ecommerce")],
    )

    head, _, tail = note.partition("The rest is")

    assert "store sales" in head
    assert "store sales" not in tail


def test_the_share_counts_every_channel_on_screen():
    """Marketplace revenue was on screen and outside the counted share, because the share
    asked whether a segment was "own" rather than whether it was visible."""
    from app.perf.budget import Budget, BudgetLine
    from app.perf.source import _perimeter_note

    plan = Budget([
        BudgetLine("Japan", "APAC", "EBU - E-business", "ecommerce",
                   "2026-07", 100.0, None),
        BudgetLine("Japan", "APAC", "MKTP - Market place", "marketplace",
                   "2026-07", 100.0, None),
        BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                   "2026-07", 800.0, None),
    ])

    note = _perimeter_note(plan, [_Unit("ecommerce"), _Unit("marketplace")])

    assert "20%" in note


def test_what_is_left_out_is_named_rather_than_gestured_at():
    """"Everything else" tells the reader nothing they can act on."""
    from app.perf.source import _perimeter_note

    note = _perimeter_note(_plan(ecommerce=100.0, resold=900.0), [_Unit("ecommerce")])

    assert "distributors" in note


def test_no_units_at_all_carries_no_caveat():
    """A caveat about nothing teaches the reader to skip caveats."""
    from app.perf.source import _perimeter_note

    assert _perimeter_note(_plan(ecommerce=100.0), units=[]) == ""


def test_no_plan_still_names_the_channels():
    """Without the file there is no share to quote, but which channels are on screen is a
    fact about the data itself and stays worth saying."""
    from app.perf.source import _perimeter_note

    assert _perimeter_note(None, [_Unit("ecommerce")]) == "E-commerce only."


def test_near_complete_coverage_names_the_gap_not_the_contents():
    """Eleven channel names read as noise, and bury the one fact worth having. The first
    screen with sell-in wired said "Dis, dpt, e-commerce, marketplace sales, store sales,
    tra, tvc, webp, whoch, whoin and whosp only" — accurate, and unreadable."""
    from app.perf.budget import Budget, BudgetLine
    from app.perf.source import _perimeter_note

    plan = Budget([
        BudgetLine("Japan", "APAC", "RET - Retail", "retail", "2026-07", 900.0, None),
        BudgetLine("Japan", "APAC", "DIS - Distributors", "dis", "2026-07", 70.0, None),
        BudgetLine("Japan", "APAC", "B2B - B2B", "b2b", "2026-07", 30.0, None),
    ])

    note = _perimeter_note(plan, [_Unit("retail"), _Unit("dis")])

    assert note.startswith("Every channel except B2B")
    assert "97%" in note
    assert "dis" not in note


def test_a_planning_code_never_reaches_the_sentence():
    """`Whoch` and `Webp` are abbreviations from a spreadsheet, printed where a reader
    expects the name of a business."""
    from app.perf.budget import Budget, BudgetLine
    from app.perf.source import _perimeter_note

    plan = Budget([
        BudgetLine("Japan", "APAC", "WHOCH - Chains Wholesale", "whoch",
                   "2026-07", 300.0, None),
        BudgetLine("Japan", "APAC", "DIS - Distributors", "dis", "2026-07", 700.0, None),
    ])

    note = _perimeter_note(plan, [_Unit("whoch")])

    assert "chain wholesale" in note.lower()
    assert "whoch" not in note.lower()


def test_full_coverage_says_so_plainly():
    from app.perf.budget import Budget, BudgetLine
    from app.perf.source import _perimeter_note

    plan = Budget([
        BudgetLine("Japan", "APAC", "RET - Retail", "retail", "2026-07", 900.0, None),
    ])

    assert _perimeter_note(plan, [_Unit("retail")]) == "Every channel the plan commits to."
