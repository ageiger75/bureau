"""Où en est le mois, où en est l'objectif, et quand on n'a pas le droit de le dire.

Un seul nombre ne répond pas à la question du lecteur : c'est l'écart entre les deux taux
qui parle. Et le premier ne se calcule pas sur les jours écoulés, parce qu'aucun mois ne se
vend à plat.

La première version de ce module alignait les années par rang de semaine. Le lecteur a
cassé le raisonnement d'une phrase : cela corrige la dérive d'un ou deux jours et ne corrige
rien quand la fête des mères passe de la deuxième à la troisième semaine, ou quand Black
Friday change de semaine. Ces tests gardent la réponse — ne pas affirmer une forme, mesurer
si une forme existe.
"""

from __future__ import annotations

from app.perf import pace


def _file(tmp_path, rows, header="market,month,week,share,year"):
    path = tmp_path / "phasing.csv"
    path.write_text("\n".join([header] + list(rows)) + "\n", encoding="utf-8")
    return str(path)


def _year(shares, market="Northland", month="11", year="2025"):
    return ["%s,%s,%d,%s,%s" % (market, month, index + 1, share, year)
            for index, share in enumerate(shares)]


def test_the_month_is_read_from_its_shape_and_never_from_the_days_elapsed(tmp_path):
    """La faute la plus commode du dossier : supposer qu'un mois se vend à plat. Elle rend
    un nombre plausible et sans rapport avec le commerce — une campagne concentre le
    chiffre sur quelques jours, et la moitié des jours ne fait pas la moitié du mois."""
    read = pace.load(_file(tmp_path, _year([0.10, 0.15, 0.55, 0.20], year="2024")
                           + _year([0.10, 0.15, 0.55, 0.20], year="2025")))

    band = read.of("Northland", "11").elapsed(3)

    # Trois semaines sur quatre écoulées, mais quatre cinquièmes du mois faits.
    assert abs(band.middle - 0.80) < 1e-9
    assert band.spread == 0.0


def test_a_month_whose_event_moves_gives_a_range_and_not_a_number(tmp_path):
    """L'objection du lecteur, tenue par le code. Une semaine qui a fait vingt pour cent
    puis cinquante-cinq n'est pas une semaine dont on connaît la part : c'est une semaine
    traversée par un événement qui bouge. Rendre un point ici serait une affirmation
    déguisée en mesure."""
    read = pace.load(_file(
        tmp_path,
        _year([0.20, 0.20, 0.40, 0.20], year="2024")     # l'événement en semaine 3
        + _year([0.20, 0.55, 0.05, 0.20], year="2025"))) # et en semaine 2 l'année suivante

    band = read.of("Northland", "11").elapsed(2)

    assert abs(band.low - 0.40) < 1e-9
    assert abs(band.high - 0.75) < 1e-9
    assert band.spread > 0.3
    assert band.verified


def test_a_single_reference_year_verifies_nothing_and_says_so(tmp_path):
    """Une seule année donne un point sans aucun moyen de savoir s'il se reproduit. C'est
    la version la plus profonde de l'objection : la forme peut être vraie, rien ne le dit."""
    read = pace.load(_file(tmp_path, _year([0.25, 0.25, 0.25, 0.25])))

    result = pace.progress("Northland", "2026-11", 2, actual=400.0, target=1000.0,
                           phasing=read)

    assert result.through_month.years == 1
    assert not result.through_month.verified
    assert "une seule année" in result.absent


def test_the_file_reveals_which_months_carry_a_moving_event(tmp_path):
    """Effet de bord précieux : le fichier désigne de lui-même les marchés et les mois
    traversés par une date mobile, ce qu'aucun calendrier tenu à la main ne resterait à
    jour pour dire."""
    read = pace.load(_file(
        tmp_path,
        _year([0.20, 0.20, 0.40, 0.20], market="Northland", year="2024")
        + _year([0.20, 0.55, 0.05, 0.20], market="Northland", year="2025")
        + _year([0.25, 0.25, 0.25, 0.25], market="Southland", year="2024")
        + _year([0.24, 0.26, 0.25, 0.25], market="Southland", year="2025")))

    moving = read.unstable(spread=0.10)

    assert [curve.market for curve, _week, _band in moving] == ["Northland"]


def test_a_week_beyond_a_year_curve_does_not_finish_that_year_month(tmp_path):
    """Un mois de cinq semaines lu sur une courbe de quatre annoncerait un mois fini la
    semaine où il reste précisément le plus à faire. L'année trop courte ne participe pas
    au lieu de rendre cent pour cent."""
    read = pace.load(_file(tmp_path, _year([0.2, 0.2, 0.2, 0.2, 0.2], year="2024")
                           + _year([0.25, 0.25, 0.25, 0.25], year="2025")))

    band = read.of("Northland", "11").elapsed(5)

    assert band.years == 1 and abs(band.high - 1.0) < 1e-9


def test_a_shape_that_does_not_sum_to_one_is_refused_and_named(tmp_path):
    """Une courbe remise à l'échelle décrirait un mois que personne n'a mesuré, avec
    l'aplomb d'une mesure. Le taux qu'elle produirait serait faux d'exactement ce qui
    manque."""
    read = pace.load(_file(tmp_path, ["Northland,11,1,0.2,2025",
                                      "Northland,11,2,0.2,2025",
                                      "Northland,11,3,0.2,2025"]))

    assert len(read) == 0
    assert read.faults and "au lieu de 1" in read.faults[0]


