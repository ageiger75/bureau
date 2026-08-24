"""Revue : confronter les hypothèses aux résultats (brief §7 FR-14)."""

from __future__ import annotations

import pytest

from app.domain.enums import NextStep, ReviewStatus
from app.domain.reviews import (
    UPCOMING_DAYS,
    ReviewInput,
    blocking_issues,
    check_review,
    is_due,
    is_upcoming,
)


def codes(items) -> set:
    return {w.code for w in items}


def review(**overrides) -> ReviewInput:
    base = {
        "planned_date": "2026-08-14",
        "status": ReviewStatus.IN_PROGRESS.value,
        "observed_results": "Les ventes en ligne ont reculé de 4 % sur deux des trois villes.",
        "gaps": "Recul plus marqué qu'attendu sur une ville.",
        "invalidated_assumptions": "Le reclassement sans départ contraint n'a pas tenu.",
        "lessons": "Mesurer l'effet digital avant de fermer, pas après.",
        "next_step": NextStep.ADJUST.value,
        "next_step_note": "",
    }
    base.update(overrides)
    return ReviewInput(**base)


# --------------------------------------------------------------------------- échéances


@pytest.mark.parametrize("days_left,expected", [(-1, True), (0, True), (1, False)])
def test_revue_echue(days_left, expected):
    assert is_due(ReviewStatus.PLANNED.value, days_left) is expected


def test_revue_terminee_n_est_jamais_echue():
    assert not is_due(ReviewStatus.COMPLETED.value, -90)
    assert not is_upcoming(ReviewStatus.COMPLETED.value, 3)


@pytest.mark.parametrize(
    "days_left,expected",
    [(0, False), (1, True), (UPCOMING_DAYS, True), (UPCOMING_DAYS + 1, False)],
)
def test_revue_a_venir(days_left, expected):
    assert is_upcoming(ReviewStatus.PLANNED.value, days_left) is expected


def test_revue_sans_date_n_est_ni_echue_ni_a_venir():
    assert not is_due(ReviewStatus.PLANNED.value, None)
    assert not is_upcoming(ReviewStatus.PLANNED.value, None)


# --------------------------------------------------------------------------- contrôles


def test_revue_complete_ne_declenche_rien():
    assert check_review(review()) == []


def test_revue_sans_resultats_est_signalee():
    assert "review_without_results" in codes(check_review(review(observed_results="")))


def test_revue_sans_lecon_est_signalee():
    """Sans leçon, la revue n'apprend rien à la décision suivante."""
    assert "review_without_lessons" in codes(check_review(review(lessons="")))


def test_aucune_hypothese_confrontee_est_un_avertissement_mineur():
    warnings = check_review(review(invalidated_assumptions=""))

    assert "no_assumption_reviewed" in codes(warnings)
    item = next(w for w in warnings if w.code == "no_assumption_reviewed")
    assert not item.is_serious
    # Le correctif dit quoi faire quand toutes les hypothèses ont tenu.
    assert "explicitement" in item.fix


def test_pas_encore_sans_condition_est_signale():
    """« Pas encore » est une issue pleine dans la doctrine maison, mais seulement avec
    une condition nommée : sans elle, c'est un report."""
    warnings = check_review(review(next_step=NextStep.NOT_YET.value, next_step_note=""))

    assert "not_yet_without_condition" in codes(warnings)


def test_pas_encore_avec_condition_ne_declenche_rien():
    warnings = check_review(
        review(
            next_step=NextStep.NOT_YET.value,
            next_step_note="Reprise si les ventes en ligne se stabilisent avant mars 2027.",
        )
    )

    assert warnings == []


# --------------------------------------------------------------------------- clôture


def test_revue_complete_peut_etre_close():
    assert blocking_issues(review()) == []


def test_clore_sans_resultats_est_impossible():
    issues = blocking_issues(review(observed_results=""))

    assert "cannot_complete_without_results" in codes(issues)


def test_clore_sans_lecon_est_impossible():
    issues = blocking_issues(review(lessons=""))

    assert "cannot_complete_without_lessons" in codes(issues)


def test_clore_sans_suite_decidee_est_impossible():
    issues = blocking_issues(review(next_step=""))

    assert "cannot_complete_without_next_step" in codes(issues)


def test_les_ecarts_ne_bloquent_pas_la_cloture():
    """Une revue peut légitimement constater qu'il n'y a pas eu d'écart."""
    assert blocking_issues(review(gaps="")) == []


def test_toutes_les_obstructions_portent_un_correctif():
    issues = blocking_issues(
        review(observed_results="", lessons="", next_step="")
    )

    assert len(issues) == 3
    assert all(i.fix.strip() for i in issues)
