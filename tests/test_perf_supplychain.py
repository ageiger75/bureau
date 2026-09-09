"""Ce que l'entrepôt voit de la supply : trois rapports de sommes, jamais des moyennes de
taux, nommés comme les mesures du cockpit et posés à côté du mail. Unités et valeurs
inventées.
"""

from __future__ import annotations

from app.perf import supplychain as S


def _osa(period, unit, rupture, demand):
    return {"period": period, "unit": unit, "rupture_eur": rupture, "demand_eur": demand, "lines": 1}


def _fc(period, market, forecast, actual):
    return {"period": period, "market": market, "forecast_eur": forecast, "actual_eur": actual}


def _order(period, channel, ordered, delivered, complete):
    return {"period": period, "channel": channel, "ordered_eur": ordered, "delivered_eur": delivered,
            "complete_eur": complete, "lines": 1}


def test_the_service_is_a_ratio_of_sums_on_the_latest_month_with_the_units_below_target_named():
    rows = [_osa("2026-07", "Northland", 5.0, 100.0), _osa("2026-08", "Northland", 1.0, 100.0),
            _osa("2026-08", "Southland", 27.0, 300.0)]
    review = S.build(osa_rows=rows)
    block = review.service
    assert block.month == "2026-08" and round(block.group.osa, 4) == 0.93
    assert [line.name for line in block.shown] == ["Southland", "Northland"]
    assert block.shown[0].below and not block.shown[1].below
    assert review.service_sentence == ("service en boutique d'août 2026, lu par l'entrepôt : 93.0 % ; "
                                       "sous la cible : Southland 91.0 %")
    assert [period for period, _rate in block.series] == ["2026-07", "2026-08"]


def test_the_bias_follows_the_report_s_sign_and_ignores_unpaired_rows():
    rows = [_fc("2026-08", "Northland", 108.0, 100.0), _fc("2026-08", "Eastland", 90.0, 100.0),
            _fc("2026-08", "Ghost", 50.0, 0.0), _fc("2026-08", "Other", 0.0, 40.0)]
    review = S.build(forecast_rows=rows)
    block = review.bias
    assert [line.name for line in block.shown] == ["Eastland", "Northland"] or \
        [line.name for line in block.shown] == ["Northland", "Eastland"]
    north = next(line for line in block.lines if line.name == "Northland")
    assert north.under and north.label == "+8.0 %" and north.word == "vend en dessous"
    east = next(line for line in block.lines if line.name == "Eastland")
    assert east.over and east.label == "-10.0 %"
    assert round(block.group.bias, 4) == -0.01 and "mesure du cockpit" in review.bias_sentence


def test_the_fill_reads_one_month_back_and_names_the_lowest_channel():
    rows = [_order("2026-08", "WEBP", 100.0, 95.0, 80.0), _order("2026-08", "DIS", 100.0, 60.0, 40.0),
            _order("2026-09", "WEBP", 100.0, 20.0, 10.0), _order("2026-09", "N/A", 50.0, 40.0, 30.0)]
    review = S.build(order_rows=rows)
    block = review.fill
    assert block.month == "2026-08" and "un mois de règlement" in review.fill_sentence
    assert round(block.group.fill, 3) == 0.775 and round(block.group.complete, 2) == 0.6
    assert S.Fill("N/A").channel_label == "sans canal"
    assert "le plus bas : Distributors 60.0 %" in review.fill_sentence
    assert "toutes marques" in review.fill_sentence


def test_the_mail_and_the_warehouse_meet_on_the_same_month_only():
    class Group:
        osa, bias, in_full = 0.98, -0.02, 0.97

    class Report:
        group, month = Group(), "2026-08"

    review = S.build(osa_rows=[_osa("2026-08", "NORTHLAND", 2.0, 100.0)],
                     forecast_rows=[_fc("2026-07", "N", 103.0, 100.0)],
                     order_rows=[_order("2026-08", "DIS", 100.0, 90.0, 50.0),
                                 _order("2026-09", "DIS", 100.0, 10.0, 0.0)])
    assert review.service.shown[0].unit_label == "Northland"
    lines = review.against(Report())
    assert len(lines) == 2
    assert lines[0].startswith("service en boutique d'août 2026 : le mail dit 98.0 %, l'entrepôt voit 98.0 % (+0.0 pt)")
    assert "livré en entier" in lines[1] and "(-7.0 pt)" in lines[1]


def test_nothing_read_is_a_stated_absence():
    review = S.build(notes=["pas encore lu"])
    assert not review.usable and review.notes == ["pas encore lu"]
    assert review.service_sentence == "" and review.against(None) == []
