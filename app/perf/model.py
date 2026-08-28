"""Normalised performance model.

One shape for every business unit, whatever the channel. Sales are never stored as a free
number: they are the product of their drivers, so a figure on screen can always be taken
apart. A dataset where sales and drivers disagree would quietly destroy the only thing
this product sells — trust in the diagnosis.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

ECOMMERCE = "ecommerce"
RETAIL = "retail"

#: Sold by the Maison to the end customer on a platform it does not run. Sell-out, and
#: kept apart from e-commerce because it has no funnel of its own: the platform owns the
#: traffic, so there are no sessions to compare and none to be recovered.
MARKETPLACE = "marketplace"

#: Driver labels per channel, in decomposition order (brief §14).
#: Sales = product of the drivers, exactly.
DRIVER_LABELS = {
    ECOMMERCE: ("Sessions", "Conversion", "AOV"),
    RETAIL: ("Traffic", "Conversion", "UPT", "ASP"),
}

#: Drivers expressed as a rate, shown as a percentage rather than a count.
RATE_DRIVERS = frozenset({"Conversion"})

#: Drivers that measure money per unit sold, as opposed to volume. They move when trading
#: changes — and also when what counts as a sale changes. A tax reform lands entirely here:
#: the basket a shopper fills is untouched, the euros recognised against it are not. Volume
#: drivers survive such a change unharmed, which is what makes the distinction worth
#: keeping: the decomposition stays readable if the reader is told which half moved for a
#: reason that has nothing to do with the market.
MONEY_DRIVERS = frozenset({"AOV", "ASP"})

#: Markets whose stores have footfall counters, and where a retail conversion rate can
#: therefore be trusted.
#:
#: Everywhere else the measure exists in the data and does not describe reality — no
#: counter, or coverage too partial to represent the estate. Showing it anyway would be
#: worse than showing nothing: a wrong number is acted upon, an absent one is asked about.
#:
#: This list is a business fact, not a technical one. Keep it here, edit it by hand, and
#: extend it market by market as counters are installed.
TRAFFIC_COUNTER_MARKETS = frozenset(
    {
        "France",
        "United Kingdom",
        "Germany",
        "Italy",
        "Spain",
        "Portugal",
        "Belgium",
        "Netherlands",
        "Switzerland",
        "Ireland",
        "Austria",
        "United States",
        "Canada",
    }
)


def retail_conversion_is_reliable(market: str) -> bool:
    return market in TRAFFIC_COUNTER_MARKETS


#: Shown wherever a retail unit carries no breakdown for this reason.
NO_COUNTER_REASON = (
    "Store footfall is not counted reliably in this market, so conversion cannot be read."
)


class Drivers:
    """Ordered multiplicative drivers of sales.

    Kept ordered because the contribution analysis is a chained decomposition: the order
    is part of the method, not an implementation detail (see `analytics.contributions`).
    """

    __slots__ = ("labels", "values")

    def __init__(self, labels: Sequence[str], values: Sequence[float]) -> None:
        if len(labels) != len(values):
            raise ValueError("each driver needs a label")
        self.labels: Tuple[str, ...] = tuple(labels)
        self.values: Tuple[float, ...] = tuple(float(v) for v in values)

    @classmethod
    def sales_only(cls, amount: float) -> "Drivers":
        """A unit whose sales are known but whose drivers are not.

        Real warehouses do not measure every channel the same way: a market may report
        footfall and tickets while an online channel reports neither. Such a unit still
        belongs in the group total and still has a gap worth seeing — it simply cannot be
        taken apart, and the screen has to say so rather than show a table of blanks.
        """
        return cls(("Sales",), (amount,))

    @property
    def has_breakdown(self) -> bool:
        return len(self.labels) > 1

    @property
    def sales(self) -> float:
        """Sales implied by the drivers. Never stored separately — never inconsistent."""
        total = 1.0
        for value in self.values:
            total *= value
        return total

    def value_of(self, label: str) -> Optional[float]:
        if label not in self.labels:
            return None
        return self.values[self.labels.index(label)]

    def pairs(self) -> List[Tuple[str, float]]:
        return list(zip(self.labels, self.values))


def retail_drivers(
    market: str,
    sales: float,
    conversion: Optional[float] = None,
    upt: Optional[float] = None,
    asp: Optional[float] = None,
) -> "Drivers":
    """Retail drivers for a market, or sales alone where footfall is not counted.

    A factory rather than a rule to remember: whoever maps a query cannot accidentally
    hand the cockpit a conversion rate from a market that has no counters. The wrong
    number never gets built, so it never has to be caught downstream.
    """
    if not retail_conversion_is_reliable(market):
        return Drivers.sales_only(sales)
    if conversion is None or upt is None or asp is None:
        return Drivers.sales_only(sales)
    traffic = sales / (conversion * upt * asp)
    return Drivers(("Traffic", "Conversion", "UPT", "ASP"), (traffic, conversion, upt, asp))


def ecommerce_drivers(
    sales: float, sessions: float, orders: float
) -> "Drivers":
    """Digital drivers that telescope to sales in the currency `sales` is expressed in.

    Sessions × (orders / sessions) × (sales / orders) = sales, exactly. Deriving the value
    per order from the same sales figure is what keeps the identity closed — and what
    allows sessions and orders to come from web analytics while the money comes from the
    sales system, in a single comparable currency.
    """
    if sessions <= 0 or orders <= 0:
        return Drivers.sales_only(sales)
    return Drivers(
        ("Sessions", "Conversion", "AOV"),
        (sessions, orders / sessions, sales / orders),
    )


class Owner:
    """A named person accountable for a business unit.

    Brief §10 is explicit: identify owners whose area needs attention, never score people.
    Nothing in this class ranks a person — the ranking applies to the business.
    """

    __slots__ = ("name", "role", "market", "escalates_to", "local_lead")

    def __init__(
        self,
        name: str,
        role: str,
        market: str,
        escalates_to: str = "",
        local_lead: str = "",
    ) -> None:
        self.name = name
        self.role = role
        self.market = market
        #: The BU head above this owner, when the owner is a country or cluster GM. Not a
        #: chain of command to invoke by default — it is there so a conversation that has
        #: already happened twice has somewhere to go.
        self.escalates_to = escalates_to
        #: Whoever runs the market day to day, when that is not the accountable owner.
        #: Named separately rather than instead: the question goes to the person who
        #: answers for the number, and the detail lives with the person on the ground.
        self.local_lead = local_lead


class BusinessUnit:
    """A market × channel, with its current period and the history that gives it context.

    History matters as much as the level: a gap that has been widening for three months is
    not the same management problem as a gap that appeared last week, even at equal euros.
    """

    __slots__ = (
        "key",
        "label",
        "market",
        "region",
        "channel",
        "owner",
        "strategic_weight",
        "actual",
        "budget",
        "last_year",
        "forecast_sales",
        "months_below_budget",
        "gap_history",
        "forecast_history",
        "market_index_pct",
        "management_explanation",
        "action_focus",
        "win_driver",
        "is_aggregate",
        "no_breakdown_reason",
        "sessions",
        "orders",
        "budget_known",
        "funnel_status",
        "context_notes",
        "perimeter",
        "chronic_plan",
    )

    def __init__(
        self,
        key: str,
        label: str,
        market: str,
        region: str,
        channel: str,
        owner: Owner,
        actual: Drivers,
        budget: Drivers,
        last_year: Drivers,
        forecast_sales: float,
        strategic_weight: float = 1.0,
        months_below_budget: int = 0,
        gap_history: Sequence[float] = (),
        forecast_history: Sequence[float] = (),
        market_index_pct: Optional[float] = None,
        management_explanation: str = "",
        action_focus: str = "",
        win_driver: str = "",
        is_aggregate: bool = False,
        no_breakdown_reason: str = "",
        sessions: Optional[float] = None,
        orders: Optional[float] = None,
        budget_known: bool = True,
        funnel_status: str = "",
        context_notes=(),
        perimeter: str = "",
        chronic_plan: str = "",
    ) -> None:
        self.key = key
        self.label = label
        self.market = market
        self.region = region
        self.channel = channel
        self.owner = owner
        self.actual = actual
        self.budget = budget
        self.last_year = last_year
        self.forecast_sales = forecast_sales
        # Strategic weight is an explicit, inspectable input — not a hidden model output.
        self.strategic_weight = strategic_weight
        self.months_below_budget = months_below_budget
        #: Monthly € gap vs budget, oldest first. Drives the acceleration factor.
        self.gap_history = tuple(gap_history)
        #: Successive forecasts for the same period, oldest first (brief §25, UK).
        self.forecast_history = tuple(forecast_history)
        #: Published market growth, when available — used to test the "difficult market"
        #: explanation rather than repeat it (brief §3.5).
        self.market_index_pct = market_index_pct
        self.management_explanation = management_explanation
        #: What the current action plan actually targets. Compared with the largest
        #: driver of the gap to detect a misaligned plan.
        self.action_focus = action_focus
        self.win_driver = win_driver
        #: True for a roll-up of many small markets. It belongs in the group total, never
        #: in the fires: there is no one to challenge about "Rest of World", and letting
        #: it take a slot would push out a market someone can actually be asked about.
        self.is_aggregate = is_aggregate
        #: Why this unit carries no driver breakdown. Shown on screen: "we do not measure
        #: footfall here" and "this channel reports sales only" are different facts, and
        #: the second is not a reason to go looking for the first.
        self.no_breakdown_reason = no_breakdown_reason
        #: Raw counts as measured, kept whether or not they formed a usable driver set.
        #: Sessions arriving with no orders is exactly the case where the drivers cannot
        #: be built — and exactly the case worth reporting, so the evidence has to survive
        #: the degradation.
        self.sessions = sessions
        self.orders = orders
        #: False when no budget exists for this market and period. A missing budget must
        #: never be read as a budget of zero: the gap would then equal the whole of sales
        #: and the market would top the screen as a triumph. Such units are kept out of
        #: both fires and wins, and counted so the omission is visible.
        self.budget_known = budget_known
        #: What the query established about this market's funnel: measured, never tracked,
        #: tracking lost, or no own site at all. Four states with four different remedies,
        #: which is why they are not collapsed into one word for "missing".
        self.funnel_status = funnel_status
        #: What happened that the numbers cannot say — a tax change, a one-off. Never a
        #: correction to a figure: what these change is the question, not the arithmetic.
        self.context_notes = list(context_notes)
        #: `own`, `platform`, `sell-in` or `other`. What a gap means depends on it: a
        #: shipment to a reseller lands in one month or the next, so a month of sell-in
        #: measured against a month of plan is mostly a statement about timing.
        self.perimeter = perimeter
        #: Set when this business has been under its plan every month for a year at a
        #: steady ratio. That is a different management problem from a gap that opened,
        #: and the two need different conversations: one is about the plan, the other is
        #: about the month. Blank unless the history earns it.
        self.chronic_plan = chronic_plan

    # ------------------------------------------------------------------ sales

    @property
    def sales_actual(self) -> float:
        return self.actual.sales

    @property
    def sales_budget(self) -> float:
        return self.budget.sales

    @property
    def sales_last_year(self) -> float:
        return self.last_year.sales

    @property
    def is_sell_in(self) -> bool:
        return self.perimeter == "sell-in"

    @property
    def basis_changed(self) -> bool:
        """Whether this gap is a statement about trading at all.

        It is not when the plan and the actual are measured on different bases, and it is
        not when they classify the same revenue under different segments. Either way the
        gap is real in the accounts and says nothing about how the market is doing — so it
        must never be handed to whoever runs that market as a performance question.
        """
        from .context import NOT_TRADING

        return any(note.kind in NOT_TRADING for note in self.context_notes)

    def decomposition_baseline(self):
        """What the drivers can honestly be compared against, and its name.

        A budget is a single committed number, not a funnel: nothing was planned for
        sessions or conversion, so a gap against it cannot be attributed to either. Last
        year, on the other hand, was measured the same way the current period was — so it
        is the only baseline a decomposition can use, and the reader has to be told which
        one was used.

        Returns `(drivers, label)` or `(None, "")`.
        """
        if not self.actual.has_breakdown:
            return None, ""
        if self.budget.has_breakdown and self.budget.labels == self.actual.labels:
            return self.budget, "plan"
        if self.last_year.has_breakdown and self.last_year.labels == self.actual.labels:
            return self.last_year, "last year"
        return None, ""

    @property
    def has_driver_breakdown(self) -> bool:
        """Whether this unit's movement can be attributed to drivers at all."""
        return self.decomposition_baseline()[0] is not None

    @property
    def gap_vs_budget(self) -> float:
        """Signed € gap. Negative means below plan."""
        return self.sales_actual - self.sales_budget

    @property
    def gap_vs_last_year(self) -> float:
        return self.sales_actual - self.sales_last_year

    @property
    def is_below_budget(self) -> bool:
        return self.gap_vs_budget < 0

    @property
    def forecast_revisions_down(self) -> int:
        """How many times the forecast for this period has been revised downwards."""
        return len(
            [
                1
                for before, after in zip(self.forecast_history, self.forecast_history[1:])
                if after < before
            ]
        )


