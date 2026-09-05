"""Le plan EBITDA par périmètre, tel que la Finance l'a budgété — et rien de plus.

Ces tests gardent trois choses : la feuille de synthèse se lit telle que la Finance
l'écrit, avec ses trois blocs — BU, flux à nettoyer, pont vers le consolidé ajusté ; le pas
de marge demandé se lit sur la feuille COP, région par région ; et aucun réel n'est jamais
déduit d'un plan. Toutes les valeurs sont inventées.
"""

from __future__ import annotations

from app.perf import ebitda as E
from tests.test_perf_actuals import _workbook


def _recap():
    return [
        ["CONSOLIDATED EBITDA ADJUSTED CONTRIBUTION BY BU", None, None, None],
        [None, "BUDGET FY27", None, None],
        [None, "SALES", "EBITDA CONSO", "EBITDA %"],
        ["JAPAN", 100.0, 12.0, 0.12],
        ["CHINA", 300.0, 75.0, 0.25],
        ["NA", 250.0, 40.0, 0.16],
        ["EMEA COUNTRIES", 240.0, 24.0, 0.10],
        ["EMEA DISTRIBUTORS", 60.0, 30.0, 0.50],
        ["BRASIL", 30.0, 3.0, 0.10],
        ["WW TR", 80.0, 32.0, 0.40],
        ["OTHER", 10.0, 6.0, 0.60],
        ["HEALTHY BUSINESS CONTRIBUTION", 1070.0, 222.0, 0.21],
        ["CLEANING ONE", 20.0, 12.0, 0.60],
        ["CLEANING TWO", 10.0, 8.0, 0.80],
        ["NON HEALTHY BUSINESS CONTRIBUTION", 30.0, 20.0, 0.67],
        [None],
        ["TOTAL BUSINESS CONTRIBUTION", 1100.0, 242.0, 0.22],
        ["FACTORY COSTS", None, 10.0],
        ["INT - DISTRIBUTION", None, -100.0],
        ["GLOBAL COSTS", None, -90.0],
        ["RESERVE", None, -10.0],
        ["CONSO EBITDA ADJUSTED", None, 52.0, 0.05],
    ]


def _cop():
    blank = [None]
    return [
        blank + ["2027 MAR"],
        blank + ["OPERATING PROFIT - CONTRIBUTION BY REGION"],
        blank + [None, None, "BUD 2027 MAR", None, None, None, "BUD 2027 MAR", None, None, None,
                 "REF3 2026 MAR", None, None],
        blank + [None, None, "AR", None, None, None, "CR", None, None, None, "AR", None, None],
        blank + ["Million Euro", None, "Sales", "OP", "%OP", None, "Sales", "OP", "%OP", None,
                 "Sales", "OP", "%OP"],
        blank + ["N.AMERICA", None, 250.0, 30.0, 0.12, None, 250.0, 30.0, 0.12, None,
                 200.0, 20.0, 0.10],
        blank + ["USA", "USA", 200.0, 25.0, 0.125, None, 200.0, 25.0, 0.125, None, 160.0, 16.0, 0.1],
        blank + ["GREATER EUROPE", None, 240.0, 36.0, 0.15, None, 240.0, 36.0, 0.15, None,
                 230.0, 23.0, 0.10],
        blank + ["SUB-TOTAL SPACE", None, 70.0, 10.0, 0.14, None, 70.0, 10.0, 0.14, None,
                 65.0, 7.0, 0.11],
        blank + ["FRANCE TOTAL", None, 60.0, 0.0, 0.0, None, 60.0, 0.0, 0.0, None,
                 70.0, -7.0, -0.10],
        blank + ["JAPAN", None, 100.0, 12.0, 0.12, None, 100.0, 12.0, 0.12, None, 110.0, 11.0, 0.10],
        blank + ["TOTAL COUNTRIES", None, 650.0, 78.0, 0.12, None, 650.0, 78.0, 0.12, None,
                 610.0, 47.0, 0.08],
        blank + ["LOI CORP", "International Costs", 0.0, -130.0],
        blank + ["TOTAL GROUP", None, 650.0, -52.0],
    ]


def _plan(tmp_path, recap=None, cop=None):
    sheets = {"1-RECAP EBITDA CONSO": recap or _recap(), "2-RECAP EBITDA SMC": _recap(),
              "EBITDA CONSO BU": [["x"]], "CMOP détaillé": [["x"]]}
    if cop is not False:
        sheets = {"COP detaillé": cop or _cop(), **sheets}
    return E.load(_workbook(tmp_path / "ebitda-budget.xlsx", sheets))


NAMES = ["Greater China", "North America", "APAC", "EMEA", "Japan", "Brazil"]


# ----------------------------------------------------------------- la synthèse


