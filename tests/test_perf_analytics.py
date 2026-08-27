"""Deterministic analytics engine (brief §21A, §26, §27).

These tests exist because the cockpit's only asset is trust in its numbers. A decomposition
that quietly loses euros, or a ranking whose factors cannot be checked by hand, would be
worse than no cockpit: it would be a confident one.

Written in English, like the rest of the cockpit — see AGENTS.md on the two languages
living in this repository during the pivot.
"""

from __future__ import annotations

import pytest

from app.perf import analytics
from app.perf.model import ECOMMERCE, RETAIL, BusinessUnit, Dataset, Drivers, Owner

OWNER = Owner("Test Owner", "Managing Director", "Testland")


def ecom(sales, conversion=0.02, aov=60.0):
    return Drivers(("Sessions", "Conversion", "AOV"), (sales / (conversion * aov), conversion, aov))


def unit(key="test", actual=None, budget=None, last_year=None, **overrides):
    base = {
        "key": key,
        "label": key.title(),
        "market": key.title(),
        "region": "Test",
        "channel": ECOMMERCE,
        "owner": OWNER,
        "actual": actual if actual is not None else ecom(900_000),
        "budget": budget if budget is not None else ecom(1_000_000),
        "last_year": last_year if last_year is not None else ecom(950_000),
        "forecast_sales": 1_000_000,
    }
    base.update(overrides)
    return BusinessUnit(**base)


# --------------------------------------------------------------------- decomposition


def test_sales_are_the_product_of_their_drivers():
    """A sales figure that its own drivers do not support would discredit every diagnosis."""
    drivers = Drivers(("Sessions", "Conversion", "AOV"), (1_000_000, 0.02, 60.0))

    assert drivers.sales == pytest.approx(1_200_000)


def test_contributions_sum_exactly_to_the_gap():
    """No unexplained residual, ever. The chained decomposition is exact by construction."""
    actual = Drivers(("Sessions", "Conversion", "AOV"), (980_000, 0.0176, 61.0))
    budget = Drivers(("Sessions", "Conversion", "AOV"), (1_000_000, 0.0210, 62.0))

    items = analytics.contributions(actual, budget)

    assert sum(item.impact for item in items) == pytest.approx(actual.sales - budget.sales)


def test_contributions_name_the_driver_that_moved():
    actual = Drivers(("Sessions", "Conversion", "AOV"), (1_000_000, 0.0150, 60.0))
    budget = Drivers(("Sessions", "Conversion", "AOV"), (1_000_000, 0.0200, 60.0))

    assert analytics.largest_driver(analytics.contributions(actual, budget)).label == "Conversion"


def test_units_with_different_drivers_cannot_be_compared():
    """Comparing an e-commerce unit with a retail one would produce a plausible number
    for a question nobody asked."""
    with pytest.raises(ValueError):
        analytics.contributions(
            Drivers(("Sessions", "Conversion", "AOV"), (1, 1, 1)),
            Drivers(("Traffic", "Conversion", "UPT", "ASP"), (1, 1, 1, 1)),
        )


# --------------------------------------------------------------------- confidence


def test_confidence_is_high_when_one_driver_explains_the_gap():
    actual = Drivers(("Sessions", "Conversion", "AOV"), (1_000_000, 0.0150, 60.0))
    budget = Drivers(("Sessions", "Conversion", "AOV"), (1_000_000, 0.0200, 60.0))
    items = analytics.contributions(actual, budget)

    assert analytics.confidence_of(items, actual.sales - budget.sales) == analytics.HIGH


def test_confidence_is_low_when_the_gap_is_spread_across_drivers():
    """A gap spread evenly is a gap we cannot yet explain, and the screen must say so
    rather than pick a favourite driver."""
    actual = Drivers(("Sessions", "Conversion", "AOV"), (960_000, 0.0192, 57.6))
    budget = Drivers(("Sessions", "Conversion", "AOV"), (1_000_000, 0.0200, 60.0))
    items = analytics.contributions(actual, budget)

    assert analytics.confidence_of(items, actual.sales - budget.sales) == analytics.LOW


# --------------------------------------------------------------------- ranking


