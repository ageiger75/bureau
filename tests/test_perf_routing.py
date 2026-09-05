"""Routing by class, before any question of size.

The failure this prevents is the one the cockpit made for months: a boundary in the
accounts, a feed that stopped and a market trading badly, all sorted together by euros,
competing for the same five slots — and the accounting item winning, because it was
larger. Three of those four are answered by people who are not the market.
"""

import pytest

from app.perf import analytics, context, routing
from app.perf.model import BusinessUnit, Dataset, Drivers

OWNER = type("Owner", (), {"name": "Marie", "role": "Managing Director"})()


def note(kind, market="United States", channel="", action_owner=""):
    return context.Note(market=market, channel=channel, since="2025-09", kind=kind,
                        text="Something the numbers cannot say.", source="CEO",
                        action_owner=action_owner)


def _drivers(value):
    return value if isinstance(value, Drivers) else Drivers.sales_only(value)


def unit(actual=9_000_000.0, budget=10_000_000.0, notes=(), **over):
    base = dict(
        key="test", label="Test", market="United States", region="AMERICAS",
        channel="webp", owner=OWNER,
        actual=_drivers(actual), budget=_drivers(budget),
        last_year=_drivers(budget), forecast_sales=0.0,
        context_notes=list(notes),
    )
    base.update(over)
    return BusinessUnit(**base)


def funnel(sales, sessions, aov=60.0):
    return Drivers(("Sessions", "Conversion", "AOV"),
                   (sessions, sales / aov / sessions, aov))


def dataset_of(*units):
    return Dataset(period_label="July 2026", as_of="", units=list(units))


# ------------------------------------------------------------------ what leaves


def test_an_accounting_boundary_is_not_a_conversation_with_a_market():
    """The worked example. €854k filed under the wrong segment took third place in the
    week's five, above two markets genuinely trading badly, because it was larger."""
    routed = routing.classify(unit(notes=[note(context.RECLASSIFIED,
                                               action_owner="Consolidation")]))

    assert routed.klass == routing.ACCOUNTING
    assert routed.surface == "data"
    assert routed.move == routing.NO_CEO_ACTION
    assert routed.destination == "Consolidation"


def test_a_broken_feed_is_a_question_for_the_data_team():
    routed = routing.classify(unit(), is_suspect=True)

    assert routed.klass == routing.DATA
    assert routed.surface == "data"
    assert routed.destination == "Équipe data"


def test_a_basis_change_is_a_definition_question():
    """Brazil: the tax regime moved and the plan predates it. The distance between them
    stopped being a measure of trading the day the yardstick changed."""
    routed = routing.classify(unit(notes=[note(context.BASIS_CHANGE, market="Brazil")]))

    assert routed.klass == routing.DEFINITION
    assert routed.move == routing.NO_CEO_ACTION
    assert routed.destination == "Finance"


def test_deliberately_stopped_trading_is_a_risk_and_not_a_miss():
    """Australia: deliveries stopped because the client is not paying. The revenue is
    genuinely missing and nobody needs to be asked why."""
    routed = routing.classify(unit(notes=[note(context.ON_HOLD, market="Australia")]))

    assert routed.klass == routing.RISK
    assert routed.surface == "business"
    assert routed.move == routing.NO_CEO_ACTION


# ------------------------------------------------------------------ what stays


def test_a_measured_gap_is_put_to_the_market():
    routed = routing.classify(unit(actual=funnel(900_000, 100_000),
                                   budget=funnel(1_000_000, 100_000)))

    assert routed.klass == routing.PERFORMANCE
    assert routed.move == routing.CHALLENGE
    assert routed.destination == ""  # the market's own lead, which is fair here


def test_an_unexplained_gap_keeps_its_rank_and_changes_its_move():
    """The rule the whole module exists for. A €2.3m gap nobody can explain stays exactly
    where its money puts it; what changes is that nobody is sent to press a market lead
    about a number the screen cannot take apart."""
    blind = unit(actual=7_700_000.0, budget=10_000_000.0)
    measured = unit(key="other", label="Other", market="Japan", channel="ecommerce",
                    actual=funnel(900_000, 100_000), budget=funnel(1_000_000, 100_000))

    found = analytics.fires(dataset_of(blind, measured))

    assert [f.unit.label for f in found] == ["Test", "Other"]  # money still decides
    assert found[0].routed.move == routing.REQUEST_DATA
    assert found[1].routed.move == routing.CHALLENGE


