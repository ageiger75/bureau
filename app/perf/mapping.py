"""Warehouse rows to the normalised model.

The join between two sources happens here, and only here: money and drivers come from the
warehouse, budget and last year from the planning file. Keeping the seam in one place is
what allows either side to change without the other noticing.

Nothing in this module invents a figure. Where a source is silent the field stays empty
and the cockpit says so — which is the behaviour every layer above depends on.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from . import context as context_module
from . import owners as owners_module
from .budget import Budget, normalise_market
from .model import (
    ECOMMERCE,
    MARKETPLACE,
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

#: What the query says about each market's funnel. Four states, established by reading the
#: warehouse rather than by guessing at it, and they have four different remedies — which
#: is the whole reason for keeping them apart instead of collapsing them into "missing".
MEASURED = "measured"
ORDERS_NOT_TRACKED = "orders_not_tracked"
ORDER_TRACKING_LOST = "order_tracking_lost"
NO_ANALYTICS_SITE = "no_analytics_site"
#: A store has no web funnel to lose. Distinguishing it from a site whose tagging broke is
#: what stops anyone being sent to repair something that was never there.
NOT_A_WEB_CHANNEL = "not_a_web_channel"

#: Which status survives when several warehouse rows fold into one channel. A channel that
#: measured anything at all is measured; otherwise the most specific fault wins, because
#: "tracking stopped on a date" is actionable where "no site" is not.
STATUS_PRECEDENCE = (
    MEASURED,
    ORDER_TRACKING_LOST,
    ORDERS_NOT_TRACKED,
    NO_ANALYTICS_SITE,
    NOT_A_WEB_CHANNEL,
)

#: Why a funnel cannot be read, in the words the reader needs. Each says who to ask.
FUNNEL_REASONS = {
    ORDERS_NOT_TRACKED: (
        "Web analytics records the visits here but never the orders — the transaction "
        "identifier is empty on every row. Sales are real; the funnel behind them is not "
        "measured. This is a tag to install, not a market to question."
    ),
    ORDER_TRACKING_LOST: (
        "Order tracking stopped on this site partway through the period, and has not "
        "resumed. The visits still arrive. This one broke recently, which means it can be "
        "found — and until it is, no driver here can be read."
    ),
    NO_ANALYTICS_SITE: (
        "The Maison has no own site measured in this market: online here happens on "
        "platforms it does not run. The revenue is counted — a shopper buying on a "
        "marketplace store is still a sale to the end customer — but the platform owns "
        "the traffic, so there is no funnel behind the number and none to repair."
    ),
}

#: The two that a data team can actually fix. The third is a fact about how the market
#: sells, and telling someone to repair it would send them after nothing.
BROKEN_FUNNELS = frozenset({ORDERS_NOT_TRACKED, ORDER_TRACKING_LOST})


#: Warehouse channel names to the cockpit's own vocabulary. The warehouse shouts and
#: hyphenates; the planning file abbreviates; the model has two words for the channels it
#: can decompose. This is where the three meet, and it has to be exhaustive rather than
#: clever: a channel that lands on the wrong name joins to the wrong budget line.
#: The warehouse reports the shape of the point of sale — mall store, street store, shop
#: in shop, outlet, road show, corner. The plan commits to one figure for all of them:
#: `RET - Retail`, one line per market.
#:
#: So the formats collapse. Keeping them apart would read as finer detail and behave as a
#: catastrophe: every format would find no budget line, be marked unbudgeted, drop out of
#: the ranking, and the entire store business — nearly half the plan — would vanish from
#: the screen while every number on it stayed technically true.
#:
#: It is also the right grain regardless. "France Retail is below plan" is a management
#: unit; "France Mall Store" is a property of the estate, and no one is accountable for it
#: separately from the rest.
CHANNEL_ALIASES = {
    # The web, on a site of ours.
    "e-commerce": ECOMMERCE,
    "ecommerce": ECOMMERCE,
    "e commerce": ECOMMERCE,
    "brand.com": ECOMMERCE,
    "web": ECOMMERCE,
    # Stores, whatever their format.
    "retail": RETAIL,
    "mall store": RETAIL,
    "street store": RETAIL,
    "shop in shop": RETAIL,
    "outlet": RETAIL,
    "road show": RETAIL,
    "corner": RETAIL,
    "special stores": RETAIL,
    "boutique": RETAIL,
    "stores": RETAIL,
    "store": RETAIL,
    # Sold by the Maison to the end customer, on a platform it does not run. Sell-out with
    # no funnel — and its own channel rather than folded into e-commerce, because the plan
    # commits to it separately and because it has no sessions to compare.
    "marketplace": MARKETPLACE,
    "market place": MARKETPLACE,
    # Small own channels the plan carries as their own lines.
    "spa": "spa",
    "cafe": "cafe",
    "café": "cafe",
    "direct selling": "direct selling",
}

def normalise_channel(name: str) -> str:
    """`E-COMMERCE` -> `ecommerce`. An unknown channel keeps its own name, lowercased.

    Never guessed into a known channel by resemblance: a channel this module does not
    recognise gets sales without drivers, which is honest, whereas one mistaken for retail
    would be handed a footfall funnel it never had.
    """
    cleaned = (name or "").strip().lower()
    return CHANNEL_ALIASES.get(cleaned, cleaned)


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


#: How each channel is written beside a market name. Without an entry a planning code
#: reaches the screen as "China Webp" or "Hong Kong Dis" — an abbreviation from a
#: spreadsheet, printed where a reader expects the name of a business.
#: What each channel actually is, in one line, and on which basis its euros are counted.
#:
#: Written because the names do not carry it. "China E-retailers" and "China E-commerce"
#: look like two shades of online selling; they are a partner who buys our stock and our
#: own site, recognised at different moments, answered by different people. A reader who
#: has to guess which is which cannot judge either — and the guess is usually wrong, since
#: the platform most people picture for China sits under a third name again.
CHANNEL_MEANING = {
    "ecommerce": "Our own site — brand.com. The one channel where the whole funnel is "
                 "ours to read: visits, conversion, basket.",
    "retail": "Our own stores. Sold when the shopper pays.",
    "marketplace": "Our own store, on someone else's platform — the Tmall flagship the "
                   "Maison operates. Still sold to the shopper, but the platform owns the "
                   "traffic, so there is no funnel of ours behind the number. In China "
                   "Tmall is the only platform on this side of the invoice.",
    "webp": "Partners who buy our stock and resell it online — Amazon in the West, and in "
            "China JD, Douyin or VIP. Invoiced when we ship, so what reaches a shopper "
            "afterwards is not in it. Not Tmall, which we operate ourselves.",
    "tra": "Travel retail operators who buy to resell: airports, ferries, border shops.",
    "dis": "Distributors who buy the range for a territory and resell it on.",
    "dpt": "Department stores buying stock for their own floors.",
    "whoch": "Chains buying stock for their own shelves.",
    "whoin": "Independent shops and pharmacies buying stock.",
    "whosp": "Spas and hotels buying product to sell on to their guests.",
    "tvc": "Television shopping channels buying stock to sell on air.",
    "b2b": "Hotels and businesses buying product they do not resell — put in a room, "
           "given away. No partner takes a margin on it.",
    "copg": "Companies buying product as gifts. Not resold.",
    "dds": "Sold person to person, outside a shop.",
    "spa": "Our own spas. Sold when the guest pays, treatments and product together.",
    "cafe": "Our own cafés. Sold when the customer pays, at the counter.",
}


CHANNEL_NAMES = {
    ECOMMERCE: "E-commerce",
    RETAIL: "Retail",
    MARKETPLACE: "Marketplace",
    "webp": "E-retailers",
    "tra": "Travel Retail",
    "dis": "Distributors",
    "dpt": "Department Stores",
    "whoch": "Chain Wholesale",
    "whoin": "Independent Wholesale",
    "whosp": "Spa Wholesale",
    "tvc": "TV Channels",
    "b2b": "Hospitality & B2B",
    "copg": "Corporate Gifts",
    "dds": "Direct Selling",
    "spa": "Spa",
    "cafe": "Café",
}


def _channel_label(channel: str) -> str:
    """How the channel is written on screen."""
    return CHANNEL_NAMES.get(channel, channel.title())


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


#: Warehouse figures that add up when rows fold together. Everything else — market names,
#: the period, the region — must agree already, and does: the fold is keyed on them.
SUMMED_FIELDS = (
    "sales_actual",
    "sales_budget",
    "sales_last_year",
    "sales_forecast",
    "sessions",
    "orders",
    "sessions_last_year",
    "orders_last_year",
)


def fold_rows(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    """Collapse warehouse rows onto one row per market, channel and period.

    The warehouse reports the shape of the point of sale; the cockpit and the plan both
    speak in channels. Several store formats therefore land on the same channel, and if
    they arrived as several units each would carry the channel's *entire* budget — the
    same commitment counted four times over, and a company shown far behind a plan it is
    in fact meeting.

    Absent stays absent through the fold: summing None with None must not produce a zero,
    or a channel nobody measured becomes a channel measured at nothing.
    """
    folded: Dict[tuple, Dict[str, object]] = {}
    order: List[tuple] = []

    for row in rows:
        raw_market = str(row.get("market") or "").strip()
        if not raw_market:
            continue
        market = normalise_market(raw_market)
        channel = normalise_channel(str(row.get("channel") or ECOMMERCE))
        period = str(row.get("period") or "")
        key = (market, channel, period)

        if key not in folded:
            merged = dict(row)
            merged["market"] = market
            merged["channel"] = channel
            folded[key] = merged
            order.append(key)
            continue

        merged = folded[key]
        for field in SUMMED_FIELDS:
            merged[field] = _add(_number(merged.get(field)), _number(row.get(field)))
        merged["funnel_status"] = _better_status(
            str(merged.get("funnel_status") or ""), str(row.get("funnel_status") or "")
        )

    return [folded[key] for key in order]


def _add(first: Optional[float], second: Optional[float]) -> Optional[float]:
    if first is None:
        return second
    if second is None:
        return first
    return first + second


def _better_status(first: str, second: str) -> str:
    ranked = [s for s in (first.strip().lower(), second.strip().lower()) if s]
    if not ranked:
        return ""
    known = [s for s in ranked if s in STATUS_PRECEDENCE]
    if not known:
        return ranked[0]
    return min(known, key=STATUS_PRECEDENCE.index)


#: Sell-in rows arrive with a segment label rather than a channel, because that is what
#: the plan commits to. The channel is derived from it by the same function the planning
#: file uses, so both sides of the join speak one vocabulary.
def sell_in_rows(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    """Turn consolidation rows into the shape `units_from_rows` reads.

    Nothing is invented here and nothing can be: invoiced revenue has no funnel, so the
    row carries money and no drivers at all. What the function does is translate the
    plan's segment label into the channel vocabulary, so a sell-in row joins to its own
    budget line rather than to none.
    """
    from .budget import channel_of, market_of

    translated: List[Dict[str, object]] = []
    for row in rows:
        segment = str(row.get("segment") or "").strip()
        if not segment:
            continue
        merged = dict(row)
        merged["channel"] = channel_of(segment)
        # The market, not the invoicing country. Travel retail is sold in airports and
        # billed from somewhere; naming it after the somewhere hides a domestic market
        # inside a worldwide one.
        merged["market"] = market_of(str(row.get("market") or ""), segment)
        # Stated rather than inferred: a sell-in row has no web funnel and never had one,
        # which is a different thing from a site whose tagging broke.
        merged["funnel_status"] = NOT_A_WEB_CHANNEL
        merged["sessions"] = None
        merged["orders"] = None
        merged["sessions_last_year"] = None
        merged["orders_last_year"] = None
        translated.append(merged)
    return translated


def _history_for(history, market, channel, budget):
    """What the last twenty-four months say about this market and channel.

    Returns the run of months below plan, the monthly gaps behind it, and — only when it
    is earned — the sentence that says the plan itself is the problem.

    All three are measured against the planning workbook. The history rows also carry the
    warehouse's own targets, and using those would buy far more months of depth: they reach
    back two years where the workbook covers the current one. It would also mean ranking
    the CEO's attention on a source the business has ruled unreliable, and which has no
    target at all for two fifths of what it sells. Fewer months of a real plan beats more
    months of a number nobody stands behind.
    """
    if history is None or budget is None:
        return 0, (), "", ""
    track = history.track_for(market, channel)
    if track is None:
        return 0, (), "", ""

    chronic = track.chronic_for(budget)
    return (
        track.months_below_for(budget),
        track.gap_history_for(budget),
        chronic.sentence if chronic is not None else "",
        track.trajectory(budget).sentence,
    )


def units_from_rows(
    rows: Sequence[Dict[str, object]],
    budget: Optional[Budget] = None,
    period_label: str = "Sales MTD",
    history=None,
    sell_in_record=None,
) -> Mapped:
    """Build business units from warehouse rows, taking budget from the file where it has one.

    The file wins on budget and last year. It covers every market, it is what the business
    committed to, and where the two sources overlap they agree. Warehouse values are kept
    as a fallback and cross-checked, because a silent divergence between the two would be
    worth knowing about long before anyone noticed it on a screen.
    """
    from .budget import is_aggregate_market, perimeter_of

    units: List[BusinessUnit] = []
    conflicts: List[BudgetConflict] = []
    seen_markets: List[tuple] = []

    for row in fold_rows(rows):
        raw_market = str(row.get("market") or "").strip()
        if not raw_market:
            continue
        market = normalise_market(raw_market)
        channel = normalise_channel(str(row.get("channel") or ECOMMERCE))
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

        # The query now states why a funnel is unreadable instead of leaving a blank for
        # this module to interpret. Where it does, its word is taken: it read the
        # warehouse, and a reason established beats a reason inferred.
        funnel_status = str(row.get("funnel_status") or "").strip().lower()

        reason = ""
        if str(row.get("segment") or "") and perimeter_of(str(row.get("segment"))) == "sell-in":
            # Short on purpose: the basis note beside it already says what is and is not
            # in the figure. Printed in full, the two lines said the same thing twice on
            # one card, and a screen that repeats itself reads as one that is padding.
            # The basis note beside it already says this was invoiced to a partner. All
            # this line adds is why there is no driver table, so that is all it says now:
            # two sentences opening on the same clause read as padding, and padding on a
            # card is what teaches a reader to skim the next one.
            reason = "No funnel behind this figure, and none missing."
        elif channel == RETAIL and not retail_conversion_is_reliable(market):
            reason = NO_COUNTER_REASON
        elif funnel_status in FUNNEL_REASONS:
            reason = FUNNEL_REASONS[funnel_status]
        elif channel == ECOMMERCE and not (sessions and orders):
            reason = "Sessions or orders are not reported for this site."
        elif channel == ECOMMERCE and not (sessions_ly and orders_ly):
            reason = (
                "Last year's sessions and orders are not available, so the movement "
                "cannot be attributed to a driver."
            )

        months_below, gap_history, chronic, vs_record = _history_for(
            history, market, channel, budget
        )
        # Sell-in has no sell-out history to read, so its trajectory arrives already
        # assembled from the two consolidation queries. Same finding, different source —
        # and the sentence names its own basis, so the two cannot be confused.
        if not vs_record and sell_in_record:
            vs_record = sell_in_record.get((market, channel), "")
        # A boundary someone has written down is not a plan to renegotiate. Last, so that
        # it silences the finding whichever source produced it: written above the line
        # that fills in sell-in, it cleared the sell-out verdict and let the sell-in one
        # straight back through — the American wholesale line would have come back in by
        # the other door after being shown out of the first.
        if any(note.kind in context_module.NOT_TRADING for note in
               context_module.notes_for(market, channel, period)):
            vs_record = ""

        units.append(
            BusinessUnit(
                key="%s-%s" % (market.lower().replace(" ", "-"), channel),
                label="%s %s" % (market, _channel_label(channel)),
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
                funnel_status=funnel_status,
                context_notes=context_module.notes_for(market, channel, period),
                perimeter=perimeter_of(str(row.get("segment") or ""))
                if row.get("segment")
                else ("own" if channel in (ECOMMERCE, RETAIL) else ""),
                # The flag existed and nothing but the mock ever set it: on real data a
                # roll-up could reach the fires and take a slot from a market someone can
                # be asked about.
                is_aggregate=is_aggregate_market(market),
                period=period,
                months_below_budget=months_below,
                gap_history=gap_history,
                chronic_plan=chronic,
                plan_vs_record=vs_record,
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
    history=None,
) -> Dataset:
    mapped = units_from_rows(
        rows, budget=budget, period_label=period_label, history=history
    )
    return Dataset(
        period_label=period_label,
        as_of=as_of,
        units=mapped.units,
        # Built here as well as in the source, so the two ways of assembling a dataset
        # cannot drift into showing different screens from the same rows.
        ytd=history.ytd(
            str(rows[0].get("period") or ""),
            budget=budget,
            sell_in=[r for r in rows if r.get("segment")],
        )
        if history and rows
        else None,
    )
