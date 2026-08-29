"""The seam between the warehouse and the planning file.

Two sources meet here and nowhere else: money and drivers come from Snowflake, budget and
last year come from Adrien's planning workbook. Everything above this module trusts that
the join is honest — that a silence on one side arrives as a silence and not as a zero,
and that a disagreement between the two is reported rather than resolved by preference.

These tests are written against invented figures with a real taxonomy, per AGENTS.md.
"""

from __future__ import annotations

import pytest

from app.perf import mapping, owners
from app.perf.budget import Budget, BudgetLine
from app.perf.model import ECOMMERCE, RETAIL

PERIOD = "2026-07"


def row(market="Japan", channel=ECOMMERCE, **overrides):
    base = {
        "market": market,
        "region": "APAC",
        "channel": channel,
        "period": PERIOD,
        "sales_actual": 1_259_700.0,
        "sessions": 1_640_000.0,
        "orders": 12_800.0,
        "sessions_last_year": 1_824_000.0,
        "orders_last_year": 17_800.0,
    }
    base.update(overrides)
    return base


def budget_of(*lines):
    return Budget(list(lines))


def line(market="Japan", channel=ECOMMERCE, period=PERIOD, budget=1_861_700.0, last_year=1_622_900.0):
    return BudgetLine(
        market=market,
        region="APAC",
        segment="EBU",
        channel=channel,
        period=period,
        budget=budget,
        last_year=last_year,
    )


# --------------------------------------------------------------------- the basic join


def test_the_warehouse_supplies_the_money_and_the_file_supplies_the_commitment():
    mapped = mapping.units_from_rows([row()], budget=budget_of(line()))

    unit = mapped.units[0]

    assert unit.sales_actual == pytest.approx(1_259_700)
    assert unit.sales_budget == pytest.approx(1_861_700)
    assert unit.budget_known is True


def test_a_market_absent_from_the_planning_file_has_no_budget_rather_than_a_zero():
    """The distinction the phantom-win bug turned on."""
    mapped = mapping.units_from_rows([row(market="Taiwan")], budget=budget_of(line()))

    unit = mapped.units[0]

    assert unit.budget_known is False
    assert unit.sales_actual == pytest.approx(1_259_700)


def test_no_budget_at_all_still_produces_units():
    """Before the file is copied onto the machine, the cockpit still shows the numbers."""
    mapped = mapping.units_from_rows([row()])

    assert len(mapped.units) == 1
    assert mapped.units[0].budget_known is False


def test_a_row_without_a_market_is_dropped():
    """A total row, or a null dimension. It cannot be attributed to anyone."""
    mapped = mapping.units_from_rows([row(market=""), row()])

    assert [u.market for u in mapped.units] == ["Japan"]


def test_market_names_are_normalised_before_the_join():
    """The warehouse says USA, the planning file says United States. Same country."""
    mapped = mapping.units_from_rows(
        [row(market="USA")],
        budget=budget_of(line(market="United States")),
    )

    unit = mapped.units[0]

    assert unit.market == "United States"
    assert unit.budget_known is True


# ------------------------------------------------------------------------- the drivers


def test_ecommerce_drivers_are_built_from_sessions_and_orders():
    mapped = mapping.units_from_rows([row()], budget=budget_of(line()))

    assert mapped.units[0].actual.labels == ("Sessions", "Conversion", "AOV")


def test_last_year_carries_drivers_so_the_movement_can_be_attributed():
    """The plan has no funnel behind it; last year is the only baseline that does."""
    mapped = mapping.units_from_rows([row()], budget=budget_of(line()))

    _, label = mapped.units[0].decomposition_baseline()

    assert label == "last year"


def test_last_year_without_its_drivers_is_a_plain_number():
    """The query has not always returned them. The unit degrades; it does not lie."""
    mapped = mapping.units_from_rows(
        [row(sessions_last_year=None, orders_last_year=None)],
        budget=budget_of(line()),
    )

    unit = mapped.units[0]

    assert unit.sales_last_year == pytest.approx(1_622_900)
    assert unit.has_driver_breakdown is False
    assert unit.no_breakdown_reason


