"""Maturité d'un dossier et transitions d'état (brief §6 et §7)."""

from __future__ import annotations

import pytest

from app.domain.cases import (
    CaseSnapshot,
    TransitionContext,
    TransitionRefused,
    assess_readiness,
    can_transition,
    next_statuses,
    offered_statuses,
    transition,
    urgency,
)
from app.domain.enums import CaseStatus


def blocker_codes(readiness) -> set:
    return {b.code for b in readiness.blockers}


def warning_codes(readiness) -> set:
    return {w.code for w in readiness.warnings}


def mature_snapshot(**overrides) -> CaseSnapshot:
    """Un dossier qui ne devrait rien bloquer. Point de départ de chaque test : on en
    dégrade un seul aspect à la fois pour vérifier que le bon bloquant apparaît."""
    base = {
        "question": "Faut-il ouvrir à Milan avant décembre ?",
        "real_decision": "Immobiliser du capital sur un actif peu réversible.",
        "option_count": 3,
        "status_quo_present": True,
        "sourced_fact_count": 4,
        "assumption_count": 2,
        "missing_verification_count": 1,
        "unsourced_fact_count": 0,
        "has_recommendation": True,
        "recommendation_has_change_conditions": True,
        # Tranche 2 : un dossier contesté, dont une prémisse a reçu une réponse.
        "challenge_count": 3,
        "unanswered_blocking_challenges": 0,
        "premise_tested": True,
        "challenges_without_evidence": 0,
        "missing_voice_labels": (),
    }
    base.update(overrides)
    return CaseSnapshot(**base)


def ready_context(**overrides) -> TransitionContext:
    base = {"readiness": assess_readiness(mature_snapshot())}
    base.update(overrides)
    return TransitionContext(**base)


def test_dossier_vide_cumule_les_bloquants():
    readiness = assess_readiness(CaseSnapshot())

    assert not readiness.is_ready
    assert blocker_codes(readiness) == {
        "no_question",
        "too_few_options",
        "no_declared_uncertainty",
        "no_recommendation",
        "never_challenged",
    }


def test_dossier_mature_est_pret():
    readiness = assess_readiness(mature_snapshot())

    assert readiness.is_ready
    assert readiness.blockers == []


def test_une_seule_option_bloque():
    """Une option unique n'est pas un arbitrage, c'est une intention à valider."""
    readiness = assess_readiness(mature_snapshot(option_count=1, status_quo_present=False))

    assert "too_few_options" in blocker_codes(readiness)


def test_plus_de_trois_options_bloque():
    readiness = assess_readiness(mature_snapshot(option_count=4))

    assert "too_many_options" in blocker_codes(readiness)


def test_absence_d_incertitude_declaree_bloque():
    readiness = assess_readiness(
        mature_snapshot(assumption_count=0, missing_verification_count=0)
    )

    assert "no_declared_uncertainty" in blocker_codes(readiness)


def test_recommandation_sans_conditions_d_invalidation_bloque():
    """Le brief §4 exige de préciser ce qui ferait changer l'avis."""
    readiness = assess_readiness(mature_snapshot(recommendation_has_change_conditions=False))

    assert "recommendation_without_change_conditions" in blocker_codes(readiness)


def test_faits_non_sources_avertissent_sans_bloquer():
    """Le choix produit : signaler, laisser décider."""
    readiness = assess_readiness(mature_snapshot(unsourced_fact_count=2))

    assert readiness.is_ready
    assert "unsourced_facts" in warning_codes(readiness)
    assert readiness.serious_warning_count >= 1


def test_message_d_avertissement_indique_le_nombre_de_faits():
    readiness = assess_readiness(mature_snapshot(unsourced_fact_count=3))

    message = next(w.message for w in readiness.warnings if w.code == "unsourced_facts")
    assert "3" in message


def test_absence_de_fait_source_avertit_sans_bloquer():
    readiness = assess_readiness(mature_snapshot(sourced_fact_count=0))

    assert readiness.is_ready
    assert "no_sourced_fact" in warning_codes(readiness)


def test_absence_de_statu_quo_est_un_avertissement_mineur():
    readiness = assess_readiness(mature_snapshot(status_quo_present=False))

    assert readiness.is_ready
    warning = next(w for w in readiness.warnings if w.code == "no_status_quo")
    assert warning.severity == "minor"


def test_cadrage_non_reformule_avertit():
    readiness = assess_readiness(mature_snapshot(real_decision=""))

    assert readiness.is_ready
    assert "real_decision_not_reframed" in warning_codes(readiness)


# --------------------------------------------------------------------------- transitions


def test_brouillon_ne_peut_pas_sauter_directement_a_pret():
    ok, reason = can_transition(CaseStatus.DRAFT.value, CaseStatus.READY.value)

    assert not ok
    assert reason


def test_analyse_vers_pret_exige_un_dossier_mature():
    with pytest.raises(TransitionRefused) as excinfo:
        transition(
            CaseStatus.ANALYSIS.value,
            CaseStatus.READY.value,
            TransitionContext(readiness=assess_readiness(CaseSnapshot())),
        )

    assert "n'est pas prêt" in str(excinfo.value)


def test_analyse_vers_pret_passe_si_le_dossier_est_mature():
    result = transition(
        CaseStatus.ANALYSIS.value, CaseStatus.READY.value, ready_context()
    )

    assert result == CaseStatus.READY.value


def test_pret_vers_pret_est_refuse():
    ok, reason = can_transition(CaseStatus.READY.value, CaseStatus.READY.value)

    assert not ok
    assert "déjà" in reason


def test_retour_en_analyse_est_autorise():
    """Découvrir une inconnue après coup doit pouvoir ramener le dossier en arrière."""
    assert transition(CaseStatus.READY.value, CaseStatus.ANALYSIS.value) == (
        CaseStatus.ANALYSIS.value
    )