def test_a_market_without_a_shape_is_named_rather_than_given_the_days_elapsed(tmp_path):
    """Un taux plausible et faux est pire qu'un trou, parce qu'il ne se signale pas."""
    read = pace.load(_file(tmp_path, _year([0.25, 0.25, 0.25, 0.25])))

    result = pace.progress("Southland", "2026-11", 2, actual=400.0, target=1000.0,
                           phasing=read)

    assert result.through_month is None
    assert not result.readable
    assert "forme du mois non mesurée" in result.absent
    # L'objectif se lit quand même : les deux absences appellent deux gestes différents,
    # une requête à l'entrepôt ou une ligne au plan.
    assert result.through_target == 0.4


def test_a_month_without_a_plan_is_not_a_month_at_zero(tmp_path):
    read = pace.load(_file(tmp_path, _year([0.25, 0.25, 0.25, 0.25])))

    result = pace.progress("Northland", "2026-11", 2, actual=400.0, target=None,
                           phasing=read)

    assert result.through_target is None
    assert "aucun objectif au plan" in result.absent


def test_the_uncertainty_of_the_shape_travels_into_the_gap(tmp_path):
    """Un avancement connu à trente-cinq points près donne un retard connu à trente-cinq
    points près. Collapser la fourchette au moment de conclure rendrait la conclusion plus
    sûre que ce sur quoi elle repose."""
    read = pace.load(_file(tmp_path, _year([0.20, 0.20, 0.40, 0.20], year="2024")
                           + _year([0.20, 0.55, 0.05, 0.20], year="2025")))

    behind = pace.progress("Northland", "2026-11", 2, 400.0, 1000.0, read).behind

    assert abs(behind.low - 0.0) < 1e-9      # 40 % du mois − 40 % du plan
    assert abs(behind.high - 0.35) < 1e-9    # 75 % du mois − 40 % du plan
    assert behind.spread > 0.3


def test_the_shape_repeats_from_one_year_to_the_next_so_the_year_is_not_a_key(tmp_path):
    """La forme d'un mois est ce qu'on cherche à voir se répéter — c'est même tout l'objet
    de la refonte. Une clé portant l'année obligerait à réécrire le fichier chaque
    exercice pour décrire la même saisonnalité."""
    read = pace.load(_file(tmp_path, _year([0.25, 0.25, 0.25, 0.25])))

    assert read.of("Northland", "2026-11") is not None
    assert read.of("Northland", "2027-11") is not None
    assert read.of("Northland", "11") is not None


def test_a_share_written_as_a_percentage_is_read_as_one(tmp_path):
    read = pace.load(_file(tmp_path, _year([25, 25, 25, 25])))

    assert abs(read.of("Northland", "11").elapsed(2).middle - 0.5) < 1e-9


def test_an_absent_file_is_an_empty_reading_and_not_a_crash(tmp_path):
    read = pace.load(str(tmp_path / "nulle-part.csv"))

    assert not read.usable and read.faults == []
    assert pace.progress("Northland", "2026-11", 2, 400.0, 1000.0, read).through_month is None


def test_a_file_missing_the_year_says_so(tmp_path):
    """La colonne qui manquait à la première version, et sans laquelle rien de tout ceci
    n'est mesurable."""
    read = pace.load(_file(tmp_path, ["Northland,11,1,0.25"],
                           header="market,month,week,share"))

    assert not read.usable
    assert "year" in read.faults[0]


def test_every_week_is_scanned_because_the_progress_is_cumulative(tmp_path):
    """Un événement qui passe de la deuxième à la troisième semaine ne change presque rien
    au cumul de fin de troisième semaine — il est dedans dans les deux cas. Fixer une
    semaine d'avance revient à choisir quels déplacements on accepte de ne pas voir."""
    read = pace.load(_file(tmp_path, _year([0.10, 0.50, 0.20, 0.20], year="2024")
                           + _year([0.10, 0.15, 0.55, 0.20], year="2025")))

    at_three = read.of("Northland", "11").elapsed(3)
    curve, week, band = read.unstable(spread=0.10)[0]

    assert at_three.spread < 0.01          # invisible à la semaine 3
    assert week == 2 and band.spread > 0.3  # évident à la semaine 2


def test_a_monotone_series_is_a_trend_and_not_a_date_that_moves(tmp_path):
    """Une date qui se déplace oscille : tôt une année, tard la suivante, tôt encore
    ensuite. Une série qui descend trois années de suite décrit autre chose — une
    fermeture, une promotion arrêtée, un canal qui part. Chercher une fête pour expliquer
    une tendance ne trouve rien et coûte une recherche entière."""
    read = pace.load(_file(
        tmp_path,
        _year([0.25, 0.25, 0.25, 0.25], market="Trend", year="2024")
        + _year([0.10, 0.10, 0.60, 0.20], market="Trend", year="2025")
        + _year([0.05, 0.05, 0.75, 0.15], market="Trend", year="2026")
        + _year([0.10, 0.50, 0.20, 0.20], market="Moves", year="2024")
        + _year([0.10, 0.15, 0.55, 0.20], market="Moves", year="2025")
        + _year([0.10, 0.55, 0.15, 0.20], market="Moves", year="2026")))

    verdicts = {curve.market: read.trending(curve, week)
                for curve, week, _band in read.unstable(spread=0.10)}

    assert verdicts["Trend"] is True
    assert verdicts["Moves"] is False