def test_a_shipment_month_is_investigated_not_challenged():
    """Sell-in carries no funnel. A partner that ordered early reads as growth and one
    that ordered late reads as collapse — neither is a conversation about demand."""
    routed = routing.classify(unit(channel="dis", perimeter="sell-in"))

    assert routed.klass == routing.PERFORMANCE
    assert routed.move == routing.INVESTIGATE


# ------------------------------------------------------------------ the two surfaces


def test_the_business_surface_holds_only_what_the_ceo_answers():
    trading = unit(key="japan", label="Japan E-commerce", market="Japan",
                   channel="ecommerce", actual=funnel(900_000, 100_000),
                   budget=funnel(1_000_000, 100_000))
    boundary = unit(key="us", label="United States Chain Wholesale", channel="whoch",
                    actual=8_000_000.0, budget=10_000_000.0,
                    notes=[note(context.RECLASSIFIED)])
    dataset = dataset_of(trading, boundary)

    assert [f.unit.label for f in analytics.fires(dataset)] == ["Japan E-commerce"]
    elsewhere = analytics.routed_elsewhere(dataset)
    assert [f.unit.label for f in elsewhere] == ["United States Chain Wholesale"]
    # And the larger number is the one that left: this is not a materiality filter.
    assert abs(elsewhere[0].gap) > abs(analytics.fires(dataset)[0].gap)


def test_nothing_material_is_dropped_by_the_routing():
    """Routed, never discarded. Every euro that leaves the ranking arrives somewhere, or
    the screen has quietly stopped reconciling with the group's own variance."""
    units = [
        unit(key="a", actual=8_000_000.0, notes=[note(context.RECLASSIFIED)]),
        unit(key="b", market="Brazil", actual=8_500_000.0,
             notes=[note(context.BASIS_CHANGE, market="Brazil")]),
        unit(key="c", market="Japan", actual=funnel(900_000, 100_000),
             budget=funnel(1_000_000, 100_000)),
    ]
    dataset = dataset_of(*units)

    placed = {f.unit.key for f in analytics.fires(dataset)}
    placed |= {f.unit.key for f in analytics.routed_elsewhere(dataset)}

    assert placed == {"a", "b", "c"}


def test_every_class_has_a_surface():
    """A class that cannot be placed on one of the three surfaces has not been thought
    through — it would reach the screen and be rendered nowhere."""
    for klass in (routing.PERFORMANCE, routing.PLAN, routing.EXECUTION, routing.RISK,
                  routing.OPPORTUNITY, routing.DATA, routing.ACCOUNTING,
                  routing.DEFINITION):
        assert routing.SURFACES[klass] in ("business", "plan", "data")
        assert routing.CLASS_LABELS[klass]


# ------------------------------------------------------------------ on the screen


def test_the_screen_shows_where_a_routed_item_went(monkeypatch):
    """Routed, not vanished.

    A reader who simply stopped seeing €854k would have no way to tell an item that was
    placed from one that was lost — and the first time they checked the group's variance
    against this screen, they would find the screen short and stop trusting it. So the
    money leaves the ranking and arrives, by name, under a heading that says whose
    question it is.
    """
    from starlette.testclient import TestClient

    import app.routes.today as today_route
    from app.main import app
    from app.perf.source import MockSource

    boundary = unit(
        key="us-whoch", label="United States Chain Wholesale", channel="whoch",
        actual=8_000_000.0, budget=10_000_000.0,
        notes=[note(context.RECLASSIFIED, action_owner="Consolidation")],
    )
    trading = unit(
        key="japan-ec", label="Japan E-commerce", market="Japan", channel="ecommerce",
        actual=funnel(900_000, 100_000), budget=funnel(1_000_000, 100_000),
    )

    class Stub(MockSource):
        def dataset(self, refresh: bool = False, wait_for_warehouse=True):
            return dataset_of(trading, boundary)

    monkeypatch.setattr(today_route, "current_source", lambda: Stub())

    with TestClient(app) as client:
        page = client.get("/").text

    assert "Pas une conversation commerciale" in page
    assert "United States Chain Wholesale" in page
    assert "Consolidation" in page
    assert "Aucune action du CEO" in page

    # And the ranking above it holds the market, not the boundary.
    where_to_push = page.split("Pas une conversation commerciale")[0]
    assert "Japan E-commerce" in where_to_push
    assert "United States Chain Wholesale" not in where_to_push