def test_a_site_reporting_no_sessions_gets_no_invented_funnel():
    mapped = mapping.units_from_rows(
        [row(sessions=None, orders=None)],
        budget=budget_of(line()),
    )

    unit = mapped.units[0]

    assert unit.actual.has_breakdown is False
    assert "not reported" in unit.no_breakdown_reason


def test_retail_conversion_is_refused_where_there_are_no_traffic_counters():
    """The CEO's own correction: outside Europe and the US the number is not real."""
    mapped = mapping.units_from_rows(
        [row(market="Japan", channel=RETAIL)],
        budget=budget_of(line(channel=RETAIL)),
    )

    unit = mapped.units[0]

    assert unit.actual.has_breakdown is False
    assert unit.no_breakdown_reason


def test_retail_in_a_counted_market_says_nothing_about_counters():
    mapped = mapping.units_from_rows(
        [row(market="France", channel=RETAIL)],
        budget=budget_of(line(market="France", channel=RETAIL)),
    )

    assert "traffic counter" not in mapped.units[0].no_breakdown_reason.lower()


# ---------------------------------------------------------------- when sources disagree


def test_a_disagreement_between_the_two_sources_is_reported():
    """Not resolved silently. Someone has to know the two are drifting apart."""
    mapped = mapping.units_from_rows(
        [row(sales_budget=1_500_000.0)],
        budget=budget_of(line(budget=1_861_700.0)),
    )

    assert len(mapped.conflicts) == 1
    assert "planning file" in mapped.conflicts[0].message


def test_the_file_wins_the_disagreement():
    """Stated by the CEO: the Excel targets are more reliable than Snowflake's."""
    mapped = mapping.units_from_rows(
        [row(sales_budget=1_500_000.0)],
        budget=budget_of(line(budget=1_861_700.0)),
    )

    assert mapped.units[0].sales_budget == pytest.approx(1_861_700)


def test_a_rounding_difference_is_not_a_conflict():
    mapped = mapping.units_from_rows(
        [row(sales_budget=1_861_699.0)],
        budget=budget_of(line(budget=1_861_700.0)),
    )

    assert mapped.conflicts == []


def test_the_warehouse_budget_is_used_when_the_file_is_silent():
    """A fallback, not a preference: better than no comparison at all."""
    mapped = mapping.units_from_rows(
        [row(market="Taiwan", sales_budget=400_000.0)],
        budget=budget_of(line()),
    )

    unit = mapped.units[0]

    assert unit.budget_known is True
    assert unit.sales_budget == pytest.approx(400_000)


# ----------------------------------------------------------------------------- owners


def test_an_unknown_market_gets_no_invented_owner(monkeypatch):
    """Putting a real person's name in front of a question they do not own is worse
    than leaving the line blank."""
    monkeypatch.setattr(owners, "current", lambda: owners.EMPTY)

    owner = owners.owner_for("Nowhereland")

    assert owner.name == ""
    assert owners.is_named(owner) is False


def test_the_markets_left_out_are_countable(monkeypatch):
    """The screen says how many were left out. It never says who they are."""
    monkeypatch.setattr(owners, "current", lambda: owners.EMPTY)

    mapped = mapping.units_from_rows(
        [row(market="Japan"), row(market="Taiwan")],
        budget=budget_of(line()),
    )

    assert mapped.markets_without_owner == ["Japan", "Taiwan"]


def test_a_named_market_carries_its_owner_through_the_join(monkeypatch):
    directory = owners.Directory(
        [
            owners.Entry(
                name="A. Manager",
                role="Managing Director",
                bu="Japon",
                zone="Japon",
                level=owners.COUNTRY_GM,
                markets=["Japan"],
            )
        ]
    )
    monkeypatch.setattr(owners, "current", lambda: directory)

    mapped = mapping.units_from_rows([row()], budget=budget_of(line()))

    assert mapped.units[0].owner.name == "A. Manager"
    assert mapped.markets_without_owner == []


# ---------------------------------------------------------------------------- dataset


def test_a_dataset_is_built_end_to_end():
    dataset = mapping.dataset_from_rows(
        [row(market="Japan"), row(market="Taiwan")],
        budget=budget_of(line()),
        period_label="Sales MTD",
        as_of="2026-07-31",
    )

    assert dataset.period_label == "Sales MTD"
    assert dataset.sales_actual == pytest.approx(2_519_400)
    # Taiwan has no plan, so it is outside the company's variance to plan.
    assert dataset.sales_budget == pytest.approx(1_861_700)
    assert [u.market for u in dataset.unbudgeted] == ["Taiwan"]


