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

from typing import Dict, List, Optional, Sequence, Tuple

from . import routing
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

    # A plan that has been missed by the same margin every month for a year is not a gap
    # that has lasted a year. Persistence exists to say "this keeps coming back and nobody
    # has fixed it"; applied here it says the opposite of what the numbers mean, and it
    # says it loudly — the factor is at its ceiling exactly where the business is at its
    # most stable. So it is stood down, and the reason names what replaced it. The euros
    # stay: the shortfall against a committed plan is real money either way.
    if unit.chronic_plan:
        persistence = 1.0
        persistence_reason = (
            "below plan every month for a year at the same ratio — a plan to reset, not a "
            "gap that opened"
        )

    # The factor discounts a *named* cause we are unsure of. Where no cause is named there
    # is no claim to discount, and applying it anyway pushed every unmeasured market down
    # the list — so the blinder the market, the lower it ranked, and blind spots buried
    # themselves. Stores arrived at 48% of the plan and ranked below smaller online gaps
    # for no reason but that nobody counts their door.
    confidence = 1.0 if baseline is None else CONFIDENCE_FACTOR[level]

    score = gap * persistence * acceleration * unit.strategic_weight * confidence

    reasons = [
        "%s below plan" % _eur(gap),
        persistence_reason,
        acceleration_reason,
    ]
    if unit.strategic_weight != 1.0:
        reasons.append("strategic weight %.2f" % unit.strategic_weight)
    if baseline is None:
        reasons.append("no diagnosis possible, so nothing is discounted")
    else:
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

    @property
    def money(self) -> float:
        """What this break obscures: last year's figure where nothing was recorded, and
        today's where something was recorded but cannot be read."""
        if self.code == "zero_against_history":
            return self.unit.sales_last_year
        return self.unit.sales_actual

    @property
    def is_material(self) -> bool:
        return self.money >= SUSPECT_FLOOR_EUR


# ------------------------------------------------------------------- reallocation


class Reallocation:
    """A market that moved between its channels and still holds its commitment.

    A country can decide, mid-year, to push one digital channel rather than another. The
    channel it left drops below plan, the channel it chose rises above it, and the market
    delivers what it promised. Ranked channel by channel, that reads as a serious problem
    in one place and a triumph in another — two confident findings about a decision
    somebody made deliberately.

    Worth saying out loud, because the mix changed and that has consequences a total
    hides. But it is not a gap, and the person who made the choice should not be asked to
    explain it as a shortfall. What is a problem is the whole falling below plan; that
    case is not a reallocation and is not reported as one.
    """

    __slots__ = ("market", "gained", "lost", "net", "moved")

    def __init__(self, market, gained, lost, net, moved) -> None:
        self.market = market
        #: Channels above plan, largest first.
        self.gained = gained
        #: Channels below it.
        self.lost = lost
        #: What the market as a whole is versus its plan — small, by definition.
        self.net = net
        #: How much moved between channels, which is the size of the decision.
        self.moved = moved

    @property
    def summary(self) -> str:
        return "%s moved %s between channels and held its plan to within %s." % (
            self.market,
            _eur(self.moved),
            _eur(abs(self.net)),
        )

    @property
    def question(self) -> str:
        return "Was this deliberate, and does the plan still describe how %s sells?" % (
            self.market,
        )


def reallocation_of(units: Sequence[BusinessUnit]) -> Optional[Reallocation]:
    """Whether these channels of one market traded places without losing money.

    Two conditions, both required. Material movement in opposite directions — otherwise
    it is noise, not a decision. And a market total that holds: the moment the whole falls
    materially below plan, this stops being a reallocation and becomes a gap that happens
    to be unevenly spread.
    """
    gained = sorted(
        (u for u in units if u.gap_vs_budget >= MATERIALITY_FLOOR_EUR),
        key=lambda u: -u.gap_vs_budget,
    )
    lost = sorted(
        (u for u in units if u.gap_vs_budget <= -MATERIALITY_FLOOR_EUR),
        key=lambda u: u.gap_vs_budget,
    )
    if not gained or not lost:
        return None

    net = sum(u.gap_vs_budget for u in units)
    if abs(net) >= MATERIALITY_FLOOR_EUR:
        return None

    moved = min(
        sum(u.gap_vs_budget for u in gained),
        -sum(u.gap_vs_budget for u in lost),
    )
    return Reallocation(units[0].market, gained, lost, net, moved)


