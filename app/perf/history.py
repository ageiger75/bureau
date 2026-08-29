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

import math

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

#: How far a second plan may differ from the one a verdict was computed on, month by
#: month, and still be read as the same plan. Matches the tolerance the mapping already
#: uses when the workbook and the warehouse disagree about a commitment.
PLAN_AGREEMENT = 0.02

#: Beyond this many points of growth, a plan is not stretching the trend — it is
#: assuming a break with it. Ten points is wide enough that an ambitious plan on a healthy
#: market passes, and narrow enough that a plan asking a shrinking market to grow does not.
STRETCH_THRESHOLD = 0.10

#: And how far the recent months must diverge from the trailing year before the business
#: is called accelerating or slowing rather than steady.
MOMENTUM_THRESHOLD = 0.05

#: Below this, a plan that diverges from the record is not worth a line. The finding is
#: measured in euros and not in points on purpose: a small line can move 400% and matter
#: to nobody, while a large one moving 12% is a conversation. Percentages rank noise to
#: the top, which is exactly what the first sell-in run did.
MATERIAL_EUR = 1_000_000.0

#: The recent window, in months. Three is the shortest run that survives one bad month;
#: compared against the same three of the previous year, so the season cancels.
RECENT_MONTHS = 3

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
    """One market, one channel, one month: what was sold, and what the warehouse targeted.

    The two are not peers and the names say so. `actual` is measured sell-out and is
    trusted. `goal` is the warehouse's goals fact — a store-target system the business has
    ruled unreliable, and which in any case has no target at all for two fifths of what it
    sells. It is kept because a diagnostic of it is worth printing once; nothing in this
    module judges performance by it.

    The plan of record is the planning workbook, and it arrives from outside: every method
    that compares takes it as an argument. Absent is not zero on either side.
    """

    __slots__ = ("period", "actual", "goal")

    def __init__(self, period: str, actual: Optional[float], goal: Optional[float]) -> None:
        self.period = period
        self.actual = actual
        self.goal = goal

    @property
    def has_goal(self) -> bool:
        """A target exists in the warehouse and is not an explicit zero."""
        return self.goal is not None and self.goal != 0

    @property
    def is_zero_goal(self) -> bool:
        """Real sales against a target of exactly zero — an absent target written down."""
        return self.goal == 0 and bool(self.actual)


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
    """One market × channel, across every month the history returned.

    Every comparison here takes the planning workbook as an argument rather than reading a
    plan off the rows. That is the whole design: the rows carry the warehouse's targets,
    which are not the plan, and a method that quietly used them would produce a confident
    sentence about a number nobody stands behind.
    """

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

    def against(self, budget) -> List[Tuple[str, float, float]]:
        """`(period, actual, plan)` for months the workbook covers and something sold.

        Oldest first. A month missing from either side is skipped rather than filled: a
        fabricated zero would read on the screen as "the gap closed", which is the opposite
        of what a missing plan means.
        """
        if budget is None:
            return []
        found = []
        for month in self.months:
            if month.actual is None:
                continue
            planned = budget.budget_for(self.market, self.channel, month.period)
            if not planned:
                continue
            found.append((month.period, month.actual, planned))
        return found

    def gap_history_for(self, budget) -> Tuple[float, ...]:
        """Monthly € gap against the plan of record, oldest first."""
        gaps = [actual - planned for _, actual, planned in self.against(budget)]
        return tuple(gaps[-GAP_HISTORY_MONTHS:])

    def months_below_for(self, budget) -> int:
        """The current run of consecutive months below plan, ending at the latest."""
        run = 0
        for _, actual, planned in reversed(self.against(budget)):
            if actual >= planned:
                break
            run += 1
        return run

    def _actual_at(self, period: str) -> Optional[float]:
        month = self.month_for(period)
        return month.actual if month is not None else None

    def _year_on_year(self, periods: Sequence[str]) -> Optional[float]:
        """Growth of these months against the same months twelve earlier.

        None unless every month on both sides is present. A partial window would compare
        five months with four and call the difference growth.
        """
        now = [self._actual_at(p) for p in periods]
        before = [self._actual_at(_shift(p, -12)) for p in periods]
        if not periods or any(v is None for v in now + before):
            return None
        base = sum(before)
        if base <= 0:
            # Not merely non-zero: positive. Sell-in carries returns and credit notes, so
            # a base can be nothing or less than nothing, and a ratio taken on it produces
            # a confident number with no meaning — -1379% on an Austrian rounding error.
            return None
        return sum(now) / base - 1.0

    def trajectory(self, budget) -> Trajectory:
        """What the record has been doing, and what the plan asks of it next.

        The reading that works today. Whether a plan is mis-set is answered by the sales
        history — trusted, two years deep — against a plan that need only cover the months
        ahead. It does not wait for a year of plan to accumulate, and it does not care
        that the plan and the record come from different files.
        """
        sold = [m.period for m in self.months if m.actual is not None]
        trailing = sold[-12:] if len(sold) >= 24 else []
        recent = sold[-RECENT_MONTHS:] if len(sold) >= 12 + RECENT_MONTHS else []

        plan_growth = None
        planned, before = [], []
        if budget is not None:
            for period in _plan_periods(budget, self.market, self.channel):
                figure = budget.budget_for(self.market, self.channel, period)
                previous = self._actual_at(_shift(period, -12))
                if figure and previous is not None:
                    planned.append(figure)
                    before.append(previous)
            if planned and sum(before) > 0:
                plan_growth = sum(planned) / sum(before) - 1.0

        return Trajectory(
            market=self.market,
            channel=self.channel,
            growth=self._year_on_year(trailing),
            recent=self._year_on_year(recent),
            plan_growth=plan_growth,
            # The euros behind the percentages, so the finding can be ranked by money.
            plan_amount=sum(planned) if planned else None,
            base_amount=sum(before) if before else None,
        )

    def chronic_for(self, budget) -> Optional[Chronic]:
        """A mis-set plan, or None.

        Deliberately hard to earn. Three conditions, all of them: the run must be long
        enough to have crossed a whole seasonal cycle, the ratio must hold steady across
        it, and it must not be so low that "the plan was optimistic" stops being a fair
        reading of it.

        Measured against the workbook and nothing else. It follows that the verdict cannot
        appear until the workbook covers a full year of closed months — which is a true
        statement about what is known, and better than a confident one drawn from targets
        the business does not stand behind.
        """
        paired = self.against(budget)
        if len(paired) < CHRONIC_WINDOW:
            return None

        run = []
        for period, actual, planned in reversed(paired):
            if actual >= planned:
                break
            run.append(actual / planned)
        if len(run) < CHRONIC_WINDOW:
            return None

        low, high = min(run), max(run)
        if high - low > CHRONIC_SPREAD or low < CHRONIC_FLOOR:
            return None
        return Chronic(months=len(run), low=low, high=high, mean=sum(run) / len(run))


