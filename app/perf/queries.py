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

## Two things the queries below still owe the warehouse

Neither changes a figure today. Both are recorded here because the person who writes the
next query is the one who needs to know, and because "it happened to be true this year" is
not the same as "the query says so".

`FLAG_TURNOVER = 1` is the house rule for excluding samples, gifts and supplies, and the
organisation's own verified queries apply it every time. None of the queries below do. On
FY26, L'Occitane brand, every row already carries it — checked to the euro — so nothing
here is wrong. But the day a query reaches a wider perimeter, another brand or an older
year, it will count samples as turnover and nothing will say so.

`SEMANTIC_VIEW()` is not the only governed door. The organisation's verified queries read
`V_SL_AI_F_SELLOUT_SALES_DETAILS` directly, writing the governed expression out in full,
and that path allows what the function refuses — a `count(distinct)` grouped by month,
which is what an average basket and a units-per-transaction need. Two measures were
declared impossible on the strength of the function's limits alone. That path carries all
brands, so it needs the brand filter written out too: without it FY26 reads €859m instead
of €836m.

## One flag that does not mean what it is called

`YEAR_TO_DATE = 1` does not mean the current year to date, whatever the view's own
documentation says. It marks the same date interval in eight successive fiscal years, so a
query using it alone returns eight years stacked — €557m where the year to date is €276m.
It is a year-on-year comparison flag. `YEAR_TO_DATE = 1 AND CURRENT_YEAR = 0` is the real
year to date, and it is the better cut because the closing day is the house's rather than
ours. `CURRENT_YEAR` on its own is exact, checked to the euro against the dates.
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
#:   ended 2024-06-22 and its current business runs on local platforms, none of which
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
#:     upt               number   -- units per ticket, governed definition; null where
#:                                   the month has no non-zero transaction
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
),
baskets as (
    -- Units per ticket, at the grain this query already has. It belongs here rather
    -- than in `KPI_READINGS`, whose contract is `scope · kpi_key · period · value`
    -- with no room for a channel: encoding one into `scope` would dirty the key the
    -- registry joins on.
    --
    -- Read on the semantic-layer fact view, because the governed definition divides by
    -- `COUNT(DISTINCT TRANSACTION_NUMBER)` and that is only right when this query owns
    -- the GROUP BY. `FLAG_TURNOVER = 1` and the brand filter are both required: the
    -- view carries every brand, and samples are not revenue.
    select
        s.store_country                              as market,
        s.store_sub_channel                          as channel,
        date_trunc('month', f.transaction_date)      as month,
        sum(iff(f.flag_zero_sales_ticket = 0, f.quantity, 0))
            / nullif(count(distinct iff(f.flag_zero_sales_ticket = 0,
                                        f.transaction_number, null)), 0) as upt
    from dwh.semantic_layer.v_sl_ai_f_sellout_sales_details f
    join dwh.semantic_layer.v_sl_ai_d_stores s on s.store_skey = f.store_skey
    cross join period p
    where f.flag_turnover = 1
      and s.store_brand = 'L''OCCITANE'
      and f.transaction_date >= dateadd(month, -26, current_date)
      and date_trunc('month', f.transaction_date) between p.first_month and p.last_month
    group by 1, 2, 3
)
select
    coalesce(s.market, b.market)                        as market,
    coalesce(s.channel, b.channel)                      as channel,
    to_char(coalesce(s.month, b.month), 'YYYY-MM')      as period,
    s.sales_actual                                      as sales_actual,
    b.sales_budget                                      as sales_budget,
    u.upt                                               as upt
from sales s
full outer join budget b
    on b.market = s.market and b.channel = s.channel and b.month = s.month
left join baskets u
    on u.market = coalesce(s.market, b.market)
   and u.channel = coalesce(s.channel, b.channel)
   and u.month = coalesce(s.month, b.month)
