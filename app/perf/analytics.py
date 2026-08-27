"""Deterministic analytics engine.

Brief §21A is explicit: do not use a language model for arithmetic Python does reliably.
Everything here is plain computation — no inference, no model call, no randomness. That is
also what makes §31 possible: every figure on screen can be traced back to its inputs.

Three things this module refuses to do:

* invent a number it cannot compute;
* present an estimate without saying it is one;
* rank anything by a score whose factors are not visible.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .model import RATE_DRIVERS, BusinessUnit, Dataset, Drivers

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

#: Share of the gap a single driver must explain for the diagnosis to be called HIGH.
HIGH_CONFIDENCE_SHARE = 0.60
MEDIUM_CONFIDENCE_SHARE = 0.35

#: A gap below this is not worth CEO attention whatever its percentage (brief §3.1).
MATERIALITY_FLOOR_EUR = 100_000.0

#: A win must beat plan by both a margin and an amount to count as unusual.
WIN_MIN_PCT = 0.05
WIN_MIN_EUR = 200_000.0

#: Traffic multiplied or divided by this much is no longer a campaign. A big launch can
#: double a market's sessions; it does not put them at fifteen times last year's.
SESSIONS_BREAK_FACTOR = 2.5
#: …and what makes it a measurement break rather than a commercial event is that the money
#: did not follow. Sales within this band of last year count as unmoved.
FLAT_SALES_PCT = 0.15


# --------------------------------------------------------------------------- variance


class Variance:
    __slots__ = ("gap", "pct")

    def __init__(self, gap: float, pct: Optional[float]) -> None:
        self.gap = gap
        self.pct = pct


def variance(actual: float, base: float) -> Variance:
    """€ gap and % gap. The percentage is absent — not zero — when the base is zero."""
    gap = actual - base
    if base == 0:
        return Variance(gap, None)
    return Variance(gap, gap / base)


# --------------------------------------------------------------- contribution analysis


class Contribution:
    __slots__ = ("label", "impact", "actual", "base")

    def __init__(self, label: str, impact: float, actual: float, base: float) -> None:
        self.label = label
        #: € effect of this driver alone, holding the others per the chaining rule below.
        self.impact = impact
        self.actual = actual
        self.base = base

    @property
    def is_rate(self) -> bool:
        return self.label in RATE_DRIVERS

    @property
    def delta_pct(self) -> Optional[float]:
        if self.base == 0:
            return None
        return (self.actual - self.base) / self.base


def contributions(actual: Drivers, base: Drivers) -> List[Contribution]:
    """Split a sales gap across its drivers, exactly.

    Chained decomposition: each driver is measured after the ones before it have moved and
    before the ones after it have. The effects therefore sum to the total gap with no
    unexplained remainder and no arbitrary rounding.

    The order is part of the method: a different order shifts the interaction terms between
    drivers. `model.DRIVER_LABELS` fixes it once per channel so that two screens can never
    attribute the same gap differently.
    """
    if actual.labels != base.labels:
        raise ValueError("cannot compare units with different drivers")

    results: List[Contribution] = []
    for index, label in enumerate(actual.labels):
        effect = 1.0
        for before in range(index):
            effect *= actual.values[before]
        effect *= actual.values[index] - base.values[index]
        for after in range(index + 1, len(actual.values)):
            effect *= base.values[after]
        results.append(
            Contribution(label, effect, actual.values[index], base.values[index])
        )
    return results


def largest_driver(items: Sequence[Contribution]) -> Optional[Contribution]:
    """The driver that moved sales the most, in either direction."""
    if not items:
        return None
    return max(items, key=lambda c: abs(c.impact))


def share_of_gap(item: Contribution, gap: float) -> Optional[float]:
    """How much of the gap this driver accounts for. Absent when the gap is nil."""
    if gap == 0:
        return None
    return item.impact / gap


def confidence_of(items: Sequence[Contribution], gap: float) -> str:
    """Confidence that the diagnosis names the right cause.

    Derived, never asserted: it reflects how concentrated the explanation is. A gap spread
    evenly across every driver is a gap we cannot yet explain, and the screen must say so
    rather than pick a favourite.
    """
    main = largest_driver(items)
    if main is None or gap == 0:
        return LOW
    share = abs(main.impact / gap)
    if share >= HIGH_CONFIDENCE_SHARE:
        return HIGH
    if share >= MEDIUM_CONFIDENCE_SHARE:
        return MEDIUM
    return LOW


# --------------------------------------------------------------------------- ranking


class Priority:
    """A ranking score with every factor exposed (brief §26 — no opaque AI ranking)."""

    __slots__ = ("score", "factors", "reasons")

    def __init__(
        self, score: float, factors: Sequence[Tuple[str, float]], reasons: Sequence[str]
    ) -> None:
        self.score = score
        self.factors = list(factors)
        self.reasons = list(reasons)


def acceleration_factor(gap_history: Sequence[float]) -> Tuple[float, str]:
    """Is the gap widening, stable, or closing?

    Compares the latest gap with the one before it. Widening earns attention now, because
    the cost of waiting a month is itself growing.
    """
    if len(gap_history) < 2:
        return 1.0, "no trend available"
    latest, previous = gap_history[-1], gap_history[-2]
    if latest < previous:
        return 1.2, "gap widening month on month"
    if latest > previous:
        return 0.85, "gap closing month on month"
    return 1.0, "gap stable month on month"


def persistence_factor(months_below_budget: int) -> Tuple[float, str]:
    """A gap that keeps coming back is a management problem, not an accident."""
    if months_below_budget <= 1:
        return 1.0, "first month below plan"
    capped = min(months_below_budget, 6)
    return 1.0 + 0.15 * (capped - 1), "%d consecutive months below plan" % months_below_budget


CONFIDENCE_FACTOR = {HIGH: 1.0, MEDIUM: 0.85, LOW: 0.7}


def priority_of(unit: BusinessUnit) -> Priority:
    """priority = € gap × persistence × acceleration × strategic weight × confidence.

    Deliberately multiplicative and deliberately small: five factors a CEO can check by
    hand. The brief warns against overengineering this, and an unverifiable ranking would
    cost more trust than a slightly imperfect one.
    """
    gap = abs(min(0.0, unit.gap_vs_budget))
    # Confidence describes how concentrated the explanation is, so it is read against the
    # baseline the decomposition could actually use — which is rarely the plan.
    baseline, _ = unit.decomposition_baseline()
    items = contributions(unit.actual, baseline) if baseline is not None else []
    level = confidence_of(items, unit.sales_actual - baseline.sales) if baseline else LOW

    persistence, persistence_reason = persistence_factor(unit.months_below_budget)
    acceleration, acceleration_reason = acceleration_factor(unit.gap_history)
    confidence = CONFIDENCE_FACTOR[level]

    score = gap * persistence * acceleration * unit.strategic_weight * confidence

    reasons = [
        "%s below plan" % _eur(gap),
        persistence_reason,
        acceleration_reason,
    ]
    if unit.strategic_weight != 1.0:
        reasons.append("strategic weight %.2f" % unit.strategic_weight)
    reasons.append("diagnosis confidence %s" % level.upper())

    return Priority(
        score=score,
        factors=[
            ("€ gap", gap),
            ("persistence", persistence),
            ("acceleration", acceleration),
            ("strategic weight", unit.strategic_weight),
            ("confidence", confidence),
        ],
        reasons=reasons,
    )


# ------------------------------------------------------------- explanation challenge


class ExplanationCheck:
    """Does management's explanation actually account for the gap? (brief §3.5, §21B)"""

    __slots__ = ("explanation", "verdict", "evidence", "residual_pct")

    SUPPORTED = "supported"
    PARTIAL = "partially supported"
    UNSUPPORTED = "unsupported"
    INSUFFICIENT = "insufficient evidence"

    def __init__(
        self,
        explanation: str,
        verdict: str,
        evidence: str,
        residual_pct: Optional[float],
    ) -> None:
        self.explanation = explanation
        self.verdict = verdict
        self.evidence = evidence
        self.residual_pct = residual_pct