class Dataset:
    """The whole normalised dataset for one period."""

    __slots__ = ("period_label", "as_of", "units", "ytd")

    def __init__(
        self,
        period_label: str,
        as_of: str,
        units: Sequence[BusinessUnit],
        ytd=None,
    ) -> None:
        self.period_label = period_label
        self.as_of = as_of
        self.units = list(units)
        #: The fiscal year to date, when a history was read. None means no history, which
        #: the screen says rather than papering over with a single month's figure.
        self.ytd = ytd

    @property
    def sales_actual(self) -> float:
        return sum(unit.sales_actual for unit in self.units)

    @property
    def sales_budget(self) -> float:
        """Group budget, over the units that have one.

        Units without a budget contribute nothing here and their sales are reported
        separately, rather than silently widening or narrowing the group variance.
        """
        return sum(unit.sales_budget for unit in self.units if unit.budget_known)

    @property
    def sales_last_year(self) -> float:
        return sum(unit.sales_last_year for unit in self.units)

    @property
    def sales_forecast(self) -> float:
        return sum(unit.forecast_sales for unit in self.units)

    def by_market(self):
        """Units grouped by market, budgeted ones only.

        A market is what a person runs; a channel is a way of reaching customers, and a
        market can move between channels during the year on purpose. So a gap has to be
        readable at both levels — and read at the market level first, because that is
        where the commitment was made.
        """
        grouped = {}
        for unit in self.units:
            if unit.is_aggregate or not unit.budget_known:
                continue
            grouped.setdefault(unit.market, []).append(unit)
        return grouped

    @property
    def markets_without_own_site(self) -> List[str]:
        """Markets that sell online only through partners who resell.

        Not a fault, and not a gap to chase: it is how those markets work. But a reader
        looking for a large market and not finding it deserves to be told why, or they
        will assume the screen lost it.
        """
        from .mapping import NO_ANALYTICS_SITE

        return sorted(
            {u.market for u in self.units if u.funnel_status == NO_ANALYTICS_SITE}
        )

    @property
    def unbudgeted(self) -> List[BusinessUnit]:
        """Units whose variance cannot be computed, because nothing was committed."""
        return [unit for unit in self.units if not unit.budget_known]

    @property
    def unbudgeted_sales(self) -> float:
        return sum(unit.sales_actual for unit in self.unbudgeted)

    def by_key(self, key: str) -> Optional[BusinessUnit]:
        for unit in self.units:
            if unit.key == key:
                return unit
        return None
