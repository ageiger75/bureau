"""Sommes-nous en ligne avec le plan — le mois en cours et l'exercice à date.

Ces tests gardent le verdict : un mot qui ne sort que si le réalisé quitte l'attendu de
plus que la tolérance, une fourchette qui contient le réalisé lue « en ligne », et un
exercice qui additionne des mois clos publiés au mois en cours sans jamais inventer un
mois manquant. Toutes les valeurs sont inventées.
"""

from __future__ import annotations

from app.perf import actuals, month as M, pace, track as T


def _phasing(tmp_path, markets=("NORTHLAND", "SOUTHLAND")):
    rows = ["market,month,week,share,year"]
    for market in markets:
        for year, shares in (("FY2025", (0.20, 0.25, 0.25, 0.20, 0.10)),
                             ("FY2026", (0.22, 0.23, 0.25, 0.20, 0.10)),
                             ("FY2027", (0.25, 0.25, 0.20, 0.20, 0.10))):
            for index, share in enumerate(shares):
                rows.append("%s,09,%d,%s,%s" % (market, index + 1, share, year))
    path = tmp_path / "phasing.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return pace.load(str(path))


def _rows(north, south, through="2026-09-14"):
    return [{"market": "NORTHLAND", "iso2": "NL", "sales_to_date": north,
             "read_through": through},
            {"market": "SOUTHLAND", "iso2": "SL", "sales_to_date": south,
             "read_through": through}]


class _Directory:
    class _Entry:
        def __init__(self, bu, name):
            self.bu, self.name = bu, name

    def __init__(self, table):
        self.table = table

    def __len__(self):
        return len(self.table)

    def entry_for(self, market, region=""):
        found = self.table.get(market)
        return self._Entry(*found) if found else None


DIRECTORY = _Directory({"Northland": ("Nord", "Personne N"), "Southland": ("Sud", "Personne S")})


def _review(tmp_path, north, south, targets=None):
    targets = targets or {"Northland": 1_000_000.0, "Southland": 500_000.0}
    return M.build(_rows(north, south), targets, _phasing(tmp_path), directory=DIRECTORY)


def _published(period_year, period_month, lines):
    read = actuals.Actuals(lines, [], year=period_year, month=period_month)
    return read


def _line(market, actual, budget):
    return actuals.Line(market, "R", "retail", actuals.SOLD, actual, 0.0, budget)


# ------------------------------------------------------------------------ le mois


def test_the_month_is_in_line_when_the_band_contains_the_actual(tmp_path):
    """Au 14, deux semaines pleines : 45 à 50 % du mois d'ordinaire selon l'exercice. Un
    réalisé de 45 % du plan est dans la fourchette, donc en ligne — et l'écart se lit du
    pire au meilleur cas."""
    review = _review(tmp_path, north=450_000.0, south=225_000.0)
    track = T.build(review)

    month = track.group.month
    assert month.usable
    assert month.label == T.IN_LINE
    assert month.actual == 675_000.0
    assert abs(month.low - 1_500_000.0 * 0.45) < 1e-6
    assert abs(month.high - 1_500_000.0 * 0.50) < 1e-6
    assert month.coverage_label == "100 %"
    assert month.gap_label == "-10.0 à +0.0 %"


def test_the_month_is_behind_only_beyond_the_tolerance(tmp_path):
    behind = T.build(_review(tmp_path, north=380_000.0, south=190_000.0))
    ahead = T.build(_review(tmp_path, north=800_000.0, south=400_000.0))

    assert behind.group.month.label == T.BEHIND
    assert ahead.group.month.label == T.AHEAD


def test_a_market_without_a_plan_is_out_of_both_terms_and_counted(tmp_path):
    review = _review(tmp_path, north=450_000.0, south=225_000.0,
                     targets={"Northland": 1_000_000.0})
    track = T.build(review)

    month = track.group.month
    assert month.actual == 450_000.0
    assert month.coverage_label == "100 %"
    assert any("Sud" == scope.name and not scope.month.usable for scope in track.perimeters)


def test_each_perimeter_gets_its_own_word(tmp_path):
    review = _review(tmp_path, north=450_000.0, south=100_000.0)
    track = T.build(review)
    by_name = {scope.name: scope for scope in track.perimeters}

    assert by_name["Nord"].lead == "Personne N"
    assert by_name["Nord"].month.label == T.IN_LINE
    assert by_name["Sud"].month.label == T.BEHIND


# ----------------------------------------------------------------------- l'année


def test_the_year_adds_the_published_closed_months_to_the_month_in_progress(tmp_path):
    """Avril à août publiés, septembre lu dans l'entrepôt : les deux s'additionnent, chacun
    avec sa base, et l'attendu de l'année garde la fourchette du mois."""
    review = _review(tmp_path, north=450_000.0, south=225_000.0)
    published = _published(2026, 8, [_line("Northland", 5_000_000.0, 5_100_000.0),
                                     _line("Southland", 2_500_000.0, 2_400_000.0)])
    track = T.build(review, published=published, directory=DIRECTORY)

    year = track.group.year
    assert track.closed_through == "2026-08"
    assert year.usable
    assert year.actual == 7_500_000.0 + 675_000.0
    assert abs(year.low - (7_500_000.0 + 1_500_000.0 * 0.45)) < 1e-6
    assert year.label == T.IN_LINE
    assert "consolidation d'avril à août" in year.basis
    north = next(scope for scope in track.perimeters if scope.name == "Nord")
    assert north.year.usable
    assert north.year.actual == 5_000_000.0 + 450_000.0


def test_a_stale_published_file_never_fills_the_missing_months(tmp_path):
    """La consolidation s'arrête à juin, l'entrepôt lit septembre : juillet et août
    manquent. L'exercice est absent avec la raison, jamais assemblé sur un trou."""
    review = _review(tmp_path, north=450_000.0, south=225_000.0)
    published = _published(2026, 6, [_line("Northland", 3_000_000.0, 3_000_000.0)])
    track = T.build(review, published=published, directory=DIRECTORY)

    assert not track.group.year.usable
    assert "juin" in track.group.year.absent and "septembre" in track.group.year.absent
    assert track.group.month.usable


def test_a_file_that_does_not_declare_its_month_is_named_not_trusted(tmp_path):
    review = _review(tmp_path, north=450_000.0, south=225_000.0)
    published = _published(None, None, [_line("Northland", 3_000_000.0, 3_000_000.0)])
    track = T.build(review, published=published)

    assert not track.group.year.usable
    assert "ne déclare pas son mois" in track.group.year.absent


class _Ytd:
    def __init__(self, actual, budget, last_period):
        self.actual, self.budget, self.last_period = actual, budget, last_period


def test_without_a_published_file_the_warehouse_year_is_the_degraded_reading(tmp_path):
    review = _review(tmp_path, north=450_000.0, south=225_000.0)
    track = T.build(review, warehouse_year=_Ytd(7_000_000.0, 7_200_000.0, "2026-08"))

    year = track.group.year
    assert year.usable
    assert "lecture dégradée" in year.basis
    assert year.actual == 7_000_000.0 + 675_000.0
    # Par périmètre, l'année attend le fichier : l'entrepôt ne la donne qu'en tout.
    assert all(not scope.year.usable for scope in track.perimeters)


def test_an_unread_month_yields_no_verdict_and_says_why():
    review = M.Review("", 0, "", [], [], ["aucune vente lue sur le mois en cours"])
    track = T.build(review)

    assert not track.usable
    assert track.absent == ["aucune vente lue sur le mois en cours"]