order by market, channel, period
"""

#: Sell-in: everything invoiced to a partner who then resells. Roughly two fifths of the
#: plan, and invisible to every sell-out source by construction — the revenue is recognised
#: when the Maison ships, not when a shopper buys.
#:
#: It comes from the management consolidation rather than from the sell-out warehouse,
#: which is not a workaround: the consolidation *is* where the plan's own actuals come
#: from, so the two reconcile by construction rather than by coincidence. The plan
#: designates its markets by a consolidation entity — `M_103`, `M_105_TRA` — and that code
#: is the join key. A company code or a customer hierarchy is someone else's answer to the
#: same question, and the two do not agree: eleven markets are billed by a hub and vanish
#: entirely under a company-based attribution.
#:
#: One row per entity, segment and month:
#:
#:     entity            text     -- 'M_103', 'M_105_TRA' — the plan's own key
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
#:     entity            text     -- 'M_103', 'M_105_TRA'
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
#:
#: Twelve keys, twenty-four months, at market scope and rolled up to `LOEP`. Every
#: percentage is a ratio of two sums, never an average of ratios, so the group figure is
#: the group's own and not the mean of its markets.
#:
#: `net_sales_hors_bulk` sits beside `net_sales`, never in place of it: the pair is what
#: measures bulk, and either figure alone measures nothing. The exclusion is
#: `FLAG_BULK IN (2, 3, 4, 5)` — the view's own `BULK_SALES` definition, not "anything
#: non-zero". The five other non-zero values (1, 6, 7, 8, 9) stay in, and that is a
#: reading rather than a default: every bulk row sits in `TRANSACTION_CHANNEL = 'OTHER'`
#: while all five sit in `'RETAIL'`, and two of them carry a unit price above the
#: ordinary retail one rather than below it. Nobody has named what they are, so the
#: choice is reversible in one line if the referential ever says.
#:
#: Five of the tracker's monthly KPIs are deliberately absent, and their absence is the
#: reading:
#:
#: * **Niveau de discount** — `EXPLICIT_DISCOUNT_EUR` and `IMPLICIT_DISCOUNT_EUR` exist in
#:   the raw fact and are not exposed by the semantic view. Reading round the governed
#:   layer to fill a column is the trade this repository has already refused once.
#: * **ATV** and **UPT** — `NB_TICKETS` counts sales *lines*, not tickets, roughly three
#:   for every transaction. Any ratio built on it is wrong by that factor, which turns a
#:   basket into a third of itself and a units-per-transaction below its floor. The
#:   governed `ATV_EUR` divides by `COUNT(DISTINCT TRANSACTION_NUMBER)`, which
#:   the view computes correctly only at the grain it is asked for, and it exposes no month
#:   dimension. Twenty-four monthly reads would be needed; one statement cannot do it.
#: * **ARC** and **Acquisition NTB nette** — the tracker states them as "sur croissance
#:   sell-out totale" and "nouveaux clients nets", neither of which names a computable
#:   quantity. A number invented from a plausible reading would be indistinguishable from
#:   a measured one.
#:
#: Two keys carry a settled figure that disagrees with the tracker, and the disagreement is
#: worth more than a silent match:
#:
#: * `heroes_wob` returns a few points under the tracker's figure for FY26. Five perimeters
#:   were tested — with and without marketplace, outlet, own retail only, turnover-relevant
#:   products — and all land within a point of each other. The cause is the hero list itself, not
#:   the scope: the product referential and the RGM figure do not designate the same
#:   products.
#: * `nps_retail` returns 72.7 against a stated global 74. "Global" is not defined: the
#:   warehouse holds four survey families, and they read 72.7 (retail), 60.9 (e-commerce),
#:   40.0 (customer service) and 16.3 (CPRVHK). Which of them the board number means is a
#:   decision, so each is returned under its own key rather than blended into one.
KPI_READINGS = """
with period as (
    select
        date_trunc('month', add_months(anchor, -1))  as last_month,
        date_trunc('month', add_months(anchor, -24)) as first_month,
        -- A shorter window for the keys only ever read year on year. Two years is what
        -- persistence needs — telling a gap that has settled in from an accident — and
        -- ATV, UPT and the Home share are never asked that question.
        date_trunc('month', add_months(anchor, -13)) as first_month_yoy
    from (
        -- Bounded: an unbounded `max(date)` on this fact reads 77 GB.
        select max(max_sales_date) as anchor
        from semantic_view(
            dwh.semantic_layer.v_sl_ai_sellout_analysis
            metrics max(f_sellout_sales_details.transaction_date) as max_sales_date
            where f_sellout_sales_details.transaction_date
                  >= dateadd(month, -3, current_date)
        )
    )
),
sellout as (
    select
        store_country,
        store_sub_channel,
        store_samestore_ty,
        is_hero,
        is_refill,
        flag_bulk,
        date_trunc('month', transaction_date) as month,
        net_sales_eur,
        quantity,
        nb_tickets,
        new_clients
    from semantic_view(
        dwh.semantic_layer.v_sl_ai_sellout_analysis
        dimensions
            d_stores.store_country,
            d_stores.store_sub_channel,
            d_stores.store_samestore_ty,
            d_products.is_hero,
            d_products.is_refill,
            f_sellout_sales_details.flag_bulk,
            f_sellout_sales_details.transaction_date
        metrics
            sum(f_sellout_sales_details.net_sales_eur) as net_sales_eur,
            sum(f_sellout_sales_details.quantity)      as quantity,
            sum(f_sellout_sales_details.nb_tickets)    as nb_tickets,
            f_sellout_sales_details.nb_new_clients     as new_clients
        where d_stores.store_brand = 'L''OCCITANE'
          and f_sellout_sales_details.transaction_date
              >= dateadd(month, -26, current_date)
    )
),
sellout_window as (
    select s.* from sellout s cross join period p
    where s.month between p.first_month and p.last_month
),
sales_keys as (
    select
        -- `grouping()` distinguishes the roll-up from a member whose country is null.
        -- Labelling both 'LOEP' made two different rows share one key, and whichever
        -- arrived last won — the same query returned a different NPS on two runs.
        iff(grouping(store_country) = 1, 'LOEP',
            coalesce(store_country, '(sans pays)'))    as scope,
        to_char(month, 'YYYY-MM')                      as period,
        sum(net_sales_eur)                             as net_sales,
        -- Bulk excluded exactly as the view's own `BULK_SALES` fact defines it:
        -- FLAG_BULK IN (2,3,4,5). The five other non-zero values — 1, 6, 7, 8, 9 —
        -- are outside that definition and are therefore kept in, which is the
        -- reading their evidence supports: they sit in TRANSACTION_CHANNEL =
        -- 'RETAIL' where every bulk row sits in 'OTHER', and two of them carry a
        -- unit price above the ordinary retail one rather than below it.
        sum(iff(flag_bulk in (2, 3, 4, 5), 0, net_sales_eur)) as net_sales_ex_bulk,
        sum(iff(is_hero = 1, net_sales_eur, 0))        as hero_sales,
        sum(iff(is_refill = 1, net_sales_eur, 0))      as refill_sales,
        sum(iff(store_samestore_ty = 'yes', net_sales_eur, 0)) as same_store_sales,
        sum(iff(store_sub_channel = 'E-COMMERCE', net_sales_eur, 0)) as brand_com_sales,

        sum(new_clients)                               as new_clients
    from sellout_window
    group by grouping sets ((store_country, month), (month))
),
traffic as (
    select
        iff(grouping(store_country) = 1, 'LOEP',
            coalesce(store_country, '(sans pays)')) as scope,
        to_char(month, 'YYYY-MM')                as period,
        sum(retail_traffic)                      as traffic
    from (
        select store_country,
               date_trunc('month', transaction_date) as month,
               retail_traffic
        from semantic_view(
            dwh.semantic_layer.v_sl_ai_sellout_analysis
            dimensions d_stores.store_country, f_store_traffic.transaction_date
            metrics sum(f_store_traffic.retail_traffic_adjusted) as retail_traffic
            where d_stores.store_brand = 'L''OCCITANE'
              and f_store_traffic.transaction_date >= dateadd(month, -26, current_date)
        )
    ) t cross join period p
    where t.month between p.first_month and p.last_month
    group by grouping sets ((store_country, month), (month))
),
surveys as (
    select
        iff(grouping(country) = 1, 'LOEP',
            coalesce(country, '(sans pays)'))     as scope,
        to_char(month, 'YYYY-MM')                as period,
        nps_type,
        sum(iff(nps_score_desc = 'Promoter', responses, 0))  as promoters,
        sum(iff(nps_score_desc = 'Detractor', responses, 0)) as detractors,
        sum(responses)                                       as responses
    from (
        select country, nps_type, nps_score_desc,
               date_trunc('month', survey_date) as month,
               responses
        from semantic_view(
            dwh.semantic_layer.v_sl_ai_survey_analysis
            dimensions f_surveys.country, f_surveys.nps_type,
                       f_surveys.nps_score_desc, f_surveys.survey_date
            metrics count(f_surveys.survey_id) as responses
            where f_surveys.survey_date >= dateadd(month, -26, current_date)
        )
    ) s cross join period p
    where s.month between p.first_month and p.last_month
    group by grouping sets ((country, month, nps_type), (month, nps_type))
),
reviews as (
    select
        iff(grouping(review_country) = 1, 'LOEP',
            coalesce(review_country, '(sans pays)')) as scope,
        to_char(month, 'YYYY-MM')         as period,
        sum(rating_total) / nullif(sum(nb_reviews), 0) as review_rating
    from (
        select review_country,
               date_trunc('month', review_date) as month,
               rating_total, nb_reviews
        from semantic_view(
            dwh.semantic_layer.v_sl_ai_survey_analysis
            dimensions product_reviews.review_country, product_reviews.review_date
            metrics sum(product_reviews.review_rating) as rating_total,
                    product_reviews.nb_reviews         as nb_reviews
            where product_reviews.review_date >= dateadd(month, -26, current_date)
        )
    ) r cross join period p
    where r.month between p.first_month and p.last_month
    group by grouping sets ((review_country, month), (month))
),
governed as (
    -- A second read path, on the semantic-layer fact view rather than through the
    -- `SEMANTIC_VIEW()` function. This is the pattern the organisation's own verified
    -- queries use, and it is what makes ATV and UPT possible at all: their governed
    -- definitions divide by `COUNT(DISTINCT TRANSACTION_NUMBER)`, which is only correct
    -- when this query owns the GROUP BY. Read through the function, the month grain was
    -- unreachable and the additive facts gave answers wrong by a factor of three.
    --
    -- `FLAG_TURNOVER = 1` is applied here, as those verified queries do, so samples,
    -- gifts-with-purchase and supplies never count as revenue. The brand filter is not
    -- optional either: this view carries every brand, and without it FY26 reads 859m
    -- instead of 836m.
    select
        iff(grouping(s.store_country) = 1, 'LOEP',
            coalesce(s.store_country, '(sans pays)'))     as scope,
        to_char(date_trunc('month', f.transaction_date), 'YYYY-MM') as period,
        sum(iff(f.flag_zero_sales_ticket = 0, f.net_sales_eur, 0)) as net_non_zero,
        sum(iff(f.flag_zero_sales_ticket = 0, f.quantity, 0))      as qty_non_zero,
        count(distinct iff(f.flag_zero_sales_ticket = 0,
                           f.transaction_number, null))            as transactions,
        sum(f.net_sales_eur)                                       as net_all,
        sum(iff(p.product_segment = 'HOME', f.net_sales_eur, 0))   as home_sales,
        -- One café, not the café business. Almost all of this lands on a single store,
        -- which the reforecast, the cleaning restatement and the consolidation each call
        -- by a different name — one of them a pseudo-country. The Maison runs a handful
        -- of cafés; sell-out sees one. Hence the key's name: one called `cafes` would
        -- promise a perimeter it does not cover, and the next reader would take the whole
        -- activity for what one site does.
        --
        -- The remainder is confectionery sold occasionally in ordinary boutiques. A
        -- box of chocolates in an outlet is not a café, which is why counting stores
        -- rather than money once suggested fifty-one of them.
        --
        -- It reads zero from May 2026. That is a closure, not an outage: the café shut
        -- in May or June, and the series stopping after April is that closure being
        -- seen. Nine of the thirteen months are usable.
        sum(iff(p.product_segment in ('MACARON', 'PATISSERIE', 'CHOCOLATS',
                                      'CHOCOLAT EVENEMENTIEL', 'CAKES', 'GLACE',
                                      'FOOD', 'BOISSONS', 'CONFISERIE'),
                f.net_sales_eur, 0))                               as cafe_sales
    from dwh.semantic_layer.v_sl_ai_f_sellout_sales_details f
    join dwh.semantic_layer.v_sl_ai_d_stores   s on s.store_skey   = f.store_skey
    join dwh.semantic_layer.v_sl_ai_d_products p on p.product_skey = f.product_skey
    cross join period pr
    where f.flag_turnover = 1
      and s.store_brand = 'L''OCCITANE'
      and f.transaction_date >= dateadd(month, -15, current_date)
      and date_trunc('month', f.transaction_date)
          between pr.first_month_yoy and pr.last_month
    group by grouping sets (
        (s.store_country, date_trunc('month', f.transaction_date)),
        (date_trunc('month', f.transaction_date)))
)
select scope, 'net_sales'   as kpi_key, period, net_sales as value from sales_keys
union all
-- Returned beside `net_sales`, never instead of it: the two together are what measure
-- bulk, and either one alone measures nothing.
select scope, 'net_sales_hors_bulk', period, net_sales_ex_bulk from sales_keys
union all
select scope, 'same_store_sales', period, same_store_sales from sales_keys
union all
select scope, 'brand_com_sales', period, brand_com_sales from sales_keys
union all
select scope, 'heroes_wob', period,
       100.0 * hero_sales / nullif(net_sales, 0) from sales_keys