# ------------------------------------------------- what the query says about the funnel
#
# The query now establishes why a funnel is unreadable instead of leaving a blank for this
# module to interpret. Four states with four different remedies, and collapsing them into
# one word for "missing" sends the wrong person after the wrong thing.


def test_the_reason_established_by_the_query_is_the_one_shown():
    """It read the warehouse. This module only ever inferred from shape."""
    mapped = mapping.units_from_rows(
        [row(funnel_status="orders_not_tracked", orders=None)],
        budget=budget_of(line()),
    )

    assert "never the orders" in mapped.units[0].no_breakdown_reason


def test_tracking_lost_is_not_the_same_as_never_tracked():
    """One is a tag to install, the other is a thing that broke on a date and can be
    found. The same blank on screen, an entirely different next step."""
    never = mapping.units_from_rows(
        [row(funnel_status="orders_not_tracked", orders=None)], budget=budget_of(line())
    ).units[0]
    lost = mapping.units_from_rows(
        [row(funnel_status="order_tracking_lost", orders=None)], budget=budget_of(line())
    ).units[0]

    assert never.no_breakdown_reason != lost.no_breakdown_reason
    assert "stopped" in lost.no_breakdown_reason


def test_a_market_selling_on_platforms_says_the_revenue_is_real():
    """The correction that mattered: no own site does not mean no sell-out. A shopper
    buying on a marketplace store is still a sale to the end customer, and calling that
    revenue "invoiced to a reseller" would have written off a real channel."""
    mapped = mapping.units_from_rows(
        [row(market="China", funnel_status="no_analytics_site", sessions=None, orders=None)],
        budget=budget_of(line(market="China")),
    )

    reason = mapped.units[0].no_breakdown_reason

    assert "revenue is counted" in reason
    assert "none to repair" in reason


def test_the_status_survives_onto_the_unit():
    mapped = mapping.units_from_rows(
        [row(funnel_status="measured")], budget=budget_of(line())
    )

    assert mapped.units[0].funnel_status == "measured"


def test_a_row_without_a_status_still_maps():
    """The column arrived after the first real screens did. Its absence must break
    neither a cached read nor an older query."""
    mapped = mapping.units_from_rows([row()], budget=budget_of(line()))

    assert mapped.units[0].funnel_status == ""
    assert mapped.units[0].actual.has_breakdown is True


# ---------------------------------------------------------------- more than one channel
#
# The query filtered to e-commerce with a single line. Lifting that filter turns one row
# per market into one per market and channel, and everything downstream has to survive it.


def test_a_warehouse_channel_name_lands_on_the_cockpit_vocabulary():
    """The warehouse shouts and hyphenates, the planning file abbreviates, the model has
    its own two words. A channel landing on the wrong name joins to the wrong budget."""
    assert mapping.normalise_channel("E-COMMERCE") == ECOMMERCE
    assert mapping.normalise_channel("Retail") == RETAIL


def test_an_unknown_channel_keeps_its_own_name():
    """Never guessed into a known one by resemblance: a channel mistaken for retail would
    be handed a footfall funnel it never had."""
    assert mapping.normalise_channel("TRAVEL RETAIL") == "travel retail"
    assert mapping.normalise_channel("Wholesale") == "wholesale"


def test_both_channels_of_one_market_become_two_units():
    mapped = mapping.units_from_rows(
        [
            row(market="France", channel="E-COMMERCE"),
            row(market="France", channel="RETAIL"),
        ],
        budget=budget_of(
            line(market="France", channel=ECOMMERCE),
            line(market="France", channel=RETAIL, budget=4_000_000.0),
        ),
    )

    assert len(mapped.units) == 2
    assert {u.key for u in mapped.units} == {"france-ecommerce", "france-retail"}


