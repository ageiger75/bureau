"""L'euro gagné est-il le bon euro — la première pièce de B5.

Ces tests gardent trois choses : le fichier se lit tel que la maison l'écrit et ses
absences sont nommées ; le mix contre le plan se lit sans aucun taux ; la repondération est
un calcul dont les deux effets somment exactement, jamais un classement et jamais un
résultat. Tous les taux sont inventés.
"""

from __future__ import annotations

from app.perf import mix as M
from app.perf.model import ECOMMERCE, RETAIL, BusinessUnit, Dataset, Drivers, Owner


def _unit(key, channel, actual, budget, market="Northland", aggregate=False):
    return BusinessUnit(
        key=key, label=key, market=market, region="Test", channel=channel,
        owner=Owner("Personne", "Rôle", "Test"),
        actual=Drivers.sales_only(actual), budget=Drivers.sales_only(budget),
        last_year=Drivers.sales_only(budget), forecast_sales=actual,
        is_aggregate=aggregate,
    )


def _dataset(units):
    return Dataset(period_label="Mois de test", as_of="2026-09-04", units=units)


def _file(tmp_path, text):
    path = tmp_path / "contribution.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


CANONICAL = ("name,kind,average_rate,as_of,source\n"
             "Retail (own),channel,0.41,2026-05,Comité (inventé)\n"
             "Brand.com,channel,0.37,2026-05,Comité (inventé)\n"
             "Distributors + Travel Retail,channel,0.52,2026-05,Comité (inventé)\n"
             "Northland Partner,partner,0.33,2026-05,Comité (inventé)\n")


# ------------------------------------------------------------------- le fichier


def test_the_file_is_read_as_the_house_writes_it(tmp_path):
    """Les noms de la maison joignent les canaux du cockpit ; un nom couvre deux canaux
    quand la maison ne tient qu'un taux pour les deux ; le partenaire est lu à part."""
    read = M.load(_file(tmp_path, CANONICAL))

    assert not read.faults
    assert read.of(RETAIL).rate == 0.41
    assert read.of(ECOMMERCE).rate == 0.37
    assert read.of("dis").rate == 0.52 and read.of("tra").rate == 0.52
    assert read.of("dis") is read.of("tra")
    assert [rate.name for rate in read.partners] == ["Northland Partner"]
    assert read.of("webp") is None
    assert read.as_of == "2026-05"


def test_a_rate_written_in_percent_reads_like_a_share(tmp_path):
    read = M.load(_file(tmp_path, "name,kind,contribution_rate\nRetail,channel,42 %\n"))

    assert not read.faults
    assert abs(read.of(RETAIL).rate - 0.42) < 1e-9


def test_an_unknown_name_is_named_not_guessed(tmp_path):
    """« Boutiques premium » ne ressemble à rien que le cockpit connaisse : la ligne est
    gardée, ne couvre rien, et le défaut dit la ligne et le nom."""
    read = M.load(_file(tmp_path, "name,kind,average_rate\nBoutiques premium,channel,0.5\n"))

    assert read.of(RETAIL) is None
    assert [rate.name for rate in read.unmapped] == ["Boutiques premium"]
    assert read.faults == ["ligne 2 : « Boutiques premium » ne désigne aucun canal du cockpit"]


def test_two_rates_for_one_channel_keep_the_first_and_name_the_second(tmp_path):
    read = M.load(_file(tmp_path, "name,kind,average_rate\nRetail,channel,0.4\n"
                                  "Stores,channel,0.5\n"))

    assert read.of(RETAIL).rate == 0.4
    assert any("déjà porté par « Retail »" in fault for fault in read.faults)


def test_a_missing_file_or_column_is_an_empty_reading(tmp_path):
    assert M.load(str(tmp_path / "nulle-part.csv")).is_empty
    read = M.load(_file(tmp_path, "name,kind\nRetail,channel\n"))
    assert read.is_empty and "average_rate" in read.faults[0]


def test_aliases_absorb_the_ways_a_name_gets_written():
    assert M.channels_of("Distributors & Travel Retail") == ("dis", "tra")
    assert M.channels_of("distributors and travel retail") == ("dis", "tra")
    assert M.channels_of("E-retailers") == ("webp",)
    assert M.channels_of("Department Stores") == ("dpt",)
    assert M.channels_of("Direct Selling") == ("direct selling",)
    assert M.channels_of("") == ()


# ----------------------------------------------------------------------- le mix


def _month():
    return _dataset([
        _unit("n-ret", RETAIL, 820.0, 770.0),
        _unit("n-web", ECOMMERCE, 180.0, 230.0),
        _unit("s-tra", "tra", 100.0, 100.0, market="Southland"),
        _unit("all", RETAIL, 5000.0, 5000.0, market="Monde", aggregate=True),
    ])


