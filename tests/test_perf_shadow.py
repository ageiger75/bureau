"""Le gris sans drapeau : gros tickets et prix hors norme lus sur le fait, et qui pose le
drapeau. Marchés, points de vente et valeurs inventés."""

from __future__ import annotations

from app.perf import shadow as S


def _rows(market, store, sub_channel, kind, monthly, flagged_share, start="2025-04", through="2026-08"):
    rows = []
    year, month = int(start[:4]), int(start[5:7])
    while "%04d-%02d" % (year, month) <= through:
        period = "%04d-%02d" % (year, month)
        value = monthly * (1.3 if period >= "2026-04" else 1.0)
        rows.append({"period": period, "market": market, "store": store, "sub_channel": sub_channel,
                     "kind": kind, "net_eur": value, "lines": 10, "flagged_eur": value * flagged_share})
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return rows


ROWS = (_rows("NORTHLAND", "ST-N-1", "SHOP IN SHOP", "quantity", 100.0, 0.1)
        + _rows("NORTHLAND", "ST-N-2", "SHOP IN SHOP", "quantity", 40.0, 0.0)
        + _rows("EASTLAND", "ST-E-1", "SHOP IN SHOP", "quantity", 80.0, 0.95)
        + _rows("NORTHLAND", "ST-N-9", "OUTLET", "price", 30.0, 0.0))


def test_big_tickets_and_odd_prices_are_read_apart_and_the_marking_is_told():
    review = S.build(ROWS)

    assert review.usable and review.window_label == "exercice à date, avril à août"
    north = review.for_market("Northland")
    assert north is not None and north.quantity.usable and north.price.usable
    assert north.quantity.ytd == 5 * 140.0 * 1.3
    assert north.quantity.growth is not None and abs(north.quantity.growth - 0.3) < 1e-9
    assert round(north.quantity.marking, 3) == round(100.0 / 140.0 * 0.1, 3)
    assert north.quantity.marks_its_bulk is False
    assert north.price.ytd == 5 * 30.0 * 1.3 and north.price.marking is None
    assert [store.code for store in north.quantity.shown] == ["ST-N-1", "ST-N-2"]
    # Un marché inventé n'est pas dans la liste des marchés validés par la Finance : son
    # zéro est un zéro de méthode, et la phrase le dit au lieu d'accuser le marché.
    assert "n'est pas validé par la Finance" in north.quantity.sentence
    assert "ne pose pas le drapeau" not in north.quantity.sentence
    east = review.for_market("Eastland")
    assert east.quantity.marks_its_bulk is True and "ne pose pas" not in east.quantity.sentence
    assert review.unmarked == [] and [m.scope for m in review.unvalidated] == ["Northland", "Eastland"]
    assert "drapeau non validé par la Finance, un zéro de méthode : 2 marchés" in review.headline


def test_a_validated_market_that_leaves_its_big_tickets_unmarked_is_told_so():
    rows = (_rows("CHINA", "ST-CN-1", "SHOP IN SHOP", "quantity", 100.0, 0.1)
            + _rows("HONG KONG", "ST-HK-1", "SHOP IN SHOP", "quantity", 80.0, 0.95))
    review = S.build(rows)
    china = review.for_market("China")
    assert china.quantity.flag_validated and china.quantity.marks_its_bulk is False
    assert "ne pose pas le drapeau" in china.quantity.sentence
    assert [m.scope for m in review.unmarked] == ["China"] and review.unvalidated == []
    assert "ne posent pas le drapeau : China" in review.headline


def test_the_window_stops_where_the_kpi_readings_stop_and_empty_rows_say_so():
    review = S.build(ROWS, through="2026-06")
    assert review.through == "2026-06"
    assert S.build([]).note == "le gris sans drapeau n'est pas encore lu"
    assert not S.build([]).usable


def test_the_unmarked_euros_and_who_carries_them_are_named():
    """Un marché qui marque ses grands comptes et pas le reste a un vrac marqué qui est un
    plancher : la mesure qui manquait est l'écart, et les points de vente qui le portent."""
    north = S.build(ROWS).for_market("Northland").quantity
    assert round(north.unmarked, 6) == round(north.ytd - north.flagged_ytd, 6)
    assert [store.code for store in north.unmarked_stores] == ["ST-N-1", "ST-N-2"]
    assert north.stores[0].unmarked_label in north.sentence and "non marqués" in north.sentence
    assert S.build(ROWS).for_market("Northland").price.unmarked == 0.0
