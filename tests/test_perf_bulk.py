"""Les deux bases du chiffre d'affaires, et le moment où elles cessent de dire la même chose."""
from app.perf import bulk, kpi


def rows(*entries):
    """`(scope, kpi_key, period, value)` — le contrat de `queries.KPI_READINGS`."""
    return [tuple(entry) for entry in entries]


def market(scope, months, sales, ex_bulk):
    """Un marché sur des mois consécutifs, sur les deux clés."""
    made = []
    for period, whole, clean in zip(months, sales, ex_bulk):
        made.append((scope, bulk.SALES_KEY, period, whole))
        made.append((scope, bulk.EX_BULK_KEY, period, clean))
    return made


THIS_YEAR = ["2026-04", "2026-05", "2026-06"]
LAST_YEAR = ["2025-04", "2025-05", "2025-06"]


def test_the_bulk_is_the_difference_between_the_two_keys():
    read = market("China", THIS_YEAR, [100.0, 100.0, 100.0], [90.0, 90.0, 90.0])
    found = bulk.market_bulk(read, "China")
    assert found.sales == 300.0
    assert found.ex_bulk == 270.0
    assert found.bulk == 30.0
    assert round(found.share, 4) == 0.1


def test_a_market_that_grows_only_because_the_bulk_came_back():
    # Les clients partent — 90 contre 100 — et le total dit que tout va bien parce
    # qu'une commande en gros a atterri. C'est le cas qui a motivé la paire.
    read = (market("Hong Kong", LAST_YEAR, [100.0] * 3, [100.0] * 3)
            + market("Hong Kong", THIS_YEAR, [110.0] * 3, [90.0] * 3))
    found = bulk.market_bulk(read, "Hong Kong")
    assert round(found.growth, 3) == 0.1
    assert round(found.growth_ex_bulk, 3) == -0.1
    assert found.changes_the_verdict
    assert found.bulk_movement == 60.0


def test_two_bases_that_move_together_are_not_a_finding():
    read = (market("Japan", LAST_YEAR, [100.0] * 3, [98.0] * 3)
            + market("Japan", THIS_YEAR, [105.0] * 3, [103.0] * 3))
    found = bulk.market_bulk(read, "Japan")
    assert not found.changes_the_verdict
    assert "la même chose" in found.sentence()


def test_opposite_signs_are_a_finding_however_small():
    # +0.5 % contre -0.5 % : un point d'écart, sous le seuil, et pourtant les deux
    # phrases sont contraires. Un seuil qui laisserait passer ça serait mal réglé.
    read = (market("Macau", LAST_YEAR, [100.0] * 3, [100.0] * 3)
            + market("Macau", THIS_YEAR, [100.5] * 3, [99.5] * 3))
    found = bulk.market_bulk(read, "Macau")
    assert found.changes_the_verdict


def test_a_missing_month_a_year_ago_withholds_the_growth_and_keeps_the_level():
    read = (market("Taiwan", LAST_YEAR[:2], [100.0] * 2, [100.0] * 2)
            + market("Taiwan", THIS_YEAR, [110.0] * 3, [100.0] * 3))
    found = bulk.market_bulk(read, "Taiwan")
    assert found.sales == 330.0
    assert not found.comparable
    assert found.growth is None
    assert found.growth_ex_bulk is None
    assert "pas de comparable" in found.sentence()


def test_a_month_the_warehouse_never_returned_is_not_read_as_zero():
    readings = [kpi.Reading("2026-04", 10.0)]
    assert bulk._sums(readings, ["2026-04", "2026-05"]) is None
    assert bulk._sums(readings, ["2026-04"]) == 10.0


def test_a_market_without_the_second_key_answers_nothing_rather_than_zero_bulk():
    read = rows(("Brazil", bulk.SALES_KEY, "2026-06", 100.0))
    assert bulk.market_bulk(read, "Brazil") is None


def test_only_the_markets_where_the_bulk_changes_the_reading_are_listed():
    read = (market("China", THIS_YEAR, [100.0] * 3, [93.0] * 3)
            + market("France", THIS_YEAR, [100.0] * 3, [99.9] * 3)
            + market("LOEP", THIS_YEAR, [200.0] * 3, [192.9] * 3))
    listed = [item.scope for item in bulk.material(read)]
    # France porte 0,1 % de bulk : le dire ne changerait rien. Et le groupe n'est pas
    # un marché — le laisser en tête classerait le total avant ses membres.
    assert listed == ["China"]


def test_the_list_is_ordered_by_euros_not_by_share():
    # Un sixième d'un petit marché et un vingtième d'un grand ne sont pas la même
    # conversation, et c'est l'argent qui décide laquelle vient d'abord.
    read = (market("Hong Kong", THIS_YEAR, [30.0] * 3, [25.0] * 3)
            + market("China", THIS_YEAR, [300.0] * 3, [280.0] * 3))
    listed = [item.scope for item in bulk.material(read)]
    assert listed == ["China", "Hong Kong"]