def test_priority_exposes_every_factor():
    """Brief §26: the ranking must be inspectable. An opaque score would not be trusted,
    and an untrusted ranking is not a ranking."""
    priority = analytics.priority_of(unit(months_below_budget=3, gap_history=(-50_000, -100_000)))

    labels = [label for label, _ in priority.factors]
    assert labels == ["€ gap", "persistence", "acceleration", "strategic weight", "confidence"]
    assert priority.reasons
    assert all(reason.strip() for reason in priority.reasons)


def test_a_persistent_gap_outranks_a_one_off_gap_of_the_same_size():
    once = unit(key="once", months_below_budget=1)
    persistent = unit(key="persistent", months_below_budget=4)

    assert analytics.priority_of(persistent).score > analytics.priority_of(once).score


def test_a_widening_gap_outranks_a_closing_gap_of_the_same_size():
    widening = unit(key="widening", gap_history=(-50_000, -100_000))
    closing = unit(key="closing", gap_history=(-100_000, -50_000))

    assert analytics.priority_of(widening).score > analytics.priority_of(closing).score


# --------------------------------------------------------------------- fires


def dataset_of(*units):
    return Dataset(period_label="Sales MTD", as_of="2026-08-26", units=units)


def test_a_small_gap_never_reaches_the_screen():
    """Brief §3.1: -30% on a small market can matter less than -3% on a large one. The
    floor is in euros for exactly that reason."""
    small = unit(key="small", actual=ecom(70_000), budget=ecom(100_000))

    assert analytics.fires(dataset_of(small)) == []


def test_an_aggregate_is_never_a_fire():
    """There is nobody to challenge about "Rest of World", and letting it take a slot
    would push out a market someone can actually be asked about."""
    rollup = unit(key="row", actual=ecom(9_000_000), budget=ecom(10_000_000), is_aggregate=True)

    assert analytics.fires(dataset_of(rollup)) == []
    # It still belongs in the group total.
    assert dataset_of(rollup).sales_actual == pytest.approx(9_000_000)


def test_fires_are_capped_so_the_screen_stays_readable():
    units = [
        unit(key="m%d" % i, actual=ecom(1_000_000 - i * 1000), budget=ecom(2_000_000))
        for i in range(9)
    ]

    assert len(analytics.fires(dataset_of(*units))) == 5


def test_fires_are_ordered_by_money_at_stake():
    big = unit(key="big", actual=ecom(8_000_000), budget=ecom(10_000_000))
    small = unit(key="small", actual=ecom(400_000), budget=ecom(1_000_000))

    assert [f.unit.key for f in analytics.fires(dataset_of(small, big))] == ["big", "small"]


def test_a_plan_aimed_at_the_wrong_driver_is_flagged_and_asked_about():
    """The sharpest thing this product can say: the numbers blame conversion, the plan
    targets acquisition."""
    misaligned = unit(
        key="japan",
        actual=Drivers(("Sessions", "Conversion", "AOV"), (1_000_000, 0.0150, 60.0)),
        budget=Drivers(("Sessions", "Conversion", "AOV"), (1_000_000, 0.0200, 60.0)),
        action_focus="Sessions",
    )

    fire = analytics.fires(dataset_of(misaligned))[0]

    assert fire.misaligned_plan
    assert "sessions" in fire.question.lower()
    assert "conversion" in fire.question.lower()


def test_a_driver_that_overshoots_the_gap_is_phrased_in_euros_not_percent():
    """When traffic offsets a conversion collapse the share exceeds 100%. Arithmetically
    right, and useless to read."""
    offset = unit(
        key="france",
        actual=Drivers(("Sessions", "Conversion", "AOV"), (1_200_000, 0.0150, 60.0)),
        budget=Drivers(("Sessions", "Conversion", "AOV"), (1_000_000, 0.0200, 60.0)),
    )

    diagnosis = analytics.fires(dataset_of(offset))[0].diagnosis

    assert "%" not in diagnosis
    assert "offset" in diagnosis


# --------------------------------------------------------- explanation challenge


def test_a_difficult_market_explanation_is_tested_not_repeated():
    """Brief §20: never accept "market conditions" without checking what it explains."""
    item = unit(
        key="japan",
        actual=ecom(820_000),
        last_year=ecom(1_000_000),
        market_index_pct=-0.04,
        management_explanation="Sales are down because the market is difficult.",
    )

    check = analytics.check_explanation(item)

    assert check.verdict == analytics.ExplanationCheck.UNSUPPORTED
    assert "unexplained" in check.evidence


