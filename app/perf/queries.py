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
        where d_stores.store_brand = 'L''OCCITANE'
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

#: The same, for the previous periods that feed the acceleration factor.
SALES_HISTORY = ""

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
join anchor a on a.period_end = s.snapshot_date
where s.segment is not null
  -- A row that is zero on both periods is a channel the entity does not use.
  -- Kept out so the screen is not padded with lines nobody can act on.
  and (s.sales_actual <> 0 or s.sales_last_year <> 0)
order by s.sales_actual desc nulls last
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
    "KPI_READINGS": KPI_READINGS,
    "MARKET_INDEX": MARKET_INDEX,
    "COMMITMENTS": COMMITMENTS,
    "FORECAST_HISTORY": FORECAST_HISTORY,
}


def missing() -> list:
    """Names of the queries still to be written."""
    return sorted(name for name, sql in ALL.items() if not sql.strip())
