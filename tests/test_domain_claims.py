"""Qualification des affirmations — l'invariant central du produit (brief §4)."""

from __future__ import annotations

from app.domain.claims import (
    ClaimInput,
    check_claim,
    count_by_category,
    resolve_category,
    source_coverage,
    unsourced_facts,
)
from app.domain.enums import ClaimCategory, Materiality


def codes(warnings) -> set:
    return {w.code for w in warnings}


def test_fait_sans_source_est_signale_mais_conserve_sa_categorie():
    """Politique retenue : avertissement, pas refus.

    L'affirmation reste un « fait » avec un avertissement sérieux. La requalifier
    automatiquement en hypothèse effacerait l'information intéressante — à savoir que
    quelqu'un a présenté cela comme établi.
    """
    claim = ClaimInput(text="Le marché croît de 8 %.", category=ClaimCategory.SOURCED_FACT.value)

    warnings = check_claim(claim)

    assert "fact_without_source" in codes(warnings)
    assert any(w.is_serious for w in warnings)
    assert (
        resolve_category(ClaimCategory.SOURCED_FACT.value, "")
        == ClaimCategory.SOURCED_FACT.value
    )


def test_avertissement_porte_un_correctif_concret():
    """Un avertissement sans geste à faire est un reproche, pas un mode d'emploi."""
    warnings = check_claim(
        ClaimInput(text="Fait", category=ClaimCategory.SOURCED_FACT.value)
    )

    assert all(w.fix.strip() for w in warnings)
    assert all(w.message.strip() for w in warnings)


def test_fait_source_sans_citation_est_un_avertissement_mineur():
    warnings = check_claim(
        ClaimInput(
            text="Le droit d'entrée est non récupérable.",
            category=ClaimCategory.SOURCED_FACT.value,
            source_ref="Projet de bail, art. 14",
        )
    )

    assert codes(warnings) == {"fact_without_quote"}
    assert not any(w.is_serious for w in warnings)


def test_fait_source_et_cite_ne_declenche_rien():
    warnings = check_claim(
        ClaimInput(
            text="Le droit d'entrée est non récupérable.",
            category=ClaimCategory.SOURCED_FACT.value,
            source_ref="Projet de bail, art. 14",
            quote="Le droit d'entrée reste acquis au bailleur.",
        )
    )

    assert warnings == []


def test_hypothese_determinante_sans_test_est_serieuse():
    """Le cas le plus dangereux : la décision repose sur une hypothèse que personne
    ne prévoit de vérifier."""
    warnings = check_claim(
        ClaimInput(
            text="L'équipe sera recrutée en quatre mois.",
            category=ClaimCategory.ASSUMPTION.value,
            rationale="Par analogie avec 2024.",
            materiality=Materiality.HIGH.value,
        )
    )

    assert "decisive_assumption_untested" in codes(warnings)
    assert any(w.is_serious for w in warnings)


def test_hypothese_determinante_avec_test_reste_acceptable():
    warnings = check_claim(
        ClaimInput(
            text="L'équipe sera recrutée en quatre mois.",
            category=ClaimCategory.ASSUMPTION.value,
            rationale="Par analogie avec 2024.",
            best_test="Consulter deux cabinets locaux avant octobre.",
            materiality=Materiality.HIGH.value,
        )
    )

    assert warnings == []


def test_hypothese_sans_justification_est_signalee():
    warnings = check_claim(
        ClaimInput(text="Le sujet est mûr.", category=ClaimCategory.ASSUMPTION.value)
    )

    assert "assumption_without_rationale" in codes(warnings)


def test_opinion_determinante_est_signalee():
    """Une opinion peut porter une décision, mais cela doit être dit."""
    warnings = check_claim(
        ClaimInput(
            text="Milan est le bon signal.",
            category=ClaimCategory.OPINION.value,
            materiality=Materiality.HIGH.value,
        )
    )

    assert "decisive_opinion" in codes(warnings)


def test_inconnue_sans_test_est_signalee():
    warnings = check_claim(
        ClaimInput(
            text="La méthode de comptage n'est pas documentée.",
            category=ClaimCategory.MISSING_VERIFICATION.value,
        )
    )

    assert "missing_verification_without_test" in codes(warnings)


def test_liste_des_faits_non_sources():
    claims = [
        ClaimInput(text="A", category=ClaimCategory.SOURCED_FACT.value, source_ref="Doc 1"),
        ClaimInput(text="B", category=ClaimCategory.SOURCED_FACT.value),
        ClaimInput(text="C", category=ClaimCategory.ASSUMPTION.value),
    ]

    result = unsourced_facts(claims)

    assert [c.text for c in result] == ["B"]


def test_couverture_est_absente_plutot_que_parfaite_sur_ensemble_vide():
    """Afficher « 100 % des faits sont sourcés » sans aucun fait serait la fausse
    précision que le brief §10 interdit."""
    assert source_coverage([]) is None
    assert source_coverage([ClaimInput(text="A", category=ClaimCategory.OPINION.value)]) is None


def test_couverture_se_calcule_sur_les_faits_seulement():
    claims = [
        ClaimInput(text="A", category=ClaimCategory.SOURCED_FACT.value, source_ref="Doc"),
        ClaimInput(text="B", category=ClaimCategory.SOURCED_FACT.value),
        ClaimInput(text="C", category=ClaimCategory.OPINION.value),
    ]

    assert source_coverage(claims) == 0.5


def test_comptage_par_categorie_couvre_toutes_les_categories():
    counts = count_by_category(
        [ClaimInput(text="A", category=ClaimCategory.SOURCED_FACT.value, source_ref="D")]
    )

    assert set(counts) == {member.value for member in ClaimCategory}
    assert counts[ClaimCategory.SOURCED_FACT.value] == 1
    assert counts[ClaimCategory.OPINION.value] == 0