union all
select scope, 'refills_wob', period,
       100.0 * refill_sales / nullif(net_sales, 0) from sales_keys
union all
select scope, 'new_clients', period, new_clients from sales_keys
union all
select scope, 'retail_traffic', period, traffic from traffic
union all
-- Survey families are returned separately. Which one the board's "NPS Global" means
-- is a decision, and blending them would answer it by arithmetic.
select scope, 'nps_retail', period,
       100.0 * (promoters - detractors) / nullif(responses, 0)
from surveys where nps_type = 'NPS_RE'
union all
select scope, 'nps_ecommerce', period,
       100.0 * (promoters - detractors) / nullif(responses, 0)
from surveys where nps_type = 'NPS_EC'
union all
select scope, 'nps_customer_service', period,
       100.0 * (promoters - detractors) / nullif(responses, 0)
from surveys where nps_type = 'NPS_CS'
union all
select scope, 'review_rating', period, review_rating from reviews
union all
-- The governed definitions, written out rather than approximated.
select scope, 'atv', period, net_non_zero / nullif(transactions, 0) from governed
union all
select scope, 'upt', period, qty_non_zero / nullif(transactions, 0) from governed
union all
-- A share, not an amount: the tracker states the Home category in percent, and a figure
-- in euros could not be scored against it. The amount is available beside it if ever
-- wanted, never instead of it.
select scope, 'home_wob', period,
       100.0 * home_sales / nullif(net_all, 0) from governed