def reallocations(dataset: Dataset) -> List[Reallocation]:
    found = [
        reallocation_of(units) for units in dataset.by_market().values()
    ]
    return sorted(
        (item for item in found if item is not None), key=lambda item: -item.moved
    )


def reallocating_markets(dataset: Dataset) -> set:
    return {item.market for item in reallocations(dataset)}


#: Note kinds that account for a market selling nothing. Trading stopped on purpose, or
#: the revenue is filed under a neighbouring segment — both explain an empty month. A tax
#: change or a one-off does not: they explain how large a gap is, not why a feed is silent.
EXPLAINS_ABSENCE = ("on_hold", "reclassified")


def _absence_is_explained(unit: BusinessUnit) -> bool:
    """Whether a note already accounts for this market reporting nothing.

    Deliberately narrow. A note is about a gap; a suspect is about a measurement. They
    overlap in exactly one place — a market that reports no sales at all — and nowhere
    else, so nowhere else may be silenced by one.
    """
    if unit.sales_actual:
        return False
    return any(note.kind in EXPLAINS_ABSENCE for note in unit.context_notes)


def suspect_of(unit: BusinessUnit) -> Optional[Suspect]:
    """Whether this unit's figures look like a break in the data rather than the business."""
    from .mapping import (
        NO_ANALYTICS_SITE,
        ORDER_TRACKING_LOST,
        ORDERS_NOT_TRACKED,
    )

    # An absence somebody has already explained is not a break in the data. Australia
    # stopped being shipped because the customer is not paying; the screen was still
    # telling its reader to go and check the feed. Sending someone to chase a pipeline
    # over a fact they wrote down themselves that morning is how a panel earns the right
    # to be ignored — and this panel's whole value is that everything in it is worth
    # reading.
    #
    # Only the absence, and only from a note that accounts for one. The first version of
    # this silenced every suspect on any noted unit, and Brazil went with it: its note is
    # about a tax change, which explains the size of a gap and says nothing whatever about
    # a missing analytics tag. A real measurement fault on €179k of sales disappeared
    # behind an unrelated sentence, which is the more expensive of the two mistakes.
    if _absence_is_explained(unit):
        return None

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

#: A data break below this obscures too little money to be worth a line on this screen.
#: Well under the materiality floor, deliberately: a broken feed is worth knowing about
#: long before the gap it hides would matter on its own.
#:
#: Small breaks are still counted in the pattern above the list. That is the whole point —
#: the shape is what says "one join, not thirteen incidents", and it is strongest with all
#: thirteen. Dropping them from the count to tidy the list would weaken the only finding
#: on the panel worth acting on.
SUSPECT_FLOOR_EUR = 10_000.0

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


#: How far a reclassified pair may fail to cancel and still be read as one boundary
#: moving. Not zero: the noted channels carry real trading alongside the reclassified
#: revenue — the American Web Partners line holds Amazon as well as Sephora — so an exact
#: offset would only ever appear if nothing else in either channel had moved.
OFFSET_TOLERANCE = 0.25