def test_the_recap_is_read_in_its_three_blocks(tmp_path):
    """Les BU, puis les flux que le budget nomme à nettoyer, puis le pont vers le consolidé
    ajusté : trois blocs, jamais confondus, et des millions rendus en euros."""
    plan = _plan(tmp_path)

    assert not plan.faults and plan.usable
    assert [line.name for line in plan.bus] == [
        "JAPAN", "CHINA", "NA", "EMEA COUNTRIES", "EMEA DISTRIBUTORS", "BRASIL", "WW TR", "OTHER"]
    assert plan.bus[0].sales == 100_000_000.0 and plan.bus[0].ebitda == 12_000_000.0
    assert plan.bus[0].rate_label == "12.0 %"
    assert plan.healthy.ebitda == 222_000_000.0
    assert [line.name for line in plan.unhealthy] == ["CLEANING ONE", "CLEANING TWO"]
    assert plan.unhealthy_total.sales == 30_000_000.0
    assert plan.total.ebitda == 242_000_000.0
    assert plan.bridge == [("FACTORY COSTS", 10_000_000.0), ("INT - DISTRIBUTION", -100_000_000.0),
                           ("GLOBAL COSTS", -90_000_000.0), ("RESERVE", -10_000_000.0)]
    assert plan.adjusted.ebitda == 52_000_000.0
    # Le taux du consolidé se lit sur les ventes totales, que la ligne du fichier ne répète pas.
    assert plan.adjusted.sales == 1_100_000_000.0


def test_two_bus_of_the_file_make_one_perimeter_of_the_screen(tmp_path):
    plan = _plan(tmp_path)
    emea = plan.perimeter("EMEA")

    assert emea.ebitda == 54_000_000.0 and emea.sales == 300_000_000.0
    assert emea.rate_label == "18.0 %"
    assert plan.perimeter("APAC") is None
    assert plan.names == ["Japan", "Greater China", "North America", "EMEA", "Brazil",
                          "Travel Retail", "Autres"]


# --------------------------------------------------------------- le pas de marge


def test_the_margin_step_reads_budget_against_the_previous_forecast(tmp_path):
    """Sur la feuille COP, aux taux réels des deux colonnes ; un sous-total n'est pas une
    région, et l'EMEA somme deux régions du fichier."""
    plan = _plan(tmp_path)

    assert [step.name for step in plan.regions] == ["N.AMERICA", "GREATER EUROPE",
                                                    "FRANCE TOTAL", "JAPAN"]
    north = plan.perimeter("North America")
    assert abs(north.step.margin_before - 0.10) < 1e-9
    assert abs(north.step.margin_budget - 0.12) < 1e-9
    assert north.step_sentence.startswith("marge opérationnelle de contribution : 10.0 % → 12.0 %")
    assert "+2.0 points" in north.step_sentence
    emea = plan.perimeter("EMEA")
    assert abs(emea.step.sales_budget - 300_000_000.0) < 1e-6
    assert abs(emea.step.margin_before - 16.0 / 300.0) < 1e-9
    assert plan.countries.name == "TOTAL COUNTRIES"


def test_without_the_cop_sheet_the_plan_is_read_and_the_step_is_absent(tmp_path):
    plan = _plan(tmp_path, cop=False)

    assert plan.usable
    assert plan.perimeter("Japan").step_sentence == ""
    assert any("COP" in fault for fault in plan.faults)


# --------------------------------------------------------------------- la revue


def test_the_review_places_the_file_on_the_screens_perimeters(tmp_path):
    review = E.build(_plan(tmp_path), NAMES)

    assert review.usable
    assert [item.name for item in review.perimeters] == ["Greater China", "North America",
                                                          "EMEA", "Japan", "Brazil"]
    assert [item.name for item in review.others] == ["Travel Retail", "Autres"]
    assert review.for_name("Japan").ebitda == 12_000_000.0
    assert review.for_name("Travel Retail").rate_label == "40.0 %"
    assert review.absent == ["sans ligne EBITDA au budget : APAC"]
    from app.perf.analytics import format_eur
    assert review.unhealthy_note.startswith(
        "dont %s d'EBITDA sur %s de ventes" % (format_eur(20_000_000), format_eur(30_000_000)))
    assert "CLEANING ONE, CLEANING TWO" in review.unhealthy_note


def test_no_actual_is_ever_derived_from_the_plan(tmp_path):
    """Le module ne porte ni atterrissage ni réel : un taux moyen ne convertit pas un écart
    de ventes en résultat, et la note le dit sur l'écran."""
    review = E.build(_plan(tmp_path), NAMES)

    assert "n'est pas lu" in review.note
    assert "jamais un atterrissage" in review.note
    for name in ("at_pace", "landing", "actual", "gap"):
        assert not hasattr(review, name)
        assert not hasattr(review.perimeters[0], name)


def test_without_the_file_the_review_names_it(tmp_path):
    review = E.build(None, NAMES)

    assert not review.usable
    assert review.absent == ["var/ebitda-budget.xlsx absent : le plan EBITDA par BU n'est pas lu"]
    assert review.for_name("Japan") is None


def test_a_workbook_without_the_recap_sheet_says_so(tmp_path):
    plan = E.load(_workbook(tmp_path / "other.xlsx", {"Summary": [["x"]]}))

    assert not plan.usable
    assert plan.faults[0].startswith("aucune feuille « RECAP EBITDA CONSO »")


def test_a_missing_file_is_a_fault_not_a_crash(tmp_path):
    plan = E.load(tmp_path / "nulle-part.xlsx")

    assert not plan.usable and plan.faults