def test_each_channel_joins_to_its_own_budget_line():
    """The failure this guards is silent: a retail unit measured against the e-commerce
    plan looks like a catastrophe and is arithmetic."""
    mapped = mapping.units_from_rows(
        [row(market="France", channel="RETAIL", sales_actual=3_800_000.0)],
        budget=budget_of(
            line(market="France", channel=ECOMMERCE, budget=1_000_000.0),
            line(market="France", channel=RETAIL, budget=4_000_000.0),
        ),
    )

    assert mapped.units[0].sales_budget == pytest.approx(4_000_000.0)


def test_a_channel_the_plan_does_not_cover_is_unbudgeted_rather_than_zeroed():
    """An unmatched channel must degrade the way a missing market does — excluded from
    the ranking, and named in what the screen says it left out."""
    mapped = mapping.units_from_rows(
        [row(market="France", channel="TRAVEL RETAIL")],
        budget=budget_of(line(market="France", channel=ECOMMERCE)),
    )

    assert mapped.units[0].budget_known is False


def test_a_retail_unit_carries_no_invented_funnel():
    """Sessions and orders belong to the web. Until footfall arrives, a store unit has a
    real gap and no measured cause — which the screen already knows how to say."""
    mapped = mapping.units_from_rows(
        [row(market="France", channel="RETAIL")],
        budget=budget_of(line(market="France", channel=RETAIL)),
    )

    assert mapped.units[0].actual.has_breakdown is False


def test_the_channel_reaches_the_label():
    mapped = mapping.units_from_rows(
        [row(market="France", channel="RETAIL")],
        budget=budget_of(line(market="France", channel=RETAIL)),
    )

    assert mapped.units[0].label == "France Retail"


# --------------------------------------------- several store formats, one channel
#
# The warehouse reports the shape of the point of sale — mall store, street store, shop in
# shop, outlet, road show, corner. The plan commits to one figure for all of them. So the
# formats fold, and the fold is the most dangerous line of code in this module.


def test_every_store_format_lands_on_retail():
    """Keeping them apart would read as finer detail and behave as a catastrophe: each
    format would find no budget line, be marked unbudgeted, and drop out of the ranking —
    taking nearly half the plan off the screen while every number stayed true."""
    for shape in ("MALL STORE", "STREET STORE", "SHOP IN SHOP", "OUTLET",
                  "ROAD SHOW", "CORNER", "SPECIAL STORES"):
        assert mapping.normalise_channel(shape) == RETAIL, shape


def test_a_marketplace_is_its_own_channel_not_e_commerce():
    """The plan commits to it separately, and it has no sessions to compare."""
    assert mapping.normalise_channel("MARKETPLACE") == "marketplace"


def test_the_formats_of_one_market_become_a_single_unit():
    mapped = mapping.units_from_rows(
        [
            row(market="France", channel="MALL STORE", sales_actual=2_000_000.0),
            row(market="France", channel="STREET STORE", sales_actual=1_500_000.0),
            row(market="France", channel="OUTLET", sales_actual=500_000.0),
        ],
        budget=budget_of(line(market="France", channel=RETAIL, budget=4_500_000.0)),
    )

    assert len(mapped.units) == 1
    assert mapped.units[0].sales_actual == pytest.approx(4_000_000.0)


def test_a_folded_channel_carries_its_budget_once():
    """The failure this exists to prevent: three formats, three units, and the same
    commitment counted three times — a company shown far behind a plan it is meeting."""
    dataset = mapping.dataset_from_rows(
        [
            row(market="France", channel="MALL STORE", sales_actual=2_000_000.0),
            row(market="France", channel="STREET STORE", sales_actual=1_500_000.0),
            row(market="France", channel="OUTLET", sales_actual=500_000.0),
        ],
        budget=budget_of(line(market="France", channel=RETAIL, budget=4_500_000.0)),
    )

    assert dataset.sales_budget == pytest.approx(4_500_000.0)


def test_folding_keeps_an_absence_absent():
    """Summing nothing with nothing must not produce a zero, or a channel nobody measured
    becomes a channel measured at nothing."""
    folded = mapping.fold_rows([
        row(market="France", channel="MALL STORE", sessions=None, orders=None),
        row(market="France", channel="OUTLET", sessions=None, orders=None),
    ])

    assert folded[0]["sessions"] is None
    assert folded[0]["orders"] is None