# ------------------------------------------------------------------ one subject


def test_a_market_losing_ground_in_two_channels_is_one_subject():
    """The duplicate a reader sees first. Japan took two of the week's five slots and had
    its lead named twice on the same page — while a fifth market, materially below plan,
    was pushed off the list by a market already on it."""
    japan_ec = unit(key="jp-ec", label="Japan E-commerce", market="Japan",
                    channel="ecommerce", actual=funnel(900_000, 100_000),
                    budget=funnel(1_000_000, 100_000))
    japan_retail = unit(key="jp-rt", label="Japan Retail", market="Japan",
                        channel="retail", actual=8_500_000.0, budget=9_000_000.0)
    korea = unit(key="kr", label="Korea Retail", market="Korea", channel="retail",
                 actual=8_800_000.0, budget=9_000_000.0)
    dataset = dataset_of(japan_ec, japan_retail, korea)

    found = analytics.issues(dataset)

    assert [issue.market for issue in found] == ["Japan", "Korea"]
    japan = found[0]
    assert len(japan.fires) == 2
    assert japan.gap == pytest.approx(-600_000.0)  # 100k + 500k, summed once
    assert "E-commerce" in japan.channels and "Retail" in japan.channels


def test_the_subject_is_ranked_on_what_the_market_loses_altogether():
    """Two channels each below the line can outweigh one larger channel — and used to
    lose to it, because they were ranked apart. Ranking channels also ranks by how finely
    a market happens to be cut, which is a fact about reporting and not about the
    business."""
    split_a = unit(key="a1", label="Split A", market="Split", channel="retail",
                   actual=8_400_000.0, budget=9_000_000.0)
    split_b = unit(key="a2", label="Split B", market="Split", channel="whoch",
                   actual=8_400_000.0, budget=9_000_000.0)
    whole = unit(key="b", label="Whole", market="Whole", channel="retail",
                 actual=8_200_000.0, budget=9_000_000.0)

    found = analytics.issues(dataset_of(split_a, split_b, whole))

    assert [issue.market for issue in found] == ["Split", "Whole"]
    assert found[0].gap == pytest.approx(-1_200_000.0)


def test_an_owner_is_named_once_for_their_market():
    japan_ec = unit(key="jp-ec", label="Japan E-commerce", market="Japan",
                    channel="ecommerce", actual=funnel(8_000_000, 100_000),
                    budget=funnel(9_000_000, 100_000))
    japan_retail = unit(key="jp-rt", label="Japan Retail", market="Japan",
                        channel="retail", actual=funnel(8_500_000, 100_000),
                        budget=funnel(9_000_000, 100_000))

    found = analytics.issues(dataset_of(japan_ec, japan_retail))
    pushes = analytics.people_to_push([issue.fires[0] for issue in found])

    assert [push.owner.name for push in pushes] == ["Marie"]


def test_a_single_channel_market_is_still_a_subject():
    """No special case below: one channel is a subject of one, and the screen prints it
    the way it always did rather than wrapping it in a heading that repeats itself."""
    alone = unit(key="solo", label="Korea Retail", market="Korea", channel="retail")

    found = analytics.issues(dataset_of(alone))

    assert found[0].is_single
    assert found[0].gap == found[0].fires[0].gap


