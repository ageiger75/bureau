"""Ce qui marche, par produit : catégories, gammes, références.

Ces tests gardent le calcul — l'exercice à date contre les mêmes mois de l'an dernier, sur
les mois présents des deux côtés — et ce que le tableau doit rendre lisible sans phrase :
l'écart en euros avant le pourcentage, la part, le dernier mois ; un lancement et un arrêt
nommés à part et jamais rangés dans « ce qui pousse » avec une croissance infinie. Valeurs
inventées, noms inventés.
"""

from __future__ import annotations

from app.perf import products as P


def _rows(level, name, values, scope="LOEP", hero=0):
    return [{"scope": scope, "level": level, "name": name, "period": period,
             "net_sales": value, "is_hero": hero} for period, value in values.items()]


def _year(last, this, launched_from=None, stopped_after=None):
    """Cinq mois d'exercice, avril à août, avec l'an dernier en face."""
    values = {}
    for month in range(4, 9):
        before, now = "2025-%02d" % month, "2026-%02d" % month
        if stopped_after is None or before <= stopped_after:
            values[before] = last
        if (launched_from is None or now >= launched_from) and (
                stopped_after is None or now <= stopped_after):
            values[now] = this
    return values


def test_the_year_to_date_is_compared_month_for_month_and_the_gap_leads():
    rows = (_rows("range", "Sable d'Or", _year(100.0, 120.0))
            + _rows("range", "Miel des Cimes", _year(200.0, 180.0))
            + _rows("range", "Lin Sauvage", _year(50.0, 52.0)))
    review = P.build(rows)

    assert review.period == "2026-08"
    assert review.months == ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
    assert "avril à août 2026" in review.basis
    level = review.level("range")
    assert level.total == 5 * (120.0 + 180.0 + 52.0)
    assert [line.name for line in level.growing] == ["Sable d'Or", "Lin Sauvage"]
    assert [line.name for line in level.falling] == ["Miel des Cimes"]
    lead = level.growing[0]
    assert lead.delta == 100.0 and lead.growth_label == "+20.0 %"
    assert lead.delta_label.startswith("+") and abs(lead.share - 120.0 / 352.0) < 1e-9
    assert abs(lead.month_growth - 0.2) < 1e-9
    assert level.title == "Gammes · 3, +0.6 % sur l'exercice"


def test_a_launch_and_a_stop_are_named_apart_never_ranked_as_growth():
    rows = (_rows("product", "Bois de Reine coffret", _year(0.0, 90.0, launched_from="2026-06"))
            + _rows("product", "Pluie d'Argile gommage", _year(70.0, 0.0, stopped_after="2025-12"))
            + _rows("product", "Sable d'Or crème mains", _year(100.0, 101.0), hero=1))
    level = P.build(rows).level("product")

    assert [line.name for line in level.launched] == ["Bois de Reine coffret"]
    assert [line.name for line in level.stopped] == ["Pluie d'Argile gommage"]
    assert [line.name for line in level.growing] == ["Sable d'Or crème mains"]
    assert level.growing[0].hero
    assert level.launched[0].growth is None and level.launched[0].growth_label == "n/d"
    assert "1 lancée sur l'exercice" in level.sentence
    assert "1 arrêtée" in level.sentence


def test_a_reference_sold_before_the_year_but_not_in_it_last_year_is_not_a_launch():
    """Une référence saisonnière qui n'a rien vendu sur ces mois l'an dernier mais
    existait avant n'est pas un lancement : elle est établie, avec un an dernier à zéro."""
    values = _year(0.0, 30.0)
    values["2025-01"] = 40.0
    level = P.build(_rows("product", "Écorce Noire bougie", values)).level("product")

    assert level.launched == []
    assert level.lines[0].launched is False and level.lines[0].growth is None


def test_months_without_last_year_are_left_out_and_said():
    values = {"2026-04": 10.0, "2026-05": 11.0, "2025-05": 10.0}
    review = P.build(_rows("category", "Corps", values))

    assert review.months == ["2026-05"]
    assert any("mai 2026 seulement" in reason for reason in review.absent)

    nothing = P.build(_rows("category", "Corps", {"2026-04": 10.0, "2026-05": 11.0}))
    assert not nothing.usable
    assert any("l'an dernier n'est pas dans la lecture" in reason for reason in nothing.absent)


def test_a_market_reads_its_categories_and_says_the_references_are_group_only():
    rows = (_rows("category", "Corps", _year(10.0, 12.0), scope="Northland")
            + _rows("product", "Sable d'Or crème mains", _year(10.0, 12.0)))
    review = P.build(rows, "Northland")

    assert [level.level for level in review.levels] == ["category"]
    assert review.absent == ["les gammes et références ne sont lues qu'au niveau du groupe"]
    assert P.scopes(rows) == ["LOEP", "Northland"]


def test_without_a_reading_the_note_is_carried_and_nothing_is_invented():
    review = P.build([], note="la lecture par produit n'est pas encore écrite")

    assert not review.usable
    assert review.absent == ["la lecture par produit n'est pas encore écrite"]
    assert review.headline == ""


def test_the_concentration_names_how_much_of_the_growth_five_lines_carry():
    rows = []
    for index in range(8):
        rows += _rows("product", "Référence %d" % index, _year(100.0, 100.0 + 8 - index))
    level = P.build(rows).level("product")

    assert len(level.growing) == 5
    assert abs(level.concentration - (8 + 7 + 6 + 5 + 4) / 36.0) < 1e-9
    assert "5 références portent 83 % de ce qui pousse" in level.sentence


def test_the_invented_rows_read_as_a_whole_screen():
    from app.perf import mock

    review = P.build(mock.product_rows())

    assert [level.level for level in review.levels] == ["category", "range", "product"]
    assert review.level("range").launched and review.level("range").stopped
    assert review.level("product").growing[0].hero
    assert review.headline.startswith("Sur l'exercice à date, les ventes font")


def test_placeholder_labels_are_not_products_and_disagreeing_levels_are_said():
    rows = (_rows("product", "AVAILABLE SKU OCC-XX1", _year(500.0, 500.0))
            + _rows("product", "Sable d'Or crème mains", _year(100.0, 110.0))
            + _rows("category", "Corps", _year(100.0, 110.0)))
    review = P.build(rows)

    assert [line.name for line in review.level("product").lines] == ["Sable d'Or crème mains"]
    assert not any("s'accordent" in reason for reason in review.absent)

    apart = P.build(rows + _rows("category", "Visage", _year(50.0, 60.0)))
    assert any("les niveaux ne s'accordent pas" in reason for reason in apart.absent)


def test_the_product_query_is_written_on_the_stored_line_never_the_translated_one():
    """La colonne traduite est un appel à un modèle par ligne : cinq minutes pour un
    `count(distinct)`, deux graphies pour une gamme, des crédits à chaque lecture."""
    from app.perf import queries

    sql = queries.PRODUCT_SALES.lower()
    assert "p.product_line " in sql or "p.product_line\n" in sql
    assert "product_line_en" not in sql
    assert "last_product_id" in sql and "store_brand" in sql
    assert "'product'" in sql and "'range'" in sql and "'category'" in sql
