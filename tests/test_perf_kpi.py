"""Managed KPIs: cadence, direction, and when a challenge must be withheld.

Each of these tests defends against a specific way of losing a CEO's trust, and each rule
comes from the KPI tracker itself rather than from an assumption about it.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.perf import fiscal
from app.perf import kpi as K

#: Mid-Q2 FY27. Every cadence test is anchored here so none of them depends on the clock.
AUGUST = date(2026, 8, 26)


def kpi(**overrides):
    base = {
        "key": "k",
        "label": "New customers",
        "definition": "Growth vs last year",
        "scope": "Japan",
        "owner": "Owner",
        "pillar": "Client Acquisition",
        "unit": "%",
        "target": 5.0,
    }
    base.update(overrides)
    return K.Kpi(**base)


# --------------------------------------------------------------------------- fiscal


def test_the_year_starts_in_april():
    assert fiscal.fiscal_year(date(2026, 4, 1)) == 2027
    assert fiscal.fiscal_year(date(2026, 3, 31)) == 2026


def test_quarters_follow_the_fiscal_year():
    assert fiscal.fiscal_quarter(date(2026, 4, 1)) == 1
    assert fiscal.fiscal_quarter(date(2026, 8, 26)) == 2
    assert fiscal.fiscal_quarter(date(2027, 1, 15)) == 4


# ----------------------------------------------------------------- direction


def test_a_positive_gap_is_always_good_news():
    """One sign convention across the cockpit, whichever way the KPI should move."""
    rising = kpi(target=5.0, readings=[K.Reading("2026-07", 6.0)])
    falling = kpi(target=20.0, direction=K.DOWN, readings=[K.Reading("2026-07", 18.0)])

    assert rising.gap > 0
    assert falling.gap > 0


def test_a_lower_is_better_kpi_above_target_is_an_alert():
    """Retail turnover over its ceiling is bad news, however the arithmetic reads."""
    turnover = kpi(
        label="Retail turnover", target=20.0, direction=K.DOWN,
        readings=[K.Reading("2026-07", 24.1)],
    )

    assert turnover.status == K.ALERT


def test_the_watch_band_matches_the_trackers_own_rule():
    """At target or better is fine, within 5% is watch, beyond is alert."""
    on_target = kpi(readings=[K.Reading("2026-07", 5.0)])
    just_under = kpi(readings=[K.Reading("2026-07", 4.8)])
    well_under = kpi(readings=[K.Reading("2026-07", 3.0)])

    assert on_target.status == K.ON_TRACK
    assert just_under.status == K.WATCH
    assert well_under.status == K.ALERT


def test_no_reading_is_not_an_alert():
    """An absent figure is an absent figure, not bad performance."""
    assert kpi(readings=[]).status == K.NO_DATA


def test_trend_is_read_in_the_direction_that_counts_as_progress():
    improving = kpi(
        target=20.0, direction=K.DOWN,
        readings=[K.Reading("2026-06", 25.0), K.Reading("2026-07", 23.0)],
    )

    assert improving.is_improving is True


# ----------------------------------------------------------------- cadence


def test_a_quarterly_kpi_is_not_late_between_readings():
    """The rule that keeps the cockpit's flags worth reading: in mid-Q2, the Q1 figure is
    the current figure, and nothing is missing."""
    quarterly = kpi(frequency=K.QUARTERLY, readings=[K.Reading("Q1 FY27", 78.0)])

    assert quarterly.expected_period(AUGUST) == "Q1 FY27"
    assert not quarterly.is_awaiting(AUGUST)


def test_a_quarterly_kpi_stuck_a_quarter_behind_is_late():
    stale = kpi(frequency=K.QUARTERLY, readings=[K.Reading("Q4 FY26", 402.0)])

    assert stale.is_awaiting(AUGUST)


def test_a_monthly_kpi_is_expected_for_the_month_that_closed():
    monthly = kpi(readings=[K.Reading("2026-07", 4.0)])

    assert monthly.expected_period(AUGUST) == "2026-07"
    assert not monthly.is_awaiting(AUGUST)


def test_a_monthly_kpi_with_no_reading_at_all_is_late():
    assert kpi(readings=[]).is_awaiting(AUGUST)


def test_a_milestone_expects_no_figure():
    """There is progress to follow, not a value to chase."""
    milestone = kpi(frequency=K.MILESTONE, target=None)

    assert milestone.expected_period(AUGUST) is None
    assert not milestone.is_awaiting(AUGUST)


# ----------------------------------------------------------------- challenge


def test_a_provisional_definition_withholds_the_challenge():
    """Sending a CEO to argue about a number nobody has agreed costs more than the insight."""
    unsettled = kpi(
        definition_status=K.PROVISIONAL,
        readings=[K.Reading("2026-07", 1.0)],
        open_question="the scoring method is not aligned across the region",
    )

    assert unsettled.status == K.ALERT        # the variance is still shown
    assert unsettled.question(AUGUST) == ""   # the question is not
    assert "not aligned" in unsettled.withheld_reason


def test_a_locked_definition_off_target_does_produce_a_question():
    settled = kpi(readings=[K.Reading("2026-07", 1.0)])

    assert settled.question(AUGUST)


def test_a_kpi_on_target_produces_no_question():
    """Silence is a valid output. A question per line would be noise."""
    assert kpi(readings=[K.Reading("2026-07", 7.0)]).question(AUGUST) == ""


def test_the_question_changes_when_the_kpi_is_recovering():
    recovering = kpi(readings=[K.Reading("2026-06", 1.0), K.Reading("2026-07", 4.0)])
    sinking = kpi(readings=[K.Reading("2026-06", 4.0), K.Reading("2026-07", 1.0)])

    assert "trajectory" in recovering.question(AUGUST)
    assert "still falling" in sinking.question(AUGUST)


def test_a_lower_is_better_kpi_is_never_told_it_is_below_target():
    """It is above its ceiling. Saying the opposite would be plainly wrong, and one wrong
    sentence costs more than ten right ones earn."""
    turnover = kpi(
        target=20.0, direction=K.DOWN,
        readings=[K.Reading("2026-06", 23.0), K.Reading("2026-07", 24.1)],
    )

    question = turnover.question(AUGUST)

    assert "below target" not in question
    assert "ceiling" in question


def test_a_kpi_merely_on_watch_stays_quiet():
    """A question per line is noise, and noise is what this screen removes."""
    watch = kpi(readings=[K.Reading("2026-07", 4.8)])

    assert watch.status == K.WATCH
    assert watch.question(AUGUST) == ""


def test_a_late_reading_is_asked_about_as_a_late_reading():
    """Asking what will move a number nobody has reported is the wrong question."""
    late = kpi(frequency=K.QUARTERLY, readings=[K.Reading("Q4 FY26", 402.0)])

    assert "late" in late.question(AUGUST)


# ----------------------------------------------------------------- selection


def test_attention_is_ordered_by_priority_then_by_distance_from_target():
    board_level = kpi(key="a", priority=K.P1, readings=[K.Reading("2026-07", 4.8)])
    function_level = kpi(key="b", priority=K.P3, readings=[K.Reading("2026-07", 1.0)])

    ordered = K.needing_attention([function_level, board_level])

    assert [item.key for item in ordered] == ["a", "b"]


def test_kpis_on_target_never_reach_the_attention_list():
    assert K.needing_attention([kpi(readings=[K.Reading("2026-07", 9.0)])]) == []


def test_value_formatting_follows_the_unit():
    assert K.format_value(kpi(unit="%"), 4.25) == "4.2%"
    assert K.format_value(kpi(unit="k clients"), 944.0) == "944k"
    assert K.format_value(kpi(unit="€"), 402.0) == "€402"
    assert K.format_value(kpi(unit="%"), None) == "—"
