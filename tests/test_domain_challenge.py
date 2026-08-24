"""Challenge : « ne critique pas pour le spectacle » (brief §9)."""

from __future__ import annotations

from app.domain.challenge import (
    EXPECTED_VOICES,
    ChallengeInput,
    check_challenge,
    group_by_voice,
    summarize,
)
from app.domain.enums import ChallengeKind, ChallengeStatus, ChallengeVoice, Severity


def codes(warnings) -> set:
    return {w.code for w in warnings}


def objection(**overrides) -> ChallengeInput:
    base = {
        "objection": "Le trafic ne dit rien de la conversion.",
        "voice": ChallengeVoice.DEVILS_ADVOCATE.value,
        "kind": ChallengeKind.PREMISE.value,
        "evidence": "Deux comptages divergents, aucune mesure de conversion.",
        "severity": Severity.SERIOUS.value,
        "status": ChallengeStatus.OPEN.value,
        "response": "",
    }
    base.update(overrides)
    return ChallengeInput(**base)


def test_objection_sans_preuve_est_signalee():
    """Enregistrée quand même : refuser pousserait à inventer une preuve pour faire
    passer le formulaire."""
    warnings = check_challenge(objection(evidence=""))

    assert "objection_without_evidence" in codes(warnings)
    assert any(w.is_serious for w in warnings)


def test_objection_fondee_et_ouverte_ne_declenche_rien():
    assert check_challenge(objection()) == []


def test_objection_bloquante_sans_reponse_est_signalee():
    warnings = check_challenge(objection(severity=Severity.BLOCKING.value))

    assert "blocking_unanswered" in codes(warnings)


def test_objection_bloquante_repondue_ne_declenche_rien():
    warnings = check_challenge(
        objection(
            severity=Severity.BLOCKING.value,
            status=ChallengeStatus.ACCEPTED.value,
            response="Retenue : l'option recommandée passe par un test.",
        )
    )

    assert warnings == []


def test_objection_classee_sans_reponse_ecrite_est_signalee():
    warnings = check_challenge(objection(status=ChallengeStatus.ANSWERED.value))

    assert "closed_without_response" in codes(warnings)


def test_objection_ecartee_sans_motif_est_signalee_en_mineur():
    warnings = check_challenge(objection(status=ChallengeStatus.REJECTED.value))

    assert "rejected_without_reason" in codes(warnings)
    minor = next(w for w in warnings if w.code == "rejected_without_reason")
    assert not minor.is_serious


def test_tous_les_avertissements_portent_un_correctif():
    warnings = check_challenge(
        objection(evidence="", status=ChallengeStatus.REJECTED.value)
    )

    assert warnings
    assert all(w.fix.strip() for w in warnings)


# --------------------------------------------------------------------------- synthèse


def test_synthese_d_un_ensemble_vide():
    summary = summarize([])

    assert summary.total == 0
    assert not summary.premise_tested
    assert summary.missing_voices == list(EXPECTED_VOICES)


def test_premisse_testee_exige_une_reponse_ecrite():
    """« Testée » veut dire qu'on y a répondu, pas seulement qu'on l'a écrite."""
    posee = summarize([objection(kind=ChallengeKind.PREMISE.value)])
    classee_sans_reponse = summarize(
        [objection(kind=ChallengeKind.PREMISE.value, status=ChallengeStatus.ACCEPTED.value)]
    )
    repondue = summarize(
        [
            objection(
                kind=ChallengeKind.PREMISE.value,
                status=ChallengeStatus.ACCEPTED.value,
                response="Retenue, d'où le marché test.",
            )
        ]
    )

    assert not posee.premise_tested
    assert not classee_sans_reponse.premise_tested
    assert repondue.premise_tested


def test_un_scenario_adverse_repondu_ne_vaut_pas_une_premisse_testee():
    summary = summarize(
        [
            objection(
                kind=ChallengeKind.ADVERSE_SCENARIO.value,
                status=ChallengeStatus.ANSWERED.value,
                response="Séquencement assumé.",
            )
        ]
    )

    assert not summary.premise_tested


def test_synthese_compte_les_bloquantes_sans_reponse():
    summary = summarize(
        [
            objection(severity=Severity.BLOCKING.value),
            objection(
                severity=Severity.BLOCKING.value,
                status=ChallengeStatus.ACCEPTED.value,
                response="Répondu.",
            ),
            objection(),
        ]
    )

    assert summary.total == 3
    assert summary.unanswered_blocking == 1
    assert summary.unanswered == 2


def test_voix_manquantes_sont_listees_avec_leur_libelle():
    summary = summarize(
        [
            objection(voice=ChallengeVoice.DEVILS_ADVOCATE.value),
            objection(voice=ChallengeVoice.FINANCE.value),
        ]
    )

    assert ChallengeVoice.CLIENT.value in summary.missing_voices
    assert "Client" in summary.missing_voice_labels
    assert "Finance" not in summary.missing_voice_labels


def test_voix_de_condition_ne_sont_pas_exigees():
    """People, Opérations et Réputation éclairent sans que leur silence bloque : la
    doctrine maison les traite comme des conditions, pas comme des sièges."""
    assert ChallengeVoice.PEOPLE.value not in EXPECTED_VOICES
    assert ChallengeVoice.OPERATIONS.value not in EXPECTED_VOICES
    assert ChallengeVoice.REPUTATION.value not in EXPECTED_VOICES


def test_regroupement_par_voix_couvre_toutes_les_voix():
    grouped = group_by_voice([objection(voice=ChallengeVoice.CLIENT.value)])

    assert set(grouped) >= {member.value for member in ChallengeVoice}
    assert len(grouped[ChallengeVoice.CLIENT.value]) == 1
    assert grouped[ChallengeVoice.FINANCE.value] == []
