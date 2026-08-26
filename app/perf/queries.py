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
| e-commerce drivers | **yes, but not from the sell-out view** — sessions and orders live in `V_SL_F_GRP_GA_SESSIONS` and `F_GRP_GA_TRANSACTIONS` |
| sales_budget | **read it from the planning file, not from here** — see below |
| sales_forecast, owner_name | **no** — neither exists in the warehouse |
| KPI definitions, targets, cadence | **no, by design** — see below |

### Retail: only where footfall is counted

**Store conversion is trustworthy in Europe and North America and nowhere else.** Elsewhere
the measure exists in the data and does not describe reality — no counter, or coverage too
partial to represent the estate.

A wrong number is acted upon; an absent one is asked about. So the rule is not advice:
build every retail unit through `model.retail_drivers(market, sales, ...)`, which returns
sales alone outside `TRAFFIC_COUNTER_MARKETS` whatever conversion it is handed. Set
`no_breakdown_reason=NO_COUNTER_REASON` so the screen says which kind of blindness it is.

Where counters exist, all four drivers come from the same facts and telescope exactly:

    Traffic × (tickets / traffic) × (quantity / tickets) × (net sales / quantity) = net sales

That conversion is a **decomposition driver**, not the reported conversion rate. The
organisation's governed CONVERSION_RATE is a different measure and belongs in the KPI
section, with its own target and owner. Two numbers, two places, never substituted.

### E-commerce: sessions exist, in the web analytics tables

Not in the sell-out semantic view — in `V_SL_F_GRP_GA_SESSIONS` and
`F_GRP_GA_TRANSACTIONS`. Sessions, orders, conversion rate and device split are all there,
by site and by period.

Use `model.ecommerce_drivers(sales, sessions, orders)`:

    Sessions × (orders / sessions) × (sales / orders) = sales

**Take `sales` in euros, not from the web analytics revenue field.** That field is in local
currency, so its levels are not comparable between sites and cannot be summed into a group
total. Deriving value-per-order from a euro sales figure keeps both the identity and the
comparability — sessions and orders from analytics, money from the sales system.

Two things to check before trusting a join: web orders and sell-out orders do not always
agree, and the channel grouping in the warehouse is the default analytics grouping rather
than the local custom ones, which makes any per-channel split unreliable.

### Channels

The `ecommerce` / `retail` distinction is not a commercial taxonomy: it says which driver
model applies. Anything that fits neither takes `Drivers.sales_only(...)` — its gap stays
visible, its cause is declared unavailable.

Sales carrying no channel at all must not be distributed silently. Unattributed revenue is
not a data-quality footnote; it is a part of the business that cannot be diagnosed, and
that is itself worth showing.

### Budget comes from the planning file

The warehouse carries goals for a minority of markets, and not for the largest ones. The
planning workbook carries all of them, and is the version the business commits to. Where
the two overlap they agree to the cent; where they differ, the file is the reference.