class Trajectory:
    """What the sales record says, and what the plan asks of it.

    This is the reading that does not need a long plan. Whether a plan is mis-set, and
    whether the business is speeding up or slowing down, are both answered by the sales
    history — which is trusted and reaches back two years — measured against a plan that
    need only cover the months ahead.

    Every comparison here is year on year, month against the same month twelve earlier, so
    the season cancels out. A December compared with a November says nothing.
    """

    __slots__ = ("market", "channel", "growth", "recent", "plan_growth", "recent_label",
                 "plan_amount", "base_amount")

    def __init__(self, market: str, channel: str, growth: Optional[float],
                 recent: Optional[float], plan_growth: Optional[float],
                 recent_label: str = "the last three months",
                 plan_amount: Optional[float] = None,
                 base_amount: Optional[float] = None) -> None:
        #: The euros behind the percentages: what the plan commits to, and what the same
        #: months delivered a year earlier. Without them a finding can only be ranked by
        #: points, and points put the smallest lines at the top.
        self.plan_amount = plan_amount
        self.base_amount = base_amount
        self.market = market
        self.channel = channel
        #: How to name the shorter window in prose. Sell-out reads three months against
        #: the same three a year earlier; sell-in reads the fiscal year to date against
        #: the same months, because its source publishes the comparison and not the
        #: series. Naming it wrongly would be a small lie in the one sentence a reader
        #: takes away.
        self.recent_label = recent_label
        #: The last twelve months against the twelve before them.
        self.growth = growth
        #: The last three months against the same three a year earlier.
        self.recent = recent
        #: What the plan asks for, against the same months one year earlier.
        self.plan_growth = plan_growth

    @property
    def momentum(self) -> Optional[float]:
        """Recent growth minus trailing growth. Positive is speeding up."""
        if self.growth is None or self.recent is None:
            return None
        return self.recent - self.growth

    @property
    def stretch(self) -> Optional[float]:
        """How much more growth the plan asks for than the record has been delivering."""
        if self.growth is None or self.plan_growth is None:
            return None
        return self.plan_growth - self.growth

    @property
    def recent_stretch(self) -> Optional[float]:
        """What the plan asks beyond what the last three months have been running at."""
        if self.recent is None or self.plan_growth is None:
            return None
        return self.plan_growth - self.recent

    @property
    def money_at_stake(self) -> Optional[float]:
        """Euros between the plan and what the record's own rate would deliver.

        Measured against the record reading *nearest* the plan — the most favourable one —
        so the figure is what the plan asks for beyond the best case the history supports,
        not a number picked to look large.
        """
        if self.plan_amount is None or not self.base_amount or self.plan_growth is None:
            return None
        if not self.records:
            return None
        nearest = min(self.records, key=lambda r: abs(self.plan_growth - r))
        return self.plan_amount - self.base_amount * (1.0 + nearest)

    @property
    def is_material(self) -> bool:
        """Worth a line at all.

        On euros, never on points. The first sell-in run ranked by percentage and put
        Austria department stores at the top of the list at -1379% — a rounding error on a
        base of nothing, printed above every real finding on the page.
        """
        money = self.money_at_stake
        return money is not None and abs(money) >= MATERIAL_EUR

    @property
    def records(self) -> List[float]:
        """Every reading of the record that is actually available.

        Two for sell-out — the trailing year and the recent quarter. One for sell-in,
        whose source publishes a year-on-year comparison rather than a series, so only the
        fiscal year to date can be read. The verdict below requires the plan to clear
        every record there is, which keeps the discipline without pretending to a reading
        that does not exist.
        """
        return [r for r in (self.growth, self.recent) if r is not None]

    @property
    def is_ahead_of_record(self) -> bool:
        """The plan assumes a break with the record, on every reading of it.

        Both, because the twelve-month figure goes stale on a business that has turned.
        The first version of this compared the plan with the trailing year alone and
        announced that China e-commerce was planned for "growth it has not shown" — while
        its last three months ran at +63%. It had just shown it. Four findings in five
        came back positive that way, which is not a signal, it is a habit.
        """
        if self.plan_growth is None or not self.records:
            return False
        return all(self.plan_growth - r > STRETCH_THRESHOLD for r in self.records)

    @property
    def is_behind_record(self) -> bool:
        """The plan asks for less than the business delivers, on both readings.

        Symmetric, and for the same reason. A plan set below the trailing year but in line
        with the recent quarter is not timid — it is a plan that has taken the turn into
        account, which is what a plan is supposed to do.
        """
        if self.plan_growth is None or not self.records:
            return False
        return all(self.plan_growth - r < -STRETCH_THRESHOLD for r in self.records)

    @property
    def direction(self) -> str:
        """`accelerating`, `slowing`, `steady`, or empty when it cannot be read."""
        moved = self.momentum
        if moved is None:
            return ""
        if moved > MOMENTUM_THRESHOLD:
            return "accelerating"
        if moved < -MOMENTUM_THRESHOLD:
            return "slowing"
        return "steady"

    @property
    def is_shipment_timed(self) -> bool:
        """True when the record is sell-in read over part of a year.

        Sell-in is shipments. A partner that ordered early shows +200% four months in and
        nothing has happened; the same partner ordering late shows -80%. The reading is
        real and it is weak, and it strengthens as the year fills — so it is labelled
        rather than hidden, and the label goes on the sentence a reader takes away.
        """
        return self.recent_label == "the fiscal year to date"

    @property
    def sentence(self) -> str:
        """The finding in one line, or empty when the plan and the record agree.

        Deliberately silent on a plan that merely continues the trend: that is most of
        them, and a line printed for every market is a line read for none.
        """
        if not (self.is_ahead_of_record or self.is_behind_record):
            return ""
        if not self.is_material:
            return ""
        turning = {
            "accelerating": " The business is speeding up, which argues for the plan.",
            "slowing": " The business is slowing down, which argues against it.",
            "steady": " The trend is steady, so nothing in the record supports the change.",
        }.get(self.direction, "")
        # Every record is named, because a reader shown one figure cannot tell a business
        # that is still falling from one that has already turned.
        said = []
        if self.growth is not None:
            said.append("the last twelve months delivered %s" % _pct(self.growth))
        if self.recent is not None:
            said.append("%s ran at %s" % (self.recent_label, _pct(self.recent)))
        where = " and ".join(said)
        side = "the plan sits above" if self.is_ahead_of_record else "the plan sits below"
        widest = max(abs(self.plan_growth - r) for r in self.records)
        # The sell-in caveat used to close this sentence, and the sentence appears on every
        # line of the plan review — ten prints of one fact on one screen, on a list read
        # top to bottom. It is carried by the SELL-IN badge now, and stated once in the
        # note at the foot: `is_shipment_timed` is what the caller reads to place it.
        return (
            "The plan asks for %s, where %s — %s every reading of the record, by up to "
            "%s. %s embedded across the year.%s"
            % (_pct(self.plan_growth), where, side, _points(widest),
               _eur(abs(self.money_at_stake)), turning)
        )


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else "%+.0f%%" % (100.0 * value)


