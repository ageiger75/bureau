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


def test_a_flow_that_does_not_bridge_to_the_actives_is_said_and_unknown_dates_are_a_segment():
    """Les clients acquis entre les deux fenêtres n'avaient pas de segment, et le contrôle
    passait en silence : quand les segments ne font pas les actifs, la lecture le dit. Un
    client sans date de première transaction connue est compté à part, jamais « réactivé »."""
    rows = [row for row in _rows() if not (row["window"] == "ty" and row["segment"] == "arc")]
    rows.append(_row("LOEP", "ty", "unknown", 5, 6, 6 * 70.0))
    rows.append(_row("LOEP", "ty", "arc", 110, 176, 13_420.0))
    review = C.build(rows)
    assert [item.name for item in review.flow] == ["retained", "reactivated", "new", "unknown"]
    assert review.part("unknown").word.startswith("sans date")
    assert not any("ne fait pas le pont" in reason for reason in review.absent)

    short = [row for row in _rows() if row["segment"] != "new"]
    assert any("ne fait pas le pont" in reason for reason in C.build(short).absent)


def test_the_client_query_is_written_on_the_confirmed_columns():
    from app.perf import queries

    sql = queries.CLIENT_FLOW.lower()
    for word in ("client_skey", "flag_walkin", "client_first_purchase_date", "transaction_till",
                 "'1900-01-01'", "'retained'", "'reactivated'", "'new'", "'unknown'", "'lost'",
                 "'walkin'", "'arc'"):
        assert word in sql, word
    # Nouveau = première transaction après la fin de l'an dernier, pas « dans l'exercice » :
    # sinon les clients acquis entre les deux fenêtres n'ont pas de segment.
    assert "first_date > pr.ly_to" in sql


def test_a_noise_segment_leaves_the_table_and_a_short_window_is_said():
    """Quelques clients sans date à panier négatif ne prennent pas une ligne ; et sur cinq
    mois, la part perdue est celle qui n'est pas encore revenue, ce que la lecture dit."""
    rows = [row for row in _rows() if not (row["window"] == "ty" and row["segment"] == "arc")]
    rows.append(_row("LOEP", "ty", "unknown", 0.4, 1, -3.0))
    rows.append(_row("LOEP", "ty", "arc", 105.4, 171, 12_997.0))
    review = C.build(rows)

    assert [item.name for item in review.flow_shown] == ["retained", "reactivated", "new"]
    assert review.part("unknown").atv_label == "—" and review.part("unknown").atv_vs_base_label == "n/d"
    assert any("hors tableau" in reason for reason in review.absent)
    assert any("les fenêtres font 5 mois" in reason for reason in review.absent)


def test_the_lost_share_compares_to_last_year_at_the_same_month():
    """72 % de la base perdue n'est un chiffre que contre l'an dernier au même mois : la
    troisième fenêtre le donne, et la phrase le porte en points."""
    rows = _rows()
    rows += [
        _row("LOEP", "ly2", "arc", 90, 140, 11_000.0),
        _row("LOEP", "ly", "retained", 60, 100, 8_500.0),
        _row("LOEP", "ly", "lost", 30, 40, 2_500.0),
        _row("LOEP", "ly", "new", 30, 45, 2_600.0),
        _row("LOEP", "ly", "reactivated", 10, 15, 1_700.0),
    ]
    review = C.build(rows)

    assert review.lost.share_label == "40 % de la base"
    assert review.lost.before_share_label == "33 %" and review.lost.share_change_label == "+7 pts"
    assert "(33 % l'an dernier au même mois, +7 pts)" in review.read
    assert review.part("new").before_share_label == "30 %"
    assert not any("l'exercice d'avant n'est pas" in reason for reason in review.absent)

    without = C.build(_rows())
    assert without.lost.before is None and without.lost.before_share_label == "—"
    assert any("l'exercice d'avant n'est pas dans la lecture" in reason for reason in without.absent)


def test_the_client_query_carries_three_windows_and_classifies_last_year_too():
    from app.perf import queries

    sql = queries.CLIENT_FLOW.lower()
    assert "'ly2'" in sql and "ly2_from" in sql and "ly2_to" in sql
    assert '''cur."window" in ('ty', 'ly')''' in sql
    assert "dateadd(month, -38, current_date)" in sql