def check_explanation(unit: BusinessUnit) -> Optional[ExplanationCheck]:
    """Test a stated cause against the market data, and quantify what it leaves unexplained.

    Never accepts "difficult market" at face value (brief §20). When no market index is
    available the answer is "insufficient evidence" — not a guess, and not silence either.
    """
    if not unit.management_explanation:
        return None

    sales_pct = variance(unit.sales_actual, unit.sales_last_year).pct
    if unit.market_index_pct is None or sales_pct is None:
        return ExplanationCheck(
            unit.management_explanation,
            ExplanationCheck.INSUFFICIENT,
            "No market benchmark available for this scope, so the explanation cannot be "
            "tested either way.",
            None,
        )

    residual = sales_pct - unit.market_index_pct
    if residual >= -0.02:
        verdict = ExplanationCheck.SUPPORTED
    elif abs(unit.market_index_pct) >= abs(sales_pct) * 0.5:
        verdict = ExplanationCheck.PARTIAL
    else:
        verdict = ExplanationCheck.UNSUPPORTED

    evidence = (
        "Market is %s while sales are %s. The market explains part of the decline; "
        "about %s remains unexplained."
        % (_pct(unit.market_index_pct), _pct(sales_pct), _pts(residual))
    )
    return ExplanationCheck(unit.management_explanation, verdict, evidence, residual)


