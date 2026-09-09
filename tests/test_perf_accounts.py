"""Les partenaires de sell-in par leur nom : l'exercice à date et trois mois contre l'an
dernier, la part du canal, le plan du canal en face — et jamais un nom deviné.
Codes, partenaires et valeurs inventés.
"""

from __future__ import annotations

from app.perf import accounts as A


def _rows(code, label, channel, months, iso2="LU"):
    return [{"period": period, "code": code, "label": label, "channel": channel,
             "iso2": iso2, "net_eur": value} for period, value in months.items()]


def _flat(value, start_year=2025):
    months = {}
    for year in (start_year, start_year + 1):
        for month in range(1, 13):
            months["%04d-%02d" % (year, month)] = value
    return {m: v for m, v in months.items() if "2025-04" <= m <= "2026-08"}


def test_the_fiscal_year_opens_in_april():
    assert A.fiscal_start("2026-08") == "2026-04"
    assert A.fiscal_start("2027-02") == "2026-04"
    assert A._months_between("2026-04", "2026-06") == ["2026-04", "2026-05", "2026-06"]


def test_a_partner_reads_against_last_year_on_both_windows_and_against_its_channel_plan():
    steady = _flat(100.0)
    rising = {m: (130.0 if m >= "2026-04" else 100.0) for m in steady}
    rows = _rows("PC_A", "ORBIS MARKET", "WEBP", rising) + _rows("PC_B", "NORDIC WEB", "WEBP", steady)
    review = A.build(rows, names={"PC_A": "Orbis"}, channel_gaps={"webp": -250.0})

    assert review.usable and review.through == "2026-08" and review.start == "2026-04"
    orbis, nordic = review.shown
    assert orbis.name == "Orbis" and orbis.named
    assert nordic.name == "Nordic Web" and not nordic.named
    assert round(orbis.growth_ytd or 0.0, 6) == 0.3 and round(orbis.growth_recent or 0.0, 6) == 0.3
    assert orbis.word == "avance" and nordic.word == "en ligne avec l'an dernier"
    assert orbis.share_label == "57 %" and orbis.channel_label == "E-retailers"
    assert orbis.channel_plan_label == "canal 250 € en dessous du plan à date"
    assert "Orbis" in review.headline and "nommé" in review.headline
    assert review.question.startswith("Orbis avance de 30.0 % sur trois mois")
    assert "Nordic Web" in review.unnamed_note


def test_a_partner_without_last_year_says_so_instead_of_a_growth():
    rows = _rows("PC_C", "GRAND BAZAR", "DPT", {"2026-06": 10.0, "2026-07": 10.0, "2026-08": 10.0})
    review = A.build(rows)
    partner = review.shown[0]
    assert partner.growth_ytd is None and partner.word == "sans an dernier"
    assert partner.growth_ytd_label == "n/d" and partner.channel_plan_label == "plan du canal non lu"
    assert review.question == ""


def test_the_plan_has_no_partner_line_and_the_review_says_it():
    review = A.build(_rows("PC_A", "X", "WEBP", _flat(1.0)))
    assert "pas de ligne par partenaire" in review.plan_note


def test_a_slipped_order_reads_as_a_recent_dip_not_a_retreat():
    months = _flat(100.0)
    months["2026-08"] = 40.0
    review = A.build(_rows("PC_A", "X", "WEBP", months))
    partner = review.shown[0]
    assert (partner.growth_ytd or 0.0) < 0 and partner.word in ("fléchit depuis peu", "recule")
    assert partner.growth_recent_label.startswith("-")


def test_names_come_from_the_sell_in_lines_of_the_partners_file():
    class Line:
        def __init__(self, base, profit_centre, partner):
            self.base, self.profit_centre, self.partner = base, profit_centre, partner

    class Partners:
        lines = [Line("sell_in", "pc_a", "Orbis"), Line("sell_out", "PC_B", "Shop"),
                 Line("sell_in", "PC_C", "")]

    assert A.names_from(Partners()) == {"PC_A": "Orbis"}


def test_an_empty_reading_is_a_stated_absence():
    review = A.build([], note="pas encore lu")
    assert not review.usable and review.note == "pas encore lu" and review.headline == ""
