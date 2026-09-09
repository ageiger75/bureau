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
    assert "1 sans an dernier" in level.sentence
    assert "1 arrêtée" in level.sentence


def test_a_line_without_last_year_on_these_months_is_named_apart_not_ranked():
    """Saisonnière ou neuve, une référence sans an dernier sur ces mois n'a pas de
    croissance : elle est nommée à part, jamais en tête de « ce qui pousse »."""
    values = _year(0.0, 30.0)
    values["2025-01"] = 40.0
    level = P.build(_rows("product", "Écorce Noire bougie", values)).level("product")

    assert [line.name for line in level.launched] == ["Écorce Noire bougie"]
    assert level.growing == [] and level.lines[0].growth is None
    assert "1 sans an dernier" in level.sentence


def test_a_label_read_through_the_wrong_encoding_is_mended():
    assert P._mended("COFFRET MÃ©TAL") == "COFFRET MéTAL"
    assert P._mended("CRÈME MAINS") == "CRÈME MAINS"


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


def test_noise_launches_and_stops_are_counted_but_not_named_and_a_full_concentration_is_silent():
    """Un arrêt de quelques euros n'est pas un fait de commerce, et « quatre catégories
    portent cent pour cent de ce qui pousse » quand quatre poussent ne dit rien."""
    rows = (_rows("category", "Corps", _year(1000.0, 1100.0))
            + _rows("category", "Visage", _year(1000.0, 1050.0))
            + _rows("category", "Divers", _year(0.3, 0.0, stopped_after="2025-12"))
            + _rows("category", "Neuf", _year(0.0, 0.2, launched_from="2026-06")))
    level = P.build(rows).level("category")

    assert len(level.launched) == 1 and level.launched_shown == []
    assert len(level.stopped) == 1 and level.stopped_shown == []
    assert "arrêtée" not in level.sentence and "sans an dernier" not in level.sentence
    assert "portent" not in level.sentence


def test_a_perimeter_reads_the_sum_of_its_markets_without_the_references():
    """La région parle de ses catégories et de ses gammes : la somme de ses marchés, mois
    par mois. Les références restent au groupe, et la lecture le dit."""
    rows = (_rows("category", "Corps", _year(100.0, 110.0), scope="Northland")
            + _rows("category", "Corps", _year(50.0, 40.0), scope="Eastland")
            + _rows("category", "Corps", _year(500.0, 900.0), scope="Elsewhere")
            + _rows("range", "Sable d'Or", _year(30.0, 33.0), scope="Northland", hero=1)
            + _rows("product", "Sable d'Or crème mains", _year(30.0, 33.0)))
    review = P.for_markets(rows, ["Northland", "Eastland"], "Nord")

    assert review.scope == "Nord"
    assert [level.level for level in review.levels] == ["category", "range"]
    corps = review.level("category").lines[0]
    assert corps.sales == 5 * 150.0 and corps.last_year == 5 * 150.0
    assert review.level("range").lines[0].hero
    assert any("catégories et les gammes de Northland, Eastland" in reason
               for reason in review.absent)

    nothing = P.for_markets(rows, ["Nowhere"], "Vide")
    assert not nothing.usable


def test_a_market_written_in_capitals_by_the_warehouse_is_the_same_market():
    """L'entrepôt écrit UNITED STATES, l'annuaire United States : une page de périmètre
    qui ne trouvait « aucune vente par produit » les lisait comme deux marchés."""
    rows = (_rows("category", "Corps", _year(100.0, 110.0), scope="USA")
            + _rows("category", "Corps", _year(10.0, 12.0), scope="CANADA"))

    assert P.build(rows, "United States").usable
    region = P.for_markets(rows, ["United States", "Canada"], "North America")
    assert region.level("category").lines[0].sales == 5 * 122.0
    assert P.scopes(rows) == ["CANADA", "USA"]
    # Et la couverture retrouve le sigle sous le nom en toutes lettres.
    kpi_rows = [{"scope": "USA", "kpi_key": "net_sales", "period": "2026-08", "value": 110.0}]
    assert [round(share, 2) for _, _, _, share in
            P.coverage(rows, kpi_rows, ["United States"], "2026-08")] == [1.0]


def test_the_reading_says_when_it_covers_only_part_of_a_market_s_sales():
    """Une région lisait un tiers de ce que sa semaine montrait : des lignes sans produit
    au référentiel. La lecture des KPI porte les ventes du même mois ; quand la lecture
    produit en couvre moins que la part attendue, le bloc le dit, marché par marché."""
    rows = (_rows("category", "Corps", _year(100.0, 110.0), scope="UNITED STATES")
            + _rows("category", "Corps", _year(100.0, 110.0), scope="CANADA"))
    kpi_rows = [{"scope": "UNITED STATES", "kpi_key": "net_sales_hors_bulk", "period": "2026-08",
                 "value": 400.0},
                {"scope": "CANADA", "kpi_key": "net_sales", "period": "2026-08", "value": 115.0}]

    found = P.coverage(rows, kpi_rows, ["United States", "Canada", "Mexico"], "2026-08")
    assert [(scope, round(share, 3)) for scope, _, _, share in found] == [
        ("United States", 0.275), ("Canada", 0.957)]

    review = P.for_markets(rows, ["United States", "Canada"], "North America")
    P.check_coverage(review, rows, kpi_rows, ["United States", "Canada"])
    assert any("United States 28 %" in reason and "Canada" not in reason
               for reason in review.absent)