def test_a_channel_that_measured_anything_counts_as_measured():
    folded = mapping.fold_rows([
        row(market="France", channel="MALL STORE", funnel_status="not_a_web_channel"),
        row(market="France", channel="OUTLET", funnel_status="measured"),
    ])

    assert folded[0]["funnel_status"] == "measured"


def test_the_most_actionable_fault_survives_the_fold():
    """"Tracking stopped on a date" can be found. "No site" cannot. When neither channel
    measured anything, the one worth chasing is the one that names a date."""
    folded = mapping.fold_rows([
        row(market="France", channel="MALL STORE", funnel_status="no_analytics_site"),
        row(market="France", channel="OUTLET", funnel_status="order_tracking_lost"),
    ])

    assert folded[0]["funnel_status"] == "order_tracking_lost"


def test_different_channels_never_fold_together():
    mapped = mapping.units_from_rows(
        [
            row(market="France", channel="MALL STORE"),
            row(market="France", channel="E-COMMERCE"),
            row(market="France", channel="MARKETPLACE"),
        ],
        budget=budget_of(
            line(market="France", channel=RETAIL),
            line(market="France", channel=ECOMMERCE),
        ),
    )

    assert len(mapped.units) == 3


def test_different_markets_never_fold_together():
    mapped = mapping.units_from_rows(
        [
            row(market="France", channel="MALL STORE"),
            row(market="Japan", channel="STREET STORE"),
        ],
        budget=budget_of(line(market="France", channel=RETAIL)),
    )

    assert {u.market for u in mapped.units} == {"France", "Japan"}


def test_a_store_is_not_told_its_web_tracking_broke():
    """A shop has no web funnel to lose. Saying otherwise sends someone to repair
    something that was never there."""
    mapped = mapping.units_from_rows(
        [row(market="France", channel="MALL STORE", funnel_status="not_a_web_channel",
             sessions=None, orders=None)],
        budget=budget_of(line(market="France", channel=RETAIL)),
    )

    assert "orders" not in mapped.units[0].no_breakdown_reason.lower()


# ---------------------------------------------------------------------------- sell-in
#
# Roughly two fifths of the plan, invisible to every sell-out source by construction: the
# revenue is recognised when the Maison ships, not when a shopper buys. It arrives from
# the management consolidation with a segment label rather than a channel, because a
# segment is what the plan commits to.


def sell_in(entity="M_024", market="Japan", segment="DIS - Distributors", **overrides):
    base = {
        "entity": entity,
        "market": market,
        "region": "APAC",
        "segment": segment,
        "period": PERIOD,
        "sales_actual": 480_000.0,
        "sales_last_year": 430_000.0,
    }
    base.update(overrides)
    return base


def test_a_segment_label_becomes_the_channel_the_plan_commits_to():
    translated = mapping.sell_in_rows([sell_in()])

    assert translated[0]["channel"] == "dis"


def test_a_sell_in_row_carries_no_funnel_and_never_pretends_to():
    translated = mapping.sell_in_rows([sell_in()])

    assert translated[0]["sessions"] is None
    assert translated[0]["orders"] is None
    assert translated[0]["funnel_status"] == mapping.NOT_A_WEB_CHANNEL


def test_a_sell_in_unit_joins_to_its_own_budget_line():
    """The failure this guards is silent and total: with no matching line every sell-in
    market is unbudgeted, drops out of the ranking, and two fifths of the plan goes
    missing while every figure on screen stays true."""
    mapped = mapping.units_from_rows(
        mapping.sell_in_rows([sell_in()]),
        budget=budget_of(
            line(market="Japan", channel="dis", budget=500_000.0),
            line(market="Japan", channel=ECOMMERCE, budget=1_861_700.0),
        ),
    )

    unit = mapped.units[0]

    assert unit.budget_known is True
    assert unit.sales_budget == pytest.approx(500_000.0)


