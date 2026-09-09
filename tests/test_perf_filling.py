"""L'indice de remplissage : le sell-in qui court devant ce qu'on sait de la vente.

Sans sell-through dans l'entrepôt, le rythme du sell-in est le seul signal de stock en
réseau, et il est nommé comme un indice. Ces tests gardent le calcul — trois mois contre
le rythme de douze et contre l'an dernier — et ce que le bloc dit de ce qu'il ne sait pas.
Segments et valeurs inventés.
"""

from __future__ import annotations

from app.perf import filling as F


def _current(segment, months, ly=100.0):
    return [{"entity": "ENT_1", "segment": segment, "period": "2026-%02d" % month,
             "sales_actual": value, "sales_last_year": ly}
            for month, value in months.items()]


def _closed(segment, value=100.0):
    return [{"entity": "ENT_1", "segment": segment, "period": period, "value": value}
            for period in ("2025-%02d" % m for m in range(4, 13))] + [
        {"entity": "ENT_1", "segment": segment, "period": "2026-%02d" % m, "value": value}
        for m in (1, 2, 3)]


def test_a_channel_billed_a_quarter_above_its_rhythm_and_last_year_is_filling():
    rows = _current("TRA - Travel Retail", {4: 100.0, 5: 100.0, 6: 150.0, 7: 150.0, 8: 150.0})
    rows += _current("DIS - Distributors", {4: 100.0, 5: 100.0, 6: 100.0, 7: 100.0, 8: 100.0})
    review = F.build(rows, _closed("TRA - Travel Retail") + _closed("DIS - Distributors"))

    assert review.months == ["2026-06", "2026-07", "2026-08"]
    travel = next(channel for channel in review.channels if channel.code == "tra")
    assert travel.recent == 450.0 and travel.last_year == 300.0
    # Le rythme : les douze derniers mois, sept clos à cent et cinq de l'exercice.
    assert round(travel.trailing_monthly, 2) == round((7 * 100 + 200 + 450) / 12, 2)
    assert travel.filling and travel.word == "se remplit"
    assert travel.known.startswith("aucun sell-through")
    distributors = next(channel for channel in review.channels if channel.code == "dis")
    assert not distributors.filling and distributors.word == "au rythme"
    assert review.sentence.startswith("Travel Retail se remplit plus vite qu'il ne vendait")
    assert "un indice, pas une mesure" in review.basis


def test_own_channels_are_left_out_and_partial_sell_through_is_named():
    rows = _current("RET - Retail", {6: 100.0, 7: 100.0, 8: 100.0})
    rows += _current("WEBP - Web Partners", {6: 100.0, 7: 100.0, 8: 100.0})
    review = F.build(rows, [])

    assert [channel.code for channel in review.channels] == ["webp"]
    assert review.channels[0].known.startswith("partiel")
    assert any("le rythme est lu sur 3 mois" in reason for reason in review.absent)
    assert not F.build([], []).usable


def test_the_invented_series_show_one_channel_filling():
    from app.perf import mock

    current, closed = mock.sell_in_series()
    review = F.build(current, closed)
    assert [channel.label for channel in review.filling] == ["Travel Retail"]
