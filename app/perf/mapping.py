"""Warehouse rows to the normalised model.

The join between two sources happens here, and only here: money and drivers come from the
warehouse, budget and last year from the planning file. Keeping the seam in one place is
what allows either side to change without the other noticing.

Nothing in this module invents a figure. Where a source is silent the field stays empty
and the cockpit says so — which is the behaviour every layer above depends on.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from . import owners as owners_module
from .budget import Budget, normalise_market
from .model import (
    ECOMMERCE,
    NO_COUNTER_REASON,
    RETAIL,
    BusinessUnit,
    Dataset,
    Drivers,
    ecommerce_drivers,
    retail_conversion_is_reliable,
    retail_drivers,
)

#: Beyond this relative distance, a budget in the planning file and one in the warehouse
#: are not two roundings of the same number. Worth knowing about; not worth blocking on.
BUDGET_DISAGREEMENT = 0.02


def _number(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class BudgetConflict:
    """The planning file and the warehouse disagree about the same commitment."""

    __slots__ = ("market", "channel", "period", "from_file", "from_warehouse")

    def __init__(self, market, channel, period, from_file, from_warehouse) -> None:
        self.market = market
        self.channel = channel
        self.period = period
        self.from_file = from_file
        self.from_warehouse = from_warehouse

    @property
    def message(self) -> str:
        return (
            "%s %s: the planning file says %.0f and the warehouse says %.0f for %s."
            % (self.market, self.channel, self.from_file, self.from_warehouse, self.period)
        )


class Mapped:
    __slots__ = ("units", "conflicts", "markets_without_owner")

    def __init__(self, units, conflicts, markets_without_owner) -> None:
        self.units = units
        self.conflicts = conflicts
        self.markets_without_owner = markets_without_owner


def _drivers_for(
    channel: str,
    market: str,
    sales: Optional[float],
    sessions: Optional[float],
    orders: Optional[float],
) -> Drivers:
    if sales is None:
        return Drivers.sales_only(0.0)
    if channel == ECOMMERCE:
        if sessions and orders:
            return ecommerce_drivers(sales, sessions, orders)
        return Drivers.sales_only(sales)
    if channel == RETAIL:
        # The factory decides; a conversion rate from an uncounted market never gets built.
        return retail_drivers(market, sales)
    return Drivers.sales_only(sales)


def units_from_rows(
    rows: Sequence[Dict[str, object]],
    budget: Optional[Budget] = None,
    period_label: str = "Sales MTD",
) -> Mapped:
    """Build business units from warehouse rows, taking budget from the file where it has one.

    The file wins on budget and last year. It covers every market, it is what the business
    committed to, and where the two sources overlap they agree. Warehouse values are kept
    as a fallback and cross-checked, because a silent divergence between the two would be
    worth knowing about long before anyone noticed it on a screen.
    """
    units: List[BusinessUnit] = []
    conflicts: List[BudgetConflict] = []
    seen_markets: List[tuple] = []

    for row in rows:
        raw_market = str(row.get("market") or "").strip()
        if not raw_market:
            continue
        market = normalise_market(raw_market)
        channel = str(row.get("channel") or ECOMMERCE).strip().lower()
        period = str(row.get("period") or "")
        seen_markets.append((market, str(row.get("region") or "").strip()))

        actual = _number(row.get("sales_actual")) or 0.0
        sessions = _number(row.get("sessions"))
        orders = _number(row.get("orders"))
        # Last year's drivers, when the query returns them. They are what makes the
        # decomposition possible at all: a budget is a committed number with no funnel
        # behind it, so nothing can be attributed to a driver against a plan.
        sessions_ly = _number(row.get("sessions_last_year"))
        orders_ly = _number(row.get("orders_last_year"))

        from_warehouse_budget = _number(row.get("sales_budget"))
        from_warehouse_ly = _number(row.get("sales_last_year"))

        from_file_budget = budget.budget_for(market, channel, period) if budget else None
        from_file_ly = budget.last_year_for(market, channel, period) if budget else None

        if (
            from_file_budget
            and from_warehouse_budget
            and abs(from_file_budget - from_warehouse_budget) / from_file_budget
            > BUDGET_DISAGREEMENT
        ):
            conflicts.append(
                BudgetConflict(
                    market, channel, period, from_file_budget, from_warehouse_budget
                )
            )

        budget_value = from_file_budget if from_file_budget is not None else from_warehouse_budget
        last_year_value = from_file_ly if from_file_ly is not None else from_warehouse_ly

        reason = ""
        if channel == RETAIL and not retail_conversion_is_reliable(market):
            reason = NO_COUNTER_REASON
        elif channel == ECOMMERCE and not (sessions and orders):
            reason = "Sessions or orders are not reported for this site."
        elif channel == ECOMMERCE and not (sessions_ly and orders_ly):
            reason = (
                "Last year's sessions and orders are not available, so the movement "
                "cannot be attributed to a driver."
            )

        units.append(
            BusinessUnit(
                key="%s-%s" % (market.lower().replace(" ", "-"), channel),
                label="%s %s" % (market, "E-commerce" if channel == ECOMMERCE else channel.title()),
                market=market,
                region=str(row.get("region") or "").strip(),
                channel=channel,
                # Region matters: it is what lets an unlisted market fall to its BU head
                # instead of going unowned.
                owner=owners_module.owner_for(market, str(row.get("region") or "")),
                actual=_drivers_for(channel, market, actual, sessions, orders),
                # Budget and last year carry no drivers: they are commitments and history,
                # not measured funnels. A gap against them is still exact.
                budget=Drivers.sales_only(budget_value if budget_value is not None else 0.0),
                budget_known=budget_value is not None,
                last_year=_drivers_for(
                    channel, market, last_year_value, sessions_ly, orders_ly
                )
                if last_year_value is not None
                else Drivers.sales_only(0.0),
                forecast_sales=_number(row.get("sales_forecast")) or 0.0,
                sessions=sessions,
                orders=orders,
                no_breakdown_reason=reason,
            )
        )

    return Mapped(
        units=units,
        conflicts=conflicts,
        markets_without_owner=sorted(
            {market for market, region in seen_markets
             if owners_module.current().entry_for(market, region) is None}
        ),
    )


def dataset_from_rows(
    rows: Sequence[Dict[str, object]],
    budget: Optional[Budget] = None,
    period_label: str = "Sales MTD",
    as_of: str = "",
) -> Dataset:
    mapped = units_from_rows(rows, budget=budget, period_label=period_label)
    return Dataset(period_label=period_label, as_of=as_of, units=mapped.units)
