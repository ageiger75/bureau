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

    e-commerce:  sessions, orders
    retail:      traffic, tickets, quantity

**And the same drivers for the same period one year earlier**, as
`sessions_last_year` and `orders_last_year`. They are not optional: a budget is a
committed number with no funnel behind it, so a movement can only be attributed to a
driver by comparing measured periods. Without last year's drivers the cockpit shows the
gap and refuses to explain it.

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
#: Every sell-out channel, one row each. `channel` carries `STORE_SUB_CHANNEL` verbatim —
#: `MALL STORE`, `SHOP IN SHOP`, `STREET STORE`, `E-COMMERCE`, `MARKETPLACE`, `OUTLET`,
#: `ROAD SHOW`, `CORNER` on the latest closed month, plus `SPA`, `MAIL ORDER`,
#: `DIRECT SELLING` and `SPECIAL STORES` which exist in history and sold nothing this
#: month. Not translated to `ecommerce`/`retail` here: which driver model applies is a
#: decision, and it belongs to whoever maps these rows, not to a `CASE` buried in SQL.
#:
#: Only `E-COMMERCE` is joined to the web funnel. Physical channels leave with their euros
#: and no levers, which the screen already knows how to show. They are never handed a
#: conversion rate borrowed from the site that shares their market — retail conversion
#: comes from footfall counters, and only where those exist.
#:
#: Money comes from the sell-out fact in euros; sessions and orders come from web
#: analytics. `PRODUCT_REVENUE` is deliberately unused: it is denominated in local
#: currency, so its levels are neither comparable between sites nor summable into a group
#: total. Returns `sessions` and `orders` raw — conversion and AOV are derived by
#: `model.ecommerce_drivers(sales, sessions, orders)`, which is what closes the identity.
#:
#: The funnel is returned for both periods. `sessions_last_year` and `orders_last_year`
#: are not symmetry for its own sake: without them the screen can show a gap and cannot
#: say which stage moved, and a gap it refuses to explain is a gap nobody acts on.
#:
#: Everything reads from `semantic_layer`, never from a raw fact. Those views are the
#: governed grain, and going around them costs both governance and scanned bytes.
#:
#: No channel split. `CHANNEL_GROUPING` in the warehouse is the default analytics grouping,
#: not the local custom ones, so any per-channel figure would be unreliable.
#:
#: `funnel_status` names why a funnel is absent instead of leaving a blank, because the four
#: cases are four different management problems and only one of them is about selling:
#:
#: - `not_a_web_channel` — a physical channel. Not a gap: there is no funnel to lose.
#: - `measured` — sessions and orders both present.
#: - `orders_not_tracked` — the site reports sessions, and `UNIQUE_TRANSACTION_ID` is null
#:   on every row in both windows. Nine markets have never populated it (BR, PL, CZ, SK, HU,
#:   NO, SE, FI, IN); Malaysia and Thailand stopped in April and May 2025. The rows exist —
#:   14 718 for Brazil in one month — so this is a tagging gap, not a missing feed.
#: - `order_tracking_lost` — orders were recorded last year and none now. Taiwan stopped on
#:   2025-07-09, Hong Kong on 2025-07-28.
#: - `no_analytics_site` — no host in the governed dimension at all. China's brand.com feed
#:   ended 2024-06-22 and its current business runs on Tmall, JD and Douyin, none of which
#:   report to Google Analytics; Mexico ended 2023-07-28, Vietnam 2023-10-31, and Luxembourg
#:   never had a site. All four still sell, so they keep their euros and lose only the
#:   decomposition.
#:
#: The brand filter cannot be the cause of any of it: it is applied to the host dimension,
#: which both funnel legs join through, so a wrong `BRAND_ID` would remove the sessions too.
#:
#: ## What the clock measures, and what it does not
#:
#: `REPORT_WH` is an X-Small, shared. The same query over the same fourteen months took
#: 258 seconds cold and 10.3 warm — so a stopwatch here measures how recently someone else
#: ran something similar, and nothing about the query. **Bytes scanned is the only honest
#: unit**, and Snowflake reports it per statement.
#:
#: That mattered: bounding the two sell-out CTEs looked like a 232 → 153 second win and
#: was a warm cache. In bytes it removed 1 GB of 173.
#:
#: The profile, in bytes rather than seconds:
#:
#: | CTE | Scanned |
#: | --- | --- |
#: | `period` — one `max(date)` | **76.94 GB** |
#: | `web` sessions | 72.93 GB |
#: | `sellout_day`, bounded | 29.63 GB |
#: | `web_orders` | negligible |
#:
#: The anchor was the largest item on the page: 77 GB to produce a single date. Bounded to
#: three months — the last transaction is recent by definition — it finds the same day and
#: the whole query drops to 109 GB.
#:
#: Two lessons worth more than the gain. A mechanism can be correctly described and
#: irrelevant: the predicate genuinely does not push into an opaque aggregation, and
#: `sellout_day` was never where the time went. And the cheapest-looking line — one
#: `max()` over one column — was the most expensive, because cost here follows what a
#: column touches, not what a statement says.
#:
#: ## What no date bound will fix
#:
#: The 73 GB of sessions are insensitive to the window: two disjoint months and fourteen
#: months scan the same 72.93 GB. `session_date` prunes nothing on
#: `V_SL_F_GRP_GA_SESSIONS` — its base table is not clustered on it. The remaining levers
#: are outside the query: cluster that table on date, or size the warehouse. Both are
#: someone's budget rather than someone's SQL.
#:
#: Neither is urgent. The screen no longer waits on this query — it renders the last read
#: and refreshes behind — so what is left is a background cost, not a person's time.
#:
#: What must not be done to make it faster: narrowing the window to the current month.
#: Last year's column is what makes the decomposition possible at all — a budget is a
#: committed number with no funnel behind it — and losing it would buy seconds at the cost
#: of the one thing this screen does that a report cannot.
#:
SALES_AND_DRIVERS = """
with period as (
    select
        date_trunc('month', add_months(anchor, -1)) as period_start,
        last_day(add_months(anchor, -1))            as period_end
    from (
        -- Bounded, and it is the single largest saving in this query: unbounded,
        -- one `max(date)` scanned 77 GB of the 173 GB the whole statement read.
        -- The latest transaction is by definition recent, so three months of
        -- slack finds it while leaving the history unread.
        select max(max_sales_date) as anchor
        from semantic_view(
            dwh.semantic_layer.v_sl_ai_sellout_analysis
            metrics max(f_sellout_sales_details.transaction_date) as max_sales_date
            where f_sellout_sales_details.transaction_date
                  >= dateadd(month, -3, current_date)
        )
    )
),
sellout_day as (
    select
        store_country_iso2 as iso2,
        store_country,
        store_business_area,
        store_sub_channel,
        transaction_date,
        net_sales_eur
    from semantic_view(
        dwh.semantic_layer.v_sl_ai_sellout_analysis
        dimensions
            d_stores.store_country_iso2,
            d_stores.store_country,
            d_stores.store_business_area,
            d_stores.store_sub_channel,
            f_sellout_sales_details.transaction_date
        metrics sum(f_sellout_sales_details.net_sales_eur) as net_sales_eur
        -- A bound the view can read on its own. The window below is expressed
        -- against the `period` CTE, which the view cannot see, so that predicate
        -- does not push down and the whole history gets aggregated at day grain
        -- to yield thirteen months.
        --
        -- Twenty-six months is deliberately generous: fourteen would do, the
        -- slack costs nothing, and a bound one month too tight would silently
        -- empty the year-earlier column rather than fail.
        where d_stores.store_brand = 'L''OCCITANE'
          and f_sellout_sales_details.transaction_date
              >= dateadd(month, -26, current_date)
    )
),
goals_day as (
    select
        store_country_iso2 as iso2,
        store_sub_channel,
        goals_date,
        goals_eur
    from semantic_view(
        dwh.semantic_layer.v_sl_ai_sellout_analysis
        dimensions d_stores.store_country_iso2,
                   d_stores.store_sub_channel,
                   f_sales_goals.goals_date
        metrics sum(f_sales_goals.goals_eur) as goals_eur
        where d_stores.store_brand = 'L''OCCITANE'
          and f_sales_goals.goals_date >= dateadd(month, -26, current_date)
    )
),
money as (
    select
        s.iso2,
        s.store_sub_channel               as channel,
        any_value(s.store_country)       as market,
        any_value(s.store_business_area) as region,
        sum(iff(s.transaction_date between p.period_start and p.period_end,
                s.net_sales_eur, 0))     as sales_actual,
        sum(iff(s.transaction_date between add_months(p.period_start, -12)
                                       and add_months(p.period_end, -12),
                s.net_sales_eur, 0))     as sales_last_year
    from sellout_day s cross join period p
    where s.transaction_date between add_months(p.period_start, -12) and p.period_end
    group by s.iso2, s.store_sub_channel
),
budget as (
    select g.iso2, g.store_sub_channel as channel, sum(g.goals_eur) as sales_budget
    from goals_day g cross join period p
    where g.goals_date between p.period_start and p.period_end
    group by g.iso2, g.store_sub_channel
),
web as (
    select
        h.hostname_country_code_iso2       as iso2,
        any_value(h.hostname_country_desc) as site_country,
        sum(iff(g.session_date between p.period_start and p.period_end,
                g.nb_sessions, 0))         as sessions,
        sum(iff(g.session_date between add_months(p.period_start, -12)
                                   and add_months(p.period_end, -12),
                g.nb_sessions, 0))         as sessions_last_year
    from dwh.semantic_layer.v_sl_f_grp_ga_sessions g
    join dwh.semantic_layer.v_sl_d_ga_hostname h on h.host_skey = g.host_skey
    cross join period p
    where h.brand_id = 'OC'
      and g.session_date between add_months(p.period_start, -12) and p.period_end
    group by h.hostname_country_code_iso2
),
web_orders as (
    select
        h.hostname_country_code_iso2 as iso2,
        count(distinct iff(t.session_date between p.period_start and p.period_end,
                           t.unique_transaction_id, null)) as orders,
        count(distinct iff(t.session_date between add_months(p.period_start, -12)
                                              and add_months(p.period_end, -12),
                           t.unique_transaction_id, null)) as orders_last_year
    from dwh.semantic_layer.v_sl_f_grp_ga_transactions t
    join dwh.semantic_layer.v_sl_d_ga_hostname h on h.host_skey = t.host_skey
    cross join period p
    where h.brand_id = 'OC'
      and t.session_date between add_months(p.period_start, -12) and p.period_end
    group by h.hostname_country_code_iso2
),
joined as (
    -- The web funnel joins e-commerce rows only. A mall store has no sessions to miss,
    -- so anything physical leaves here with its euros and no levers at all — never with
    -- a conversion rate borrowed from the site that happens to share its market.
    select
        coalesce(m.market, w.site_country)      as market,
        coalesce(m.channel, 'E-COMMERCE')       as channel,
        m.region                                as region,
        m.sales_actual                          as sales_actual,
        b.sales_budget                          as sales_budget,
        m.sales_last_year                       as sales_last_year,
        iff(m.channel is null or m.channel = 'E-COMMERCE', w.iso2, null) as web_iso2,
        iff(m.channel is null or m.channel = 'E-COMMERCE', w.sessions, null)
                                                as sessions,
        iff(m.channel is null or m.channel = 'E-COMMERCE', w.sessions_last_year, null)
                                                as sessions_last_year,
        iff(m.channel is null or m.channel = 'E-COMMERCE', o.orders, null) as orders,
        iff(m.channel is null or m.channel = 'E-COMMERCE', o.orders_last_year, null)
                                                as orders_last_year,
        m.channel is null or m.channel = 'E-COMMERCE' as is_web_channel,
        p.period_start                          as period_start
    from money m
    full outer join web w
        on w.iso2 = m.iso2 and m.channel = 'E-COMMERCE'
    left join budget b
        on b.iso2 = m.iso2 and b.channel = m.channel
    left join web_orders o
        on o.iso2 = coalesce(m.iso2, w.iso2) and (m.channel is null or m.channel = 'E-COMMERCE')
    cross join period p
)
select
    market                             as market,
    channel                            as channel,
    region                             as region,
    cast(null as varchar)              as owner_name,
    sales_actual                       as sales_actual,
    sales_budget                       as sales_budget,
    sales_last_year                    as sales_last_year,
    cast(null as number(38, 4))        as sales_forecast,
    sessions                           as sessions,
    sessions_last_year                 as sessions_last_year,
    -- Nulled rather than zeroed where no order identifier exists. A zero would read as
    -- "nobody ordered" on a market that sells every day; null reads as "unknown", which
    -- is what it is, and `funnel_status` says why.
    iff(coalesce(orders, 0) = 0, null, orders)                       as orders,
    iff(coalesce(orders, 0) = 0, null, orders_last_year)             as orders_last_year,
    case
        when not is_web_channel                   then 'not_a_web_channel'
        when web_iso2 is null                     then 'no_analytics_site'
        when coalesce(orders, 0) > 0              then 'measured'
        when coalesce(orders_last_year, 0) > 0    then 'order_tracking_lost'
        else                                           'orders_not_tracked'
    end                                as funnel_status,
    to_char(period_start, 'YYYY-MM')   as period
from joined
order by sales_actual desc nulls last
"""