class ReclassificationCheck:
    """Do the two halves of a reclassified pair actually cancel?

    A note that says "this revenue is filed on the other side of a boundary" makes a
    testable claim: what one channel gained, its neighbour lost. The claim is worth testing
    because it is easy to write down backwards — and a note pointing at the wrong side
    sends someone to correct the source that was right.

    The test is deliberately one-directional. When the two gaps cancel, the boundary
    explains them and that is worth saying. When they do not, this cannot tell whether the
    note is wrong or whether real trading is riding along in the same channels, so it says
    both and asks rather than accuses.
    """

    __slots__ = ("market", "legs", "net", "gross", "notes")

    def __init__(self, market: str, legs: Sequence[Tuple[str, float]], net: float,
                 gross: float, notes=()) -> None:
        self.market = market
        #: (channel label, € gap), in the order they appear on screen.
        self.legs = list(legs)
        self.net = net
        #: The notes themselves, shown beside the verdict. Not decoration: the euros
        #: cannot read prose, so a note written backwards passes the offset test — and
        #: printing it next to the machine's account of the direction is what makes the
        #: disagreement visible to the person who wrote it.
        self.notes = list(notes)
        #: The largest leg, which is what the net is judged against. Summing the legs
        #: instead would compare a residual with a figure that already contains it.
        self.gross = gross

    @property
    def crossed(self) -> bool:
        """Did anything actually move across the boundary this month?

        A boundary shift makes one channel gain and its neighbour lose. Two losses mean
        nothing crossed — the revenue that gets misfiled simply did not ship. Sephora, the
        case this was built for, ships in waves: the American boundary moved in four
        months of the last two years and in none of the others.

        Without this the check confronts a claim on a month where the claim says nothing,
        finds the halves do not cancel — of course they do not — and reports that the note
        may name the wrong side. It would be accusing a correct note of being backwards,
        which is worse than staying quiet.
        """
        return any(gap > 0 for _, gap in self.legs) and any(gap < 0 for _, gap in self.legs)

    @property
    def offsets(self) -> bool:
        if self.gross <= 0 or not self.crossed:
            return False
        return abs(self.net) / self.gross <= OFFSET_TOLERANCE

    @property
    def direction(self) -> str:
        """Which side gained and which lost, in the machine's own words.

        This is the half the check could not otherwise reach. The test above compares
        euros, so a note whose prose describes the boundary backwards passes it silently —
        the numbers cancel either way. Stating the direction here puts that sentence
        beside the note on screen, where a reader can see the two disagree.
        """
        gained = [label for label, gap in self.legs if gap > 0]
        lost = [label for label, gap in self.legs if gap < 0]
        if not gained or not lost:
            return ""
        return "The revenue lands in %s and is missing from %s." % (
            _listed_labels(gained), _listed_labels(lost)
        )

    @property
    def message(self) -> str:
        moved = _listed_labels([label for label, _ in self.legs])
        if not self.crossed:
            return (
                "%s: nothing crossed the boundary this month — %s move the same way, so "
                "there is no split to test. The note stands unexamined until a month in "
                "which the revenue it describes actually ships."
                % (self.market, moved)
            )
        if self.offsets:
            return (
                "%s: %s move against each other and very nearly cancel — %s left over on "
                "%s crossing the boundary. %s The note holds: this is where the revenue "
                "is filed, not how it sold."
                % (self.market, moved, _eur(abs(self.net)), _eur(self.gross),
                   self.direction)
            ).replace("  ", " ")
        return (
            "%s: %s are noted as one boundary, but they do not cancel — %s is left over "
            "on %s crossing. %s Either the note names the wrong side, or these channels "
            "are also trading away from plan on their own."
            % (self.market, moved, _eur(abs(self.net)), _eur(self.gross), self.direction)
        ).replace("  ", " ")


def reclassification_checks(dataset: Dataset) -> List[ReclassificationCheck]:
    """One check per market carrying reclassification notes on two or more channels.

    A single noted channel is not checkable: a boundary has two sides, and only one of
    them being described says nothing about whether the description is right.
    """
    from .context import RECLASSIFIED

    by_market: Dict[str, List[BusinessUnit]] = {}
    for unit in dataset.units:
        if unit.is_aggregate or not unit.budget_known:
            continue
        if any(note.kind == RECLASSIFIED for note in unit.context_notes):
            by_market.setdefault(unit.market, []).append(unit)

    found = []
    for market, units in sorted(by_market.items()):
        if len(units) < 2:
            continue
        legs = [(unit.label, unit.gap_vs_budget) for unit in units]
        net = sum(gap for _, gap in legs)
        gross = max(abs(gap) for _, gap in legs)
        seen, notes = set(), []
        for unit in units:
            for note in unit.context_notes:
                if note.kind == RECLASSIFIED and note.text not in seen:
                    seen.add(note.text)
                    notes.append(note)
        found.append(ReclassificationCheck(market, legs, net, gross, notes))
    return found


def suspects(dataset: Dataset) -> List[Suspect]:
    """Every break, whatever its size — the pattern above the list is read from these."""
    found = [suspect_of(unit) for unit in dataset.units if not unit.is_aggregate]
    return [item for item in found if item is not None]