union all
-- Beside `net_sales`, never instead of it, exactly as `net_sales_hors_bulk` is.
select scope, 'net_sales_cafe_86champs', period, cafe_sales from governed
"""

#: Published market growth per market, used to test "the market is difficult" rather than
#: repeat it. Leave empty if no benchmark exists — the cockpit then says so explicitly
#: instead of inventing one.
MARKET_INDEX = ""

#: Commitments, if they are tracked in the warehouse. Leave empty to keep entering them
#: in the cockpit itself.
COMMITMENTS = ""

#: Successive forecasts for the same period, oldest first — the forecast credibility flag.
FORECAST_HISTORY = ""

#: Le mois en cours, marché par marché, jusqu'au dernier jour lu. Sell-out seulement : le
#: sell-in n'avance pas en jours — une facture tombe quand elle tombe — et tant qu'aucun
#: calendrier d'expédition n'est connecté, il n'a pas d'avancement à afficher.
#:
#: Bornée au mois : c'est la plus petite lecture de ce fichier, et elle doit le rester,
#: parce qu'elle est la seule que l'écran a le droit de payer sans cache chaud.
#:
#: Contrat : `market · iso2 · sales_to_date · read_through · first_day_sales`, une ligne
#: par marché.
MONTH_TO_DATE = """
with day as (
    select
        store_country                 as market,
        store_country_iso2            as iso2,
        transaction_date,
        net_sales_eur
    from semantic_view(
        dwh.semantic_layer.v_sl_ai_sellout_analysis
        dimensions
            d_stores.store_country,
            d_stores.store_country_iso2,
            f_sellout_sales_details.transaction_date
        metrics sum(f_sellout_sales_details.net_sales_eur) as net_sales_eur
        where d_stores.store_brand = 'L''OCCITANE'
          and f_sellout_sales_details.transaction_date >= date_trunc('month', current_date)
    )
)
select
    market,
    iso2,
    sum(net_sales_eur)                                   as sales_to_date,
    max(transaction_date)                                as read_through,
    -- Le 1er du mois à part. Un marché dont le sell-out est versé par paquets porte
    -- jusqu'à quatre dixièmes de son mois sur ce seul jour ; lu comme une vente, ce
    -- paquet met le marché « en avance » de vingt points le 3 du mois. La part est
    -- rendue, jamais corrigée : c'est un défaut d'alimentation, pas un fait de commerce.
    sum(iff(transaction_date = date_trunc('month', current_date), net_sales_eur, 0))
                                                         as first_day_sales
from day
group by market, iso2
"""


#: Le sell-out au jour, marché par marché, sur les six dernières semaines et sur les mêmes
#: dates un an plus tôt — 364 jours en arrière, pour que lundi tombe sur lundi. C'est ce qui
#: permet de lire la semaine contre la semaine précédente et contre la même semaine de l'an
#: dernier sans qu'un week-end de plus ou de moins fausse la comparaison.
DAILY_SALES = """
select
    store_country                 as market,
    store_country_iso2            as iso2,
    transaction_date,
    net_sales_eur
from semantic_view(
    dwh.semantic_layer.v_sl_ai_sellout_analysis
    dimensions
        d_stores.store_country,
        d_stores.store_country_iso2,
        f_sellout_sales_details.transaction_date
    metrics sum(f_sellout_sales_details.net_sales_eur) as net_sales_eur
    where d_stores.store_brand = 'L''OCCITANE'
      and (f_sellout_sales_details.transaction_date >= dateadd(day, -42, current_date)
           or f_sellout_sales_details.transaction_date
              between dateadd(day, -406, current_date) and dateadd(day, -364, current_date))
)
"""


#: Le sell-in facturé au jour, du 1er du mois en cours à hier, et les mêmes dates un an
#: plus tôt : `window · invoice_date · iso2 · channel · net_eur`. `window` vaut `current`
#: ou `last_year` ; `channel` est le code du centre de profit (TRA, WEBP, DIS, WHOCH…),
#: jamais la colonne de canal de la facture, vide quatre fois sur cinq ; `net_eur` est le
#: net au taux fixe, jamais au taux de la facture. Écrit par l'agent entrepôt contre
#: V_SL_F_SELLIN_INVOICE_ITEM. Une seule marque, comme le sell-out : la table en porte cinq,
#: et poser cinq marques à côté d'une seule ferait une croissance de rien. `window` est un
#: mot réservé, d'où les guillemets, qui doivent survivre au littéral.
SELL_IN_DAILY = """
select
    'current'                                       as "window",
    i.billing_date                                  as invoice_date,
    i.country                                       as iso2,
    i.profit_center_group_channel                   as channel,
    round(sum(i.net_invoice_amount_eur_annual), 2)  as net_eur
from dwh.semantic_layer.v_sl_f_sellin_invoice_item i
where i.brand_caption = 'L''OCCITANE'
  and i.billing_date >= date_trunc('month', current_date)
  and i.billing_date <= dateadd(day, -1, current_date)
group by 1, 2, 3, 4
union all
select
    'last_year'                                     as "window",
    i.billing_date                                  as invoice_date,
    i.country                                       as iso2,
    i.profit_center_group_channel                   as channel,
    round(sum(i.net_invoice_amount_eur_annual), 2)  as net_eur
from dwh.semantic_layer.v_sl_f_sellin_invoice_item i
where i.brand_caption = 'L''OCCITANE'
  and i.billing_date >= add_months(date_trunc('month', current_date), -12)
  and i.billing_date <= last_day(add_months(date_trunc('month', current_date), -12))