# ----------------------------------------------------------------- data quality


class Suspect:
    """A figure the cockpit refuses to read as a business event.

    A market at zero with a non-zero history is a broken feed far more often than a
    collapse. Ranking it as the largest gap of the month would put a data incident at the
    top of a CEO's attention, and the second time that happens nobody reads the list.

    So these are separated, not hidden: still shown, but as something to ask the data team
    about rather than the market director.
    """

    __slots__ = ("unit", "code", "message", "fix")

    def __init__(self, unit: BusinessUnit, code: str, message: str, fix: str) -> None:
        self.unit = unit
        self.code = code
        self.message = message
        self.fix = fix


def suspect_of(unit: BusinessUnit) -> Optional[Suspect]:
    """Whether this unit's figures look like a break in the data rather than the business."""
    from .mapping import (
        NO_ANALYTICS_SITE,
        ORDER_TRACKING_LOST,
        ORDERS_NOT_TRACKED,
    )

    # A market with no own site is not a broken feed. It sells through partners who
    # resell, so having no funnel — and often no own online revenue at all — is how that
    # market works. Sending anyone to repair it would send them after nothing.
    if unit.funnel_status == NO_ANALYTICS_SITE:
        return None

    # Where the query established why the funnel is unreadable, its word is taken. It read
    # the warehouse; the heuristics below only ever inferred from shape. Note that orders
    # now arrive as absent rather than as zero, which is correct and which is exactly why
    # the shape-based check underneath can no longer see these markets.
    # A market that recorded nothing at all outranks a missing tag, whatever the query
    # says about its funnel. Otherwise Finland — no sales, and no order tracking either —
    # is told that "the sales are real" underneath a figure of zero.
    if unit.sales_actual == 0 and (unit.sales_last_year > 0 or unit.sales_budget > 0):
        return Suspect(
            unit,
            code="zero_against_history",
            message="No sales recorded this period, against %s last year."
            % _eur(unit.sales_last_year),
            fix="Check the feed before reading this as a commercial collapse.",
        )

    if unit.funnel_status == ORDER_TRACKING_LOST:
        return Suspect(
            unit,
            code="order_tracking_lost",
            message="Order tracking stopped on this site during the period, on %s of "
            "sales." % _eur(unit.sales_actual),
            fix="This broke recently, so it can be found. Ask the data team, not the "
            "market.",
        )
    if unit.funnel_status == ORDERS_NOT_TRACKED:
        return Suspect(
            unit,
            code="traffic_without_orders",
            message="Visits are recorded here but orders never are, on %s of sales."
            % _eur(unit.sales_actual),
            fix="A tag to install, not a market to question. The sales are real; the "
            "funnel behind them is not measured.",
        )

    # Sessions arriving with no orders behind them: the business is there, the
    # transactional tracking is not. Read from the raw counts rather than the drivers,
    # because this is precisely the case where no driver set could be built.
    sessions = unit.sessions if unit.sessions is not None else unit.actual.value_of("Sessions")
    orders = unit.orders
    if orders is None and unit.actual.has_breakdown:
        conversion = unit.actual.value_of("Conversion")
        orders = None if conversion is None or sessions is None else conversion * sessions
    if (
        sessions is not None
        and orders is not None
        and sessions > 0
        and orders == 0
        and unit.sales_actual > 0
    ):
        return Suspect(
            unit,
            code="traffic_without_orders",
            message="%s sessions and no recorded orders, on %s of sales."
            % (_num(sessions), _eur(unit.sales_actual)),
            fix="Transaction tracking is missing here; the drivers cannot be read until "
            "it is fixed.",
        )

    # Traffic that moves by a multiple while the money stays still. A campaign can double
    # a market's sessions, but it moves the sales with it; measurement changes — a tag
    # deployed, a domain merged, a bot filter switched off — move the traffic alone.
    # Both signatures turned up in the real feed the first time last year's funnel was
    # queried alongside this year's: sessions off by an order of magnitude in either
    # direction, revenue unmoved. Without last year's drivers they were invisible.
    sessions_before = unit.last_year.value_of("Sessions")
    if (
        sessions is not None
        and sessions_before is not None
        and sessions > 0
        and sessions_before > 0
        and unit.sales_last_year > 0
    ):
        factor = sessions / sessions_before
        sales_move = (unit.sales_actual - unit.sales_last_year) / unit.sales_last_year
        if (
            factor >= SESSIONS_BREAK_FACTOR or factor <= 1.0 / SESSIONS_BREAK_FACTOR
        ) and abs(sales_move) <= FLAT_SALES_PCT:
            return Suspect(
                unit,
                code="traffic_discontinuity",
                message="Sessions are %s last year's while sales moved %s. Traffic does "
                "not move like that on its own."
                % (_factor(factor), _pct(sales_move, digits=1)),
                fix="Compare the two periods' tracking before reading any driver here: a "
                "tag, a domain or a bot filter changed, not the audience.",
            )
    return None


