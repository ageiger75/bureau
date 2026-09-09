"""La conversation sur les clients : le pont, le flux, et la phrase qui en découle.

Valeurs et marchés inventés. Ce que les tests gardent : le pont additionne bien clients,
tickets et ventes ; le flux lit ses parts sur la bonne base ; la phrase dit où la valeur
s'érode d'après les paniers, pas d'après un avis ; une somme de marchés se dit approximative.
"""

from __future__ import annotations

from app.perf import clients as C


def _row(scope, window, segment, clients, transactions, sales, through="2026-08"):
    return {"scope": scope, "window": window, "through": through, "segment": segment,
            "clients": clients, "transactions": transactions, "sales": sales}


def _rows(scope="LOEP", retained_atv=70.0):
    # Des dizaines de clients, pas des milliers : les comptes s'écrivent alors tels quels.
    return [
        _row(scope, "ly", "arc", 100, 160, 12_800.0),          # panier 80
        _row(scope, "ly", "walkin", 200, 200, 10_000.0),
        _row(scope, "ty", "arc", 105, 170, 13_000.0),
        _row(scope, "ty", "walkin", 190, 190, 9_800.0),
        _row(scope, "ty", "retained", 60, 110, 110 * retained_atv),
        _row(scope, "ty", "reactivated", 10, 13, 13 * 76.0),
        _row(scope, "ty", "new", 35, 47, 47 * 60.0),
        _row(scope, "ty", "lost", 40, 50, 4_000.0),
    ]


def test_the_bridge_reads_clients_times_basket_against_last_year():
    review = C.build(_rows())

    arc = review.pair("arc")
    assert arc.clients_label == "105" and arc.clients_growth_label == "+5.0 %"
    assert arc.atv_label == "76 €" and arc.atv_growth_label == "-4.4 %"
    assert arc.sales_growth_label == "+1.6 %"
    assert round(review.registered_share, 3) == round(13_000.0 / 22_800.0, 3)
    assert review.headline.startswith("105 clients enregistrés (+5.0 %) × panier 76 € (-4.4 %) = ")
    assert "(+1.6 %)" in review.headline
    assert "avril à août 2026" in review.basis
    assert review.net_change == 5


def test_the_flow_reads_its_shares_on_the_base_and_the_actives():
    review = C.build(_rows())

    assert review.lost.share_label == "40 % de la base"
    assert review.part("retained").share_label == "60 % de la base"
    assert review.part("new").share_label == "33 % des actifs"
    assert review.part("reactivated").share_label == "10 % des actifs"
    assert review.part("new").atv_vs_base_label == "-25.0 %"


def test_the_sentence_says_where_the_value_erodes_from_the_baskets():
    eroding = C.build(_rows(retained_atv=70.0))
    assert "l'érosion de valeur est dans le cœur fidèle" in eroding.read
    assert "-12.5 % de panier" in eroding.read
    assert eroding.question.startswith("Les fidèles achètent moins cher")

    holding = C.build(_rows(retained_atv=84.0))
    assert "les retenus achètent plus cher" in holding.read
    assert holding.question.startswith("Le recrutement compense-t-il")


def test_a_sum_of_markets_is_said_approximate_and_a_missing_reading_is_said():
    rows = _rows("NORTHLAND") + _rows("EASTLAND")
    region = C.for_markets(rows, ["Northland", "Eastland"], "Nord")
    assert region.approximate and "compte deux fois" in region.basis
    assert region.pair("arc").clients_label == "210"

    nothing = C.build([], note="la lecture des clients n'est pas encore écrite")
    assert not nothing.usable and nothing.absent == ["la lecture des clients n'est pas encore écrite"]
    assert C.build(_rows(), "Nulle").absent == ["aucune lecture clients pour Nulle"]


def test_the_invented_rows_read_as_a_whole_block():
    from app.perf import mock

    review = C.build(mock.client_rows())
    assert review.usable and review.flow and review.lost is not None
    assert review.headline and review.read and review.question