def test_the_window_is_the_most_recent_months_on_both_keys():
    months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    read = market("Korea", months, [10.0] * 6, [9.0] * 6)
    found = bulk.market_bulk(read, "Korea", months=3)
    assert list(found.periods) == ["2026-04", "2026-05", "2026-06"]
    assert found.sales == 30.0


def test_dictionary_rows_from_the_warehouse_read_the_same_as_cached_sequences():
    as_dicts = [{"SCOPE": "China", "KPI_KEY": bulk.SALES_KEY,
                 "PERIOD": "2026-06", "VALUE": 100.0},
                {"SCOPE": "China", "KPI_KEY": bulk.EX_BULK_KEY,
                 "PERIOD": "2026-06", "VALUE": 90.0}]
    found = bulk.market_bulk(as_dicts, "China", months=1)
    assert found.bulk == 10.0
    assert bulk.scopes(as_dicts) == ["China"]


def test_previous_year_only_understands_months():
    assert bulk.previous_year("2026-04") == "2025-04"
    assert bulk.previous_year("2026") == ""
    assert bulk.previous_year("") == ""


def test_rates_are_fractions_like_every_other_rate_on_this_screen():
    # Deux conventions dans un même code, c'est ainsi qu'un taux de croissance arrive
    # à l'écran cent fois trop grand. Le filtre `pct` des gabarits multiplie par cent.
    assert bulk.MATERIAL_SHARE < 1.0
    assert bulk.DIVERGENCE < 1.0
    read = (market("India", LAST_YEAR, [100.0] * 3, [100.0] * 3)
            + market("India", THIS_YEAR, [110.0] * 3, [110.0] * 3))
    found = bulk.market_bulk(read, "India")
    assert round(found.growth, 3) == 0.1


def test_a_cold_cache_shows_nothing_rather_than_starting_a_two_minute_query(monkeypatch):
    """Un chargement de page ne doit jamais pouvoir déclencher la lecture de l'entrepôt.

    C'est une seconde lecture de lignes que l'écran paie déjà ailleurs. Cache froid :
    la paire n'a pas été lue, le bloc n'apparaît pas, et personne n'attend deux minutes.
    """
    from app.perf import source

    monkeypatch.setattr(source, "_read_kpi_cache", lambda: None)
    # `self` n'est pas utilisé : la méthode ne lit que le cache, et c'est le propos.
    assert source.SnowflakeSource.bulk_findings(None) == []


def test_the_window_can_be_ended_on_a_chosen_month():
    """Les trois mois les plus frais et le trimestre clos par la Finance ne sont pas les
    mêmes mois. Sommer les uns en croyant lire les autres se lirait comme un écart."""
    months = ["2026-04", "2026-05", "2026-06", "2026-07"]
    read = market("China", months, [10.0, 20.0, 30.0, 40.0], [9.0, 18.0, 27.0, 36.0])

    fresh = bulk.market_bulk(read, "China", months=3)
    quarter = bulk.market_bulk(read, "China", months=3, through="2026-06")

    assert list(fresh.periods) == ["2026-05", "2026-06", "2026-07"]
    assert list(quarter.periods) == ["2026-04", "2026-05", "2026-06"]
    assert quarter.sales == 60.0


def test_a_window_ending_before_anything_read_answers_nothing():
    read = market("China", THIS_YEAR, [10.0] * 3, [9.0] * 3)
    assert bulk.market_bulk(read, "China", through="2020-01") is None


def test_the_reconciliation_refuses_a_window_that_is_not_the_quarter_compared():
    """Soustraire le bulk d'un autre trimestre répondrait à une autre question.

    La commande préfère ne rien soustraire et le dire : un rapprochement faux par un mois
    de décalage tombe juste de temps en temps, ce qui est la pire façon d'avoir raison.
    """
    from app import cli
    from app.perf import source

    read = (market("LOEP", ["2026-04", "2026-05", "2026-06", "2026-07"],
                   [100.0] * 4, [90.0] * 4))
    monkeypatched = list(read)
    source_cache = source._read_kpi_cache
    try:
        source._read_kpi_cache = lambda: monkeypatched
        assert cli._bulk_over(["2026-04", "2026-05", "2026-06"]) == 30.0
        # Deux mois demandés, trois lus : la fenêtre ne tombe pas sur le trimestre.
        assert cli._bulk_over(["2026-04", "2026-06"]) is None
        source._read_kpi_cache = lambda: None
        assert cli._bulk_over(["2026-04"]) is None
    finally:
        source._read_kpi_cache = source_cache