def _factor(value: float) -> str:
    """'15.9x' or 'a quarter of' — a multiple reads better than a percentage past 2x."""
    if value >= 1.0:
        return "%.1fx" % value
    return "%.2fx" % value


#: Beyond this many markets sharing one fault, it stops being a coincidence.
PATTERN_THRESHOLD = 3

#: What a repeated fault means, as opposed to a single occurrence of it. The distinction
#: changes who is asked and what is asked of them.
PATTERN_MEANING = {
    "traffic_without_orders": (
        "%d markets report sessions with no orders at all, on %s of sales between them. "
        "That many independent tracking failures in one month is not plausible: this is "
        "one join not matching, not %d separate incidents."
    ),
    "traffic_discontinuity": (
        "%d markets show traffic moving by a multiple while their sales sit still, on %s "
        "between them. A change of that shape arriving in several markets at once is a "
        "change in how traffic is counted, not %d coincidences."
    ),
    "order_tracking_lost": (
        "%d markets lost their order tracking during the period, on %s of sales between "
        "them. Tracking that stops in several markets at once stops for one reason — a "
        "deployment, a migration — not %d times."
    ),
    "zero_against_history": (
        "%d markets report no sales at all against a real history, worth %s last year. "
        "A feed that stops for %d markets at once stopped once."
    ),
}


def patterns(found: Sequence[Suspect]) -> List[str]:
    """What several markets failing the same way means, said once.

    A list of twelve identical incidents reads as twelve problems and gets triaged as
    none. Naming the shape sends the question to the right place — one query to fix rather
    than twelve markets to chase — and it is the only thing on this screen that a reader
    could work out for themselves but reliably will not.
    """
    by_code = {}
    for item in found:
        by_code.setdefault(item.code, []).append(item)

    said = []
    for code, items in sorted(by_code.items(), key=lambda pair: -len(pair[1])):
        if len(items) < PATTERN_THRESHOLD or code not in PATTERN_MEANING:
            continue
        money = sum(
            item.unit.sales_last_year if code == "zero_against_history"
            else item.unit.sales_actual
            for item in items
        )
        said.append(PATTERN_MEANING[code] % (len(items), _eur(money), len(items)))
    return said


def suspects(dataset: Dataset) -> List[Suspect]:
    found = [suspect_of(unit) for unit in dataset.units if not unit.is_aggregate]
    return [item for item in found if item is not None]


# --------------------------------------------------------------------------- fires