group by 1, 2, 3, 4
"""


#: Le sell-out par produit, à trois niveaux, sur treize mois : ce qui marche et ce qui
#: recule, catégorie par catégorie, gamme par gamme, référence par référence. Une ligne par
#: `scope · level · name · period` :
#:
#:     scope       text     -- 'LOEP' pour le groupe, sinon le pays (STORE_COUNTRY)
#:     level       text     -- 'category', 'range' ou 'product'
#:     name        text     -- le libellé du niveau, jamais un code seul
#:     period      text     -- 'YYYY-MM', le mois de transaction
#:     net_sales   number   -- NET_SALES_EUR, FLAG_TURNOVER = 1, hors vrac (FLAG_BULK 2 à 5)
#:     is_hero     number   -- 1 quand la référence est un héros du référentiel, sinon 0
#:
#: Les catégories et les gammes sont rendues pour le groupe et pour chaque pays ; les
#: références pour le groupe seulement — quarante pays fois quelques milliers de références
#: fois treize mois n'est pas une lecture, c'est un extrait. Treize mois, pour que
#: l'exercice à date ait son an dernier en face mois par mois ; la fenêtre s'aligne sur
#: celle de `KPI_READINGS` (`first_month_yoy`).
#:
#: Les trois libellés viennent de la dimension produit, colonnes confirmées par l'agent
#: entrepôt le 8 septembre 2026 sur la dimension seule puis sur un mois, puis sur treize :
#:
#: - `category` = `PRODUCT_SEGMENT`, une vingtaine de valeurs, celle que `home_wob` lit
#:   déjà. La vue promeut un sous-segment au rang de segment par un `case` ; c'est sa
#:   lecture, pas la nôtre.
#: - `range` = `PRODUCT_LINE`, la franchise telle qu'elle est **stockée**. Jamais
#:   `PRODUCT_LINE_EN` : cette colonne n'est pas stockée, c'est un appel à un modèle de
#:   traduction évalué ligne à ligne à chaque lecture — un simple `count(distinct)` dessus
#:   a été annulé deux fois au plafond de cinq minutes, elle n'est pas déterministe (la
#:   même gamme en deux graphies d'une lecture à l'autre) et chaque appel coûte des crédits.
#:   Une requête qui l'introduirait ici casserait la lecture sans qu'aucun garde-fou du
#:   dépôt ne le voie : c'est un `select` légitime.
#: - `product` = `LAST_PRODUCT_DESC_EN`, identité par `LAST_PRODUCT_ID`, qui rassemble
#:   les rebrandings d'une même référence. Les libellés d'attente du référentiel
#:   (« AVAILABLE SKU … ») sont écartés par le lecteur, pas ici.
#:
#: Le filtre de marque porte sur le **magasin**, comme partout ailleurs dans ce fichier :
#: ce qu'une boutique de la marque vend d'une autre marque reste dans ses ventes, et une
#: catégorie qui pèse moins d'un pour cent n'atteint jamais les cinq lignes de l'écran.
#: Filtrer aussi la marque produit serait une décision, pas une correction.
#:
#: Mesuré à la validation : treize mois en moins d'une minute, quelques gigaoctets ; la
#: fenêtre de l'exercice en compte jusqu'à vingt-quatre, pour le double au plus — la
#: lecture se relance donc par le cockpit lui-même (`manage.py products --refresh`,
#: `?refresh=1`), jamais par un agent. `query_history` rend zéro octet scanné pour cette
#: requête parce que le fait est lu par un accès Search Optimization qu'elle n'attribue
#: pas ; le volume se lit dans `get_query_operator_stats`. Ne jamais conclure « requête
#: gratuite » d'un zéro sur ce compte.
PRODUCT_SALES = """
with period as (
    select
        last_month,
        -- L'exercice à date et le même exercice à date un an plus tôt. Treize mois
        -- glissants laissaient l'exercice sans an dernier avant le mois courant : il
        -- ouvre en avril, la fenêtre ouvre en avril de l'année précédente — entre treize
        -- et vingt-quatre mois, jamais plus.
        add_months(date_from_parts(
            iff(month(last_month) >= 4, year(last_month), year(last_month) - 1), 4, 1),
            -12)                                     as first_month
    from (
        select date_trunc('month', add_months(anchor, -1)) as last_month
        from (
        -- Bounded: an unbounded `max(date)` on this fact reads 77 GB.
        select max(max_sales_date) as anchor
        from semantic_view(
            dwh.semantic_layer.v_sl_ai_sellout_analysis
            metrics max(f_sellout_sales_details.transaction_date) as max_sales_date
            where f_sellout_sales_details.transaction_date
                  >= dateadd(month, -3, current_date)
        )
    ))
),
base as (
    select
        s.store_country,
        date_trunc('month', f.transaction_date)  as month,
        p.product_segment                        as category,
        p.product_line                           as range_name,
        p.last_product_id                        as product_id,
        p.last_product_desc_en                   as product_name,
        p.is_hero,
        f.net_sales_eur
    from dwh.semantic_layer.v_sl_ai_f_sellout_sales_details f
    join dwh.semantic_layer.v_sl_ai_d_stores   s on s.store_skey   = f.store_skey
    join dwh.semantic_layer.v_sl_ai_d_products p on p.product_skey = f.product_skey
    cross join period pr
    where f.flag_turnover = 1
      and s.store_brand = 'L''OCCITANE'
      -- Bulk excluded exactly as the view's own `BULK_SALES` fact defines it.
      and coalesce(f.flag_bulk, 0) not in (2, 3, 4, 5)
      and f.transaction_date >= dateadd(month, -26, current_date)
      and date_trunc('month', f.transaction_date)
          between pr.first_month and pr.last_month
)
select
    iff(grouping(store_country) = 1, 'LOEP',
        coalesce(store_country, '(sans pays)'))    as scope,
    'category'                                     as level,
    coalesce(category, '(sans catégorie)')         as name,
    to_char(month, 'YYYY-MM')                      as period,
    sum(net_sales_eur)                             as net_sales,
    0                                              as is_hero
from base
group by grouping sets ((store_country, category, month), (category, month))
union all
select
    iff(grouping(store_country) = 1, 'LOEP',
        coalesce(store_country, '(sans pays)')),
    'range',
    coalesce(range_name, '(sans gamme)'),
    to_char(month, 'YYYY-MM'),
    sum(net_sales_eur),
    0
from base
group by grouping sets ((store_country, range_name, month), (range_name, month))
union all
-- Group only: forty countries times thousands of references times thirteen months is
-- an extract, not a reading.
select
    'LOEP',
    'product',
    coalesce(max(product_name), '(sans libellé)'),
    to_char(month, 'YYYY-MM'),
    sum(net_sales_eur),
    max(iff(is_hero = 1, 1, 0))