def test_a_sell_in_unit_says_why_it_has_no_cause():
    """Not "the tracking is broken" — there was never anything to track. What happens
    after the invoice is a different measurement problem, and naming it as a funnel gap
    would send someone to fix a tag that does not exist."""
    mapped = mapping.units_from_rows(
        mapping.sell_in_rows([sell_in()]),
        budget=budget_of(line(market="Japan", channel="dis")),
    )

    unit = mapped.units[0]

    # The fact is carried by two sentences now, not one: the basis note says what the
    # figure counts, and this says why no driver table follows it. They used to open on
    # the same clause, which read as padding — and padding on a card teaches a reader to
    # skim the next one.
    assert "none missing" in unit.no_breakdown_reason
    assert "invoiced to a partner" in unit.basis_note
    assert "not measured here" in unit.basis_note


def test_a_row_with_no_segment_is_dropped():
    assert mapping.sell_in_rows([sell_in(segment="")]) == []


def test_sell_in_and_sell_out_live_side_by_side():
    """Disjoint by construction — different channels — so the group total is a sum, not a
    risk of counting the same euro twice."""
    dataset = mapping.dataset_from_rows(
        [row(market="Japan", channel="E-COMMERCE", sales_actual=1_259_700.0)]
        + mapping.sell_in_rows([sell_in(sales_actual=480_000.0)]),
        budget=budget_of(
            line(market="Japan", channel=ECOMMERCE, budget=1_861_700.0),
            line(market="Japan", channel="dis", budget=500_000.0),
        ),
    )

    assert len(dataset.units) == 2
    assert dataset.sales_actual == pytest.approx(1_739_700.0)
    assert dataset.sales_budget == pytest.approx(2_361_700.0)


def test_a_planning_code_never_becomes_a_market_label():
    """"China Webp" and "Hong Kong Dis" put a spreadsheet abbreviation where a reader
    expects the name of a business."""
    mapped = mapping.units_from_rows(
        mapping.sell_in_rows([
            {"entity": "M_007", "market": "China", "region": "CHINA",
             "segment": "WEBP - Web Partners", "period": PERIOD,
             "sales_actual": 1_000_000.0, "sales_last_year": 900_000.0},
        ]),
        budget=budget_of(line(market="China", channel="webp")),
    )

    assert mapped.units[0].label == "China E-retailers"


def test_a_sell_in_unit_knows_it_is_sell_in():
    mapped = mapping.units_from_rows(
        mapping.sell_in_rows([
            {"entity": "M_024", "market": "Japan", "region": "APAC",
             "segment": "DIS - Distributors", "period": PERIOD,
             "sales_actual": 480_000.0, "sales_last_year": 430_000.0},
        ]),
        budget=budget_of(line(market="Japan", channel="dis")),
    )

    assert mapped.units[0].is_sell_in is True


def test_an_own_channel_is_not_sell_in():
    mapped = mapping.units_from_rows([row()], budget=budget_of(line()))

    assert mapped.units[0].is_sell_in is False


def test_every_channel_the_screen_names_says_what_it_is():
    """A name the reader cannot decode is the same defect as a warehouse code printed in
    prose. "E-retailers" and "E-commerce" look like two shades of online selling; they are
    a partner who buys our stock and our own site, recognised at different moments and
    answered by different people.
    """
    from app.perf.mapping import CHANNEL_MEANING, CHANNEL_NAMES

    assert set(CHANNEL_NAMES) <= set(CHANNEL_MEANING)
    for channel, meaning in CHANNEL_MEANING.items():
        assert meaning.endswith("."), channel
        assert len(meaning) > 30, channel


def test_the_three_online_channels_are_told_apart():
    """The confusion this table exists to end: the platform most readers picture for China
    is not either of the two channels whose names sound like it."""
    from app.perf.mapping import CHANNEL_MEANING

    assert "brand.com" in CHANNEL_MEANING["ecommerce"]
    # Tmall we operate: sold to the shopper. JD, Douyin and VIP buy our stock: shipped.
    # The two sit under names that sound alike and fall on opposite sides of the invoice,
    # which is the confusion this table exists to end.
    assert "Tmall" in CHANNEL_MEANING["marketplace"]
    assert "JD" in CHANNEL_MEANING["webp"]
    assert "Not Tmall" in CHANNEL_MEANING["webp"]
    assert "JD" not in CHANNEL_MEANING["marketplace"]
    # And each says on which side of the invoice its euros are counted.
    assert "shipper" not in CHANNEL_MEANING["webp"]
    assert "when we ship" in CHANNEL_MEANING["webp"]
