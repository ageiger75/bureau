"""Revue : confronter les hypothèses d'origine aux résultats observés (brief §7 FR-14).

C'est l'étape qui distingue une mémoire décisionnelle d'un simple archivage. Le brief §3 en
fait un objectif mesurable : « revues à 3 ou 6 mois comparant hypothèses initiales et
résultats observés ».

La revue est créée automatiquement au moment de la décision, à la date choisie. Une revue
qu'il faudrait penser à créer soi-même n'a jamais lieu.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .enums import NextStep, ReviewStatus
from .warnings import MINOR, QualityWarning, warning

# Fenêtre d'anticipation d'une revue sur l'écran d'accueil.
UPCOMING_DAYS = 14


@dataclass(frozen=True)
class ReviewInput:
    """Vue minimale d'une revue, indépendante de l'ORM."""

    planned_date: str
    status: str = ReviewStatus.PLANNED.value
    observed_results: str = ""
    gaps: str = ""
    invalidated_assumptions: str = ""
    lessons: str = ""
    next_step: str = ""
    next_step_note: str = ""


def is_due(status: str, days_left: Optional[int]) -> bool:
    """Une revue est échue si sa date est passée et qu'elle n'est pas terminée."""
    if status == ReviewStatus.COMPLETED.value:
        return False
    return days_left is not None and days_left <= 0


def is_upcoming(status: str, days_left: Optional[int]) -> bool:
    if status == ReviewStatus.COMPLETED.value:
        return False
    return days_left is not None and 0 < days_left <= UPCOMING_DAYS


def check_review(item: ReviewInput) -> List[QualityWarning]:
    """Avertissements portés par une revue en cours de rédaction."""
    warnings: List[QualityWarning] = []

    if not item.observed_results.strip():
        warnings.append(
            warning(
                "review_without_results",
                "Aucun résultat observé consigné.",
                "Écrire ce qui s'est réellement passé, chiffres à l'appui quand ils existent.",
            )
        )

    if not item.lessons.strip():
        warnings.append(
            warning(
                "review_without_lessons",
                "Aucune leçon tirée : la revue n'apprend rien à la décision suivante.",
                "Écrire ce qu'on saura mieux la prochaine fois, même si c'est inconfortable.",
            )
        )

    if not item.invalidated_assumptions.strip():
        warnings.append(
            warning(
                "no_assumption_reviewed",
                "Aucune hypothèse confrontée aux faits.",
                "Reprendre les hypothèses du dossier et dire laquelle a tenu, laquelle non. "
                "Si toutes ont tenu, l'écrire explicitement.",
                severity=MINOR,
            )
        )

    if item.next_step == NextStep.NOT_YET.value and not item.next_step_note.strip():
        warnings.append(
            warning(
                "not_yet_without_condition",
                "« Pas encore » sans condition nommée n'est pas une issue, c'est un report.",
                "Nommer la condition qui déclencherait la reprise, et une date de revisite.",
            )
        )

    return warnings


def blocking_issues(item: ReviewInput) -> List[QualityWarning]:
    """Ce qui empêche de clore la revue.

    Plus exigeant que `check_review` : on peut enregistrer une revue partielle et y revenir,
    mais on ne peut pas la déclarer terminée sans résultats, sans leçons ni sans conclusion.
    """
    issues: List[QualityWarning] = []

    if not item.observed_results.strip():
        issues.append(
            warning(
                "cannot_complete_without_results",
                "Impossible de clore une revue sans résultats observés.",
                "Consigner ce qui a été constaté.",
            )
        )

    if not item.lessons.strip():
        issues.append(
            warning(
                "cannot_complete_without_lessons",
                "Impossible de clore une revue sans leçon.",
                "Une revue sans enseignement réutilisable ne sert qu'à cocher une case.",
            )
        )

    if not item.next_step:
        issues.append(
            warning(
                "cannot_complete_without_next_step",
                "Aucune suite décidée : maintenir, ajuster, revenir en arrière, ou « pas encore ».",
                "Choisir la suite. Ne pas choisir est aussi une décision, mais elle doit être écrite.",
            )
        )

    return issues