class Fire:
    """A business area where CEO attention has the highest economic value."""

    __slots__ = (
        "unit",
        "gap",
        "gap_pct",
        "contributions",
        "main_driver",
        "main_share",
        "confidence",
        "priority",
        "movement",
        "explanation_check",
        "misaligned_plan",
        "forecast_flag",
        "baseline_label",
    )

    def __init__(self, unit: BusinessUnit) -> None:
        self.unit = unit
        var = variance(unit.sales_actual, unit.sales_budget)
        self.gap = var.gap
        self.gap_pct = var.pct
        # A channel that reports no drivers cannot be taken apart. Attributing its whole
        # gap to a single "Sales" pseudo-driver would be arithmetically true and say
        # nothing, so the breakdown is simply absent and the screen states it.
        baseline, baseline_label = unit.decomposition_baseline()
        #: What the drivers were compared against. Named on screen, because "conversion
        #: explains the gap" means something different against a plan and against last
        #: year, and the reader must not have to guess which.
        self.baseline_label = baseline_label
        self.contributions = (
            contributions(unit.actual, baseline) if baseline is not None else []
        )
        self.main_driver = largest_driver(self.contributions)
        # The share is of the movement the decomposition actually measures, which is the
        # movement against the baseline — not against the plan, when they differ.
        self.movement = (
            unit.sales_actual - baseline.sales if baseline is not None else self.gap
        )
        self.main_share = (
            share_of_gap(self.main_driver, self.movement) if self.main_driver else None
        )
        self.confidence = confidence_of(self.contributions, self.movement)
        self.priority = priority_of(unit)
        self.explanation_check = check_explanation(unit)
        #: The sharpest question this product can ask: the plan targets one thing while
        #: the numbers point at another (brief §25, Japan).
        self.misaligned_plan = bool(
            unit.action_focus
            and self.main_driver is not None
            and unit.action_focus.lower() != self.main_driver.label.lower()
        )
        #: A forecast cut repeatedly is its own management issue, separate from the gap:
        #: it means the numbers being planned against are not to be trusted (brief §25).
        self.forecast_flag = (
            "Forecast revised down %d times for this period."
            % unit.forecast_revisions_down
            if unit.forecast_revisions_down >= 2
            else ""
        )

    @property
    def has_breakdown(self) -> bool:
        return bool(self.contributions)

    @property
    def diagnosis(self) -> str:
        if not self.has_breakdown:
            if self.unit.no_breakdown_reason:
                return "%s The gap is real; its cause is not measured." % (
                    self.unit.no_breakdown_reason,
                )
            return (
                "No driver breakdown is reported here, so the gap cannot be attributed."
            )
        if self.main_driver is None or self.main_share is None:
            return "No single driver stands out; the gap is spread across all of them."
        share = abs(self.main_share)
        if share > 1.15:
            # The driver cost more than the total movement because another one offset it.
            # Saying "291% of the gap" would be arithmetically right and useless.
            return "%s cost %s on its own%s; other drivers partly offset it." % (
                self.main_driver.label,
                _eur(abs(self.main_driver.impact)),
                self.measured_against,
            )
        # Phrased so the sentence works for every driver label, singular or plural:
        # "Sessions accounts for" and "Conversion account for" are both wrong.
        return "About %s of the %s comes from %s." % (
            _share(share),
            self.measured_what,
            _driver_word(self.main_driver.label),
        )

    # The decomposition is not always measured against the plan, so the sentence cannot
    # always say "gap". A plan is a committed number with no funnel behind it: when it
    # carries no drivers, the only base with a funnel is last year. Naming the wrong base
    # would be a small lie told in a confident voice, which is the one thing the CEO
    # cannot afford to read here.

    @property
    def measured_against(self) -> str:
        """The comparison base, as a suffix, or nothing when it is the plan."""
        if self.baseline_label == "last year":
            return " versus last year"
        return ""

    @property
    def measured_what(self) -> str:
        """The noun for what was decomposed: a gap against plan, a movement against LY."""
        if self.baseline_label == "last year":
            return "movement versus last year"
        return "gap"

    @property
    def question(self) -> str:
        """One sharp question, derived from the numbers rather than written in advance.

        Order matters. A plan aimed at the wrong driver is the most valuable thing this
        product can tell a CEO, so it outranks everything else — including a forecast that
        keeps moving, which is a real issue but a slower one.
        """
        if not self.has_breakdown:
            # The missing measurement is the finding. Asking what will move a driver
            # nobody measures would be asking for a guess.
            return (
                "%s below plan where we cannot see why. What would it take to measure "
                "this properly?" % _eur(abs(self.gap))
            )
        if self.misaligned_plan and self.main_driver is not None:
            return "Why is the plan focused on %s when %s is the largest driver of the gap?" % (
                self.unit.action_focus.lower(),
                _driver_word(self.main_driver.label),
            )
        if self.forecast_flag:
            return (
                "The forecast has been cut %d times. What has to be true for this one to "
                "hold?" % self.unit.forecast_revisions_down
            )
        if self.main_driver is None:
            return "What would it take to explain this gap before the next review?"
        return (
            "What will move %s within 30 days, and how much of the %s gap does each "
            "action close?" % (_driver_word(self.main_driver.label), _eur(abs(self.gap)))
        )