from base
group by product_id, month
"""

#: Les clients : le pont « clients × panier = ventes » et le flux de la base, sur l'exercice
#: à date contre le même exercice à date un an plus tôt, pour le groupe et par pays. Une
#: ligne par `scope · window · segment` :
#:
#:     scope         text    -- 'LOEP' pour le groupe, sinon le pays (STORE_COUNTRY)
#:     window        text    -- 'ty' l'exercice à date, 'ly' le même un an avant, 'ly2' deux ans avant
#:     through       text    -- 'YYYY-MM', le dernier mois complet de la fenêtre 'ty'
#:     segment       text    -- voir ci-dessous
#:     clients       number  -- clients (ou visites pour 'walkin') distincts dans la fenêtre
#:     transactions  number  -- tickets
#:     sales         number  -- NET_SALES_EUR, FLAG_TURNOVER = 1, hors vrac
#:     channel       text    -- vide sur les totaux ; sur `new`, le sous-canal du premier
#:                              ticket de la fenêtre (STORE_SUB_CHANNEL) ; sur `lost` et sur
#:                              `arc` de la base, celui du dernier ticket — la ligne découpée
#:
#: Segments, sur le sell-out en propre (boutiques et site) :
#:
#: - `arc` : les clients enregistrés actifs dans la fenêtre — Active Registered Clients.
#: - `walkin` : les tickets sans client enregistré ; `clients` compte les tickets.
#: - `retained` : dans 'ty', les clients actifs dans 'ty' qui l'étaient aussi dans 'ly'.
#: - `reactivated` : actifs dans 'ty', pas dans 'ly', mais déjà clients avant 'ly'.
#: - `new` : première transaction dans 'ty'.
#: - `lost` : dans 'ty', les clients de la base 'ly' sans transaction dans 'ty' ; leurs
#:   `sales` et `transactions` sont ceux de 'ly', ce qui a été perdu.
#:
#: - `unknown` : actifs dans 'ty', absents de 'ly', sans date de première transaction
#:   connue — la dimension porte une date sentinelle sur plus d'un tiers des clients, et
#:   un tel client tomberait mécaniquement en « réactivé » puisque la sentinelle est
#:   « avant l'an dernier ». Il est compté à part plutôt que mal rangé.
#:
#: La fenêtre 'ly' porte les mêmes segments que 'ty', classés contre 'ly2' : la part
#: perdue de cette année se compare ainsi à celle de l'an dernier au même mois. 'ly2' ne
#: porte que `arc` et `walkin`, c'est la base d'avant. Le cockpit obtient cela en lançant
#: la requête deux fois — `__SHIFT__` à 0 puis à 12 — et en décalant la seconde d'une
#: fenêtre (`source.read_client_flow`). Colonnes confirmées par l'agent entrepôt le 9 septembre 2026 sur un pays :
#: la clé client `CLIENT_SKEY` sur le fait ; un ticket sans client n'a ni clé nulle ni
#: valeur d'attente unique, il porte la clé d'un pseudo-client que la dimension marque
#: `FLAG_WALKIN` — une liste de clés en dur serait fausse au premier marché suivant ; la
#: clé de ticket est le quadruplet magasin, date, caisse, numéro ; la première
#: transaction est `CLIENT_FIRST_PURCHASE_DATE`, avec ses variantes site et boutique, la
#: sentinelle étant le premier janvier 1900. Le contrôle interne validé : `arc + walkin`
#: égale la base au centime ; `retained + reactivated + new` n'égalait pas `arc` parce que
#: les clients acquis entre les deux fenêtres n'avaient pas de segment — d'où `new` défini
#: comme « première transaction après la fin de 'ly' », et non « dans 'ty' ».
#:
#: Les `grouping sets` portent sur le client, jamais sur le résultat : un client retenu
#: au groupe peut être nouveau dans un pays, et sommer les pays donnerait un autre
#: chiffre que le groupe. Un pays a pris une vingtaine de secondes ; le groupe entier se
#: lit par le cockpit, derrière l'écran, jamais par un agent.
CLIENT_FLOW = """
with period as (
    select
        last_month,
        to_char(last_month, 'YYYY-MM')                                     as through,
        last_day(last_month)                                               as ty_to,
        date_from_parts(iff(month(last_month) >= 4, year(last_month),
                            year(last_month) - 1), 4, 1)                   as ty_from,
        add_months(date_from_parts(iff(month(last_month) >= 4, year(last_month),
                                       year(last_month) - 1), 4, 1), -12)  as ly_from,
        last_day(add_months(last_month, -12))                              as ly_to
    from (
        -- __SHIFT__ vaut 0 pour l'exercice en cours, 12 pour le même calcul un an plus
        -- tôt : le cockpit lance les deux et les assemble. Trois fenêtres en une requête
        -- passaient le plafond de cinq minutes de l'entrepôt ; deux fois deux fenêtres
        -- tiennent chacune sous la minute et disent la même chose.
        select date_trunc('month', add_months(anchor, -1 - __SHIFT__)) as last_month
        from (
            -- Bounded: an unbounded `max(date)` on this fact reads 77 GB.
            select max(max_sales_date) as anchor
            from semantic_view(
                dwh.semantic_layer.v_sl_ai_sellout_analysis
                metrics max(f_sellout_sales_details.transaction_date) as max_sales_date
                where f_sellout_sales_details.transaction_date
                      >= dateadd(month, -3, current_date)
            )
        )
    )
),
base as (
    select
        s.store_country,
        f.client_skey,
        coalesce(c.flag_walkin, 0)                                   as flag_walkin,
        -- La première transaction connue, la sentinelle écartée sur chacune des trois
        -- dates ; null quand aucune n'est connue.
        nullif(least(
            coalesce(nullif(c.client_first_purchase_date,        '1900-01-01'), '9999-12-31'),
            coalesce(nullif(c.client_first_purchase_date_ecom,   '1900-01-01'), '9999-12-31'),
            coalesce(nullif(c.client_first_purchase_date_retail, '1900-01-01'), '9999-12-31')
        ), '9999-12-31')                                             as first_date,
        f.store_skey || '|' || f.transaction_date || '|' || f.transaction_till
            || '|' || f.transaction_number                           as ticket,
        iff(f.transaction_date >= pr.ty_from, 'ty', 'ly')            as "window",
        f.transaction_date,
        s.store_sub_channel                                          as sub_channel,
        f.net_sales_eur
    from dwh.semantic_layer.v_sl_ai_f_sellout_sales_details f
    join dwh.semantic_layer.v_sl_ai_d_stores  s on s.store_skey  = f.store_skey
    join dwh.semantic_layer.v_sl_ai_d_clients c on c.client_skey = f.client_skey
    cross join period pr
    where f.flag_turnover = 1
      and s.store_brand = 'L''OCCITANE'
      and coalesce(f.flag_bulk, 0) not in (2, 3, 4, 5)
      and f.transaction_date >= dateadd(month, -26 - __SHIFT__, current_date)
      and (f.transaction_date between pr.ly_from and pr.ly_to
           or f.transaction_date between pr.ty_from and pr.ty_to)
),
-- Un client, une fenêtre, un périmètre : le pays, et le groupe par le roll-up — un client
-- actif dans deux pays compte une fois au groupe.
scoped as (
    select
        iff(grouping(store_country) = 1, 'LOEP',
            coalesce(store_country, '(sans pays)'))    as scope,
        "window",
        client_skey,
        max(flag_walkin)                               as flag_walkin,
        min(first_date)                                as first_date,
        -- Le canal du premier ticket de la fenêtre : d'où le client est entré. Et celui
        -- du dernier : d'où il est parti, quand il ne revient pas.
        min_by(sub_channel, transaction_date)          as entry_channel,
        max_by(sub_channel, transaction_date)          as last_channel,
        count(distinct ticket)                         as transactions,
        sum(net_sales_eur)                             as sales
    from base
    group by grouping sets ((store_country, "window", client_skey), ("window", client_skey))
),
registered as (
    select * from scoped where flag_walkin = 0
),
classified as (
    select
        ty.scope,
        ty.client_skey,
        ty.transactions,
        ty.sales,
        ty.entry_channel,
        case
            when ly.client_skey is not null        then 'retained'
            when ty.first_date is null             then 'unknown'
            when ty.first_date > pr.ly_to          then 'new'
            else                                        'reactivated'
        end                                            as segment
    from registered ty
    left join registered ly
      on ly.scope = ty.scope and ly."window" = 'ly' and ly.client_skey = ty.client_skey
    cross join period pr
    where ty."window" = 'ty'
)
select scope, 'ty' as "window", pr.through, segment,
       count(*) as clients, sum(transactions) as transactions, sum(sales) as sales,
       null as channel