def _points(value: float) -> str:
    return "%.0f points" % (100.0 * abs(value))


def _eur(amount: float) -> str:
    """Readable euros. The cockpit's own formatter, imported late to avoid a cycle."""
    from .analytics import format_eur

    return format_eur(amount)


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
        "plan_source",
        "shipped_through",
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
        plan_source: str = "",
        shipped_through: str = "",
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
        #: Which plan this was measured against, named on screen. Two sources with very
        #: different standing sit behind this figure, and a reader who cannot tell them
        #: apart cannot judge the number.
        self.plan_source = plan_source
        #: The last month of sell-in inside this total. The two perimeters close on
        #: different dates — the consolidation on a snapshot, the warehouse on a
        #: transaction — so a year to date can legitimately hold four months of one and
        #: three of the other. Legitimate, and invisible unless it is named.
        self.shipped_through = shipped_through

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
    def covered_label(self) -> str:
        """Coverage as text, never rounded up.

        This share is printed only when something is *not* covered, so a rounding that
        reaches 100% makes the sentence contradict the clause that follows it — "a plan
        covers 100% of what was sold" directly above "€432k carrying no plan at all".
        Rounding down is also the only safe direction for a completeness figure: it can
        understate what the screen reads, never overstate it.
        """
        covered = self.covered
        if covered is None:
            return ""
        floored = math.floor(covered * 1000) / 10.0
        return "%g%%" % floored

    @property
    def basis_caveat(self) -> str:
        """Said only when the two perimeters do not end on the same month.

        Most months they do, and a line printed every time is a line read none of the
        time. When they diverge it has to be said: a total labelled to July that carries
        June's shipments is the kind of quiet inaccuracy that costs a screen its standing
        the first time someone checks it against the accounts.
        """
        if not self.shipped_through or self.shipped_through == self.last_period:
            return ""
        return (
            "Sold to %s, shipped to %s: the two sources close on different dates — the "
            "warehouse on a transaction, the consolidation on a snapshot — so this total "
            "holds one more month of shop sales than of partner invoices."
            % (_month_label(self.last_period), _month_label(self.shipped_through))
        )

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

    def summed(self, periods: Sequence[str]) -> Dict[str, float]:
        """Actual sales per market over exactly these months.

        Written for the check against Finance's own quarter, and the reason it exists is
        that the obvious shortcut is wrong: the screen's `sales_actual` is one month, and
        setting a month beside a quarter produces a difference that is three quarters
        calendar and no part of it a finding.
        """
        wanted = set(periods)
        found: Dict[str, float] = {}
        for (market, _channel), track in self.tracks.items():
            for month in track.months:
                if month.period in wanted and month.actual is not None:
                    found[market] = found.get(market, 0.0) + month.actual
        return found

    def ytd(self, anchor: str = "", budget=None, sell_in=()) -> Optional[Ytd]:
        """The fiscal year to date, ending at `anchor` (the last complete month).

        Measured against the planning workbook when one is given, and that is not a
        preference — it is the difference between a figure worth quoting and one that is
        not. The warehouse's goals fact turned out to cover 57% of measured sales: whole
        markets carry no target in any of twenty-four months, China's stores and
        marketplaces among them. A year-to-date built on it would compare a complete
        actual with a plan missing two fifths of the business.

        The workbook has no such hole, and the year to date is the one window where it can
        be used: it covers the current fiscal year, which is exactly the period being
        summed. The twenty-four-month trend still runs on the goals fact, because nothing
        else reaches back that far — but a trend is a shape and a total is a claim.

        The two sources are never mixed. A pair the workbook does not cover is unbudgeted,
        not quietly filled from the other source: a total assembled from two definitions
        of "plan" is a total nobody can reconcile with anything.

        Sums matched pairs only, whichever source. What is left over is counted apart and
        returned alongside — on real data it is large enough to turn a year behind plan
        into a year ahead of it.
        """
        last = anchor or self.latest_period
        first = _fiscal_start(last)
        if not first or budget is None:
            # No workbook, no year to date. The alternative would be a total measured
            # against the warehouse's targets, which cover 57% of what is sold and which
            # the business does not stand behind — a figure that looks quotable and is not.
            return None

        actual = budget_total = unbudgeted = unsold = zero_goal = 0.0
        unbudgeted_lines = unsold_lines = zero_goal_lines = 0
        periods = set()

        for track in self.tracks.values():
            for month in track.months:
                if not (first <= month.period <= last):
                    continue
                periods.add(month.period)
                planned = budget.budget_for(track.market, track.channel, month.period)
                if month.actual is not None and planned:
                    actual += month.actual
                    budget_total += planned
                elif planned == 0 and month.actual:
                    zero_goal += month.actual
                    zero_goal_lines += 1
                elif planned is None and month.actual is not None:
                    unbudgeted += month.actual
                    unbudgeted_lines += 1
                elif month.actual is None and planned:
                    unsold += planned
                    unsold_lines += 1

        # Sell-in arrives as rows rather than as a track: the consolidation publishes a
        # cumulative column, not a series, so it has no twenty-four-month history to fold
        # into `tracks`. What it does have is the months of the current year, and the
        # workbook carries their plan — which is everything a year-to-date needs. Without
        # this the headline covers the two thirds of the Maison the warehouse measures and
        # says so, which is honest and is not the question anyone asked.
        for market, channel, period, sold in _sell_in_months(sell_in, budget):
            months_of = _months_in(period)
            if not months_of or not (first <= months_of[-1] <= last):
                continue
            periods.update(m for m in months_of if first <= m <= last)
            planned = _plan_across(budget, market, channel, months_of)
            if planned:
                actual += sold
                budget_total += planned
            elif planned == 0:
                zero_goal += sold
                zero_goal_lines += 1
            else:
                unbudgeted += sold
                unbudgeted_lines += 1

        if not periods:
            return None
        shipped = [
            m for _, _, period, _ in _sell_in_months(sell_in)
            for m in _months_in(period) if first <= m <= last
        ]
        return Ytd(
            label=_fiscal_label(last),
            first_period=first,
            last_period=last,
            actual=actual,
            budget=budget_total,
            unbudgeted_actual=unbudgeted,
            unsold_budget=unsold,
            unbudgeted_lines=unbudgeted_lines,
            unsold_lines=unsold_lines,
            months=len(periods),
            zero_goal_actual=zero_goal,
            zero_goal_lines=zero_goal_lines,
            plan_source="the planning workbook",
            shipped_through=max(shipped) if shipped else "",
        )