def test_the_mix_against_the_plan_reads_without_any_rate():
    """La première question — a-t-on vendu là où le plan le voulait — n'a besoin d'aucun
    taux. Sans fichier, elle se lit entière et le panneau dit ce qu'il attend."""
    review = M.build(_month(), None)

    assert review.usable and not review.weighs
    by_label = {piece.label: piece for piece in review.slices}
    assert by_label["Retail"].plan_share_label == "70 %"
    assert by_label["Retail"].actual_share_label == "75 %"
    assert by_label["Retail"].mix_gap_label == "+5"
    assert by_label["E-commerce"].mix_gap_label == "-5"
    assert by_label["Travel Retail"].mix_gap_label == "0"
    assert review.uncovered_note == ""
    assert any("var/contribution.csv" in reason for reason in review.absent)


def test_an_aggregate_is_never_counted_twice():
    review = M.build(_month(), None)

    assert review.total_actual == 1100.0
    assert review.total_budget == 1100.0


def test_the_reweighting_is_a_calculation_whose_two_effects_sum_exactly(tmp_path):
    """Σ taux × écart = effet volume + effet mix, à l'identique. Chaque terme porte son
    coefficient ; aucun n'est un résultat."""
    read = M.load(_file(tmp_path, CANONICAL))
    review = M.build(_month(), read)

    assert review.weighs
    retail = next(piece for piece in review.slices if piece.channel == RETAIL)
    assert retail.rate_label == "41 %"
    assert abs(retail.weighted - 0.41 * 50.0) < 1e-9
    web = next(piece for piece in review.slices if piece.channel == ECOMMERCE)
    assert abs(web.weighted - 0.37 * -50.0) < 1e-9
    assert abs(review.weighted - (0.41 * 50.0 - 0.37 * 50.0)) < 1e-9
    assert abs(review.volume_effect + review.mix_effect - review.weighted) < 1e-9
    # Ventes et plan égaux : tout l'écart repondéré est du mix, rien du volume.
    assert abs(review.volume_effect) < 1e-9
    assert review.coverage_label == "100 %"


def test_a_channel_without_a_rate_is_absent_with_its_weight_never_zero(tmp_path):
    """Un canal vendu que le fichier ne nomme pas sort du calcul et le dit avec son poids.
    Il n'est ni pris à zéro, ni à la moyenne des autres : la couverture le porte."""
    read = M.load(_file(tmp_path, "name,kind,average_rate\nRetail,channel,0.4\n"
                                  "Brand.com,channel,0.3\n"))
    review = M.build(_month(), read)

    travel = next(piece for piece in review.slices if piece.channel == "tra")
    assert not travel.covered and travel.weighted is None and travel.rate_label == "absent"
    assert review.uncovered_note == "Sans taux, donc hors du calcul : Travel Retail (9 % des ventes)."
    assert review.coverage_label == "91 %"
    assert not review.thin
    # La somme ne prend que les canaux couverts, sans rien inventer pour le troisième.
    assert abs(review.weighted - (0.4 * 50.0 - 0.3 * 50.0)) < 1e-9


def test_thin_coverage_is_said_not_hidden(tmp_path):
    read = M.load(_file(tmp_path, "name,kind,average_rate\nTravel Retail,channel,0.5\n"))
    review = M.build(_month(), read)

    assert review.weighs and review.thin
    assert review.coverage_label == "9 %"


def test_rows_are_ordered_by_plan_weight_never_by_rate(tmp_path):
    """La protection qui compte : ranger par taux dirait où pousser, et le taux moyen le
    dirait à l'envers. Le canal au taux le plus haut est ici le plus léger, et reste
    dernier."""
    read = M.load(_file(tmp_path, "name,kind,average_rate\nRetail,channel,0.3\n"
                                  "Brand.com,channel,0.4\nTravel Retail,channel,0.9\n"))
    review = M.build(_month(), read)

    assert [piece.channel for piece in review.slices] == [RETAIL, ECOMMERCE, "tra"]


def test_the_marginal_rate_is_declared_absent_and_no_ebitda_is_named(tmp_path):
    read = M.load(_file(tmp_path, CANONICAL))
    review = M.build(_month(), read)

    assert review.marginal.startswith("Taux marginal : absent")
    assert "taux moyen" in review.no_ranking
    everything = " ".join([review.marginal, review.no_ranking, review.partners_note,
                           review.uncovered_note] + review.absent)
    assert "EBITDA" not in everything and "résultat" not in everything


def test_partner_lines_are_read_but_never_applied_to_a_channel(tmp_path):
    read = M.load(_file(tmp_path, CANONICAL))
    review = M.build(_month(), read)

    assert "Northland Partner" in review.partners_note
    assert "non appliqué" in review.partners_note


def test_file_faults_reach_the_review_by_name(tmp_path):
    read = M.load(_file(tmp_path, "name,kind,average_rate\nRetail,channel,abc\n"))
    review = M.build(_month(), read)

    assert any("taux illisible pour « Retail »" in reason for reason in review.absent)


def test_no_comparable_unit_is_said_not_rendered_as_an_empty_mix():
    review = M.build(_dataset([]), None)

    assert not review.usable
    assert any("Aucune unité comparable" in reason for reason in review.absent)