def test_only_two_moves_put_a_commercial_owner_in_the_room():
    """A gap the screen can take apart, or a plan somebody set. Everything else is real
    work owned by data, ops or finance — and printing it as a conversation is how a page
    tells its reader to investigate a figure and then hands them someone to press."""
    measured = unit(key="a", label="Measured", market="A",
                    actual=funnel(900_000, 100_000), budget=funnel(1_000_000, 100_000))
    blind = unit(key="b", label="Blind", market="B",
                 actual=7_000_000.0, budget=9_000_000.0)
    shipped = unit(key="c", label="Shipped", market="C", channel="dis",
                   perimeter="sell-in", actual=7_000_000.0, budget=9_000_000.0)

    dataset = dataset_of(measured, blind, shipped)
    found = analytics.fires(dataset)

    # All three are ranked: size decides, and the two blind ones are the larger.
    assert [f.unit.label for f in found] == ["Blind", "Shipped", "Measured"]
    # Only one of them is a conversation.
    pushes = analytics.people_to_push(found)
    assert [p.fire.unit.label for p in pushes] == ["Measured"]


# ------------------------------------------------------- the plan review, in two lists


def planned(label, sentence, market="M", notes=()):
    return unit(key=label.lower(), label=label, market=market, notes=notes,
                plan_vs_record=sentence)


def test_the_two_directions_are_two_lists():
    """A plan above everything the record shows will be missed every month, and the misses
    will not be news. A plan below what the business is already doing is a forecast to
    redo. Mixed into one list they cancel out: fourteen lines and no way to tell which
    half is which."""
    above = planned("Japan EC", "au-dessus de chaque lecture du réalisé — "
                                "%s embarqués sur l\'année" % analytics.format_eur(5_000_000), market="Japan")
    below = planned("HK Travel", "ont fait +21 %% — en dessous de chaque lecture du "
                                 "réalisé, jusqu\'à 3 points d\'écart. %s embarqués sur l\'année"
                                 % analytics.format_eur(12600000), market="HK")
    dataset = dataset_of(above, below)

    assert [i.unit.label for i in routing.plan_reviews(dataset, above=True)] == ["Japan EC"]
    assert [i.unit.label for i in routing.plan_reviews(dataset, above=False)] == ["HK Travel"]


def test_a_base_effect_never_opens_the_list():
    """"+15962%" is not growth, it is a base. A new listing, a first shipment, an
    accounting boundary already noted — any of them makes the percentage a statement about
    last year's emptiness. The first line of a Finance review has to survive Finance.
    """
    base = planned("UK Chain", "ont fait +15962 %% — en dessous de chaque lecture du "
                               "réalisé, jusqu\'à 3 points d\'écart. %s embarqués sur l\'année"
                               % analytics.format_eur(44500000), market="UK")
    real = planned("HK Travel", "ont fait +21 %% — en dessous de chaque lecture du "
                                "réalisé, jusqu\'à 3 points d\'écart. %s embarqués sur l\'année"
                                % analytics.format_eur(12600000), market="HK")

    found = routing.plan_reviews(dataset_of(base, real), above=False)

    assert [i.unit.label for i in found] == ["HK Travel", "UK Chain"]
    assert found[0].base_effect is False
    assert found[1].base_effect is True   # kept and marked, never silently dropped
    # And the larger amount is the one demoted: this is not a materiality filter.
    assert found[1].amount > found[0].amount


def test_a_market_whose_figures_are_already_noted_cannot_carry_a_comparison():
    """The American boundary is the case: a channel whose revenue is filed on the wrong
    side is not a business that grew, and its growth rate says nothing about its plan."""
    noted = planned("US Chain", "ont fait +40 %% — en dessous de chaque lecture du "
                                "réalisé, jusqu\'à 3 points d\'écart. %s embarqués sur l\'année"
                                % analytics.format_eur(9000000), market="US",
                    notes=[note(context.RECLASSIFIED)])

    found, = routing.plan_reviews(dataset_of(noted), above=False)

    assert found.base_effect


def test_a_franchised_market_carries_no_badge_on_its_sold_figure():
    """Il y en a eu un pendant une heure, sur une prémisse mesurée fausse.

    Le réseau franchisé n'est pas dans le flux du vendu : il n'y a donc rien à escompter
    sur ce chiffre, et un badge qui dit le contraire ferait douter d'un nombre juste. Le
    fait est vrai du commerce et faux de la figure — la pire combinaison.
    """
    sold = unit(market="France", channel="retail", perimeter="own")

    assert routing.badges_for(sold, has_breakdown=True) == []