That is not a workaround. **A budget is a decision, not a measurement** — it belongs with
the other governance artefacts, next to KPI targets and definitions. `app/perf/budget.py`
reads it; `SALES_AND_DRIVERS` should return actuals and drivers and leave `sales_budget`
and `sales_last_year` to the file.

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
#:
#: E-commerce only. Money comes from the sell-out fact in euros; sessions and orders come
#: from web analytics. `PRODUCT_REVENUE` is deliberately unused: it is denominated in local
#: currency, so its levels are neither comparable between sites nor summable into a group
#: total. Returns `sessions` and `orders` raw — conversion and AOV are derived by
#: `model.ecommerce_drivers(sales, sessions, orders)`, which is what closes the identity.
#:
#: No channel split. `CHANNEL_GROUPING` in the warehouse is the default analytics grouping,
#: not the local custom ones, so any per-channel figure would be unreliable.
#:
#: The join is on ISO2 country, and it is a full outer join on purpose: a market with euro
#: sales but no analytics site (China, Mexico, Luxembourg, Vietnam) keeps its revenue in the
#: group total, and a site with traffic but no sales would still appear. Dropping either
#: would silently shrink the business.
SALES_AND_DRIVERS = """
with period as (
    select
        date_trunc('month', add_months(anchor, -1)) as period_start,
        last_day(add_months(anchor, -1))            as period_end
    from (
        select max(max_sales_date) as anchor
        from semantic_view(
            dwh.semantic_layer.v_sl_ai_sellout_analysis
            metrics max(f_sellout_sales_details.transaction_date) as max_sales_date
        )
    )
),
sellout_day as (
    select
        store_country_iso2 as iso2,
        store_country,
        store_business_area,
        transaction_date,
        net_sales_eur
    from semantic_view(
        dwh.semantic_layer.v_sl_ai_sellout_analysis
        dimensions
            d_stores.store_country_iso2,
            d_stores.store_country,
            d_stores.store_business_area,
            f_sellout_sales_details.transaction_date
        metrics sum(f_sellout_sales_details.net_sales_eur) as net_sales_eur
        where d_stores.store_sub_channel = 'E-COMMERCE'
          and d_stores.store_brand = 'L''OCCITANE'
    )
),
goals_day as (
    select
        store_country_iso2 as iso2,
        goals_date,
        goals_eur
    from semantic_view(
        dwh.semantic_layer.v_sl_ai_sellout_analysis
        dimensions d_stores.store_country_iso2, f_sales_goals.goals_date
        metrics sum(f_sales_goals.goals_eur) as goals_eur
        where d_stores.store_sub_channel = 'E-COMMERCE'
          and d_stores.store_brand = 'L''OCCITANE'
    )
),
money as (
    select
        s.iso2,
        any_value(s.store_country)       as market,
        any_value(s.store_business_area) as region,
        sum(iff(s.transaction_date between p.period_start and p.period_end,
                s.net_sales_eur, 0))     as sales_actual,
        sum(iff(s.transaction_date between add_months(p.period_start, -12)
                                       and add_months(p.period_end, -12),
                s.net_sales_eur, 0))     as sales_last_year
    from sellout_day s cross join period p
    where s.transaction_date between add_months(p.period_start, -12) and p.period_end
    group by s.iso2
),
budget as (
    select g.iso2, sum(g.goals_eur) as sales_budget
    from goals_day g cross join period p
    where g.goals_date between p.period_start and p.period_end
    group by g.iso2
),
web as (
    select
        h.hostname_country_code_iso2       as iso2,
        any_value(h.hostname_country_desc) as site_country,
        sum(g.nb_sessions)                 as sessions
    from dwh.semantic_layer.v_sl_f_grp_ga_sessions g
    join dwh.semantic_layer.v_sl_d_ga_hostname h on h.host_skey = g.host_skey
    cross join period p
    where h.brand_id = 'OC'
      and g.session_date between p.period_start and p.period_end
    group by h.hostname_country_code_iso2
),
web_orders as (
    select
        t.hostname_country_iso2                as iso2,
        count(distinct t.unique_transaction_id) as orders
    from dwh.public.f_grp_ga_transactions t cross join period p
    where t.brand = 'OCC'
      and t.transaction_date_day between p.period_start and p.period_end
    group by t.hostname_country_iso2
)
select
    coalesce(m.market, w.site_country) as market,
    'ecommerce'                        as channel,
    m.region                           as region,
    cast(null as varchar)              as owner_name,
    m.sales_actual                     as sales_actual,
    b.sales_budget                     as sales_budget,
    m.sales_last_year                  as sales_last_year,
    cast(null as number(38, 4))        as sales_forecast,
    w.sessions                         as sessions,
    o.orders                           as orders,
    to_char(p.period_start, 'YYYY-MM') as period
from money m
full outer join web w on w.iso2 = m.iso2
left join budget b     on b.iso2 = coalesce(m.iso2, w.iso2)
left join web_orders o on o.iso2 = coalesce(m.iso2, w.iso2)
cross join period p
order by m.sales_actual desc nulls last
"""

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