#: How many broken feeds are named individually. The same cap, and the same reason, as
#: the fire list: a sixth would not be read, and pretending otherwise makes the first five
#: worth less. It bites harder here, because the finding in this panel is the *shape* —
#: one join failing across ten markets is one incident — and a list long enough to scroll
#: buries the two lines that say so.
SUSPECT_LIST_LIMIT = 5


def worth_listing(found: Sequence[Suspect], limit: int = SUSPECT_LIST_LIMIT
                  ) -> List[Suspect]:
    """The ones large enough to name, largest first, capped.

    A break worth 827 euros is real and is not worth a line on a screen a CEO reads in two
    minutes. It still counts in the pattern above: thirteen markets failing the same way
    is the finding, and it is thirteen whether or not each one is individually worth
    printing.
    """
    ranked = sorted(
        (item for item in found if item.is_material),
        key=lambda item: -item.money,
    )
    return ranked[:limit]


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
        "boundary_standing",
        "routed",
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
        #: Whether the boundary claim this card rests on was actually testable this
        #: month. Filled by `fires()`, which is where the other channels are in scope.
        #: A note saying "this gap is a boundary, not a result" takes the market's own
        #: question off the card — so a card must not state that claim flatly on a month
        #: when the screen's own check could not run. It said so two panels below and
        #: nowhere on the card the claim was doing its work.
        self.boundary_standing = ""
        #: What kind of problem this is, and therefore what to do about it. Carried on
        #: the card rather than left implicit: a gap with no measurable cause and a gap
        #: with a diagnosis deserve the same rank and different sentences.
        self.routed = routing.classify(unit)

    @property
    def has_breakdown(self) -> bool:
        return bool(self.contributions)

    @property
    def unattributed(self) -> float:
        """The part of the plan gap the drivers cannot reach.

        Two bridges sit behind one headline. The drivers explain the movement against last
        year; the plan asked for something else again, and the distance between the two is
        growth that was planned and did not happen. Nothing here can attribute it, because
        nobody planned a session count or a conversion rate — so it is named and left
        unattributed rather than folded into a driver that would then be wrong.
        """
        if not self.has_breakdown or self.baseline_label == "plan":
            return 0.0
        return self.gap - self.movement

    @property
    def bridge(self) -> str:
        """Both bridges in one sentence, when they differ."""
        if not self.unattributed:
            return ""
        return (
            "Two bridges: %s against %s, which the drivers above take apart, and %s of "
            "planned growth that did not happen, which nothing here can attribute — no "
            "plan was ever set for sessions or conversion. Together they are the %s "
            "gap against plan."
            % (_eur(self.movement), self.baseline_label, _eur(self.unattributed),
               _eur(self.gap))
        )

    @property
    def chronic_plan(self) -> str:
        """The history's verdict that the plan, not the month, is what is wrong."""
        return self.unit.chronic_plan

    @property
    def plan_vs_record(self) -> str:
        """What the plan asks of this business against what it has been delivering."""
        return self.unit.plan_vs_record

    @property
    def context_notes(self):
        return self.unit.context_notes

    @property
    def action_owner(self) -> str:
        """Who has to act, when a note says it is not the market's lead.

        The screen was printing a country manager's name and, two lines below it, a
        sentence saying the market was not the one to question. Both were right and the
        pair was wrong: a note could already change the question and could not change who
        it was addressed to.
        """
        for note in self.unit.context_notes:
            if note.action_owner:
                return note.action_owner
        return ""

    @property
    def basis_caveat(self) -> str:
        """Which drivers moved for a reason that is not the market.

        A tax change lands entirely on money per unit sold: the basket a shopper fills is
        untouched, the euros recognised against it are not. So the decomposition is still
        arithmetically exact and still says "most of the movement comes from AOV" — true,
        and useless as a management signal unless the reader is told which half of the
        funnel moved because the yardstick moved.
        """
        from .context import BASIS_CHANGE
        from .model import MONEY_DRIVERS

        moved = any(n.kind == BASIS_CHANGE for n in self.unit.context_notes)
        if not moved or not self.has_breakdown:
            return ""
        affected = [c.label for c in self.contributions if c.label in MONEY_DRIVERS]
        if not affected:
            return ""
        return (
            "%s measures money per unit sold, so it carries the change of basis above as "
            "well as any change in trading. The volume drivers beside it do not."
            % _listed_labels(affected)
        )

    @property
    def diagnosis(self) -> str:
        # Context first. Everything below explains a gap; this says whether the gap means
        # what it appears to mean, which has to be read before, not after.
        leading = [n for n in self.unit.context_notes if n.meaning]
        if leading:
            note = leading[0]
            return "%s %s" % (note.meaning, note.text)
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

        Order matters. Context comes first: a gap that is not measured on the same basis
        as its plan does not need a better measurement, it needs a rebased plan. After
        that, a plan aimed at the wrong driver is the most valuable thing this product can
        tell a CEO, so it outranks everything else — including a forecast that keeps
        moving, which is a real issue but a slower one.
        """
        # Context outranks even the missing measurement. Asking how to measure a gap
        # better is the right question only once the gap is known to mean what it looks
        # like — and "why is Brazil down" has an answer nobody needs to go and find.
        asked = [n for n in self.unit.context_notes if n.question]
        if asked:
            return asked[0].question
        if any(n.kind == "on_hold" for n in self.unit.context_notes):
            # The money is genuinely missing, so this stays a fire — but the person who
            # runs the market did not lose it, and asking them why sales collapsed when
            # the Maison chose to stop shipping wastes the meeting and the screen's
            # credibility with it.
            return (
                "What has to happen for this to resume, how much is owed, and what does "
                "the delay cost by the time it does?"
            )
        if self.unit.plan_vs_record and not self.unit.chronic_plan:
            # A plan asking for growth the record has never shown will be missed every
            # month of the year, and asking what moves a driver in thirty days sends
            # someone after a cause that is not there. The question belongs to whoever
            # signed the number, and it is worth asking in month four rather than in
            # month twelve.
            return (
                "Was this plan ever reachable? What it asks for is not what this business "
                "has been delivering — is the number wrong, or is there a change behind "
                "it that has not happened yet?"
            )
        if self.unit.chronic_plan:
            # Before every question about this month, because none of them has an answer
            # here. "What will move conversion in 30 days" asked of a business that has
            # delivered the same steady 93% of its plan every month for a year sends
            # someone to find a cause that does not exist, and again the month after.
            return (
                "Has this plan ever been met? The shortfall has been the same every month "
                "for a year or more — is the target wrong, or is something structural "
                "being tolerated?"
            )
        if self.unit.is_sell_in:
            # Sell-in is shipments. A month of it against a month of plan is mostly a
            # statement about when an order was placed, so "what would it take to measure
            # this properly" is the wrong question twice over: nothing is mismeasured, and
            # the answer nobody needs is a better funnel.
            return (
                "Is this a shipment landing in another month, or has the partner cut its "
                "orders?"
            )
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


def fires(dataset: Dataset, limit: Optional[int] = 5) -> List[Fire]:
    """The units that most deserve attention, worst first.

    Capped on purpose: the brief optimises for CEO attention, not completeness. A sixth
    fire would not be read, and pretending otherwise would make the first five worth less.
    `limit=None` returns every candidate, which is what clustering needs — the cap belongs
    on the subjects a reader ends up with, not on the channels that feed them.
    """
    # A market that moved between its channels and still holds its plan has not lost
    # anything. Ranking the channel it left would be a confident finding about a decision
    # somebody made on purpose — and the channel it chose would appear, two panels down,
    # as a triumph. Both are listed as one reallocation instead.
    moved = reallocating_markets(dataset)

    # The class decides the surface, and only the business surface is ranked here. A
    # boundary in the accounts, a feed that stopped and a definition still being argued
    # are all real work — none of them is a question for a market's lead, and each cost a
    # slot in a list of five that is supposed to be the week's five most valuable
    # conversations.
    candidates = [
        Fire(unit)
        for unit in dataset.units
        if unit.budget_known
        and unit.is_below_budget
        and not unit.is_aggregate
        and routing.classify(unit, is_suspect=suspect_of(unit) is not None).is_business
        and unit.market not in moved
        and abs(unit.gap_vs_budget) >= MATERIALITY_FLOOR_EUR
    ]
    candidates.sort(key=lambda fire: fire.priority.score, reverse=True)
    ranked = candidates if limit is None else candidates[:limit]
    _attach_boundary_standing(ranked, dataset)
    return ranked


class Issue:
    """One subject, not one channel.

    A market losing ground in two channels is one conversation with one person, and the
    screen used to make it two — Japan taking two of the week's five slots and its lead
    named twice on the same page. Ranking channels also quietly ranks by how finely a
    market happens to be cut: a business split across three channels outranks an identical
    one reported as a single line, on nothing but its reporting shape.

    The money still decides. An issue's weight is the sum of its members' — each member
    keeps its own arithmetic, so an order that looks wrong can still be checked line by
    line rather than argued with.
    """

    __slots__ = ("market", "owner", "fires", "gap", "score")

    def __init__(self, market: str, fires: Sequence[Fire]) -> None:
        self.market = market
        self.fires = list(fires)
        self.owner = self.fires[0].unit.owner
        self.gap = sum(fire.gap for fire in self.fires)
        self.score = sum(fire.priority.score for fire in self.fires)

    @property
    def label(self) -> str:
        return self.market

    @property
    def channels(self) -> str:
        """The channels behind the subject, named — a total nobody can locate is a total
        nobody acts on."""
        return _listed_labels([fire.unit.channel_label for fire in self.fires])

    @property
    def is_single(self) -> bool:
        return len(self.fires) == 1

    @property
    def question(self) -> str:
        """The sharpest question in the subject, asked once."""
        return self.fires[0].question


def issues(dataset: Dataset, limit: int = 5) -> List[Issue]:
    """The subjects that most deserve attention, worst first.

    Clustered by market and owner: the two things that decide who is in the room. A
    finer grouping — by outcome, by KPI family — is the right end state and needs
    metadata the tracker does not carry yet; grouping by market already removes the
    duplicate that a reader sees first.
    """
    by_market: Dict[str, List[Fire]] = {}
    for fire in fires(dataset, limit=None):
        by_market.setdefault(fire.unit.market, []).append(fire)

    found = [Issue(market, group) for market, group in by_market.items()]
    found.sort(key=lambda issue: issue.score, reverse=True)
    return found[:limit]


def routed_elsewhere(dataset: Dataset) -> List["Fire"]:
    """Material gaps that are somebody else's to answer, worst first.

    Not dropped — routed. Each is a real amount of money filed under the wrong segment, or
    measured against a plan that no longer compares, or sitting in a market that stopped
    trading on purpose. They keep their whole card: the diagnosis, the boundary check, the
    question. What they lose is the slot: a list of five that is meant to be the week's
    five most valuable conversations cannot spend one of them on a question the reader
    would have to forward.
    """
    found = [
        Fire(unit)
        for unit in dataset.units
        if unit.budget_known
        and unit.is_below_budget
        and not unit.is_aggregate
        and suspect_of(unit) is None
        and not routing.classify(unit).is_business
        and abs(unit.gap_vs_budget) >= MATERIALITY_FLOOR_EUR
    ]
    found.sort(key=lambda fire: fire.gap)
    _attach_boundary_standing(found, dataset)
    return found


def _attach_boundary_standing(found: Sequence["Fire"], dataset: Dataset) -> None:
    """Carry the boundary check's verdict onto the cards it is about.

    The check runs on the whole market and prints its own panel. The card, meanwhile,
    prints the note's claim — "the gap here is a boundary rather than a result" — as
    settled, and on the strength of it the market's own question disappears. When the
    check could not run, the two halves of the screen say different things about the
    same euros, and only one of them is on the card the reader acts from.
    """
    from .context import RECLASSIFIED

    checks = {check.market: check for check in reclassification_checks(dataset)}
    for fire in found:
        if not any(note.kind == RECLASSIFIED for note in fire.unit.context_notes):
            continue
        check = checks.get(fire.unit.market)
        if check is None:
            fire.boundary_standing = (
                "Only one side of this boundary is noted, so nothing here can check it: "
                "a boundary has two sides, and one description says nothing about "
                "whether it is right."
            )
        elif not check.crossed:
            fire.boundary_standing = (
                "Not checked this month: nothing crossed this boundary — %s move the "
                "same way — so the sentence above rests on the note alone."
                % _listed_labels([label for label, _ in check.legs])
            )
        elif check.offsets:
            fire.boundary_standing = (
                "Checked this month: the two sides cancel to %s. %s"
                % (_eur(abs(check.net)), check.direction)
            )
        else:
            fire.boundary_standing = (
                "Checked this month and they do not cancel: %s left over. Either the "
                "note names the wrong side, or these channels are also trading away "
                "from plan on their own." % _eur(abs(check.net))
            )


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

    # Everything else the funnel multiplies by, named from the data rather than written
    # into the sentence. Online it is one driver; in a store it is two, units per ticket
    # and price per unit. A formula that names some of its factors is a formula the reader
    # cannot reproduce, which is worse than showing none.
    rest = [
        (name, unit.actual.value_of(name) or 0.0)
        for name in unit.actual.labels
        if name not in (volume_label, label)
    ]

    return Opportunity(
        unit=unit,
        driver=label,
        amount=amount,
        assumption=(
            "Assumes %s returns to last year's %s while %s and the other drivers hold at "
            "today's level."
            % (_driver_word(label), _level_pct(before, digits=2), volume_label.lower())
        ),
        # The formula as it is actually computed, which is not what this line used to
        # say. `Drivers.sales` is the product of every driver, so the recovery already
        # carries today's AOV — the displayed line omitted it, and a reader checking the
        # arithmetic would have found a number they could not reproduce.
        calculation=(
            "%s %s × (%s − %s)%s = %s"
            % (volume_label, _num(volume_now), _level_pct(before, digits=2),
               _level_pct(now, digits=2),
               "".join(" × %s %s" % (_driver_word(name), _driver_value(name, value))
                       for name, value in rest),
               _eur(amount))
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
    # The other half of the same decision. A channel that grew because its market chose to
    # push it is not a playbook another market could copy — it is one country's arbitrage,
    # and the channel beside it paid for it.
    moved = reallocating_markets(dataset)

    found = []
    for unit in dataset.units:
        if unit.market in moved:
            continue
        if not unit.budget_known:
            # Beating a budget that does not exist is not an achievement.
            continue
        if unit.is_sell_in:
            # A shipment that landed early beats its month by any margin you like, and
            # beats it again in reverse next month. Calling that a playbook to replicate
            # would send someone to copy a calendar. Until several months are in hand
            # there is nothing here to praise or to learn from.
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
    """One line per person, and never two for the same one.

    Fed from the subjects rather than the channels: the deduplication below caught the
    repeat, but only after the ranking had already spent two of its five slots on the
    same market — so the name appeared once and the market twice, which is the same
    failure wearing a different hat.
    """
    pushes: List[Push] = []
    seen = set()
    for fire in items:
        owner = fire.unit.owner
        if owner.name in seen:
            continue
        if fire.unit.basis_changed:
            # The gap is real in the accounts and is not this person's to answer for.
            # Handing it to them would be the cockpit's most expensive kind of mistake:
            # confidently wrong, about a named human being.
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


def _driver_value(label: str, value: float) -> str:
    """A driver's value in the unit that driver is measured in.

    Three kinds, and guessing between them is how "UPT €2" reaches a screen: a rate, an
    amount of money per unit sold, and a plain count. Anything unrecognised is printed as
    a number with no unit claimed — a missing unit costs a little, a wrong one costs the
    line its credibility.
    """
    from .model import MONEY_DRIVERS, RATE_DRIVERS

    if label in RATE_DRIVERS:
        return _level_pct(value, digits=2)
    if label in MONEY_DRIVERS:
        return _eur(value)
    return _num(value)


def _level_pct(value: Optional[float], digits: int = 1) -> str:
    """A rate as it stands, with no sign.

    `_pct` always signs, which is right for a movement and wrong for a level: printed
    the same way, last year's conversion rate of 2.30% reads as a rise of 2.30 points —
    and the driver tables two cards above print exactly that kind of number in exactly
    that form. Same notation, two different quantities, is how a reader stops being able
    to tell which one they are looking at.
    """
    if value is None:
        return "n/a"
    return "%.*f%%" % (digits, value * 100)


#: Driver labels that are initialisms, not words. Lower-casing them mid-sentence turns
#: "AOV" into "aov", which reads as a typo in the one sentence the CEO reads first.
INITIALISMS = frozenset({"AOV", "UPT", "ASP"})


def _listed_labels(labels) -> str:
    if len(labels) < 2:
        return "".join(labels)
    return "%s and %s" % (", ".join(labels[:-1]), labels[-1])


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