def _months_in(period: str) -> List[str]:
    """`2025-04..2025-05` -> both months. A single month returns itself.

    The consolidation cannot always separate two months: a snapshot missing from a
    cumulative series makes the pair inseparable. Said as a pair rather than split by a
    rule of thumb, here as everywhere else — a figure invented to fill a column is worth
    less than an honest range.
    """
    text = (period or "").strip()
    if ".." not in text:
        return [text] if text else []
    first, _, last = text.partition("..")
    months, guard = [], 0
    current = first.strip()
    while current and guard < 24:
        months.append(current)
        if current == last.strip():
            break
        current = _shift(current, 1)
        guard += 1
    return months


def _plan_across(budget, market: str, channel: str, months: Sequence[str]):
    """The plan for these months added together, or None when it covers none of them.

    A range is confronted with the plan's own months summed, never with one of them: the
    two sides have to describe the same span or the comparison is a coincidence.
    """
    if budget is None:
        return None
    figures = [budget.budget_for(market, channel, m) for m in months]
    found = [f for f in figures if f is not None]
    return sum(found) if found else None


def plan_places(budget) -> Dict[Tuple[str, str], Tuple[str, str]]:
    """`(entity, segment)` -> `(market, channel)`, from the plan's own key.

    The entity code is what the consolidation itself uses, and it is what the plan uses to
    say which market a line belongs to. A country name is the weaker key by some distance:
    names are typed by people and translated twice on the way here, while eleven markets
    are billed by a hub and would vanish entirely under a name-based join.

    The suffixed spelling is registered as an alias because the workbook writes the same
    entity two ways — bare for most, `_UNLOC` for a few — while the consolidation always
    writes the suffix.
    """
    from .budget import channel_of, normalise_market

    places: Dict[Tuple[str, str], Tuple[str, str]] = {}
    for line in budget.lines if budget else []:
        if line.entity:
            where = (normalise_market(line.market), channel_of(line.segment))
            places.setdefault((line.entity, line.segment), where)
    # Aliases second, and only where nothing real claims the key. A workbook that carries
    # `M_102_UNLOC` as an entity in its own right must keep it: registered in one pass, an
    # alias derived from `M_102` could take the key first and quietly send that market's
    # revenue to its neighbour. The reconciliation code says the same thing in its own
    # words — "an exact line written later overwrites the alias" — and this is what
    # copying half of it looks like.
    for line in budget.lines if budget else []:
        if line.entity:
            key = (line.entity + "_UNLOC", line.segment)
            if key not in places:
                places[key] = (normalise_market(line.market), channel_of(line.segment))
    return places


