"""Où en est le mois, par périmètre — la pièce de B3 que le lecteur voit.

Ces tests gardent la jointure et ses trois absences nommées. Le calcul des deux taux est
gardé ailleurs, dans les tests du module de rythme.
"""

from __future__ import annotations

from app.perf import month as M
from app.perf import pace


def _phasing(tmp_path, market="JAPAN", month="09"):
    rows = ["market,month,week,share,year"]
    for year, shares in (("FY2025", (0.20, 0.25, 0.25, 0.20, 0.10)),
                         ("FY2026", (0.22, 0.23, 0.25, 0.20, 0.10))):
        for index, share in enumerate(shares):
            rows.append("%s,%s,%d,%s,%s" % (market, month, index + 1, share, year))
    path = tmp_path / "phasing.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return pace.load(str(path))


def _rows(through="2026-09-17"):
    return [{"market": "JAPAN", "iso2": "JP", "sales_to_date": 2_000_000.0,
             "read_through": through},
            {"market": "NORTHLAND", "iso2": "NL", "sales_to_date": 500_000.0,
             "read_through": through}]


def test_the_two_rates_are_read_side_by_side_and_never_alone(tmp_path):
    """Le besoin tient en une phrase : où j'en suis dans le mois, pas seulement à la fin.
    Un seul nombre n'y répond pas — l'écart entre les deux est l'information."""
    review = M.build(_rows(), {"Japan": 4_000_000.0}, _phasing(tmp_path))

    japan = next(line for line in review.lines if line.market == "Japan")
    assert review.week == 3 and review.month == "2026-09"
    assert japan.readable
    assert japan.month_done == "70 %"       # 0.20+0.25+0.25 = 0.70 · 0.22+0.23+0.25 = 0.70
    assert japan.target_done == "50 %"
    assert japan.behind == "+20 pts"


def test_a_market_without_a_month_shape_says_so_instead_of_using_the_days_elapsed(tmp_path):
    review = M.build(_rows(), {"Japan": 4_000_000.0, "Northland": 1_000_000.0},
                     _phasing(tmp_path))

    northland = next(line for line in review.lines if line.market == "Northland")
    assert not northland.readable
    assert "forme du mois non mesurée" in northland.absent
    assert northland.target_done == "50 %"   # l'objectif se lit quand même


def test_a_market_without_a_plan_line_is_not_a_market_at_zero(tmp_path):
    review = M.build(_rows(), {"Japan": 4_000_000.0}, _phasing(tmp_path))

    northland = next(line for line in review.lines if line.market == "Northland")
    assert "aucun objectif au plan" in northland.absent


def test_the_week_comes_from_the_last_day_read_and_not_from_today(tmp_path):
    """L'écran se lit un lundi sur des ventes arrêtées au vendredi : la semaine est celle
    du dernier jour lu, sinon le mois paraît en retard de trois jours qui n'existent pas."""
    review = M.build(_rows(through="2026-09-08"), {"Japan": 4_000_000.0},
                     _phasing(tmp_path))

    assert review.week == 2 and review.through == "2026-09-08"


def test_markets_are_grouped_by_perimeter_and_the_md_is_named(tmp_path):
    """Le lecteur lit par périmètre, le MD nommé, ses marchés dessous. Un marché
    qu'aucun périmètre ne place est rendu à part — jamais rangé par ressemblance."""
    class Person:
        def __init__(self, name, perimeter, zone):
            self.name, self.perimeter, self.zone = name, perimeter, zone

    class Org:
        usable = True
        people = [Person("Une dirigeante", "Japon", "Japon")]

        def leads(self):
            return {"Japon": self.people[0]}

    review = M.build(_rows(), {"Japan": 4_000_000.0}, _phasing(tmp_path), org=Org())

    assert [group.name for group in review.groups] == ["Japon"]
    assert review.groups[0].lead == "Une dirigeante"
    assert [line.market for line in review.unplaced] == ["Northland"]


def test_without_an_org_the_markets_are_still_read_and_the_absence_is_named(tmp_path):
    review = M.build(_rows(), {"Japan": 4_000_000.0}, _phasing(tmp_path), org=None)

    assert review.usable and not review.groups
    assert any("organigramme absent" in reason for reason in review.absent)


def test_a_month_with_nothing_read_is_an_absence_and_not_a_month_at_zero():
    review = M.build([], {}, None)

    assert not review.usable
    assert "aucune vente lue" in review.absent[0]


def test_the_shape_uncertainty_is_kept_as_a_range_on_the_screen(tmp_path):
    rows = ["market,month,week,share,year"]
    for year, shares in (("FY2025", (0.20, 0.20, 0.40, 0.20)),
                         ("FY2026", (0.20, 0.55, 0.05, 0.20))):
        for index, share in enumerate(shares):
            rows.append("JAPAN,09,%d,%s,%s" % (index + 1, share, year))
    path = tmp_path / "phasing.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    review = M.build(_rows(through="2026-09-10"), {"Japan": 4_000_000.0},
                     pace.load(str(path)))

    japan = next(line for line in review.lines if line.market == "Japan")
    assert japan.month_done == "40–75 %"
    assert japan.behind == "-10 à +25 pts"


def test_targets_come_from_sell_out_lines_of_the_month_only():
    class Line:
        def __init__(self, market, segment, period, budget):
            self.market, self.segment, self.period, self.budget = (
                market, segment, period, budget)

    class Budget:
        lines = [Line("Japan", "RET - Retail", "2026-09", 1_000.0),
                 Line("Japan", "EBU - E-business", "2026-09", 500.0),
                 Line("Japan", "WHS - Wholesale", "2026-09", 9_000.0),   # sell-in
                 Line("Japan", "RET - Retail", "2026-08", 7_000.0)]      # autre mois

    assert M.targets_from_budget(Budget(), "2026-09") == {"Japan": 1_500.0}


def test_the_sell_in_is_declared_without_a_rate_rather_than_interpolated(tmp_path):
    review = M.build(_rows(), {"Japan": 4_000_000.0}, _phasing(tmp_path))

    assert "n'avance pas en jours" in review.sell_in