def test_without_a_benchmark_the_verdict_is_insufficient_evidence_not_a_guess():
    item = unit(key="x", management_explanation="Consumer sentiment is weak.")

    assert analytics.check_explanation(item).verdict == analytics.ExplanationCheck.INSUFFICIENT


def test_no_explanation_produces_no_verdict():
    assert analytics.check_explanation(unit(key="x")) is None


# --------------------------------------------------------------------- opportunities


def test_an_opportunity_shows_its_counterfactual():
    """Brief §27: always display calculation, assumption, upside and confidence."""
    item = unit(
        key="france",
        actual=Drivers(("Sessions", "Conversion", "AOV"), (1_200_000, 0.0180, 60.0)),
        budget=Drivers(("Sessions", "Conversion", "AOV"), (1_200_000, 0.0200, 60.0)),
        last_year=Drivers(("Sessions", "Conversion", "AOV"), (1_100_000, 0.0210, 60.0)),
    )

    opportunity = analytics.opportunity_of(item)

    assert opportunity.amount > 0
    assert opportunity.assumption.strip()
    assert opportunity.calculation.strip()
    assert opportunity.confidence in (analytics.HIGH, analytics.MEDIUM, analytics.LOW)


def test_no_opportunity_when_conversion_already_beats_last_year():
    """Recovering something that has not been lost is a wish, not an opportunity."""
    item = unit(
        key="x",
        actual=Drivers(("Sessions", "Conversion", "AOV"), (1_000_000, 0.0220, 60.0)),
        last_year=Drivers(("Sessions", "Conversion", "AOV"), (1_000_000, 0.0200, 60.0)),
    )

    assert analytics.opportunity_of(item) is None


def test_opportunity_confidence_drops_when_the_volume_behind_it_is_shrinking():
    """The counterfactual then assumes something the business is not currently doing."""
    shrinking = unit(
        key="x",
        actual=Drivers(("Sessions", "Conversion", "AOV"), (800_000, 0.0180, 60.0)),
        last_year=Drivers(("Sessions", "Conversion", "AOV"), (1_100_000, 0.0230, 60.0)),
    )

    assert analytics.opportunity_of(shrinking).confidence == analytics.MEDIUM


# --------------------------------------------------------------------- wins


def test_a_win_must_beat_both_plan_and_last_year():
    """Beating a plan that was cut is not a win."""
    against_cut_plan = unit(
        key="x", actual=ecom(1_100_000), budget=ecom(1_000_000), last_year=ecom(1_400_000)
    )

    assert analytics.wins(dataset_of(against_cut_plan)) == []


def test_a_real_outperformance_is_surfaced():
    strong = unit(
        key="us", actual=ecom(5_000_000), budget=ecom(4_390_000), last_year=ecom(4_240_000)
    )

    found = analytics.wins(dataset_of(strong))

    assert len(found) == 1
    assert found[0].gap > 0


# --------------------------------------------------------------------- people


def test_each_owner_appears_once_however_many_fires_they_own():
    a = unit(key="a", actual=ecom(600_000), budget=ecom(2_000_000))
    b = unit(key="b", actual=ecom(700_000), budget=ecom(2_000_000))

    pushes = analytics.people_to_push(analytics.fires(dataset_of(a, b)))

    assert len(pushes) == 1
    assert pushes[0].owner.name == OWNER.name


def test_the_reason_to_push_someone_is_always_a_number():
    """Brief §10: this ranks business areas, never people."""
    item = unit(key="a", actual=ecom(600_000), budget=ecom(2_000_000))

    push = analytics.people_to_push(analytics.fires(dataset_of(item)))[0]

    assert "€" in push.reason
    assert push.question.strip()


# ------------------------------------------------- channels without driver data


def sales_only_unit(key, actual, budget, last_year=None):
    """A channel that reports sales but neither traffic nor conversion.

    Not a hypothetical: an online channel may report neither, while the stores next to it
    report both. The cockpit has to hold both kinds at once.
    """
    return unit(
        key=key,
        actual=Drivers.sales_only(actual),
        budget=Drivers.sales_only(budget),
        last_year=Drivers.sales_only(last_year if last_year is not None else budget),
    )


