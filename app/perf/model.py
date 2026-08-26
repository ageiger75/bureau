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

#: Driver labels per channel, in decomposition order (brief §14).
#: Sales = product of the drivers, exactly.
DRIVER_LABELS = {
    ECOMMERCE: ("Sessions", "Conversion", "AOV"),
    RETAIL: ("Traffic", "Conversion", "UPT", "ASP"),
}

#: Drivers expressed as a rate, shown as a percentage rather than a count.
RATE_DRIVERS = frozenset({"Conversion"})


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


class Owner:
    """A named person accountable for a business unit.

    Brief §10 is explicit: identify owners whose area needs attention, never score people.
    Nothing in this class ranks a person — the ranking applies to the business.
    """

    __slots__ = ("name", "role", "market")

    def __init__(self, name: str, role: str, market: str) -> None:
        self.name = name
        self.role = role
        self.market = market


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
    def has_driver_breakdown(self) -> bool:
        """Whether this unit's gap can be attributed to drivers at all."""
        return self.actual.has_breakdown and self.budget.has_breakdown

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

    __slots__ = ("period_label", "as_of", "units")

    def __init__(self, period_label: str, as_of: str, units: Sequence[BusinessUnit]) -> None:
        self.period_label = period_label
        self.as_of = as_of
        self.units = list(units)

    @property
    def sales_actual(self) -> float:
        return sum(unit.sales_actual for unit in self.units)

    @property
    def sales_budget(self) -> float:
        return sum(unit.sales_budget for unit in self.units)

    @property
    def sales_last_year(self) -> float:
        return sum(unit.sales_last_year for unit in self.units)

    @property
    def sales_forecast(self) -> float:
        return sum(unit.forecast_sales for unit in self.units)

    def by_key(self, key: str) -> Optional[BusinessUnit]:
        for unit in self.units:
            if unit.key == key:
                return unit
        return None