from classified cross join period pr
group by scope, pr.through, segment
union all
-- Les nouveaux, par canal d'entrée : la même ligne, découpée. Le total reste au-dessus.
select scope, 'ty', pr.through, 'new',
       count(*), sum(transactions), sum(sales), coalesce(entry_channel, '(sans canal)')
from classified cross join period pr
where segment = 'new'
group by scope, pr.through, entry_channel
union all
select scope, "window", pr.through, 'arc',
       count(*), sum(transactions), sum(sales), null
from registered cross join period pr
group by scope, "window", pr.through
union all
-- La base de l'an dernier, par canal du dernier ticket : le dénominateur de la part
-- perdue par canal. La ligne découpée, le total reste au-dessus.
select scope, 'ly', pr.through, 'arc',
       count(*), sum(transactions), sum(sales), coalesce(last_channel, '(sans canal)')
from registered cross join period pr
where "window" = 'ly'
group by scope, pr.through, last_channel
union all
select scope, "window", pr.through, 'walkin',
       sum(transactions), sum(transactions), sum(sales), null
from scoped cross join period pr
where flag_walkin = 1
group by scope, "window", pr.through
union all
select ly.scope, 'ty', pr.through, 'lost',
       count(*), sum(ly.transactions), sum(ly.sales), null
from registered ly
left join registered ty
  on ty.scope = ly.scope and ty."window" = 'ty' and ty.client_skey = ly.client_skey
cross join period pr
where ly."window" = 'ly' and ty.client_skey is null
group by ly.scope, pr.through
union all
-- Les perdus, par canal de leur dernier ticket : d'où ils sont partis.
select ly.scope, 'ty', pr.through, 'lost',
       count(*), sum(ly.transactions), sum(ly.sales), coalesce(ly.last_channel, '(sans canal)')
from registered ly
left join registered ty
  on ty.scope = ly.scope and ty."window" = 'ty' and ty.client_skey = ly.client_skey
cross join period pr
where ly."window" = 'ly' and ty.client_skey is null
group by ly.scope, pr.through, ly.last_channel
"""


#: Le sell-in facturé par partenaire nommé, au mois, depuis avril de l'exercice précédent :
#: l'e-retailer, l'enseigne, l'opérateur de voyage par leur nom — pas « e-retailers ». Une ligne par
#: `period · code · label · channel · iso2` :
#:
#:     period      text     -- 'YYYY-MM', le mois de facturation
#:     code        text     -- PROFIT_CENTER_GROUP_ID, la clé sous laquelle var/partners.csv nomme
#:     label       text     -- PROFIT_CENTER_GROUP_DESC, le libellé de l'entrepôt, à défaut de nom
#:     channel     text     -- PROFIT_CENTER_GROUP_CHANNEL, le code du canal (WEBP, DPT, TRA…)
#:     iso2        text     -- le pays de facturation, jamais un marché : un e-retailer mondial y a un seul pays
#:     net_eur     number   -- le net au taux fixe, comme SELL_IN_DAILY
#:
#: Le nom commercial n'est pas dans l'entrepôt : il vient de var/partners.csv, écrit à la
#: main (`profit_centre → partner`). Ce que le fichier ne nomme pas garde le libellé du
#: centre de profit, jamais un nom deviné. Le plan n'a pas de ligne par partenaire : le
#: partenaire se lit contre l'an dernier et contre le plan de son canal, et le bloc le dit.
#: La fenêtre ouvre en avril de l'exercice précédent pour que l'exercice à date ait son an
#: dernier mois par mois, comme `PRODUCT_SALES`.
PARTNER_SELL_IN = """
select
    to_char(date_trunc('month', i.billing_date), 'YYYY-MM')  as period,
    i.profit_center_group_id                                as code,
    max(i.profit_center_group_desc)                         as label,
    i.profit_center_group_channel                           as channel,
    i.country                                               as iso2,
    round(sum(i.net_invoice_amount_eur_annual), 2)          as net_eur
from dwh.semantic_layer.v_sl_f_sellin_invoice_item i
where i.brand_caption = 'L''OCCITANE'
  and i.billing_date >= add_months(date_trunc('year', dateadd(month, -3, current_date)), -9)
  and i.billing_date <= dateadd(day, -1, current_date)
group by 1, 2, 4, 5
"""


#: La fenêtre des trois lectures supply : d'avril de l'exercice précédent au dernier mois
#: clos, exclu le mois en cours.
_SUPPLY_FROM = "add_months(date_trunc('year', dateadd(month, -3, current_date)), -9)"
_SUPPLY_TO = "date_trunc('month', current_date)"

#: Le service en boutique tel que l'entrepôt le tient : la valeur de la demande en rupture
#: sur la valeur de la demande, par mois et par unité — jamais une moyenne de taux. Une
#: ligne par `period · unit` : `rupture_eur`, `demand_eur`, `lines`. Le cockpit fait
#: `1 - rupture / demand`.
#:
#: Écrit par l'agent entrepôt le 9 septembre 2026 et vérifié sur un mois ; quatre pièges :
#: `FLAG_OSA_WITHOUT_IN_TRANSIT = 1` marque la RUPTURE, d'où la soustraction ; quatre
#: drapeaux coexistent (avec et sans en-transit, deux « plus ») sans définition arrêtée, et
#: celui-ci est le plus proche de ce que la supply publie ; le fait ne porte AUCUNE marque,
#: la lecture est toutes marques ; le pays n'est pas sur le fait, seulement l'unité, et la
#: jointure vers un pays logistique n'a pas été vérifiée — elle n'est pas ici tant qu'elle
#: ne l'est pas. Le fait est au jour × site × produit × vendeur : un mois à la fois,
#: `__FROM__` et `__TO__` posés par `source.read_osa`, sinon la lecture passe le plafond.
OSA_MONTHLY = """
select
    to_char(date_trunc('month', f.snapshot_date), 'YYYY-MM')          as period,
    f.business_unit                                                   as unit,
    round(sum(iff(lp.flag_osa_without_in_transit = 1,
                  f.awd_adjusted_irpp_amount_eur, 0)), 2)             as rupture_eur,
    round(sum(f.awd_adjusted_irpp_amount_eur), 2)                     as demand_eur,
    count(*)                                                          as lines