def test_transition_sans_diagnostic_vers_pret_est_refusee():
    with pytest.raises(TransitionRefused):
        transition(CaseStatus.ANALYSIS.value, CaseStatus.READY.value)


# --------------------------------------------------- boucle décisionnelle (tranche 2)


def test_decider_exige_une_decision_enregistree():
    """Changer le statut ne doit pas suffire : le choix, les raisons, les réserves et la
    date de revue doivent être conservés (brief §2)."""
    with pytest.raises(TransitionRefused) as excinfo:
        transition(CaseStatus.READY.value, CaseStatus.DECIDED.value, ready_context())

    assert "écran Décision" in str(excinfo.value)


def test_decider_passe_avec_une_decision_enregistree():
    result = transition(
        CaseStatus.READY.value,
        CaseStatus.DECIDED.value,
        ready_context(has_decision=True),
    )

    assert result == CaseStatus.DECIDED.value


def test_executer_exige_au_moins_un_engagement():
    with pytest.raises(TransitionRefused) as excinfo:
        transition(
            CaseStatus.DECIDED.value,
            CaseStatus.EXECUTING.value,
            ready_context(has_decision=True),
        )

    assert "elle s'oublie" in str(excinfo.value)


def test_executer_passe_avec_un_engagement():
    result = transition(
        CaseStatus.DECIDED.value,
        CaseStatus.EXECUTING.value,
        ready_context(has_decision=True, commitment_count=1),
    )

    assert result == CaseStatus.EXECUTING.value


def test_passer_a_revoir_exige_une_revue_planifiee():
    with pytest.raises(TransitionRefused):
        transition(
            CaseStatus.EXECUTING.value,
            CaseStatus.TO_REVIEW.value,
            ready_context(has_decision=True, commitment_count=2),
        )


def test_clore_exige_une_revue_terminee():
    """Clore sans confronter les hypothèses aux résultats fait perdre le seul
    enseignement réutilisable."""
    with pytest.raises(TransitionRefused) as excinfo:
        transition(
            CaseStatus.TO_REVIEW.value,
            CaseStatus.CLOSED.value,
            ready_context(has_decision=True, commitment_count=2, has_planned_review=True),
        )

    assert "revue n'est pas terminée" in str(excinfo.value)


def test_clore_passe_avec_une_revue_terminee():
    result = transition(
        CaseStatus.TO_REVIEW.value,
        CaseStatus.CLOSED.value,
        ready_context(has_decision=True, review_completed=True),
    )

    assert result == CaseStatus.CLOSED.value


def test_reouverture_depuis_clos_est_possible_et_explicite():
    """Le brief §6 : « Réouverture explicite uniquement »."""
    assert transition(CaseStatus.CLOSED.value, CaseStatus.ANALYSIS.value) == (
        CaseStatus.ANALYSIS.value
    )


def test_reouverture_depuis_a_revoir_est_possible():
    assert transition(CaseStatus.TO_REVIEW.value, CaseStatus.ANALYSIS.value) == (
        CaseStatus.ANALYSIS.value
    )


def test_etats_proposes_couvrent_la_boucle():
    assert next_statuses(CaseStatus.DRAFT.value) == [CaseStatus.ANALYSIS.value]
    assert CaseStatus.DECIDED.value in next_statuses(CaseStatus.READY.value)
    assert next_statuses(CaseStatus.EXECUTING.value) == [CaseStatus.TO_REVIEW.value]


def test_decider_et_clore_ne_sont_pas_proposes_comme_boutons_d_etat():
    """Ils passent par leur écran : proposer « Décidé » comme un simple changement de
    statut laisserait croire qu'on peut décider sans rien enregistrer."""
    assert CaseStatus.DECIDED.value not in offered_statuses(CaseStatus.READY.value)
    assert CaseStatus.ANALYSIS.value in offered_statuses(CaseStatus.READY.value)
    assert CaseStatus.CLOSED.value not in offered_statuses(CaseStatus.TO_REVIEW.value)


# --------------------------------------------------- challenge (tranche 2)


def test_dossier_jamais_conteste_ne_peut_pas_etre_pret():
    """Le risque principal du produit : devenir une machine à confirmer l'intuition."""
    readiness = assess_readiness(mature_snapshot(challenge_count=0))

    assert "never_challenged" in blocker_codes(readiness)


def test_objection_bloquante_sans_reponse_bloque():
    readiness = assess_readiness(mature_snapshot(unanswered_blocking_challenges=2))

    assert "unanswered_blocking_challenge" in blocker_codes(readiness)


def test_aucune_premisse_testee_bloque():
    readiness = assess_readiness(mature_snapshot(premise_tested=False))

    assert "no_premise_tested" in blocker_codes(readiness)


def test_objection_sans_preuve_avertit_sans_bloquer():
    readiness = assess_readiness(mature_snapshot(challenges_without_evidence=1))

    assert readiness.is_ready
    assert "objections_without_evidence" in warning_codes(readiness)


def test_voix_absentes_sont_signalees_sans_bloquer():
    readiness = assess_readiness(
        mature_snapshot(missing_voice_labels=("Finance", "Client"))
    )

    assert readiness.is_ready
    warning = next(w for w in readiness.warnings if w.code == "voices_not_heard")
    assert "Finance" in warning.message
    assert warning.severity == "minor"


# --------------------------------------------------------------------------- urgence


def test_classes_d_urgence():
    assert urgency(-1) == "overdue"
    assert urgency(0) == "critical"
    assert urgency(3) == "critical"
    assert urgency(4) == "soon"
    assert urgency(10) == "soon"
    assert urgency(11) == "later"
    assert urgency(None) == "none"
