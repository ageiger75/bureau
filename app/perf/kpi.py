"""Managed KPIs: targets, direction, cadence, and whether a figure may be challenged.

Sales decompose into drivers. A KPI does not — it is a number somebody owns, with a target
somebody agreed, reported on a cadence somebody set. The cockpit therefore reads it under
three rules that come from the tracker itself, and each exists to prevent a specific way of
losing a CEO's trust:

1. **Cadence governs freshness.** A quarterly KPI has no August value, and saying so is not
   an alert — it is the calendar. Flagging it would train the reader to ignore flags.
2. **Direction decides what a gap is.** Retail turnover above target is bad news; a brand
   ranking above target is good news. One rule cannot serve both.
3. **A provisional definition suspends the challenge.** When the definition or the target is
   still moving, the variance is shown and the CEO question is withheld, with the reason.
   Sending a CEO to challenge someone about a number nobody has agreed yet costs more than
   the insight is worth.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from . import fiscal

# ------------------------------------------------------------------ vocabulary

MONTHLY = "monthly"
QUARTERLY = "quarterly"
HALF_YEARLY = "half_yearly"
ANNUAL = "annual"
MILESTONE = "milestone"

UP = "up"
DOWN = "down"

LOCKED = "locked"
PROVISIONAL = "provisional"

P1 = "P1"
P2 = "P2"
P3 = "P3"

#: Performance: where the figure stands against what was asked of it. One axis, and only
#: one — a KPI is never called "watch" because its reading is old.
ON_TRACK = "on_track"
WATCH = "watch"
ALERT = "alert"
CANNOT_JUDGE = "cannot_judge"

#: Freshness: whether the figure that exists is the one that should. The second axis, and
#: orthogonal to the first on purpose: a KPI can sit exactly on target and be two months
#: stale, and a screen that folds the two into one verdict has to lie about one of them.
#:
#: Three states, not the four the design calls for. `due_soon` needs the day a reading is
#: expected to land — a normal reporting lag, which varies by KPI and lives in nobody's
#: column yet. Inventing one would turn every KPI amber for a week each month on a rule
#: this cockpit made up.
FRESH = "fresh"
OVERDUE = "overdue"
NOT_DUE = "not_due"

FRESHNESS_LABELS = {
    FRESH: "Current",
    OVERDUE: "Reading overdue",
    NOT_DUE: "Not due yet",
}

#: The tracker's own rule: at target or better is fine, within 5% is watch, beyond is alert.
WATCH_BAND = 0.05

FREQUENCY_LABELS = {
    MONTHLY: "Monthly",
    QUARTERLY: "Quarterly",
    HALF_YEARLY: "Half-yearly",
    ANNUAL: "Annual",
    MILESTONE: "Milestone",
}

STATUS_LABELS = {
    ON_TRACK: "On track",
    WATCH: "Watch",
    ALERT: "Alert",
    CANNOT_JUDGE: "Cannot judge",
}


class Reading:
    """One reported value, and the period it belongs to."""

    __slots__ = ("period", "value")

    def __init__(self, period: str, value: float) -> None:
        self.period = period
        self.value = float(value)


class Kpi:
    __slots__ = (
        "key",
        "label",
        "definition",
        "scope",
        "owner",
        "pillar",
        "unit",
        "direction",
        "frequency",
        "source",
        "definition_status",
        "priority",
        "target",
        "last_year",
        "readings",
        "open_question",
    )

    def __init__(
        self,
        key: str,
        label: str,
        definition: str,
        scope: str,
        owner: str,
        pillar: str,
        unit: str,
        target: Optional[float],
        direction: str = UP,
        frequency: str = MONTHLY,
        source: str = "",
        definition_status: str = LOCKED,
        priority: str = P2,
        last_year: Optional[float] = None,
        readings: Sequence[Reading] = (),
        open_question: str = "",
    ) -> None:
        self.key = key
        self.label = label
        self.definition = definition
        self.scope = scope
        self.owner = owner
        self.pillar = pillar
        self.unit = unit
        self.target = target
        self.direction = direction
        self.frequency = frequency
        self.source = source
        self.definition_status = definition_status
        self.priority = priority
        self.last_year = last_year
        #: Oldest first.
        self.readings = list(readings)
        #: What is still unsettled about the definition or the target. Shown instead of a
        #: challenge, so the reader knows why no question is being asked.
        self.open_question = open_question

    # ------------------------------------------------------------------ readings

    @property
    def latest(self) -> Optional[Reading]:
        return self.readings[-1] if self.readings else None

    @property
    def previous(self) -> Optional[Reading]:
        return self.readings[-2] if len(self.readings) >= 2 else None

    @property
    def has_reading(self) -> bool:
        return bool(self.readings)

    # ------------------------------------------------------------------ judgement

    @property
    def gap(self) -> Optional[float]:
        """Signed distance from target, positive when the KPI is where it should be.

        Direction-aware, so a single sign convention holds across the whole cockpit: a
        positive gap is always good news, whichever way the KPI is supposed to move.
        """
        if self.latest is None or self.target is None:
            return None
        raw = self.latest.value - self.target
        return raw if self.direction == UP else -raw

    @property
    def gap_ratio(self) -> Optional[float]:
        if self.gap is None or not self.target:
            return None
        return self.gap / abs(self.target)

    @property
    def status(self) -> str:
        """Where the figure stands. Never a comment on how old it is."""
        if self.latest is None or self.target is None:
            return CANNOT_JUDGE
        ratio = self.gap_ratio
        if ratio is None:
            return CANNOT_JUDGE
        if ratio >= 0:
            return ON_TRACK
        if abs(ratio) <= WATCH_BAND:
            return WATCH
        return ALERT

    @property
    def trend(self) -> Optional[float]:
        """Change since the previous reading, in the direction that counts as progress."""
        if self.latest is None or self.previous is None:
            return None
        raw = self.latest.value - self.previous.value
        return raw if self.direction == UP else -raw

    @property
    def is_improving(self) -> Optional[bool]:
        trend = self.trend
        return None if trend is None else trend > 0

    # ------------------------------------------------------------------ cadence

    def expected_period(self, today: Optional[date] = None) -> Optional[str]:
        """The last period for which a figure should exist by now.

        `None` for a milestone: there is no value to expect, only progress to follow.
        """
        day = today or date.today()
        if self.frequency == MONTHLY:
            return fiscal.month_label(fiscal.previous_month(day))
        if self.frequency == QUARTERLY:
            return fiscal.quarter_label(fiscal.previous_quarter_end(day))
        if self.frequency == HALF_YEARLY:
            return fiscal.half_label(fiscal.previous_half_end(day))
        if self.frequency == ANNUAL:
            return fiscal.year_label(fiscal.previous_year_end(day))
        return None

    def freshness(self, today: Optional[date] = None) -> str:
        """Whether the figure that exists is the one that should exist by now."""
        expected = self.expected_period(today)
        if expected is None:
            return NOT_DUE
        if self.latest is None or self.latest.period != expected:
            return OVERDUE
        return FRESH

    def freshness_label(self, today: Optional[date] = None) -> str:
        return FRESHNESS_LABELS[self.freshness(today)]

    def is_awaiting(self, today: Optional[date] = None) -> bool:
        """Is a figure genuinely late, as opposed to simply not due?

        This is the guardrail that keeps a quarterly KPI from being reported missing every
        month it is not collected.
        """
        expected = self.expected_period(today)
        if expected is None:
            return False
        if self.latest is None:
            return True
        return self.latest.period != expected

    # ------------------------------------------------------------------ challenge

    @property
    def can_be_challenged(self) -> bool:
        """Whether a CEO question may be raised on this KPI.

        False while the definition or target is provisional. The variance is still shown —
        hiding it would be worse — but nobody is sent to argue about a number that is not
        yet agreed.
        """
        return self.definition_status == LOCKED

    @property
    def withheld_reason(self) -> str:
        if self.can_be_challenged:
            return ""
        if self.open_question:
            return "Definition still open — %s" % self.open_question
        return "Definition or target not locked yet; the variance is shown, the challenge is not."

    def question(self, today: Optional[date] = None) -> str:
        """One question, or nothing at all. Silence is a valid output here.

        Three ways this method stays quiet, each deliberate: the definition is not agreed,
        the KPI is merely on watch rather than off track, or it is at target. A question
        on every line would be noise, and noise is what this screen exists to remove.
        """
        if not self.can_be_challenged:
            return ""
        if self.latest is None:
            # Nothing has ever been reported: there is no performance to ask about, and
            # the figure itself is the blocker.
            return "No reading has ever arrived. What is holding it up?"
        if self.status != ALERT:
            return ""

        if self.is_improving:
            return "Short of target but improving. Is the trajectory enough to close it?"
        if self.direction == DOWN:
            # "Below target" would be plainly wrong for a KPI that is supposed to fall.
            return "Above the ceiling and still rising. What changes it before the next reading?"
        return "Below target and still falling. What changes it before the next reading?"


# --------------------------------------------------------------------------- selection


def needing_attention(kpis: Sequence[Kpi]) -> List[Kpi]:
    """KPIs off target, worst relative gap first.

    Priority breaks ties: a P1 tracked at board level outranks a P3 followed inside a
    function, at equal distance from target.
    """
    priority_rank = {P1: 0, P2: 1, P3: 2}
    off = [kpi for kpi in kpis if kpi.status in (WATCH, ALERT)]
    off.sort(
        key=lambda kpi: (
            priority_rank.get(kpi.priority, 3),
            kpi.gap_ratio if kpi.gap_ratio is not None else 0.0,
        )
    )
    return off


def awaiting(kpis: Sequence[Kpi], today: Optional[date] = None) -> List[Kpi]:
    return [kpi for kpi in kpis if kpi.is_awaiting(today)]


def worth_showing(kpis: Sequence[Kpi], today: Optional[date] = None) -> List[Kpi]:
    """Everything off on either axis, each KPI once.

    The panel used to list a KPI for being off target and then list it again, below, for
    being overdue — the same line twice, under two headings, as if they were two problems.
    They are two facts about one KPI, and the card shows both.
    """
    off = {id(item) for item in needing_attention(kpis)}
    ordered = needing_attention(kpis) + [
        item for item in kpis
        if id(item) not in off and item.freshness(today) == OVERDUE
    ]
    return ordered


def provisional(kpis: Sequence[Kpi]) -> List[Kpi]:
    return [kpi for kpi in kpis if not kpi.can_be_challenged]


def by_scope(kpis: Sequence[Kpi], scope: str) -> List[Kpi]:
    return [kpi for kpi in kpis if kpi.scope == scope]


#: What a KPI without a pillar is filed under. Named rather than folded into whichever
#: heading happens to be first: a KPI whose domain nobody stated is a fact about the
#: tracker, and hiding it inside a domain it does not belong to is how a panel called
#: "Customers" ended up carrying a supply-chain metric.
UNFILED = "Not assigned to a pillar"


def by_pillar(kpis: Sequence[Kpi]) -> List[Tuple[str, List[Kpi]]]:
    """KPIs grouped under the pillar the tracker files them under, largest group first.

    The domain comes from the tracker and from nowhere else — never from a keyword, an
    owner, or which query happened to produce the figure. Grouping them by the query is
    what put customer recruitment, an advocacy score and a refill rate under one heading
    called "Customers": three pillars, one label, and a reader who would have taken the
    lot for a picture of the customer base.
    """
    groups: Dict[str, List[Kpi]] = {}
    for item in kpis:
        groups.setdefault((item.pillar or "").strip() or UNFILED, []).append(item)
    return sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))


def format_value(kpi: Kpi, value: Optional[float]) -> str:
    """A KPI value with its unit, at the precision the unit deserves."""
    if value is None:
        return "—"
    unit = kpi.unit
    if unit == "%":
        return "%.1f%%" % value
    if unit == "k clients":
        return "%.0fk" % value
    if unit == "€":
        return "€%.0f" % value
    if unit == "score":
        return "%.0f" % value
    if unit == "M€":
        return "€%.1fm" % value
    return "%.1f %s" % (value, unit)