def fires(dataset: Dataset, limit: int = 5) -> List[Fire]:
    """The units that most deserve attention, worst first.

    Capped on purpose: the brief optimises for CEO attention, not completeness. A sixth
    fire would not be read, and pretending otherwise would make the first five worth less.
    """
    candidates = [
        Fire(unit)
        for unit in dataset.units
        if unit.budget_known
        and unit.is_below_budget
        and not unit.is_aggregate
        # A broken feed is not a fire. It is listed separately, as a question for the
        # data team rather than for the market.
        and suspect_of(unit) is None
        and abs(unit.gap_vs_budget) >= MATERIALITY_FLOOR_EUR
    ]
    candidates.sort(key=lambda fire: fire.priority.score, reverse=True)
    return candidates[:limit]


# --------------------------------------------------------------------- opportunities


class Opportunity:
    """Realistic incremental revenue, with the counterfactual written out (brief §27)."""

    __slots__ = ("unit", "driver", "amount", "assumption", "calculation", "confidence")

    def __init__(
        self,
        unit: BusinessUnit,
        driver: str,
        amount: float,
        assumption: str,
        calculation: str,
        confidence: str,
    ) -> None:
        self.unit = unit
        self.driver = driver
        self.amount = amount
        self.assumption = assumption
        self.calculation = calculation
        self.confidence = confidence

    @property
    def question(self) -> str:
        return "What would it take to bring %s back to last year's level?" % (
            self.driver.lower(),
        )


def opportunity_of(unit: BusinessUnit) -> Optional[Opportunity]:
    """Counterfactual: today's volume at last year's conversion.

    Only computed where it means something — a driver that fell against last year while
    the ones feeding it held up. That is a recovery the business has already proved it can
    achieve, which is what separates an opportunity from a wish.
    """
    label = "Conversion"
    now = unit.actual.value_of(label)
    before = unit.last_year.value_of(label)
    if now is None or before is None or before <= now:
        return None

    recovered = Drivers(
        unit.actual.labels,
        [
            before if driver == label else value
            for driver, value in unit.actual.pairs()
        ],
    )
    amount = recovered.sales - unit.actual.sales
    if amount < MATERIALITY_FLOOR_EUR:
        return None

    # Confidence falls when the volume feeding the recovery is itself shrinking: the
    # counterfactual then assumes something the business is not currently doing.
    volume_label = unit.actual.labels[0]
    volume_now = unit.actual.value_of(volume_label) or 0.0
    volume_before = unit.last_year.value_of(volume_label) or 0.0
    level = HIGH if volume_now >= volume_before else MEDIUM

    return Opportunity(
        unit=unit,
        driver=label,
        amount=amount,
        assumption=(
            "Assumes %s returns to last year's %s while %s and the other drivers hold at "
            "today's level."
            % (_driver_word(label), _pct(before, digits=2), volume_label.lower())
        ),
        calculation=(
            "%s %s × %s %s (LY) vs actual sales"
            % (volume_label, _num(volume_now), _driver_word(label), _pct(before, digits=2))
        ),
        confidence=level,
    )


