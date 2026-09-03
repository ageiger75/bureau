"""Où en est le mois, et où en est l'objectif. Deux taux, et leur écart.

Un seul nombre ne répond pas à la question du lecteur. À 60 % du mois et 60 % du plan on
est dans les temps ; à 60 % du mois et 40 % du plan il reste 40 % du mois pour rattraper
vingt points. C'est l'écart qui parle, donc il faut les deux — et le premier ne se calcule
pas sur les jours écoulés, parce qu'aucun mois ne se vend à plat.
"""

from __future__ import annotations

import io

from app.perf import pace


def _file(tmp_path, rows, header="market,month,week,share"):
    path = tmp_path / "phasing.csv"
    path.write_text("\n".join([header] + list(rows)) + "\n", encoding="utf-8")
    return str(path)


def _flat(market="Northland", month="11"):
    return ["%s,%s,%d,0.25" % (market, month, week) for week in (1, 2, 3, 4)]


def test_the_month_is_read_from_its_shape_and_never_from_the_days_elapsed():
    """La faute la plus commode du dossier : supposer qu'un mois se vend à plat. Elle rend
    un nombre plausible et sans rapport avec le commerce — une campagne concentre le
    chiffre sur quelques jours, et la moitié des jours ne fait pas la moitié du mois."""
    curve = pace.Curve("Northland", "11", [0.10, 0.15, 0.55, 0.20])

    # Trois semaines sur quatre sont écoulées, mais quatre cinquièmes du mois sont faits.
    assert curve.elapsed(3) == 0.80
    assert curve.elapsed(1) == 0.10


def test_a_week_the_shape_does_not_describe_is_not_a_finished_month():
    """Un mois de cinq semaines lu sur une courbe de quatre rendrait un avancement complet
    la semaine où il reste précisément le plus à faire."""
    curve = pace.Curve("Northland", "11", [0.25, 0.25, 0.25, 0.25])

    assert curve.elapsed(5) is None
    assert curve.elapsed(0) is None


def test_a_shape_that_does_not_sum_to_one_is_refused_and_named(tmp_path):
    """Une courbe remise à un décrirait un mois que personne n'a mesuré, avec l'aplomb
    d'une mesure. Le taux qu'elle produirait serait faux d'exactement ce qui manque."""
    path = _file(tmp_path, ["Northland,11,1,0.2", "Northland,11,2,0.2",
                            "Northland,11,3,0.2"])

    read = pace.load(path)

    assert len(read) == 0
    assert read.faults and "au lieu de 1" in read.faults[0]


def test_a_market_without_a_shape_is_named_rather_than_given_the_days_elapsed(tmp_path):
    """C'est la règle du dossier appliquée ici : un taux plausible et faux est pire qu'un
    trou, parce qu'il ne se signale pas."""
    read = pace.load(_file(tmp_path, _flat()))

    result = pace.progress("Southland", "2026-11", 2, actual=400.0, target=1000.0,
                           phasing=read)

    assert result.through_month is None
    assert not result.readable
    assert "forme du mois non mesurée" in result.absent
    # L'objectif, lui, se lit : les deux absences sont séparées parce qu'elles appellent
    # deux gestes différents — une requête à l'entrepôt, ou une ligne au plan.
    assert result.through_target == 0.4


def test_a_month_without_a_plan_is_not_a_month_at_zero(tmp_path):
    read = pace.load(_file(tmp_path, _flat()))

    result = pace.progress("Northland", "2026-11", 2, actual=400.0, target=None,
                           phasing=read)

    assert result.through_target is None
    assert result.through_month == 0.5
    assert "aucun objectif au plan" in result.absent


def test_the_gap_between_the_two_rates_is_what_the_reader_came_for(tmp_path):
    """Le nombre qui déclenche une conversation : il reste tant de mois pour rattraper
    tant de points."""
    read = pace.load(_file(tmp_path, ["Northland,11,1,0.10", "Northland,11,2,0.50",
                                      "Northland,11,3,0.20", "Northland,11,4,0.20"]))

    result = pace.progress("Northland", "2026-11", 2, actual=400.0, target=1000.0,
                           phasing=read)

    assert result.through_month == 0.60
    assert result.through_target == 0.40
    assert abs(result.points_behind - 0.20) < 1e-9


def test_no_gap_is_computed_against_a_rate_that_does_not_exist(tmp_path):
    """Un écart calculé contre un taux supposé serait un chiffre inventé présenté comme
    une mesure."""
    read = pace.load(_file(tmp_path, _flat()))

    assert pace.progress("Ailleurs", "2026-11", 2, 400.0, 1000.0, read).points_behind is None


def test_the_shape_repeats_from_one_year_to_the_next_so_the_year_is_not_a_key(tmp_path):
    """La forme d'un mois est ce qui se répète — c'est même sa raison d'être. Une clé
    portant l'année obligerait à réécrire le fichier chaque exercice pour décrire la même
    saisonnalité."""
    read = pace.load(_file(tmp_path, _flat(month="11")))

    assert read.of("Northland", "2026-11") is not None
    assert read.of("Northland", "2027-11") is not None
    assert read.of("Northland", "11") is not None


def test_a_share_written_as_a_percentage_is_read_as_one(tmp_path):
    """Le fichier est tenu à la main et les deux écritures sont légitimes. Refuser « 25 »
    ferait perdre une courbe entière pour une convention."""
    read = pace.load(_file(tmp_path, ["Northland,11,1,25", "Northland,11,2,25",
                                      "Northland,11,3,25", "Northland,11,4,25"]))

    assert read.of("Northland", "11").elapsed(2) == 0.5


def test_an_absent_file_is_an_empty_reading_and_not_a_crash(tmp_path):
    read = pace.load(str(tmp_path / "nulle-part.csv"))

    assert not read.usable and read.faults == []
    assert pace.progress("Northland", "2026-11", 2, 400.0, 1000.0, read).through_month is None


def test_a_file_missing_a_column_says_which_one(tmp_path):
    path = _file(tmp_path, ["Northland,11,1"], header="market,month,week")

    read = pace.load(path)

    assert not read.usable
    assert "share" in read.faults[0]