#: Twenty-four months at the grain of `SALES_AND_DRIVERS`, so the screen can stop
#: comparing one month to one month — the loudest noise and the faintest signal it has.
#:
#: It feeds three things the cockpit already computes and cannot currently supply:
#: persistence ("three consecutive months below plan"), acceleration ("the gap is
#: widening"), and the fiscal year to date. A month-on-month reading is worst exactly
#: where decisions are heaviest: a shipment that slips across a month boundary shows up
#: as a collapse followed by a rebound, and neither happened.
#:
#: One row per market, channel and month:
#:
#:     market            text
#:     channel           text     -- `STORE_SUB_CHANNEL`, verbatim, as in SALES_AND_DRIVERS
#:     period            text     -- 'YYYY-MM'
#:     sales_actual      number   -- euros, tax excluded
#:     sales_budget      number   -- euros, from the goals fact; null where none is set
#:
#: Both sides are joined with a full outer join on purpose. A month with a plan and no
#: sales is not an empty row: it is a market that stopped selling while still carrying a
#: commitment, which is the strongest signal this query can carry.
SALES_HISTORY = """
with period as (
    select
        -- The latest closed month, and twenty-four months of context behind it.
        date_trunc('month', add_months(anchor, -1))       as last_month,
        date_trunc('month', add_months(anchor, -24))      as first_month
    from (
        -- Bounded, for the reason established on SALES_AND_DRIVERS: unbounded, one
        -- `max(date)` reads 77 GB. The latest transaction is recent by definition.
        select max(max_sales_date) as anchor
        from semantic_view(
            dwh.semantic_layer.v_sl_ai_sellout_analysis
            metrics max(f_sellout_sales_details.transaction_date) as max_sales_date
            where f_sellout_sales_details.transaction_date
                  >= dateadd(month, -3, current_date)
        )
    )
),
sellout_day as (
    select
        store_country,
        store_sub_channel,
        transaction_date,
        net_sales_eur
    from semantic_view(
        dwh.semantic_layer.v_sl_ai_sellout_analysis
        dimensions
            d_stores.store_country,
            d_stores.store_sub_channel,
            f_sellout_sales_details.transaction_date
        metrics sum(f_sellout_sales_details.net_sales_eur) as net_sales_eur
        -- A bound the view can read on its own. The window below is expressed
        -- against the `period` CTE, which the view cannot see, so that predicate
        -- does not push down. Twenty-six months leaves the slack a two-year window
        -- needs without reading the whole history.
        where d_stores.store_brand = 'L''OCCITANE'
          and f_sellout_sales_details.transaction_date
              >= dateadd(month, -26, current_date)
    )
),
goals_day as (
    select
        store_country,
        store_sub_channel,
        goals_date,
        goals_eur
    from semantic_view(
        dwh.semantic_layer.v_sl_ai_sellout_analysis
        dimensions d_stores.store_country,
                   d_stores.store_sub_channel,
                   f_sales_goals.goals_date
        metrics sum(f_sales_goals.goals_eur) as goals_eur
        where d_stores.store_brand = 'L''OCCITANE'
          and f_sales_goals.goals_date >= dateadd(month, -26, current_date)
    )
),
sales as (
    select
        s.store_country                            as market,
        s.store_sub_channel                        as channel,
        date_trunc('month', s.transaction_date)    as month,
        sum(s.net_sales_eur)                       as sales_actual
    from sellout_day s cross join period p
    where date_trunc('month', s.transaction_date) between p.first_month and p.last_month
    group by 1, 2, 3
),
budget as (
    select
        g.store_country                        as market,
        g.store_sub_channel                    as channel,
        date_trunc('month', g.goals_date)      as month,
        sum(g.goals_eur)                       as sales_budget
    from goals_day g cross join period p
    where date_trunc('month', g.goals_date) between p.first_month and p.last_month
    group by 1, 2, 3
)
select
    coalesce(s.market, b.market)                        as market,
    coalesce(s.channel, b.channel)                      as channel,
    to_char(coalesce(s.month, b.month), 'YYYY-MM')      as period,
    s.sales_actual                                      as sales_actual,
    b.sales_budget                                      as sales_budget
from sales s
full outer join budget b
    on b.market = s.market and b.channel = s.channel and b.month = s.month
order by market, channel, period
"""