def test_a_channel_without_drivers_still_shows_its_gap():
    """It belongs in the total and in the ranking; only its cause is unavailable."""
    opaque = sales_only_unit("brandcom", 8_600_000, 9_400_000)

    found = analytics.fires(dataset_of(opaque))

    assert len(found) == 1
    assert found[0].gap == pytest.approx(-800_000)


def test_a_channel_without_drivers_says_so_instead_of_inventing_a_cause():
    fire = analytics.fires(dataset_of(sales_only_unit("brandcom", 8_600_000, 9_400_000)))[0]

    assert not fire.has_breakdown
    assert fire.contributions == []
    assert "cannot be attributed" in fire.diagnosis


def test_the_question_for_an_unmeasured_channel_asks_for_the_measurement():
    """Asking what will move a driver nobody measures would be asking for a guess."""
    fire = analytics.fires(dataset_of(sales_only_unit("brandcom", 8_600_000, 9_400_000)))[0]

    assert "cannot see why" in fire.question


def test_sales_only_drivers_still_total_correctly():
    assert Drivers.sales_only(1_234_567.0).sales == pytest.approx(1_234_567.0)
    assert not Drivers.sales_only(1.0).has_breakdown


# ------------------------------------------- driver availability by market


def test_retail_conversion_is_refused_where_footfall_is_not_counted():
    """A wrong number is acted upon; an absent one is asked about.

    The factory refuses whatever it is handed, so a mapping written months from now
    cannot reintroduce a conversion rate from a market that has no counters.
    """
    from app.perf.model import retail_drivers

    with_counters = retail_drivers("France", 17_600_000, 0.1175, 2.10, 47.50)
    without = retail_drivers("Japan", 8_900_000, 0.1400, 2.00, 50.00)

    assert with_counters.has_breakdown
    assert not without.has_breakdown
    # The sales figure survives intact; only the attribution is withheld.
    assert without.sales == pytest.approx(8_900_000)


def test_retail_drivers_fall_back_when_a_component_is_missing():
    from app.perf.model import retail_drivers

    assert not retail_drivers("France", 1_000_000, None, 2.0, 40.0).has_breakdown


def test_ecommerce_drivers_close_the_identity_exactly():
    """Sessions and orders come from analytics, money from the sales system. Deriving
    value-per-order from the same sales figure is what keeps the product exact."""
    from app.perf.model import ecommerce_drivers

    drivers = ecommerce_drivers(sales=5_400_000, sessions=4_967_000, orders=62_197)

    assert drivers.sales == pytest.approx(5_400_000)
    assert drivers.value_of("Conversion") == pytest.approx(62_197 / 4_967_000)


def test_ecommerce_without_sessions_degrades_rather_than_divides_by_zero():
    from app.perf.model import ecommerce_drivers

    assert not ecommerce_drivers(sales=1_000_000, sessions=0, orders=0).has_breakdown


def test_the_screen_says_which_kind_of_blindness_it_is():
    """"We do not count footfall here" and "this channel reports sales only" are
    different facts, and the second is not a reason to go looking for the first."""
    from app.perf.model import NO_COUNTER_REASON, retail_drivers

    unmeasured = unit(
        key="japan-retail",
        actual=retail_drivers("Japan", 8_900_000),
        budget=retail_drivers("Japan", 9_600_000),
        last_year=retail_drivers("Japan", 9_250_000),
        no_breakdown_reason=NO_COUNTER_REASON,
    )

    fire = analytics.fires(dataset_of(unmeasured))[0]

    assert "footfall is not counted" in fire.diagnosis
    assert "cannot see why" in fire.question


# --------------------------------------------------------- broken feeds vs real gaps


def test_a_market_at_zero_against_a_real_history_is_treated_as_a_broken_feed():
    """Observed in the real data: a market reporting nothing this month against a
    non-zero last year, with sessions still arriving. A collapse would be visible in the
    traffic too."""
    silent = unit(
        key="finland",
        actual=Drivers.sales_only(0.0),
        budget=Drivers.sales_only(9_000.0),
        last_year=Drivers.sales_only(8_361.0),
        sessions=4_712.0,
        orders=0.0,
    )

    flagged = analytics.suspects(dataset_of(silent))

    assert len(flagged) == 1
    assert flagged[0].code == "zero_against_history"