from dwh.semantic_layer.v_sl_f_grp_inventory_osa f
join dwh.semantic_layer.v_sl_f_grp_inventory_osa_last_product lp
  on lp.f_grp_inventory_osa_skey = f.f_grp_inventory_osa_last_product_fkey
where f.snapshot_date >= date '__FROM__'
  and f.snapshot_date <  date '__TO__'
group by 1, 2
"""

#: La prévision de demande à M-3 contre le réel, par mois et par marché de prévision, en
#: valeur, marque L'Occitane : `period · market · forecast_eur · actual_eur`. Le cockpit
#: fait le biais `(forecast - actual) / actual` — négatif, les ventes sont au-dessus de la
#: prévision, la convention du rapport — et la précision `1 - |forecast - actual| / actual`,
#: toujours sur des sommes. Écrit par l'agent entrepôt le 9 septembre 2026. Le marché de
#: prévision est un code ; son libellé vient de la dimension zone × canal, distinct par
#: zone (`label`), et le code reste à côté pour le jour où deux libellés se ressemblent.
#:
#: Réserve à garder écrite : sur le mois vérifié, ce calcul trouve la prévision AU-DESSUS
#: du réel quand le rapport de la supply dit l'inverse, et la précision dépend entièrement
#: de la maille (du simple au triple selon qu'on la calcule par produit ou par marché).
#: C'est donc la mesure du cockpit, nommée comme telle, jamais celle de la supply. Le
#: périmètre « STD » du rapport n'est pas identifié.
FORECAST_BIAS = """
with f as (
    select forecast_month_date as month_date, forecast_area_id as market,
           sum(forecast_amount_lrpp_eur) as forecast_eur
    from dwh.semantic_layer.v_sl_f_sales_forecast
    where forecast_month_date >= %(from)s and forecast_month_date < %(to)s
      and forecast_lag = -3 and brand_id = 'OC'
    group by 1, 2
),
a as (
    select actual_sales_month_date as month_date, forecast_area_id as market,
           sum(actual_amount_lrpp_eur) as actual_eur
    from dwh.semantic_layer.v_sl_f_actual_sales_forecast
    where actual_sales_month_date >= %(from)s and actual_sales_month_date < %(to)s
      and brand_id = 'OC'
    group by 1, 2
),
d as (
    select forecast_area_id as market, max(forecast_area_desc) as label
    from dwh.semantic_layer.v_sl_d_forecast_area_channel
    group by 1
)
select to_char(coalesce(f.month_date, a.month_date), 'YYYY-MM')  as period,
       coalesce(f.market, a.market)                              as market,
       d.label                                                   as label,
       round(coalesce(f.forecast_eur, 0), 2)                     as forecast_eur,
       round(coalesce(a.actual_eur, 0), 2)                       as actual_eur
from f full outer join a on f.month_date = a.month_date and f.market = a.market
left join d on d.market = coalesce(f.market, a.market)
""" % {"from": _SUPPLY_FROM, "to": _SUPPLY_TO}

#: Le sell-in livré sur commandé, en valeur, par mois de livraison demandée et par canal de
#: centre de profit : `period · channel · ordered_eur · delivered_eur · complete_eur ·
#: lines`. Le cockpit fait `delivered / ordered` et la part des lignes livrées en entier.
#: Écrit par l'agent entrepôt le 9 septembre 2026.
#:
#: Ce n'est PAS le « livré en entier » de la supply : sur le mois vérifié, cette mesure
#: rend dix points de moins que le rapport, et de moitié à presque tout selon le canal ;
#: le rapport porte sur un carnet retraité qu'on ne sait pas reproduire. La vue n'expose
#: aucune marque, la lecture est toutes marques ; les colonnes livrées sont reconstruites
#: par la vue (« proxy ») ; les lignes rejetées sont exclues ; la date est la livraison
#: demandée, et une autre date donnerait une autre valeur.
ORDER_FILL = """
select to_char(date_trunc('month', requested_delivery_date), 'YYYY-MM')     as period,
       coalesce(nullif(trim(profit_center_group_channel), ''), 'N/A')       as channel,
       round(sum(net_value_eur_annual), 2)                                  as ordered_eur,
       round(sum(delivered_net_value_eur_annual_proxy), 2)                  as delivered_eur,
       round(sum(iff(is_fully_delivered, net_value_eur_annual, 0)), 2)      as complete_eur,
       count(*)                                                             as lines
from dwh.semantic_layer.v_sl_f_sellin_order_item
where requested_delivery_date >= %(from)s and requested_delivery_date < %(to)s
  and not is_rejected
group by 1, 2
""" % {"from": _SUPPLY_FROM, "to": _SUPPLY_TO}

ALL = {
    "SALES_AND_DRIVERS": SALES_AND_DRIVERS,
    "SALES_HISTORY": SALES_HISTORY,
    "SELL_IN": SELL_IN,
    "SELL_IN_HISTORY": SELL_IN_HISTORY,
    "KPI_READINGS": KPI_READINGS,
    "MARKET_INDEX": MARKET_INDEX,
    "COMMITMENTS": COMMITMENTS,
    "FORECAST_HISTORY": FORECAST_HISTORY,
    "MONTH_TO_DATE": MONTH_TO_DATE,
    "DAILY_SALES": DAILY_SALES,
    "SELL_IN_DAILY": SELL_IN_DAILY,
    "PRODUCT_SALES": PRODUCT_SALES,
    "CLIENT_FLOW": CLIENT_FLOW,
    "PARTNER_SELL_IN": PARTNER_SELL_IN,
    "OSA_MONTHLY": OSA_MONTHLY,
    "FORECAST_BIAS": FORECAST_BIAS,
    "ORDER_FILL": ORDER_FILL,
}


def missing() -> list:
    """Names of the queries still to be written."""
    return sorted(name for name, sql in ALL.items() if not sql.strip())
