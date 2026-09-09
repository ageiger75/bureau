"""Le gris et le vrac : le vrac lu marché par marché contre l'an dernier, d'où il vient,
et le budget des flux à nettoyer en face, en ordre de grandeur. Marchés et valeurs inventés.
"""

from __future__ import annotations

from app.perf import grey as G


def _rows(scope, sales, bulk_share, start="2025-04", through="2026-08", bump=None):
    rows = []
    year, month = int(start[:4]), int(start[5:7])
    while "%04d-%02d" % (year, month) <= through:
        period = "%04d-%02d" % (year, month)
        share = bulk_share
        if bump and period >= bump[0]:
            share = bump[1]
        rows.append({"scope": scope, "kpi_key": "net_sales", "period": period, "value": sales})
        rows.append({"scope": scope, "kpi_key": "net_sales_hors_bulk", "period": period,
                     "value": sales * (1 - share)})
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return rows


class _Line:
    def __init__(self, name, sales):
        self.name, self.sales = name, sales


class _Plan:
    unhealthy = [_Line("FLUX UN", 600.0), _Line("FLUX DEUX", 600.0)]
    unhealthy_total = _Line("TOTAL", 1200.0)


def test_the_bulk_is_read_per_market_with_its_origin_and_its_growth():
    rows = (_rows("LOEP", 1000.0, 0.05, bump=("2026-04", 0.06))
            + _rows("Northland", 500.0, 0.08, bump=("2026-04", 0.10))
            + _rows("Eastland", 300.0, 0.02) + _rows("Westland", 200.0, 0.0))
    review = G.build(rows)

    assert review.usable and review.start == "2026-04" and review.through == "2026-08"
    assert G.build(_rows("LOEP", 1.0, 0.1) + _rows("HONG KONG", 1.0, 0.1)).shown[0].scope == "Hong Kong"
    assert review.group.bulk == 300.0 and review.group.bulk_ly == 250.0
    assert review.group.word == "monte" and "le vrac lu monte" in review.headline
    assert [item.scope for item in review.shown] == ["Northland", "Eastland"]
    assert review.origin_sentence == "il vient de Northland 83 %, Eastland 10 %"
    assert review.shown[0].share_label == "10 %" and review.shown[0].word == "monte"
    assert review.shown[1].word == "tient"
    assert review.question.startswith("Northland : le vrac monte de 25.0 %")
    assert len(review.series) == 6 and review.series[-1][0] == "2026-08"


def test_the_budget_s_cleaning_flows_sit_in_front_as_an_order_of_magnitude():
    rows = _rows("LOEP", 1000.0, 0.05) + _rows("Northland", 500.0, 0.10)
    review = G.build(rows, plan=_Plan())
    assert review.expected_to_date == 500.0
    assert "FLUX UN, FLUX DEUX" in review.plan_sentence
    assert "en dessous" in review.plan_sentence and "ne marque pas" in review.plan_sentence

    without = G.build(rows)
    assert "pas de ligne de plan" in without.plan_sentence


def test_shares_never_exceed_the_markets_sum_when_the_group_is_read_smaller():
    rows = _rows("LOEP", 1000.0, 0.01) + _rows("Northland", 500.0, 0.10)
    review = G.build(rows)
    assert review.total_bulk == 250.0 and review.origin_sentence == "il vient de Northland 100 %"


def test_without_the_two_bases_the_reading_is_a_stated_absence():
    review = G.build([{"scope": "LOEP", "kpi_key": "net_sales", "period": "2026-08", "value": 1.0}])
    assert not review.usable and "deux bases" in review.note