def opportunities(dataset: Dataset, limit: int = 5) -> List[Opportunity]:
    # A suspect unit is excluded here for the same reason it is excluded from the fire
    # list, and more urgently: "recover last year's conversion and gain €4m" computed on a
    # tracking break is a number the CEO would act on. A gap merely wastes attention; a
    # phantom opportunity spends it.
    found = [
        item
        for item in (
            opportunity_of(unit)
            for unit in dataset.units
            if not unit.is_aggregate and suspect_of(unit) is None
        )
        if item
    ]
    found.sort(key=lambda item: item.amount, reverse=True)
    return found[:limit]


# --------------------------------------------------------------------------- wins


class Win:
    """Unusually strong performance, surfaced to be replicated rather than applauded."""

    __slots__ = ("unit", "gap", "gap_pct", "vs_last_year_pct", "driver")

    def __init__(self, unit: BusinessUnit) -> None:
        self.unit = unit
        self.gap = unit.gap_vs_budget
        self.gap_pct = variance(unit.sales_actual, unit.sales_budget).pct
        self.vs_last_year_pct = variance(unit.sales_actual, unit.sales_last_year).pct
        self.driver = unit.win_driver

    @property
    def question(self) -> str:
        return "Is this playbook replicable in other markets?"


def wins(dataset: Dataset, limit: int = 3) -> List[Win]:
    found = []
    for unit in dataset.units:
        if not unit.budget_known:
            # Beating a budget that does not exist is not an achievement.
            continue
        var = variance(unit.sales_actual, unit.sales_budget)
        beats_last_year = unit.gap_vs_last_year > 0
        if (
            var.pct is not None
            and var.pct >= WIN_MIN_PCT
            and var.gap >= WIN_MIN_EUR
            and beats_last_year
        ):
            found.append(Win(unit))
    found.sort(key=lambda win: win.gap, reverse=True)
    return found[:limit]


# ----------------------------------------------------------------- people to push


class Push:
    """An owner whose area needs the CEO this week.

    Brief §10: this ranks business areas, never people. Nothing here scores an individual,
    and the reason shown is always about the numbers.
    """

    __slots__ = ("owner", "reason", "question", "fire")

    def __init__(self, owner, reason: str, question: str, fire: Fire) -> None:
        self.owner = owner
        self.reason = reason
        self.question = question
        self.fire = fire


def people_to_push(items: Sequence[Fire], limit: int = 5) -> List[Push]:
    pushes: List[Push] = []
    seen = set()
    for fire in items:
        owner = fire.unit.owner
        if owner.name in seen:
            continue
        seen.add(owner.name)
        reason = "%s is %s below plan. %s" % (
            fire.unit.label,
            _eur(abs(fire.gap)),
            fire.diagnosis,
        )
        if fire.misaligned_plan:
            reason += " The current plan targets %s." % fire.unit.action_focus.lower()
        pushes.append(Push(owner, reason, fire.question, fire))
        if len(pushes) >= limit:
            break
    return pushes


# --------------------------------------------------------------------------- format


def _eur(amount: float) -> str:
    """Euros at the scale a CEO reads them: millions above a million, thousands below."""
    sign = "-" if amount < 0 else ""
    value = abs(amount)
    if value >= 1_000_000:
        return "%s€%.1fm" % (sign, value / 1_000_000)
    if value >= 1_000:
        return "%s€%.0fk" % (sign, value / 1_000)
    return "%s€%.0f" % (sign, value)


def _pct(value: Optional[float], digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return "%+.*f%%" % (digits, value * 100) if digits else "%+.0f%%" % (value * 100)


#: Driver labels that are initialisms, not words. Lower-casing them mid-sentence turns
#: "AOV" into "aov", which reads as a typo in the one sentence the CEO reads first.
INITIALISMS = frozenset({"AOV", "UPT", "ASP"})


def _driver_word(label: str) -> str:
    return label if label in INITIALISMS else label.lower()


def _share(value: float) -> str:
    """A share of a gap, unsigned: the direction is already in the sentence."""
    return "%.0f%%" % (value * 100)


def _pts(value: float) -> str:
    return "%.0f points" % abs(value * 100)


def _num(value: float) -> str:
    if value >= 1_000_000:
        return "%.1fm" % (value / 1_000_000)
    if value >= 1_000:
        return "%.0fk" % (value / 1_000)
    return "%.2f" % value


#: Exposed for the templates, which must never re-implement formatting.
format_eur = _eur
format_pct = _pct
format_num = _num
format_share = _share