def test_traffic_without_orders_is_a_tracking_gap_not_a_conversion_problem():
    """Also observed: hundreds of thousands of sessions, no recorded orders, and real
    revenue. The business is there; the transactional tracking is not."""
    untracked = unit(
        key="hongkong",
        actual=Drivers.sales_only(51_000.0),
        budget=Drivers.sales_only(1_200_000.0),
        last_year=Drivers.sales_only(900_000.0),
        sessions=686_994.0,
        orders=0.0,
    )

    flagged = analytics.suspects(dataset_of(untracked))

    assert len(flagged) == 1
    assert flagged[0].code == "traffic_without_orders"


def test_a_broken_feed_never_competes_for_attention_with_a_real_gap():
    """The whole point. A data incident at the top of the list teaches a CEO to stop
    reading the list, and then the real gaps go unread too."""
    broken = unit(
        key="broken",
        actual=Drivers.sales_only(0.0),
        budget=Drivers.sales_only(20_000_000.0),
        last_year=Drivers.sales_only(19_000_000.0),
    )
    real = unit(key="real", actual=ecom(8_600_000), budget=ecom(9_400_000))

    ranked = analytics.fires(dataset_of(broken, real))

    assert [f.unit.key for f in ranked] == ["real"]


def test_a_genuine_zero_with_no_history_is_not_flagged():
    """A market that has never sold anything is not a broken feed."""
    new_market = unit(
        key="new",
        actual=Drivers.sales_only(0.0),
        budget=Drivers.sales_only(0.0),
        last_year=Drivers.sales_only(0.0),
    )

    assert analytics.suspects(dataset_of(new_market)) == []


def test_every_suspect_says_what_to_do_about_it():
    """Ask the data team, not the market director — and the screen has to say which."""
    silent = unit(
        key="finland",
        actual=Drivers.sales_only(0.0),
        budget=Drivers.sales_only(9_000.0),
        last_year=Drivers.sales_only(8_361.0),
    )

    flag = analytics.suspects(dataset_of(silent))[0]

    assert flag.message.strip()
    assert flag.fix.strip()


# ------------------------------------------------- a budget that does not exist (§21A)
#
# The planning file does not cover every market the warehouse reports. Before these tests,
# a missing budget arrived as zero, the gap came out as the market's entire turnover, and
# the least-known market in the company was crowned its greatest success. A silent zero is
# the most dangerous default in the cockpit: it is indistinguishable from a real number.


def test_a_market_with_no_budget_is_never_a_win():
    """Beating a budget that does not exist is not an achievement."""
    unbudgeted = unit(
        key="taiwan",
        actual=ecom(2_000_000),
        budget=Drivers.sales_only(0.0),
        budget_known=False,
        last_year=ecom(1_900_000),
    )

    assert [w.unit.key for w in analytics.wins(dataset_of(unbudgeted))] == []


def test_a_market_with_no_budget_is_never_a_fire():
    """Nor is it a failure. There is simply nothing to compare it to."""
    unbudgeted = unit(
        key="taiwan",
        actual=ecom(10_000),
        budget=Drivers.sales_only(0.0),
        budget_known=False,
        last_year=ecom(1_900_000),
    )

    assert [f.unit.key for f in analytics.fires(dataset_of(unbudgeted))] == []


def test_a_missing_budget_is_left_out_of_the_company_total():
    """Otherwise the company looks ahead of a plan it was never measured against."""
    covered = unit(key="japan", actual=ecom(900_000), budget=ecom(1_000_000))
    uncovered = unit(
        key="taiwan",
        actual=ecom(2_000_000),
        budget=Drivers.sales_only(0.0),
        budget_known=False,
    )

    dataset = dataset_of(covered, uncovered)

    assert dataset.sales_budget == pytest.approx(1_000_000)
    assert dataset.sales_actual == pytest.approx(2_900_000)


def test_the_omission_stays_visible():
    """Excluded, but not hidden: the screen has to be able to say what it left out."""
    uncovered = unit(
        key="taiwan",
        actual=ecom(2_000_000),
        budget=Drivers.sales_only(0.0),
        budget_known=False,
    )

    dataset = dataset_of(unit(key="japan"), uncovered)

    assert [u.key for u in dataset.unbudgeted] == ["taiwan"]
    assert dataset.unbudgeted_sales == pytest.approx(2_000_000)


