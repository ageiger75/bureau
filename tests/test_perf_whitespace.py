"""Les white spaces internes : trois formes, chacune avec son hypothèse.

Ces tests gardent ce que chaque forme exige avant de parler — des pairs assez nombreux, un
mix sous le plan assez longtemps, assez de boutiques pour une médiane — et ce qu'elle ne
fait jamais : deviner une taille sans nommer d'où elle vient. Valeurs inventées.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.perf import whitespace as W
from app.perf.analytics import format_eur


def _unit(market, channel, actual, budget, history=(), ytd=None, label=None):
    return SimpleNamespace(market=market, channel=channel, channel_label=label or channel.title(),
                           sales_actual=actual, sales_budget=budget, gap_history=tuple(history),
                           gap_year_to_date=ytd, is_aggregate=False, budget_known=True)


def _store(code, market, actual):
    return SimpleNamespace(code=code, name="Boutique %s" % code, market=market, status="open",
                           actual=actual, last_year=None, budget=None, is_bulk=False)


PLACED = {"Northland": "Nord", "Eastland": "Nord", "Westland": "Nord", "Southland": "Sud"}


def test_a_channel_the_peers_carry_and_the_market_lacks_is_sized_on_the_peers_median_share():
    units = [
        _unit("Northland", "retail", 800.0, 800.0), _unit("Northland", "ecommerce", 200.0, 200.0),
        _unit("Eastland", "retail", 700.0, 700.0), _unit("Eastland", "ecommerce", 300.0, 300.0),
        _unit("Westland", "retail", 1000.0, 1000.0),
    ]
    found = W.absent_channels(units, PLACED)

    assert [(space.market, space.label) for space in found] == [("Westland", "Ecommerce")]
    # Part médiane des pairs : 20 % et 30 %, médiane 25 %, sur mille de ventes.
    assert found[0].amount == 250.0
    assert "Northland, Eastland" in found[0].basis
    assert found[0].question.startswith("Pourquoi Westland n'a pas Ecommerce")


def test_a_market_without_its_own_site_is_not_a_missing_channel_and_peers_must_be_enough():
    units = [
        _unit("Northland", "retail", 800.0, 800.0), _unit("Northland", "ecommerce", 200.0, 200.0),
        _unit("Eastland", "retail", 700.0, 700.0), _unit("Eastland", "ecommerce", 300.0, 300.0),
        _unit("Westland", "retail", 1000.0, 1000.0),
        _unit("Southland", "retail", 500.0, 500.0),
    ]
    assert W.absent_channels(units, PLACED, no_site=["Westland"]) == []
    # Southland est seule dans son périmètre : pas de pair, pas de white space.
    assert not any(space.market == "Southland" for space in W.absent_channels(units, PLACED))


def test_a_channel_below_its_planned_share_for_three_months_is_a_white_space_sized_on_the_year():
    units = [
        _unit("Northland", "retail", 900.0, 800.0, history=(10.0, 20.0, 30.0)),
        _unit("Northland", "ecommerce", 100.0, 200.0, history=(-50.0, -80.0, -100.0), ytd=-400.0),
    ]
    found = W.mixes_below_plan(units)

    assert [(space.market, space.label, space.amount) for space in found] == [("Northland", "Ecommerce", 400.0)]
    assert "10 % du marché contre 20 % au plan" in found[0].basis
    # Deux mois seulement sous le plan : pas encore.
    short = [_unit("Northland", "retail", 900.0, 800.0), _unit("Northland", "ecommerce", 100.0, 200.0, history=(5.0, -80.0, -100.0))]
    assert W.mixes_below_plan(short) == []


def test_stores_under_half_the_median_are_counted_and_sized_at_the_median():
    stores = [_store("N%d" % n, "Northland", value) for n, value in enumerate((100.0, 100.0, 100.0, 100.0, 100.0, 30.0, 40.0))]
    stores.append(SimpleNamespace(code="N-BULK", name="vrac", market="Northland", status="open",
                                  actual=5.0, last_year=None, budget=None, is_bulk=True))
    stores.append(_store("S1", "Southland", 10.0))
    sales = SimpleNamespace(usable=True, stores=stores)

    found = W.stores_below_median(sales)

    assert [(space.market, space.label) for space in found] == [("Northland", "2 boutiques sur 7")]
    assert found[0].amount == 130.0
    assert format_eur(100.0) in found[0].basis
    assert found[0].details[0].startswith("N5 Boutique N5")
    assert W.stores_below_median(None) == []


def test_the_review_names_what_it_could_not_read_and_the_external_gap():
    dataset = SimpleNamespace(units=[], markets_without_own_site=[])
    review = W.build(dataset, {}, None)

    assert not review.usable
    assert any("aucune unité lue" in reason for reason in review.absent)
    assert any("ventes par boutique non lues" in reason for reason in review.absent)
    assert any("Beauté Research" in reason for reason in review.absent)
