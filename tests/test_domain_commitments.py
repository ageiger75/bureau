"""Engagements : rendre le retard visible, sans agir à l'extérieur (brief §7 FR-10)."""

from __future__ import annotations

import pytest

from app.domain.commitments import (
    CLOSED,
    DUE_SOON,
    DUE_SOON_DAYS,
    NO_DATE,
    ON_TRACK,
    OVERDUE,
    CommitmentInput,
    alert_level,
    check_commitment,
    is_closed,
    summarize,
)
from app.domain.enums import CommitmentStatus


def codes(warnings) -> set:
    return {w.code for w in warnings}


def commitment(**overrides) -> CommitmentInput:
    base = {
        "action": "Mettre en place le suivi mensuel des ventes en ligne.",
        "owner_name": "Direction e-commerce",
        "due_date": "2026-07-31",
        "status": CommitmentStatus.OPEN.value,
        "is_critical": False,
        "evidence": "",
    }
    base.update(overrides)
    return CommitmentInput(**base)


# --------------------------------------------------------------------------- alertes


@pytest.mark.parametrize(
    "days_left,expected",
    [
        (-1, OVERDUE),
        (0, DUE_SOON),
        (DUE_SOON_DAYS, DUE_SOON),
        (DUE_SOON_DAYS + 1, ON_TRACK),
        (None, NO_DATE),
    ],
)
def test_niveaux_d_alerte(days_left, expected):
    assert alert_level(CommitmentStatus.OPEN.value, days_left) == expected


@pytest.mark.parametrize(
    "status", [CommitmentStatus.DONE.value, CommitmentStatus.CANCELLED.value]
)
def test_engagement_clos_n_est_jamais_en_retard(status):
    """Le retard concerne ce qui reste à faire, pas ce qui est derrière nous."""
    assert alert_level(status, -60) == CLOSED
    assert is_closed(status)


def test_engagement_bloque_reste_en_retard():
    """Bloqué n'est pas clos : c'est précisément ce qu'il faut voir."""
    assert alert_level(CommitmentStatus.BLOCKED.value, -5) == OVERDUE
    assert not is_closed(CommitmentStatus.BLOCKED.value)


# --------------------------------------------------------------------------- contrôles


def test_engagement_sans_proprietaire_est_signale():
    warnings = check_commitment(commitment(owner_name=""))

    assert "commitment_without_owner" in codes(warnings)


def test_engagement_sans_echeance_est_signale():
    """Sans date, il ne remontera jamais comme en retard : c'est le pire des cas."""
    warnings = check_commitment(commitment(due_date=None))

    assert "commitment_without_due_date" in codes(warnings)


def test_engagement_complet_ne_declenche_rien():
    assert check_commitment(commitment(), days_left=10) == []


def test_termine_sans_preuve_est_un_avertissement_mineur():
    """Le produit ne lit aucun système externe : il ne peut pas constater l'avancement seul."""
    warnings = check_commitment(
        commitment(status=CommitmentStatus.DONE.value), days_left=-10
    )

    assert "done_without_evidence" in codes(warnings)
    assert not any(w.is_serious for w in warnings)


def test_engagement_critique_bloque_est_serieux():
    warnings = check_commitment(
        commitment(is_critical=True, status=CommitmentStatus.BLOCKED.value), days_left=5
    )

    assert "critical_blocked" in codes(warnings)
    assert any(w.is_serious for w in warnings)


def test_engagement_critique_en_retard_appelle_une_revue_pas_une_relance():
    warnings = check_commitment(commitment(is_critical=True), days_left=-3)

    assert "critical_overdue" in codes(warnings)
    fix = next(w.fix for w in warnings if w.code == "critical_overdue")
    assert "relance" in fix


# --------------------------------------------------------------------------- synthèse


def test_synthese_d_un_ensemble_vide_n_affiche_aucun_pourcentage():
    """Un « 100 % » sans engagement serait la fausse précision interdite au brief §10."""
    summary = summarize([])

    assert summary.total == 0
    assert summary.completion_label == "Aucun engagement"
    assert not summary.all_closed


def test_synthese_compte_retards_et_criticites():
    summary = summarize(
        [
            (commitment(is_critical=True), -5),
            (commitment(), -2),
            (commitment(status=CommitmentStatus.DONE.value, evidence="Note du 6 mai."), -30),
            (commitment(status=CommitmentStatus.IN_PROGRESS.value), 20),
        ]
    )

    assert summary.total == 4
    assert summary.overdue == 2
    assert summary.critical_overdue == 1
    assert summary.done == 1
    assert summary.open_count == 3


def test_deux_engagements_de_meme_libelle_sont_comptes_separement():
    """Régression : une version antérieure indexait les échéances sur le texte de l'action,
    ce qui faisait disparaître le second des deux homonymes."""
    summary = summarize(
        [(commitment(action="Relancer le bailleur"), -1),
         (commitment(action="Relancer le bailleur"), -1)]
    )

    assert summary.total == 2
    assert summary.overdue == 2


def test_rearbitrage_est_compte():
    summary = summarize(
        [(commitment(status=CommitmentStatus.REARBITRATION_NEEDED.value), 5)]
    )

    assert summary.rearbitration_needed == 1
    assert summary.open_count == 1


def test_avancement_s_accorde_en_nombre():
    un = summarize([(commitment(status=CommitmentStatus.DONE.value), 1),
                    (commitment(), 1)])
    deux = summarize([(commitment(status=CommitmentStatus.DONE.value), 1),
                      (commitment(status=CommitmentStatus.DONE.value), 1),
                      (commitment(), 1)])

    assert un.completion_label == "1 engagement sur 2 terminé"
    assert deux.completion_label == "2 engagements sur 3 terminés"
