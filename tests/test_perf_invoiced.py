"""Le sell-in du mois : facturé depuis le 1er, contre les mêmes premiers jours facturés l'an
dernier. Ces tests gardent l'alignement à jours facturés égaux, la fenêtre à dates égales
rendue à côté, le canal lu par code, et l'absence de tout plan. Tout est inventé."""

from __future__ import annotations

import datetime

from app.perf import invoiced as I

TODAY = datetime.date(2026, 9, 6)


def _rows():
    rows = []
    # Cette année : mardi 1er à samedi 5 septembre, quatre jours ouvrés facturés (mar-ven).
    for day in (1, 2, 3, 4):
        rows.append({"window": "current", "invoice_date": "2026-09-%02d" % day, "iso2": "JP",
                     "channel": "WEBP", "net_eur": 100.0})
        rows.append({"window": "current", "invoice_date": "2026-09-%02d" % day, "iso2": "FR",
                     "channel": "dis", "net_eur": 50.0})
    # L'an dernier : lundi 1er à vendredi 5, cinq jours facturés, puis la suite du mois.
    for day in range(1, 27):
        if datetime.date(2025, 9, day).weekday() < 5:
            rows.append({"window": "last_year", "invoice_date": "2025-09-%02d" % day, "iso2": "JP",
                         "channel": "WEBP", "net_eur": 80.0})
            rows.append({"window": "last_year", "invoice_date": "2025-09-%02d" % day, "iso2": "FR",
                         "channel": "dis", "net_eur": 50.0})
    return rows


def test_the_month_is_compared_on_equal_business_days_and_the_calendar_window_beside():
    review = I.build(_rows(), {"JP": "Japan", "FR": "France"}, today=TODAY)

    assert review.usable
    assert review.days == 4
    assert review.title == "Sell-in facturé du 1er au 4 septembre"
    # 600 facturés sur quatre jours ouvrés ; l'an dernier, quatre jours ouvrés depuis le
    # lundi 1er septembre 2025 s'arrêtent au jeudi 4 : 4 × 130 = 520.
    assert review.group.current == 600.0
    assert review.group.aligned == 520.0
    assert review.group.growth_label == "+15 %"
    assert ", +15 % à jours ouvrés égaux sur septembre 2025 (4 jours ouvrés)" in review.sentence
    assert "à dates égales" in review.sentence


def test_a_saturday_in_the_window_counts_in_the_total_never_in_the_growth():
    """Mardi 1er à samedi 5 septembre 2026 : quatre jours ouvrés et un samedi. La croissance
    compare les quatre jours ouvrés aux quatre premiers de l'an dernier, lundi 1er à jeudi 4 ;
    le samedi reste dans le facturé à date, et la fenêtre à dates égales prend le vendredi 5
    de l'an dernier, elle."""
    rows = _rows()
    rows.append({"window": "current", "invoice_date": "2026-09-05", "iso2": "JP",
                 "channel": "WEBP", "net_eur": 10.0})
    review = I.build(rows, {"JP": "Japan", "FR": "France"}, today=TODAY)

    assert review.days == 4
    assert review.title == "Sell-in facturé du 1er au 5 septembre"
    assert review.group.current == 610.0 and review.group.current_business == 600.0
    assert review.group.aligned == 520.0
    assert review.group.growth_label == "+15 %"
    assert review.group.same_dates == 650.0
    assert "dont 10 € le week-end" in review.sentence
    assert I.aligned_end(datetime.date(2025, 9, 1), 4) == datetime.date(2025, 9, 4)
    assert I.aligned_end(datetime.date(2026, 8, 1), 1) == datetime.date(2026, 8, 3)
    assert I.business_days(datetime.date(2026, 9, 1), datetime.date(2026, 9, 5)) == 4


def test_channels_are_read_by_profit_centre_code_and_named_for_the_screen():
    review = I.build(_rows(), {"JP": "Japan", "FR": "France"}, today=TODAY)
    by_name = {line.name: line for line in review.channels}

    assert set(by_name) == {"E-retailers", "Distributors"}
    assert by_name["E-retailers"].current == 400.0
    assert by_name["E-retailers"].growth_label == "+25 %"
    assert by_name["Distributors"].growth_label == "+0 %"


def test_countries_become_markets_and_markets_become_perimeters(tmp_path):
    from tests.test_perf_owners import HEADER, directory_file
    from app.perf import owners

    directory = owners.load(directory_file(tmp_path, [
        ["Annuaire"], HEADER,
        ["Japon", "Aiko", "TANAKA", "General Manager, Japan", "Japon", "Patron de BU", "", "Tokyo"],
    ]))
    review = I.build(_rows(), {"JP": "Japan", "FR": "France"}, directory=directory, today=TODAY)

    assert [line.name for line in review.perimeters] == ["Japon"]
    assert review.for_name("Japon").current == 400.0
    assert review.loose is not None and review.loose.current == 200.0


def test_a_missing_last_year_is_said_and_nothing_is_compared_to_the_plan():
    rows = [row for row in _rows() if row["window"] == "current"]
    review = I.build(rows, {}, today=TODAY)

    assert any("aucune facture sur ce mois" in reason for reason in review.absent)
    assert review.group.growth_label == "—"
    assert "jamais contre le plan" in review.note
    for name in ("budget", "plan", "target", "gap"):
        assert not hasattr(review.group, name)


def test_without_invoices_the_review_names_it():
    review = I.build([], {}, today=TODAY)

    assert not review.usable
    assert review.absent == ["aucune facture lue sur le mois en cours : le sell-in du mois ne se lit pas"]


def test_codes_that_are_not_commercial_channels_are_kept_apart_and_named():
    rows = _rows()
    rows.append({"window": "current", "invoice_date": "2026-09-02", "iso2": "FR",
                 "channel": "HOLD", "net_eur": 1000.0})
    rows.append({"window": "current", "invoice_date": "2026-09-02", "iso2": "FR",
                 "channel": "", "net_eur": 5.0})
    review = I.build(rows, {"JP": "Japan", "FR": "France"}, today=TODAY)

    assert review.group.current == 600.0
    assert review.other.current == 1005.0
    assert review.other_codes == ["HOLD", "vide"]
    assert review.other_note.startswith("%s facturés hors canaux commerciaux (HOLD, vide)" % __import__("app.perf.analytics", fromlist=["format_eur"]).format_eur(1005.0))
    assert all(line.name != "HOLD" for line in review.channels)