# ---------------------------------------------------- what the drivers are measured against
#
# A budget is a committed number with no funnel behind it: nobody planned a conversion
# rate. So a gap against plan cannot be attributed to a driver, and the decomposition has
# to fall back on the only baseline that was measured the same way — last year. The reader
# then has to be told which one was used, because the two answer different questions.


def test_a_plan_without_drivers_falls_back_to_last_year():
    plain_budget = unit(
        key="japan",
        actual=ecom(900_000),
        budget=Drivers.sales_only(1_000_000),
        last_year=ecom(950_000),
    )

    baseline, label = plain_budget.decomposition_baseline()

    assert label == "last year"
    assert baseline.labels == ("Sessions", "Conversion", "AOV")


def test_a_plan_with_matching_drivers_is_preferred():
    """When the plan does carry a funnel, it answers the more useful question."""
    planned = unit(key="japan", actual=ecom(900_000), budget=ecom(1_000_000))

    _, label = planned.decomposition_baseline()

    assert label == "plan"


def test_no_common_baseline_means_no_attribution():
    """Silence beats a decomposition against a number that was measured differently."""
    orphan = unit(
        key="japan",
        actual=ecom(900_000),
        budget=Drivers.sales_only(1_000_000),
        last_year=Drivers.sales_only(950_000),
    )

    assert orphan.decomposition_baseline() == (None, "")
    assert orphan.has_driver_breakdown is False


def test_mismatched_drivers_never_raise():
    """The bug this replaces was a 500 on the home page, not a wrong number."""
    plain_budget = unit(
        key="japan",
        actual=ecom(900_000),
        budget=Drivers.sales_only(1_000_000),
        last_year=ecom(950_000),
    )

    fire = analytics.fires(dataset_of(plain_budget))[0]

    assert fire.gap == pytest.approx(-100_000)
    assert fire.movement == pytest.approx(-50_000)


def test_the_diagnosis_names_the_baseline_it_used():
    """"-€100k against plan, and here is why" would be a small lie in a confident voice:
    the why was measured against last year."""
    plain_budget = unit(
        key="japan",
        actual=ecom(900_000, conversion=0.016),
        budget=Drivers.sales_only(1_000_000),
        last_year=ecom(950_000, conversion=0.02),
    )

    fire = analytics.fires(dataset_of(plain_budget))[0]

    assert fire.baseline_label == "last year"
    assert "versus last year" in fire.diagnosis


def test_a_plan_baseline_still_speaks_of_a_gap():
    """Against a plan the word is 'gap'; the sentence must not say 'versus last year'."""
    planned = unit(
        key="japan",
        actual=ecom(900_000, conversion=0.0185),
        budget=ecom(1_000_000, conversion=0.02),
    )

    fire = analytics.fires(dataset_of(planned))[0]

    assert fire.baseline_label == "plan"
    assert "of the gap comes from" in fire.diagnosis
    assert "versus last year" not in fire.diagnosis


def test_the_contributions_still_add_up_to_the_measured_movement():
    """The fallback changes the baseline, never the arithmetic."""
    plain_budget = unit(
        key="japan",
        actual=ecom(900_000, conversion=0.016),
        budget=Drivers.sales_only(1_000_000),
        last_year=ecom(950_000, conversion=0.02),
    )

    fire = analytics.fires(dataset_of(plain_budget))[0]
    total = sum(c.impact for c in fire.contributions)

    assert total == pytest.approx(fire.movement)
    assert fire.movement != fire.gap


# ------------------------------------------------- traffic that moves without the money
#
# The failure mode last year's funnel made visible. A market whose sessions arrive at a
# multiple of last year's while revenue sits still has not found an audience — its
# measurement changed. A tag deployed, a domain merged, a bot filter switched off.
#
# These are the most dangerous rows on the screen, because their sales gap is usually
# small enough to pass unremarked while their decomposition is enormous.


def sessions_of(sales, sessions, aov=60.0):
    """Drivers pinned to a session count, so the break can be built explicitly."""
    orders = sales / aov
    return Drivers(("Sessions", "Conversion", "AOV"), (sessions, orders / sessions, aov))