#: Sell-in: everything invoiced to a partner who then resells. Roughly two fifths of the
#: plan, and invisible to every sell-out source by construction — the revenue is recognised
#: when the Maison ships, not when a shopper buys.
#:
#: It comes from the management consolidation rather than from the sell-out warehouse,
#: which is not a workaround: the consolidation *is* where the plan's own actuals come
#: from, so the two reconcile by construction rather than by coincidence. The plan
#: designates its markets by a consolidation entity — `M_024`, `M_098_TRA` — and that code
#: is the join key. A company code or a customer hierarchy is someone else's answer to the
#: same question, and the two do not agree: eleven markets are billed by a hub and vanish
#: entirely under a company-based attribution.
#:
#: One row per entity, segment and month:
#:
#:     entity            text     -- 'M_024', 'M_098_TRA' — the plan's own key
#:     market            text     -- for display; the entity is what joins
#:     region            text
#:     segment           text     -- the plan's segment label, e.g. 'DIS - Distributors'
#:     period            text     -- 'YYYY-MM'
#:     sales_actual      number   -- euros, at the plan's exchange year
#:     sales_last_year   number   -- the same month one year earlier, same rates
#:
#: No drivers, and none invented: invoiced revenue has no funnel behind it. The cockpit
#: shows the gap and says the cause is not measured, which is the truth.
#:
#: Three traps this cost a day to find, worth keeping written down:
#:
#: * amounts are in thousands, like the planning workbook;
#: * the current-year column is cumulative from the start of the fiscal year, so one month
#:   is a difference between snapshots — and a month whose snapshot is missing cannot be
#:   separated from its neighbour. Emit those as `2025-04..2025-05` rather than splitting
#:   them by a rule of thumb; `manage.py reconcile` confronts a range with the plan's own
#:   months added together, and an invented figure would be worth less than none;
#: * the exchange year is a fixed set of rates for the whole year, so converting a month
#:   between two exchange years is the ratio of two constants — derivable from the annual
#:   reconciliation and verifiable against it, which is what makes it a conversion rather
#:   than an adjustment.
#:
#: Validate with `manage.py budget --spec` and `manage.py reconcile` before wiring it in.
SELL_IN = """
with usable as (
    -- The freshest exchange year that actually carries figures. The newest
    -- snapshot of all is the budget cut, whose current-year column is still
    -- empty; anchoring on it would return a screen of blanks.
    select
        exchange_year,
        snapshot_date,
        row_number() over (order by exchange_year desc, snapshot_date desc) as freshness
    from dwh.public.f_management_operating_profit_country
    where brand_code = 'OC'
      and account_code in ('PPL101', 'PPL102')
    group by 1, 2
    having sum(abs(coalesce(actual_ty, 0))) > 0
),
anchor as (
    select exchange_year, snapshot_date as period_end from usable where freshness = 1
),
ytd as (
    -- Net sales is gross less discounts and returns. Both columns are read from
    -- the same rows of the same exchange year, so the current period and the
    -- year-earlier one are stated at identical rates by construction — no
    -- conversion, and nothing to reconcile between them.
    select
        f.entity_code,
        f.country,
        f.region,
        case f.channel
            when 'WEB PARTNERS'      then 'WEBP - Web Partners'
            when 'TRAVEL RETAIL'     then 'TRA - Travel retail'
            when 'DISTRIBUTORS'      then 'DIS - Distributors'
            when 'DEPARTMENT STORES' then 'DPT - Department Stores'
            when 'CHAINS WHOLESALE'  then 'WHOCH - Chains Wholesale'
            when 'WHOLESALE INDEP'   then 'WHOIN - Wholesale indep'
            when 'WHOLESALES SPA'    then 'WHOSP - Wholesales SPA'
            when 'TV CHANNELS'       then 'TVC - TV Channels'
        end as segment,
        f.snapshot_date,
        sum(iff(f.account_code in ('PPL101', 'PPL102'),
                coalesce(f.actual_ty, 0), 0)) * 1000 as ytd_actual,
        sum(iff(f.account_code in ('PPL101', 'PPL102'),
                coalesce(f.actual_ly, 0), 0)) * 1000 as ytd_last_year
    from dwh.public.f_management_operating_profit_country f
    join anchor a on a.exchange_year = f.exchange_year
    where f.brand_code = 'OC'
      and f.snapshot_date <= a.period_end
      and f.channel in ('WEB PARTNERS', 'TRAVEL RETAIL', 'DISTRIBUTORS',
                        'DEPARTMENT STORES', 'CHAINS WHOLESALE', 'WHOLESALE INDEP',
                        'WHOLESALES SPA', 'TV CHANNELS')
    group by 1, 2, 3, 4, 5
),
stepped as (
    -- Both amount columns are cumulative from the start of the fiscal year, so a
    -- month is a difference between snapshots. The fiscal year opens in April,
    -- hence the March anchor for the very first snapshot.
    select
        y.entity_code,
        y.country,
        y.region,
        y.segment,
        y.snapshot_date,
        y.ytd_actual - coalesce(
            lag(y.ytd_actual) over (partition by y.entity_code, y.segment
                                    order by y.snapshot_date), 0) as sales_actual,
        y.ytd_last_year - coalesce(
            lag(y.ytd_last_year) over (partition by y.entity_code, y.segment
                                       order by y.snapshot_date), 0) as sales_last_year,
        datediff(
            'month',
            coalesce(
                lag(y.snapshot_date) over (partition by y.entity_code, y.segment
                                           order by y.snapshot_date),
                -- No earlier snapshot for this pair: its year-to-date is the
                -- whole year so far. The fiscal year opens on 1 April, and the
                -- baseline sits one month before it so that the opening month
                -- comes out as a span of one.
                add_months(
                    date_from_parts(
                        year(y.snapshot_date) - iff(month(y.snapshot_date) >= 4, 0, 1),
                        4, 1),
                    -1)),
            y.snapshot_date) as months_covered
    from ytd y
)
select
    s.entity_code as entity,
    s.country     as market,
    s.region      as region,
    s.segment     as segment,
    case
        when s.months_covered <= 1 then to_char(s.snapshot_date, 'YYYY-MM')
        -- A missing snapshot makes two months inseparable. Said plainly rather
        -- than split by a rule of thumb: `reconcile` confronts a range with the
        -- plan's own months added together, and an invented split would be worth
        -- less than none.
        else to_char(add_months(s.snapshot_date, 1 - s.months_covered), 'YYYY-MM')
             || '..' || to_char(s.snapshot_date, 'YYYY-MM')
    end                         as period,
    s.sales_actual              as sales_actual,
    s.sales_last_year           as sales_last_year,
    cast(null as number(38, 4)) as sales_budget,
    cast(null as number(38, 4)) as sales_forecast,
    cast(null as varchar)       as owner_name
from stepped s
-- Every month of the exchange year, not only the latest. The final anchor join used to
-- sit here, and it made this query answer one question well and another silently wrong:
-- the screen wants the closed month, the year to date wants all of them. Filtering the
-- rows is the caller's business — a query that has already decided cannot be asked the
-- other question, and the year to date added one month of sell-in to four of sell-out
-- without anything saying so.
where s.segment is not null
  -- A row that is zero on both periods is a channel the entity does not use.
  -- Kept out so the screen is not padded with lines nobody can act on.
  and (s.sales_actual <> 0 or s.sales_last_year <> 0)
order by s.snapshot_date, s.sales_actual desc nulls last
"""

