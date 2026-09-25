"""Le carnet de commandes ouvert : trois paquets sur la date de promesse, par canal, au
niveau du groupe, et sa date de lecture. Valeurs inventées."""

from __future__ import annotations

from app.perf import mock, orderbook as O


def test_the_book_reads_late_month_and_beyond_by_channel_and_says_who_carries_the_late():
    review = O.build(mock.orderbook_rows(), read_at="2026-09-25 08:00 UTC")
    assert review.usable and review.read_label == "carnet lu le 2026-09-25 08:00 UTC"
    webp = review.channels["WEBP"]
    assert webp.month == 420_000.0 and webp.late == 90_000.0 and webp.blocked == 30_000.0
    group = review.group
    assert group.month == 800_000.0 and group.late == 1_030_000.0 and group.beyond == 5_500_000.0
    assert group.due == 1_830_000.0 and group.late_exceeds_month
    text = review.sentence
    assert text.startswith("carnet ouvert : promis d'ici la fin du mois")
    assert "dont Travel Retail" in text and "(87 %)" in text
    assert "le retard dépasse le promis du mois" in text and "carnet lu le 2026-09-25 08:00 UTC" in text
    assert [b.name for b in review.shown][:2] == ["TRA", "WEBP"]
    assert O.build([]).note == "le carnet de commandes n'est pas lu" and not O.build([]).usable
    assert "n'est pas lu" in O.build([]).sentence


def test_the_order_queries_read_forward_only():
    from app.perf import queries, source

    assert queries.ORDER_FILL.strip() == ""
    assert "proxy" in source.ORDER_FILL_NOTE and source.MockSource().order_rows() == []
    book = queries.ORDER_BOOK
    assert "try_to_number(o.bill_to_skey)" in book and "try_to_number(o.product_skey)" in book
    assert "committed_delivery_date" in book and "open_net_value_eur_annual > 0" in book
    assert "p.channel_type_desc in ('SELL IN', 'B2B')" in book and "k.product_brand_id = 'OC'" in book
    assert "country" not in book and "market" not in book
    assert "proxy" not in book and "billed" not in book
    assert queries.ALL["ORDER_BOOK"] is book
