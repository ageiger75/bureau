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


def test_sell_in_is_declared_absent_rather_than_left_out():
    """The whole point of the register. A missing measure is invisible by nature."""
    assert provenance.REGISTER["sell_in"].maturity == provenance.ABSENT


# ------------------------------------------------------- the caveat on the big number


def _plan(own, resold):
    lines = []
    if own:
        lines.append(BudgetLine("Japan", "APAC", "RET - Retail", "retail",
                                "2026-07", own, None))
    if resold:
        lines.append(BudgetLine("Japan", "APAC", "DIS - Distributors", "dis",
                                "2026-07", resold, None))
    return Budget(lines)


def test_the_headline_figure_says_what_it_leaves_out():
    from app.perf.source import _perimeter_note

    note = _perimeter_note(_plan(own=600.0, resold=400.0))

    assert "40%" in note
    assert "resell" in note


def test_the_share_is_read_from_the_file_not_written_into_the_code():
    """A number hard-coded into a caveat is a caveat that quietly stops being true. The
    mix changes every year; the sentence has to change with it."""
    from app.perf.source import _perimeter_note

    assert "10%" in _perimeter_note(_plan(own=900.0, resold=100.0))
    assert "70%" in _perimeter_note(_plan(own=300.0, resold=700.0))


def test_a_plan_that_is_entirely_own_channels_carries_no_caveat():
    """Silence is correct here. A caveat about nothing teaches the reader to skip caveats."""
    from app.perf.source import _perimeter_note

    assert _perimeter_note(_plan(own=1000.0, resold=0.0)) == ""


def test_no_plan_at_all_carries_no_caveat():
    from app.perf.source import _perimeter_note

    assert _perimeter_note(None) == ""
