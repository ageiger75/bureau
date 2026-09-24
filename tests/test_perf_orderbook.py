"""Le carnet de commandes ouvert : trois paquets sur la date de promesse, par marché, et
sa date de lecture. Valeurs et marchés inventés."""

from __future__ import annotations

from app.perf import mock, orderbook as O, page as P, track


def test_the_book_reads_late_month_and_beyond_by_market_and_sums_a_perimeter():
    review = O.build(mock.orderbook_rows(), read_at="2026-09-24 08:00 UTC")
    assert review.usable and review.read_label == "lu le 2026-09-24 08:00 UTC"
    japan = review.markets["Japan"]
    assert japan.month == 420_000.0 and japan.late == 90_000.0 and japan.beyond == 1_500_000.0
    assert japan.due == 510_000.0 and japan.blocked == 30_000.0
    china = review.markets["China"]
    assert china.late > china.month and "le retard dépasse le promis du mois" in china.sentence
    both = review.for_markets(["Japan", "France"], "Nord")
    assert both is not None and both.month == 680_000.0 and both.late == 130_000.0
    assert review.for_markets(["Nulle part"]) is None
    assert O.build([]).note == "le carnet de commandes n'est pas lu" and not O.build([]).usable


def test_the_together_card_projects_the_month_of_sell_in_from_the_book():
    class _Billed:
        current, share_by_now = 560.0, 0.46

    sell_out = track.Verdict(440.0, 500.0, 580.0, 1.0)
    book = O.Book("Nord")
    book.add("month", 300.0, 0.0, 3)
    book.add("late", 200.0, 50.0, 2)
    together = P.Together(sell_out, _Billed(), 1_000.0, book=book, book_read="2026-09-24 08:00 UTC")
    assert together.month_end_sell_in == 1_060.0
    assert together.month_end_verdict.label == "en avance"
    text = together.book_sentence
    assert text.startswith("avec le carnet : facturé") and "contre" in text and "en avance" in text
    assert "carnet lu le 2026-09-24 08:00 UTC" in text and "manque au mois" not in text

    late_book = O.Book("Nord")
    late_book.add("late", 400.0, 0.0, 4)
    late_book.add("month", 100.0, 0.0, 1)
    late = P.Together(sell_out, _Billed(), 1_000.0, book=late_book)
    assert "le retard dépasse le promis" in late.book_sentence

    assert P.Together(sell_out, _Billed(), 1_000.0).book_sentence == ""


def test_the_order_queries_never_read_the_proxies():
    from app.perf import queries

    assert "proxy" not in queries.ORDER_FILL and "is_fully_delivered" not in queries.ORDER_FILL
    assert "net_value_eur_annual - coalesce(open_net_value_eur_annual, 0)" in queries.ORDER_FILL
    assert "delivery_status_code = 'C'" in queries.ORDER_FILL
    book = queries.ORDER_BOOK
    assert "try_to_number(o.bill_to_skey)" in book and "try_to_number(o.product_skey)" in book
    assert "committed_delivery_date" in book and "open_net_value_eur_annual > 0" in book
    assert "p.channel_type_desc in ('SELL IN', 'B2B')" in book and "k.product_brand_id = 'OC'" in book
    assert "proxy" not in book and "billed" not in book
    assert queries.ALL["ORDER_BOOK"] is book