#: The same sell-in figures, over a whole fiscal year, for the reconciliation to run
#: against — `manage.py reconcile --from-warehouse`.
#:
#: It exists because a measurement that cannot be repeated is a claim, not a guarantee.
#: The 98% agreement that promoted sell-in out of "not measured" was produced by a
#: throwaway script on one machine: nobody else could reproduce it, and nobody — including
#: whoever wrote it — could tell six months later whether it still held. Versioned here,
#: the check runs monthly in one command and catches the drift it was built to catch.
#:
#: One row per entity, segment and month, over the last complete fiscal year:
#:
#:     entity            text     -- 'M_024', 'M_098_TRA'
#:     segment           text     -- the plan's segment label
#:     period            text     -- 'YYYY-MM', or 'YYYY-MM..YYYY-MM' for months the
#:                                   source cannot separate. Never split by a rule of
#:                                   thumb: a figure invented to fill a column is worth
#:                                   less than an honest pair.
#:     value             number   -- euros, at the plan's exchange year
#:
#: No market column is needed: the entity is what joins, and it is what the plan uses.
SELL_IN_HISTORY = """
with bounds as (
    -- The last complete fiscal year, derived rather than written down: the year
    -- opens on 1 April and closes on 31 March, so today's month decides which
    -- one has finished. The plan states its figures at the *following* year's
    -- rates, because its actuals sit in that year's prior-year column.
    select
        year(current_date) - iff(month(current_date) >= 4, 0, 1) as closing_year
),
years as (
    select
        'FY' || to_varchar(closing_year)     as data_year,
        'FY' || to_varchar(closing_year + 1) as plan_year,
        date_from_parts(closing_year - 1, 4, 1) as fiscal_start,
        date_from_parts(closing_year, 3, 31)    as fiscal_end
    from bounds
),
month_ytd as (
    select
        f.entity_code,
        case f.channel
            when 'WEB PARTNERS'      then 'WEBP - Web Partners'
            when 'TRAVEL RETAIL'     then 'TRA - Travel retail'
            when 'DISTRIBUTORS'      then 'DIS - Distributors'
            when 'DEPARTMENT STORES' then 'DPT - Department Stores'
            when 'CHAINS WHOLESALE'  then 'WHOCH - Chains Wholesale'
            when 'WHOLESALE INDEP'   then 'WHOIN - Wholesale indep'
            when 'WHOLESALES SPA'    then 'WHOSP - Wholesales SPA'
            when 'TV CHANNELS'       then 'TVC - TV Channels'
        end as segment,
        f.snapshot_date,
        sum(iff(f.account_code in ('PPL101', 'PPL102'),
                coalesce(f.actual_ty, 0), 0)) * 1000 as ytd
    from dwh.public.f_management_operating_profit_country f
    join years y on y.data_year = f.exchange_year
    where f.brand_code = 'OC'
      and f.snapshot_date between y.fiscal_start and add_months(y.fiscal_end, 1)
      and f.channel in ('WEB PARTNERS', 'TRAVEL RETAIL', 'DISTRIBUTORS',
                        'DEPARTMENT STORES', 'CHAINS WHOLESALE', 'WHOLESALE INDEP',
                        'WHOLESALES SPA', 'TV CHANNELS')
    group by 1, 2, 3
),
data_year_annual as (
    -- The closing year-to-date is the year, by definition of a cumulative column.
    select entity_code, sum(ytd) as annual
    from month_ytd
    where snapshot_date = (select max(snapshot_date) from month_ytd)
    group by 1
),
plan_year_annual as (
    -- The same year, restated at the rates the plan is stated in. It lives in the
    -- next exchange year's prior-year column.
    select
        f.entity_code,
        sum(iff(f.account_code in ('PPL101', 'PPL102'),
                coalesce(f.actual_ly, 0), 0)) * 1000 as annual
    from dwh.public.f_management_operating_profit_country f
    join years y on y.plan_year = f.exchange_year
    where f.brand_code = 'OC'
      and f.channel in ('WEB PARTNERS', 'TRAVEL RETAIL', 'DISTRIBUTORS',
                        'DEPARTMENT STORES', 'CHAINS WHOLESALE', 'WHOLESALE INDEP',
                        'WHOLESALES SPA', 'TV CHANNELS')
      and f.snapshot_date = (
          select max(snapshot_date)
          from dwh.public.f_management_operating_profit_country g
          join years z on z.plan_year = g.exchange_year
          where g.brand_code = 'OC')
    group by 1
),
rate as (
    -- An exchange year is one fixed rate set for the whole year, so the two annual
    -- totals for an entity differ by a constant. Deriving it here and checking the
    -- restated series still sums to the annual total is what makes this a
    -- conversion rather than an adjustment.
    select d.entity_code, p.annual / d.annual as ratio
    from data_year_annual d
    join plan_year_annual p on p.entity_code = d.entity_code
    where d.annual <> 0
),
stepped as (
    select
        m.entity_code,
        m.segment,
        m.snapshot_date,
        m.ytd - coalesce(
            lag(m.ytd) over (partition by m.entity_code, m.segment
                             order by m.snapshot_date), 0) as month_value,
        datediff(
            'month',
            coalesce(
                lag(m.snapshot_date) over (partition by m.entity_code, m.segment
                                           order by m.snapshot_date),
                (select add_months(fiscal_start, -1) from years)),
            m.snapshot_date) as months_covered
    from month_ytd m
)
select
    s.entity_code as entity,
    s.segment     as segment,
    case
        when s.months_covered <= 1 then to_char(s.snapshot_date, 'YYYY-MM')
        -- A snapshot missing from the middle of a cumulative series makes two
        -- months inseparable. Said as a pair rather than split by a rule of
        -- thumb: `reconcile` confronts a range with the plan's own months added
        -- together, and a figure invented to fill a column is worth less than an
        -- honest pair.
        else to_char(add_months(s.snapshot_date, 1 - s.months_covered), 'YYYY-MM')
             || '..' || to_char(s.snapshot_date, 'YYYY-MM')
    end                                    as period,
    s.month_value * coalesce(r.ratio, 1)   as value
from stepped s
left join rate r on r.entity_code = s.entity_code
where s.segment is not null
order by s.entity_code, s.segment, s.snapshot_date
"""

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
    "SELL_IN": SELL_IN,
    "SELL_IN_HISTORY": SELL_IN_HISTORY,
    "KPI_READINGS": KPI_READINGS,
    "MARKET_INDEX": MARKET_INDEX,
    "COMMITMENTS": COMMITMENTS,
    "FORECAST_HISTORY": FORECAST_HISTORY,
}


def missing() -> list:
    """Names of the queries still to be written."""
    return sorted(name for name, sql in ALL.items() if not sql.strip())
