"""Le same-store sales, deuxième chiffre du board, lu dans la lecture des KPI.

Ces tests gardent le calcul — le dernier mois contre le même l'an dernier, l'exercice à
date sur les mois qui existent des deux côtés — et ce que le chiffre dit de lui-même : des
magasins comparables, vrac compris, jamais « hors cleaning ». Valeurs inventées.
"""

from __future__ import annotations

from app.perf import samestore as S


def _rows(scope="LOEP", values=None):
    values = values or {}
    return [{"scope": scope, "kpi_key": "same_store_sales", "period": period, "value": value}
            for period, value in values.items()]


def test_the_month_and_the_fiscal_year_to_date_are_compared_to_last_year():
    values = {"2025-04": 100.0, "2025-05": 100.0, "2025-06": 100.0,
              "2026-04": 110.0, "2026-05": 99.0, "2026-06": 121.0}
    grown = S.build(_rows(values=values))

    assert grown.period == "2026-06"
    assert grown.growth_label == "+21.0 %"
    assert grown.ytd_growth_label == "+10.0 %"
    assert grown.months == 3 and grown.missing == []
    assert grown.ytd_label == "avril à juin"
    assert grown.word == "+10.0 %"
    assert "magasins comparables, sell-out, vrac compris" in grown.sentence
    assert "hors cleaning" not in grown.sentence


def test_a_month_without_last_year_is_named_and_left_out_of_the_cumul():
    values = {"2025-05": 100.0, "2026-04": 50.0, "2026-05": 105.0}
    grown = S.build(_rows(values=values))

    assert grown.ytd_growth_label == "+5.0 %"
    assert grown.missing == ["2026-04"]
    assert "sans l'an dernier sur avril 2026" in grown.sentence


def test_without_last_year_at_all_the_month_alone_is_said_and_the_word_follows_it():
    grown = S.build(_rows(values={"2026-08": 100.0}))

    assert grown.growth is None and grown.ytd_growth is None
    assert grown.word == "n/d"


def test_another_scope_reads_apart_and_nothing_is_invented_for_an_absent_one():
    rows = _rows(values={"2025-08": 100.0, "2026-08": 90.0}) + _rows("Japan", {"2025-08": 10.0, "2026-08": 12.0})

    assert S.build(rows).growth_label == "-10.0 %"
    assert S.build(rows, scope="Japan").growth_label == "+20.0 %"
    assert S.build(rows, scope="Nowhere") is None
    assert [item.scope for item in S.by_scopes(rows, ["Japan", "Nowhere"])] == ["Japan"]


def test_the_demo_rows_give_the_screen_a_reading():
    from app.perf import mock

    grown = S.build(mock.kpi_rows())
    assert grown is not None and grown.ytd_growth is not None
