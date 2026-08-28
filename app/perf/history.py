"""Twenty-four months behind the month on the screen.

A cockpit that reads one month against one plan is at the mercy of the calendar. A
shipment that slips across a month end shows as a collapse and then a rebound, and
neither happened. Everything in this module exists to put a month back into the series it
belongs to, and it answers three questions the single-month view cannot:

* **How long?** — how many consecutive months this business has been below its plan.
* **Which way?** — whether the gap is widening or closing.
* **How much, so far this year?** — the fiscal year to date, summed honestly.

"Summed honestly" is the whole difficulty of the third one. The history joins actuals to
plans with a full outer join, and on real data a quarter of the rows come back with one
side missing: revenue nobody budgeted, and plans nothing was sold against. Adding the
first into a total and comparing it to a plan that never covered it overstates performance
by more than half. So the year-to-date figure here sums *matched pairs only* and reports
the two unmatched amounts beside it, where they can be seen rather than absorbed.

The plan in this history is the warehouse's goals fact, not the planning workbook: the
workbook covers the current fiscal year, and a ratio computed across two different
definitions of "plan" would be an artefact rather than a trend. Where the two overlap they
are checked against each other, and a series whose two plans disagree carries no verdict.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from . import fiscal
from .mapping import fold_rows

#: A run this long, at a ratio this steady, is not a gap that opened. A full year, because
#: anything shorter cannot tell a mis-set plan from a seasonal one: a plan that is too high
#: for the winter and right for the summer is a different problem, and a six-month window
#: would call it chronic every winter.
CHRONIC_WINDOW = 12

#: How much the ratio may move across that run and still count as steady. Twelve points is
#: wide enough to survive a real business's monthly noise and narrow enough that a genuine
#: deterioration — which travels — falls out of it.
CHRONIC_SPREAD = 0.12

#: Below this, a steady ratio is not a plan set slightly high; it is a business delivering
#: two thirds of what it promised, and calling that a planning error would excuse it.
CHRONIC_FLOOR = 0.70

#: How many monthly gaps to carry forward. Acceleration reads the last two; more than this
#: is never used and would only make the object heavier to cache.
GAP_HISTORY_MONTHS = 6


def _number(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Month:
    """One market, one channel, one month: what was sold and what was planned.

    Either side may be absent, and absent is not zero. A month with a plan and no sales is
    a business that stopped selling while still carrying a commitment; a month with sales
    and no plan is revenue nobody committed to. Zeroing either one would turn both of those
    into ordinary rows.
    """

    __slots__ = ("period", "actual", "budget")

    def __init__(self, period: str, actual: Optional[float], budget: Optional[float]) -> None:
        self.period = period
        self.actual = actual
        self.budget = budget

    @property
    def is_paired(self) -> bool:
        """Both sides present, and the plan side is an actual plan.

        A goal of exactly zero is excluded, and that is not a rounding decision. The goals
        fact carries explicit zeros — whole channels sit at 0 for months on end. Paired
        with real sales, a zero goal reads as "beat the plan by everything we sold", which
        is the single most flattering sentence this cockpit could produce and the least
        true. Nobody committed to nothing; nobody committed at all.

        Zero against zero is left out too: it is not a plan met, it is a channel that is
        not trading, and counting it would put a row nobody looks at into a total.
        """
        return self.actual is not None and self.budget is not None and self.budget != 0

    @property
    def is_zero_goal(self) -> bool:
        """Real sales against a goal of exactly zero — an absent plan written as a number."""
        return self.budget == 0 and bool(self.actual)

    @property
    def gap(self) -> Optional[float]:
        if not self.is_paired:
            return None
        return self.actual - self.budget

    @property
    def ratio(self) -> Optional[float]:
        if not self.is_paired or not self.budget:
            return None
        return self.actual / self.budget


class Chronic:
    """A plan this business has been under every month for a year, by the same margin."""

    __slots__ = ("months", "low", "high", "mean")

    def __init__(self, months: int, low: float, high: float, mean: float) -> None:
        self.months = months
        self.low = low
        self.high = high
        self.mean = mean

    @property
    def shortfall_pct(self) -> float:
        return 100.0 * (1.0 - self.mean)

    @property
    def sentence(self) -> str:
        return (
            "Below plan in each of the last %d months, at a ratio that never left "
            "%.2f–%.2f. A shortfall that steady for a year is a plan set about %.0f%% "
            "above what this business delivers, not a gap that opened — the question is "
            "the plan, not the month."
            % (self.months, self.low, self.high, self.shortfall_pct)
        )


class Track:
    """One market × channel, across every month the history returned."""

    __slots__ = ("market", "channel", "months")

    def __init__(self, market: str, channel: str, months: Sequence[Month]) -> None:
        self.market = market
        self.channel = channel
        #: Oldest first. Sorting on the 'YYYY-MM' text is a chronological sort.
        self.months = sorted(months, key=lambda m: m.period)

    def month_for(self, period: str) -> Optional[Month]:
        for month in self.months:
            if month.period == period:
                return month
        return None

    @property
    def paired(self) -> List[Month]:
        return [month for month in self.months if month.is_paired]

    @property
    def gap_history(self) -> Tuple[float, ...]:
        """Monthly € gap against plan, oldest first, over paired months only.

        A month where one side is missing is skipped rather than filled: a fabricated zero
        would read on the screen as "the gap closed", which is the opposite of what a
        missing plan means.
        """
        gaps = [month.gap for month in self.paired]
        return tuple(gaps[-GAP_HISTORY_MONTHS:])

    @property
    def months_below_budget(self) -> int:
        """The current run of consecutive paired months below plan, ending at the latest."""
        run = 0
        for month in reversed(self.paired):
            if month.actual >= month.budget:
                break
            run += 1
        return run

    @property
    def chronic(self) -> Optional[Chronic]:
        """A mis-set plan, or None.

        Deliberately hard to earn. Three conditions, all of them: the run must be long
        enough to have crossed a whole seasonal cycle, the ratio must hold steady across it,
        and it must not be so low that "the plan was optimistic" stops being a fair reading
        of it.
        """
        paired = self.paired
        if len(paired) < CHRONIC_WINDOW:
            return None

        run: List[Month] = []
        for month in reversed(paired):
            if month.actual >= month.budget:
                break
            run.append(month)
        if len(run) < CHRONIC_WINDOW:
            return None

        ratios = [month.ratio for month in run if month.ratio is not None]
        if len(ratios) != len(run):
            return None
        low, high = min(ratios), max(ratios)
        if high - low > CHRONIC_SPREAD or low < CHRONIC_FLOOR:
            return None
        return Chronic(
            months=len(run), low=low, high=high, mean=sum(ratios) / len(ratios)
        )


class Ytd:
    """The fiscal year to date, with what could not be compared kept beside it.

    Four numbers rather than two, because the honest version of "how are we doing this
    year" needs all four: what was sold and planned where both exist, what was sold with
    nothing committed against it, and what was committed with nothing sold against it.
    """

    __slots__ = (
        "label",
        "first_period",
        "last_period",
        "actual",
        "budget",
        "unbudgeted_actual",
        "unsold_budget",
        "zero_goal_actual",
        "unbudgeted_lines",
        "unsold_lines",
        "zero_goal_lines",
        "months",
    )

    def __init__(
        self,
        label: str,
        first_period: str,
        last_period: str,
        actual: float,
        budget: float,
        unbudgeted_actual: float,
        unsold_budget: float,
        unbudgeted_lines: int,
        unsold_lines: int,
        months: int,
        zero_goal_actual: float = 0.0,
        zero_goal_lines: int = 0,
    ) -> None:
        self.label = label
        self.first_period = first_period
        self.last_period = last_period
        self.actual = actual
        self.budget = budget
        self.unbudgeted_actual = unbudgeted_actual
        self.unsold_budget = unsold_budget
        self.unbudgeted_lines = unbudgeted_lines
        self.unsold_lines = unsold_lines
        self.months = months
        #: Sold against a goal of exactly zero. Kept apart from the plainly unbudgeted
        #: because the two need different conversations: one is a target nobody set, the
        #: other is a target someone set to nothing.
        self.zero_goal_actual = zero_goal_actual
        self.zero_goal_lines = zero_goal_lines

    @property
    def gap(self) -> float:
        return self.actual - self.budget

    @property
    def pct(self) -> Optional[float]:
        """A fraction, not a percentage — the same units as `analytics.Variance.pct`.

        Not a detail: the template's `pct` filter multiplies by a hundred, so a figure in
        percent here reaches the screen a hundred times too large. Absent rather than zero
        when nothing was planned, for the same reason it is absent there.
        """
        if not self.budget:
            return None
        return self.gap / self.budget

    @property
    def outside(self) -> float:
        """Everything sold that no plan covers, however the absence is written."""
        return self.unbudgeted_actual + self.zero_goal_actual

    @property
    def covered(self) -> Optional[float]:
        """Share of measured sales that a real plan actually covers."""
        total = self.actual + self.outside
        if total <= 0:
            return None
        return self.actual / total

    @property
    def has_unmatched(self) -> bool:
        return bool(self.unbudgeted_actual or self.unsold_budget or self.zero_goal_actual)


class History:
    """Every track the history query returned, addressable by market and channel."""

    __slots__ = ("tracks", "periods")

    def __init__(self, tracks: Dict[Tuple[str, str], Track]) -> None:
        self.tracks = tracks
        self.periods = sorted(
            {month.period for track in tracks.values() for month in track.months}
        )

    def __len__(self) -> int:
        return len(self.tracks)

    def track_for(self, market: str, channel: str) -> Optional[Track]:
        return self.tracks.get((market, channel))

    @property
    def latest_period(self) -> str:
        return self.periods[-1] if self.periods else ""

    def ytd(self, anchor: str = "") -> Optional[Ytd]:
        """The fiscal year to date, ending at `anchor` (the last complete month).

        Sums matched pairs only. The two unmatched amounts are counted separately and
        returned alongside, never folded in: on the real warehouse the unbudgeted actual
        alone is large enough to turn a year behind plan into a year ahead of it.
        """
        last = anchor or self.latest_period
        first = _fiscal_start(last)
        if not first:
            return None

        actual = budget = unbudgeted = unsold = zero_goal = 0.0
        unbudgeted_lines = unsold_lines = zero_goal_lines = 0
        periods = set()

        for track in self.tracks.values():
            for month in track.months:
                if not (first <= month.period <= last):
                    continue
                periods.add(month.period)
                if month.is_paired:
                    actual += month.actual
                    budget += month.budget
                elif month.is_zero_goal:
                    zero_goal += month.actual
                    zero_goal_lines += 1
                elif month.budget is None and month.actual is not None:
                    unbudgeted += month.actual
                    unbudgeted_lines += 1
                elif month.actual is None and month.budget:
                    unsold += month.budget
                    unsold_lines += 1

        if not periods:
            return None
        return Ytd(
            label=_fiscal_label(last),
            first_period=first,
            last_period=last,
            actual=actual,
            budget=budget,
            unbudgeted_actual=unbudgeted,
            unsold_budget=unsold,
            unbudgeted_lines=unbudgeted_lines,
            unsold_lines=unsold_lines,
            months=len(periods),
            zero_goal_actual=zero_goal,
            zero_goal_lines=zero_goal_lines,
        )


def _month_start(period: str):
    """'2026-07' -> date(2026, 7, 1), or None if it is not a month at all."""
    from datetime import date

    parts = (period or "").split("-")
    if len(parts) != 2:
        return None
    try:
        year, month = int(parts[0]), int(parts[1])
        return date(year, month, 1)
    except ValueError:
        return None


def _fiscal_start(period: str) -> str:
    """The April that opens the fiscal year `period` falls in."""
    day = _month_start(period)
    if day is None:
        return ""
    return "%04d-%02d" % (fiscal.fiscal_year(day) - 1, fiscal.FISCAL_START_MONTH)


def _fiscal_label(period: str) -> str:
    day = _month_start(period)
    if day is None:
        return "Year to date"
    return "%s to date" % fiscal.year_label(day)


def from_rows(rows: Sequence[Dict[str, object]]) -> History:
    """Build the history from `SALES_HISTORY` rows.

    Folded through the same function the current month uses, and for the same reason: the
    warehouse reports the shape of the point of sale, so several store formats land on one
    channel. Folded any other way, the history would be keyed differently from the units it
    is meant to describe, and every store line would silently find no track.
    """
    collected: Dict[Tuple[str, str], List[Month]] = {}
    for row in fold_rows(rows):
        market = str(row.get("market") or "").strip()
        channel = str(row.get("channel") or "").strip()
        period = str(row.get("period") or "").strip()
        if not market or not channel or not period:
            continue
        collected.setdefault((market, channel), []).append(
            Month(
                period=period,
                actual=_number(row.get("sales_actual")),
                budget=_number(row.get("sales_budget")),
            )
        )

    return History(
        {
            key: Track(market=key[0], channel=key[1], months=months)
            for key, months in collected.items()
        }
    )
