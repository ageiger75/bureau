"""The SQL this repository cannot write for you.

Every constant below is a placeholder. They stay empty on purpose: the schema lives in
your warehouse, not here, and a query invented from a guess would return numbers that look
right and are not — the one failure this product cannot survive.

Filling them is a job for whoever knows the schema. Cortex Code, already authenticated on
the machine, knows the tables, the columns and the governance rules; it is better placed
to write these six queries than anything working from a description.

## What each query must return

One row per business unit and period, with these columns, lowercased:

    market            text     -- 'Japan', 'France', …
    channel           text     -- 'ecommerce' or 'retail'
    region            text
    owner_name        text
    sales_actual      number   -- the period's actual net sales
    sales_budget      number
    sales_last_year   number
    sales_forecast    number

Plus the drivers, which must multiply out to sales — the cockpit checks this and will
refuse a row where they disagree:

    e-commerce:  sessions, conversion_rate, aov
    retail:      traffic, conversion_rate, upt, asp

For KPIs, one row per KPI and reading:

    kpi_key, label, definition, scope, owner_name, pillar, unit,
    target, direction ('up'|'down'), frequency, source,
    definition_status ('locked'|'provisional'), priority ('P1'|'P2'|'P3'),
    period, value

## What the warehouse can and cannot supply

Established against `DWH.SEMANTIC_LAYER.V_SL_AI_SELLOUT_ANALYSIS`, the semantic view
behind the Sell Out Analyst agent. Prefer it to raw tables: its measures are the ones the
organisation already reports.

| Cockpit needs | Warehouse |
| --- | --- |
| sales_actual, sales_budget, sales_last_year | yes — NET_SALES_EUR and the goals fact |
| market, region, channel | yes — STORE_COUNTRY, STORE_BUSINESS_AREA, TRANSACTION_CHANNEL |
| retail drivers | yes — derive them so they telescope (see below) |
| e-commerce drivers | **no** — no sessions anywhere. Such channels carry sales only. |
| sales_forecast, owner_name | **no** — neither exists in the warehouse |
| KPI definitions, targets, cadence | **no, by design** — see below |

### Deriving retail drivers

Derive all four from the same facts, so the identity closes by construction:

    Traffic × (tickets / traffic) × (quantity / tickets) × (net sales / quantity) = net sales

This is a telescoping product, exact to the cent, which is what makes "about 90% of the
gap comes from conversion" a sentence worth saying.

The conversion computed this way is a **decomposition driver**, not the reported
conversion rate. The organisation's governed CONVERSION_RATE is a different measure and
belongs in the KPI section, with its own target and owner. Two numbers, two places, two
purposes — never silently substituted for one another.

### Channels

The `ecommerce` / `retail` distinction in the model is not a commercial taxonomy: it says
which driver model applies. Map a channel to `retail` where footfall and tickets exist,
and give every other channel `Drivers.sales_only(...)` — its gap stays visible, its cause
is declared unavailable.

Sales carrying no channel at all must not be distributed silently. Unattributed revenue is
not a data-quality footnote; it is a part of the business that cannot be diagnosed, and
that is itself worth showing.

### Why KPI metadata is absent, and should stay absent

Definitions, targets, direction, cadence and whether a definition is settled are not data.
They are governance decisions, and they live in the KPI tracker. **The warehouse supplies
values; the tracker supplies meaning.** `KPI_READINGS` therefore returns readings only —
scope, kpi_key, period, value — and the cockpit holds the registry.

MARKET_INDEX, COMMITMENTS and FORECAST_HISTORY have no warehouse source. Left empty, the
cockpit says so explicitly, which is the correct outcome rather than a gap to paper over.

## Two things to preserve

Prefer measures the organisation has already modelled over recomputing from raw tables.
If this cockpit shows a number that differs from the one in a team's Power BI report, the
argument is lost in the room whatever the arithmetic says.

Keep the grain at market × channel × period. Finer detail belongs to the Investigate
screen, which does not exist yet.
"""

from __future__ import annotations

#: Sales and their drivers, current period, one row per market × channel.
SALES_AND_DRIVERS = ""

#: The same, for the previous periods that feed the acceleration factor.
SALES_HISTORY = ""

#: KPI readings only — scope, kpi_key, period, value. Definitions, targets, direction and
#: cadence come from the tracker, not from here.
KPI_READINGS = ""

#: Published market growth per market, used to test "the market is difficult" rather than
#: repeat it. Leave empty if no benchmark exists — the cockpit then says so explicitly
#: instead of inventing one.
MARKET_INDEX = ""

#: Commitments, if they are tracked in the warehouse. Leave empty to keep entering them
#: in the cockpit itself.
COMMITMENTS = ""

#: Successive forecasts for the same period, oldest first — the forecast credibility flag.
FORECAST_HISTORY = ""

ALL = {
    "SALES_AND_DRIVERS": SALES_AND_DRIVERS,
    "SALES_HISTORY": SALES_HISTORY,
    "KPI_READINGS": KPI_READINGS,
    "MARKET_INDEX": MARKET_INDEX,
    "COMMITMENTS": COMMITMENTS,
    "FORECAST_HISTORY": FORECAST_HISTORY,
}


def missing() -> list:
    """Names of the queries still to be written."""
    return sorted(name for name, sql in ALL.items() if not sql.strip())
