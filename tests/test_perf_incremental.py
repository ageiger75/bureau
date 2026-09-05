"""La marge incrémentale par canal, mesurée au compte de gestion — le taux du prochain euro.

Ces tests gardent trois choses : seul le statut « mesure » fait d'une ligne un taux, et les
autres sont nommés par leur statut, jamais pris au taux moyen ; le fichier se lit tel que
l'agent entrepôt l'écrit, avec sa date d'instantané ; et le mix pose ce taux à côté du taux
moyen sans jamais l'y substituer. Toutes les valeurs sont inventées.
"""

from __future__ import annotations

from app.perf import incremental as I
from app.perf import mix as M
from tests.test_perf_mix import CANONICAL, _file, _month

HEADER = ("snapshot_date,snapshot_date_prev,channel_group,channel,sales_ty,stable_sales_ty,"
          "coverage_pct,countries_total,countries_stable,incremental_margin_pct,"
          "incremental_margin_prev_pct,average_margin_pct,sign_agreement,status\n")

CHANNELS = HEADER + (
    "2026-03-01,2025-03-01,SELL OUT,RETAIL,700000,690000,98.6,37,34,147.0,-274.3,13.8,"
    "signes opposes,mesure mais signe instable entre les deux paires\n"
    "2026-03-01,2025-03-01,SELL IN,WEB PARTNERS,260000,257000,98.7,12,8,49.7,26.5,42.4,"
    "meme signe,mesure\n"
    "2026-03-01,2025-03-01,SELL IN,DEPARTMENT STORES,57000,56000,99.0,6,3,35.4,72.9,34.8,"
    "meme signe,mesure\n"
    "2026-03-01,2025-03-01,SELL IN,CHAINS WHOLESALE,680000,53000,7.8,20,5,63.1,40.0,44.7,"
    "meme signe,mesure sur couverture partielle 7.8 % des ventes du canal\n"
    "2026-03-01,2025-03-01,SELL OUT,E-BUSINESS,279000,241000,86.5,14,9,-13.9,52.8,34.6,"
    "signes opposes,mesure mais signe instable entre les deux paires\n"
    "2026-03-01,2025-03-01,SELL IN,ONE SPA WORLD,33000,33000,100,1,1,-51.9,NULL,11.0,"
    ",ABSENT aucune cellule a serie stable\n"
)


def _read(tmp_path, text=CHANNELS):
    path = tmp_path / "incremental_margin_channels.csv"
    path.write_text(text, encoding="utf-8")
    return I.load(str(path))


# ------------------------------------------------------------------- le fichier


def test_only_the_measured_status_makes_a_rate(tmp_path):
    """Un signe qui change quand on décale la paire, une couverture partielle, une absence :
    trois statuts, nommés tels quels, et aucun ne pose un taux sur le canal."""
    read = _read(tmp_path)

    assert abs(read.of("webp").marginal - 0.497) < 1e-9
    assert read.of("webp").label == "50 %"
    assert read.of("dpt").label == "35 %"
    assert read.of("retail") is None
    assert read.of("whoch") is None
    assert read.of("ecommerce") is None
    assert [rate.name for rate in read.measured] == ["WEB PARTNERS", "DEPARTMENT STORES"]
    retail = next(rate for rate in read.unmeasured if rate.name == "RETAIL")
    assert retail.status == "mesure mais signe instable entre les deux paires"
    assert abs(retail.marginal - 1.47) < 1e-9 and not retail.measured
    assert read.snapshot == "2026-03-01"


def test_the_lever_is_marginal_minus_average_on_the_same_base(tmp_path):
    read = _read(tmp_path)

    assert abs(read.of("webp").lever - (0.497 - 0.424)) < 1e-9
    assert read.of("webp").lever_label == "+7 pts"
    assert read.of("dpt").lever_label == "+1 pt"


def test_the_management_account_labels_join_the_cockpit_channels(tmp_path):
    read = _read(tmp_path)

    assert read.of("webp").screen_name == "E-retailers"
    assert I.channels_of("E-BUSINESS") == ("ecommerce",)
    assert I.channels_of("MARKET PLACE") == ("marketplace",)
    assert I.channels_of("CHAINS WHOLESALE") == ("whoch",)
    assert I.channels_of("WHOLESALE INDEP") == ("whoin",)
    assert I.channels_of("DIGITAL DIRECT SELLING") == ("direct selling",)
    # Un client, pas un canal : la ligne est gardée, ne couvre rien, et le défaut le dit.
    assert [rate.name for rate in read.unmapped] == ["ONE SPA WORLD"]
    assert any("ONE SPA WORLD" in fault for fault in read.faults)


def test_null_is_an_absence_not_a_zero(tmp_path):
    read = _read(tmp_path)
    spa = next(rate for rate in read.rates if rate.name == "ONE SPA WORLD")

    assert spa.previous is None


def test_a_missing_file_or_column_is_an_empty_reading(tmp_path):
    assert I.load(str(tmp_path / "nulle-part.csv")).is_empty
    read = _read(tmp_path, "channel,status\nRETAIL,mesure\n")
    assert read.is_empty and "incremental_margin_pct" in read.faults[0]


def test_a_measured_line_without_a_readable_rate_is_named_and_demoted(tmp_path):
    read = _read(tmp_path, HEADER + "2026-03-01,2025-03-01,SELL IN,B2B,1,1,100,1,1,NULL,1,1,,mesure\n")

    assert read.of("b2b") is None
    assert any("sans taux lisible" in fault for fault in read.faults)


# ----------------------------------------------------------------------- le mix


def test_the_mix_carries_the_marginal_rate_beside_the_average_never_instead(tmp_path):
    """E-commerce est mesuré au fichier de contribution mais son taux marginal est à signe
    instable : il garde son taux moyen et n'a pas de taux marginal. Retail de même. Le
    calcul marginal ne somme que ce qui est mesuré, et dit sa couverture."""
    month = _month()
    review = M.build(month, M.load(_file(tmp_path, CANONICAL)), _read(tmp_path))

    assert review.weighs and not review.measures
    assert review.marginal.startswith("Taux marginal : absent")

    month.units[0].channel = "webp"  # la même unité, vendue en E-retailers
    month.units[0].key = "n-webp"
    review = M.build(month, M.load(_file(tmp_path, CANONICAL)), _read(tmp_path))

    assert review.measures
    webp = next(piece for piece in review.slices if piece.channel == "webp")
    assert webp.marginal_label == "50 %" and webp.lever_label == "+7 pts"
    assert abs(webp.weighted_marginal - 0.497 * 50.0) < 1e-9
    assert abs(review.weighted_marginal - 0.497 * 50.0) < 1e-9
    assert review.marginal_coverage_label == "75 %"
    assert review.marginal.startswith("Taux marginal mesuré au compte de gestion (instantané du 2026-03-01)")
    assert "E-retailers 50 %" in review.marginal
    assert "E-commerce (mesure mais signe instable entre les deux paires)" in review.marginal
    assert "Travel Retail (absent du fichier)" in review.marginal
    # Le taux moyen n'a pas bougé et se lit à côté : absent pour E-retailers, que le fichier
    # de contribution ne nomme pas, présent pour E-commerce.
    assert webp.rate_label == "absent"
    assert next(piece for piece in review.slices if piece.channel == "ecommerce").rate_label == "37 %"


def test_the_file_faults_reach_the_review_by_name(tmp_path):
    review = M.build(_month(), None, _read(tmp_path))

    assert any(reason.startswith("marge incrémentale, ligne 7") for reason in review.absent)
