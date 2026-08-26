"""Fiscal calendar: the year runs April to March.

FY27 means April 2026 to March 2027, and Q2 FY27 means July to September 2026. Getting
this wrong would make the cockpit ask for a quarter that has not closed, or declare a
figure missing while the quarter is still running — the fastest way to teach a CEO to
ignore an alert.
"""

from __future__ import annotations

from datetime import date

#: First month of the fiscal year.
FISCAL_START_MONTH = 4


def fiscal_year(day: date) -> int:
    """FY label as a number: 1 April 2026 falls in FY27."""
    return day.year + 1 if day.month >= FISCAL_START_MONTH else day.year


def fiscal_quarter(day: date) -> int:
    """1 to 4, where Q1 is April to June."""
    return ((day.month - FISCAL_START_MONTH) % 12) // 3 + 1


def fiscal_half(day: date) -> int:
    """1 for April to September, 2 for October to March."""
    return 1 if fiscal_quarter(day) <= 2 else 2


def month_label(day: date) -> str:
    return "%04d-%02d" % (day.year, day.month)


def quarter_label(day: date) -> str:
    return "Q%d FY%02d" % (fiscal_quarter(day), fiscal_year(day) % 100)


def half_label(day: date) -> str:
    return "H%d FY%02d" % (fiscal_half(day), fiscal_year(day) % 100)


def year_label(day: date) -> str:
    return "FY%02d" % (fiscal_year(day) % 100)


def previous_month(day: date) -> date:
    """First day of the month before `day`'s month."""
    if day.month == 1:
        return date(day.year - 1, 12, 1)
    return date(day.year, day.month - 1, 1)


def previous_quarter_end(day: date) -> date:
    """A day inside the last fiscal quarter that has fully closed."""
    current = date(day.year, day.month, 1)
    while fiscal_quarter(current) == fiscal_quarter(day) and current.year == day.year:
        current = previous_month(current)
        if fiscal_quarter(current) != fiscal_quarter(day):
            break
    return current


def previous_half_end(day: date) -> date:
    current = date(day.year, day.month, 1)
    guard = 0
    while fiscal_half(current) == fiscal_half(day) and guard < 12:
        current = previous_month(current)
        guard += 1
    return current


def previous_year_end(day: date) -> date:
    return date(fiscal_year(day) - 1, FISCAL_START_MONTH - 1 or 12, 1)