def _sell_in_months(rows, budget=None) -> List[Tuple[str, str, str, float]]:
    """`(market, channel, period, sold)` from consolidation rows, folded per period.

    Resolved through the plan's entity code where it can be, and by market name only when
    it cannot. The year to date used to join on the name alone while the trajectory beside
    it joined on the entity — two keys for one job, and the weaker one where the money is.
    """
    from .budget import channel_of, normalise_market

    places = plan_places(budget)
    collected: Dict[Tuple[str, str, str], float] = {}
    for row in rows or []:
        segment = str(row.get("segment") or "").strip()
        period = str(row.get("period") or "").strip()
        sold = _number(row.get("sales_actual"))
        if not segment or not period or sold is None:
            continue
        where = places.get((str(row.get("entity") or "").strip(), segment))
        if where is None:
            market = normalise_market(str(row.get("market") or "").strip())
            if not market:
                continue
            where = (market, channel_of(segment))
        key = (where[0], where[1], period)
        collected[key] = collected.get(key, 0.0) + sold
    return [(k[0], k[1], k[2], v) for k, v in sorted(collected.items())]


def _shift(period: str, months: int) -> str:
    """'2026-07' shifted by whole months. The only date arithmetic here."""
    try:
        year, month = (int(part) for part in period.split("-"))
    except ValueError:
        return ""
    total = year * 12 + (month - 1) + months
    return "%04d-%02d" % (total // 12, total % 12 + 1)


def _plan_periods(budget, market: str, channel: str) -> List[str]:
    """Every month the workbook commits to for this market and channel, in order."""
    return sorted({
        line.period
        for line in budget.lines
        if line.market == market and line.channel == channel and line.budget
    })


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


#: Month names, for the one place a period is written out in prose rather than printed
#: as a code. Duplicating the list in `source` would be worse than importing it: two
#: spellings of July is exactly the kind of drift nobody notices until it is on a screen.
def _month_label(period: str) -> str:
    """'2026-07' -> 'July'."""
    from .source import _MONTHS

    parts = (period or "").split("-")
    if len(parts) != 2:
        return period
    try:
        month = int(parts[1])
    except ValueError:
        return period
    return _MONTHS[month - 1] if 1 <= month <= 12 else period


def _fiscal_label(period: str) -> str:
    day = _month_start(period)
    if day is None:
        return "Year to date"
    return "%s to date" % fiscal.year_label(day)


def explained_pairs(period: str = "") -> set:
    """Market and channel pairs whose divergence a note already accounts for.

    A boundary written down is not a plan to renegotiate. The American wholesale line
    carries a note saying the accounts file Sephora on the other side of it; without this,
    the same fact comes back a second time as "the plan asks for +525%" and sends someone
    to argue with a plan that is not wrong.
    """
    from . import context as context_module

    return {
        (note.market, note.channel)
        for note in context_module.current().notes
        if note.kind in context_module.NOT_TRADING and note.market and note.channel
        and (not note.since or not period or period >= note.since)
    }


def sell_in_trajectories(closed_year, current, budget, explained=()) -> List[Trajectory]:
    """What the sell-in plan asks, against what the partners have actually been buying.

    Built from the two queries that already exist rather than a third nobody has run.
    `SELL_IN_HISTORY` gives the last closed fiscal year month by month, restated at the
    plan's own rates; `SELL_IN` gives the current year to date with each month's
    year-earlier figure beside it, at those same rates. Both sides of every comparison
    here are therefore stated identically, which is the property that makes the sell-in
    reconciliation exact and is worth preserving.

    Only one reading of the record is available. The consolidation publishes a comparison,
    not a series: it says what this month did against the same month last year, and never
    what the twelve months before that did. So the record is the fiscal year to date, and
    the sentence says so rather than implying a year.

    The join is on the plan's own entity code, not on a country name. Names are typed by
    people and translated twice on the way here; the code is what the consolidation uses.
    """
    from .budget import channel_of, normalise_market

    #: (entity, segment) -> market and channel, from the plan. The suffixed spelling is
    #: registered as an alias, because the workbook types the same entity two ways while
    #: the consolidation always writes the suffix.
    named = plan_places(budget)
    planned: Dict[Tuple[str, str], float] = {}
    for line in budget.lines if budget else []:
        if not line.entity or not line.budget:
            continue
        where = (normalise_market(line.market), channel_of(line.segment))
        planned[where] = planned.get(where, 0.0) + line.budget

    last_year: Dict[Tuple[str, str], float] = {}
    for row in closed_year or []:
        where = named.get(
            (str(row.get("entity") or ""), str(row.get("segment") or ""))
        )
        value = _number(row.get("value"))
        if where is not None and value is not None:
            last_year[where] = last_year.get(where, 0.0) + value

    to_date: Dict[Tuple[str, str], List[float]] = {}
    for row in current or []:
        where = named.get(
            (str(row.get("entity") or ""), str(row.get("segment") or ""))
        )
        if where is None:
            continue
        now, before = _number(row.get("sales_actual")), _number(row.get("sales_last_year"))
        if now is None or before is None:
            continue
        running = to_date.setdefault(where, [0.0, 0.0])
        running[0] += now
        running[1] += before

    from .budget import is_aggregate_market

    skip = set(explained)
    found = []
    for where in sorted(set(planned) & set(last_year)):
        # A roll-up has no one to answer for it, and a slot it takes is a slot a real
        # market loses.
        if where in skip or is_aggregate_market(where[0]):
            continue
        base = last_year[where]
        now, before = to_date.get(where, [None, None])
        found.append(
            Trajectory(
                market=where[0],
                channel=where[1],
                # Absent, and stated as absent: the consolidation publishes a comparison,
                # not a series, so a trailing twelve-month growth cannot be read from it.
                growth=None,
                recent=(now / before - 1.0) if before and before > 0 else None,
                plan_growth=(planned[where] / base - 1.0) if base > 0 else None,
                recent_label="the fiscal year to date",
                plan_amount=planned[where],
                base_amount=base,
            )
        )
    return found


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
                goal=_number(row.get("sales_budget")),
            )
        )

    return History(
        {
            key: Track(market=key[0], channel=key[1], months=months)
            for key, months in collected.items()
        }
    )