def test_traffic_at_a_multiple_of_last_year_with_flat_sales_is_a_data_break():
    broken = unit(
        key="hongkong",
        actual=sessions_of(51_000, 687_000),
        budget=Drivers.sales_only(50_000),
        last_year=sessions_of(46_000, 43_000),
    )

    flag = analytics.suspect_of(broken)

    assert flag is not None
    assert flag.code == "traffic_discontinuity"


def test_traffic_collapsing_to_a_quarter_with_flat_sales_is_the_same_break():
    """The signature is symmetric: what matters is that revenue did not follow."""
    broken = unit(
        key="brazil",
        actual=sessions_of(178_000, 206_000),
        budget=Drivers.sales_only(180_000),
        last_year=sessions_of(180_000, 905_000),
    )

    assert analytics.suspect_of(broken).code == "traffic_discontinuity"


def test_traffic_growth_that_carries_the_money_is_a_real_result():
    """A market whose sessions and sales rise together has found an audience. Flagging it
    would turn the guard into noise, and a guard nobody trusts protects nothing."""
    growing = unit(
        key="france",
        actual=sessions_of(1_200_000, 900_000),
        budget=Drivers.sales_only(1_100_000),
        last_year=sessions_of(1_000_000, 730_000),
    )

    assert analytics.suspect_of(growing) is None


def test_a_conversion_collapse_on_stable_traffic_is_not_flagged():
    """The case the cockpit exists to surface. It must reach the fire list untouched."""
    real = unit(
        key="uk",
        actual=sessions_of(715_000, 950_000),
        budget=Drivers.sales_only(1_000_000),
        last_year=sessions_of(1_000_000, 1_000_000),
    )

    assert analytics.suspect_of(real) is None


def test_a_broken_market_never_becomes_an_opportunity():
    """"Recover last year's conversion and gain €4m" computed on a tracking break is a
    number the CEO would act on. A wasted glance is cheap; a wasted quarter is not."""
    broken = unit(
        key="hongkong",
        actual=sessions_of(2_000_000, 9_000_000),
        budget=Drivers.sales_only(2_000_000),
        last_year=sessions_of(2_050_000, 500_000),
    )

    assert analytics.opportunity_of(broken) is not None  # the raw counterfactual exists
    assert analytics.opportunities(dataset_of(broken)) == []  # and is refused


def test_the_flag_says_who_to_ask():
    """The data team, not the market director — the distinction the whole panel is for."""
    broken = unit(
        key="hongkong",
        actual=sessions_of(51_000, 687_000),
        budget=Drivers.sales_only(50_000),
        last_year=sessions_of(46_000, 43_000),
    )

    flag = analytics.suspect_of(broken)

    assert "tracking" in flag.fix
    assert "audience" in flag.fix


def test_an_initialism_survives_the_sentence():
    """"About 65% of the movement comes from aov" reads as a typo, in the one sentence
    the CEO reads first."""
    aov_led = unit(
        key="japan",
        actual=Drivers(("Sessions", "Conversion", "AOV"), (1_000_000.0, 0.02, 45.0)),
        budget=Drivers.sales_only(1_500_000.0),
        last_year=Drivers(("Sessions", "Conversion", "AOV"), (1_000_000.0, 0.02, 60.0)),
    )

    fire = analytics.fires(dataset_of(aov_led))[0]

    assert "AOV" in fire.diagnosis
    assert "aov" not in fire.diagnosis
    assert "AOV" in fire.question


def test_an_ordinary_driver_is_still_lower_cased():
    """The rule is about initialisms, not about shouting every driver name."""
    session_led = unit(
        key="australia",
        actual=Drivers(("Sessions", "Conversion", "AOV"), (700_000.0, 0.02, 60.0)),
        budget=Drivers.sales_only(1_500_000.0),
        last_year=Drivers(("Sessions", "Conversion", "AOV"), (1_000_000.0, 0.02, 60.0)),
    )

    fire = analytics.fires(dataset_of(session_led))[0]

    assert "comes from sessions" in fire.diagnosis


# ------------------------------------------------------ one fault, or many incidents
#
# The first real screen showed twelve markets each reporting sessions and no orders. Read
# as a list, that is twelve problems and gets triaged as none. Read as a shape, it is one
# join not matching — one query to fix rather than twelve markets to chase.


def _no_orders(key, sales):
    return unit(
        key=key,
        actual=sessions_of(sales, sales * 4),
        budget=Drivers.sales_only(sales),
        last_year=sessions_of(sales, sales * 4),
        orders=0,
        sessions=sales * 4,
    )


def test_several_markets_failing_the_same_way_are_named_as_one_fault():
    dataset = dataset_of(*[_no_orders("m%d" % i, 100_000) for i in range(5)])

    said = analytics.patterns(analytics.suspects(dataset))

    assert len(said) == 1
    assert "5 markets" in said[0]
    assert "not 5 separate incidents" in said[0]


def test_the_pattern_carries_the_money_behind_it():
    """Twelve small markets and twelve large ones are not the same problem."""
    dataset = dataset_of(*[_no_orders("m%d" % i, 200_000) for i in range(4)])

    assert "€800k" in analytics.patterns(analytics.suspects(dataset))[0]


def test_two_markets_are_not_yet_a_pattern():
    """Below the threshold, coincidence is still the simpler explanation, and a pattern
    claimed too early is a pattern nobody believes the next time."""
    dataset = dataset_of(_no_orders("a", 100_000), _no_orders("b", 100_000))

    assert analytics.patterns(analytics.suspects(dataset)) == []


def test_the_instances_are_still_listed_beneath_the_pattern():
    """Naming the shape must not hide which markets are affected — that is what makes it
    checkable."""
    dataset = dataset_of(*[_no_orders("m%d" % i, 100_000) for i in range(4)])

    assert len(analytics.suspects(dataset)) == 4


def test_different_faults_are_never_merged_into_one_pattern():
    silent = unit(
        key="finland",
        actual=Drivers.sales_only(0.0),
        budget=Drivers.sales_only(9_000.0),
        last_year=Drivers.sales_only(8_361.0),
    )
    dataset = dataset_of(silent, *[_no_orders("m%d" % i, 100_000) for i in range(4)])

    said = analytics.patterns(analytics.suspects(dataset))

    assert len(said) == 1
    assert "no orders at all" in said[0]


# ------------------------------------------- absent orders, now absent rather than zero
#
# The query was corrected to return no order count where the transaction identifier is
# empty, instead of returning zero. That is right — zero reads as "nobody bought" on a
# market that sells every day — and it silently disarmed the shape-based guard, which
# could only ever see a zero. The status is what the guard reads now.


def _with_status(status, **overrides):
    fields = {
        "key": "brazil",
        "actual": Drivers.sales_only(179_000.0),
        "budget": Drivers.sales_only(200_000.0),
        "last_year": Drivers.sales_only(180_000.0),
        "funnel_status": status,
        "sessions": 207_000.0,
        "orders": None,
    }
    fields.update(overrides)
    return unit(**fields)


def test_an_absent_order_count_is_still_caught_by_the_status():
    """The regression this guards: orders stopped being zero, so the old check stopped
    firing, and a dozen markets would have walked into the ranking looking ordinary."""
    flag = analytics.suspect_of(_with_status("orders_not_tracked"))

    assert flag is not None
    assert flag.code == "traffic_without_orders"


def test_tracking_lost_carries_its_own_code():
    """Because its remedy is different: something broke on a date and can be found."""
    flag = analytics.suspect_of(_with_status("order_tracking_lost"))

    assert flag.code == "order_tracking_lost"
    assert "recently" in flag.fix


def test_a_market_selling_on_platforms_is_never_flagged_as_broken():
    """Its revenue is real sell-out and its missing funnel is not a fault. Sending anyone
    to repair it would send them after nothing, and a guard that cries about normality is
    a guard nobody reads."""
    assert analytics.suspect_of(_with_status("no_analytics_site")) is None


def test_a_platform_market_with_no_online_sales_is_not_a_broken_feed_either():
    no_site = _with_status(
        "no_analytics_site",
        actual=Drivers.sales_only(0.0),
        last_year=Drivers.sales_only(0.0),
        budget=Drivers.sales_only(0.0),
    )

    assert analytics.suspect_of(no_site) is None


def test_markets_selling_on_platforms_are_listable():
    """A reader looking for a large market and not finding it assumes the screen lost it,
    and stops trusting the rest of the list."""
    dataset = dataset_of(
        _with_status("no_analytics_site", key="china", market="China"),
        _with_status("measured", key="japan", market="Japan", orders=12_800.0),
    )

    assert dataset.markets_without_own_site == ["China"]
