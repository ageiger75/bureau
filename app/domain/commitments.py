"""Engagements : suivre l'exécution sans jamais agir à l'extérieur (brief §7 FR-10).

Le produit ne relance personne, n'envoie rien, ne modifie aucun système. Il rend le retard
**visible**, ce qui est l'essentiel du problème décrit au brief §2 : « les engagements
existent dans plusieurs comptes rendus, sans lien direct avec la décision initiale ».
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .enums import COMMITMENT_CLOSED_STATUSES, CommitmentStatus
from .warnings import MINOR, QualityWarning, warning

# Niveaux d'alerte, du plus grave au plus calme.
OVERDUE = "overdue"
DUE_SOON = "due_soon"
ON_TRACK = "on_track"
CLOSED = "closed"
NO_DATE = "no_date"

ALERT_LABELS: Dict[str, str] = {
    OVERDUE: "En retard",
    DUE_SOON: "Échéance proche",
    ON_TRACK: "Dans les temps",
    CLOSED: "Clos",
    NO_DATE: "Sans échéance",
}

# Fenêtre au-delà de laquelle une échéance n'est plus « proche ». Sept jours : la maille
# de la revue hebdomadaire d'un dirigeant.
DUE_SOON_DAYS = 7


@dataclass(frozen=True)
class CommitmentInput:
    """Vue minimale d'un engagement, indépendante de l'ORM."""

    action: str
    owner_name: str = ""
    due_date: Optional[str] = None
    status: str = CommitmentStatus.OPEN.value
    is_critical: bool = False
    evidence: str = ""


def is_closed(status: str) -> bool:
    return status in COMMITMENT_CLOSED_STATUSES


def alert_level(status: str, days_left: Optional[int]) -> str:
    """Niveau d'alerte d'un engagement.

    Un engagement terminé ou annulé n'est jamais « en retard » : le retard concerne ce qui
    reste à faire, pas ce qui est derrière nous.
    """
    if is_closed(status):
        return CLOSED
    if days_left is None:
        return NO_DATE
    if days_left < 0:
        return OVERDUE
    if days_left <= DUE_SOON_DAYS:
        return DUE_SOON
    return ON_TRACK


def check_commitment(item: CommitmentInput, days_left: Optional[int] = None) -> List[QualityWarning]:
    """Avertissements portés par un engagement pris isolément."""
    warnings: List[QualityWarning] = []

    if not item.owner_name.strip():
        warnings.append(
            warning(
                "commitment_without_owner",
                "Engagement sans propriétaire nommé.",
                "Nommer une personne. « L'équipe » n'est le nom de personne.",
            )
        )

    if not item.due_date:
        warnings.append(
            warning(
                "commitment_without_due_date",
                "Engagement sans échéance : il ne remontera jamais comme en retard.",
                "Poser une date, même approximative.",
            )
        )

    if item.status == CommitmentStatus.DONE.value and not item.evidence.strip():
        warnings.append(
            warning(
                "done_without_evidence",
                "Déclaré terminé sans preuve d'avancement.",
                "Écrire ce qui permet de le vérifier — le produit ne peut pas le constater "
                "seul, il ne lit aucun système externe.",
                severity=MINOR,
            )
        )

    if item.is_critical and item.status == CommitmentStatus.BLOCKED.value:
        warnings.append(
            warning(
                "critical_blocked",
                "Engagement critique bloqué : la décision d'origine est en cause.",
                "Lever le blocage ou passer l'engagement en « À ré-arbitrer ».",
            )
        )

    if item.is_critical and alert_level(item.status, days_left) == OVERDUE:
        warnings.append(
            warning(
                "critical_overdue",
                "Engagement critique en retard.",
                "Un engagement critique en retard doit déclencher une revue, pas une relance.",
            )
        )

    return warnings


@dataclass
class CommitmentSummary:
    """État de l'exécution sur un dossier."""

    total: int = 0
    open_count: int = 0
    overdue: int = 0
    critical_overdue: int = 0
    done: int = 0
    rearbitration_needed: int = 0

    @property
    def all_closed(self) -> bool:
        return self.total > 0 and self.open_count == 0

    @property
    def completion_label(self) -> str:
        """Avancement en texte. Rien n'est affiché sur un ensemble vide : un « 100 % »
        sans engagement serait de la fausse précision (brief §10)."""
        if self.total == 0:
            return "Aucun engagement"
        return "%d engagement%s sur %d terminé%s" % (
            self.done,
            "s" if self.done > 1 else "",
            self.total,
            "s" if self.done > 1 else "",
        )


def summarize(pairs: Iterable[Tuple[CommitmentInput, Optional[int]]]) -> CommitmentSummary:
    """Agrège l'état des engagements.

    Chaque paire associe un engagement au nombre de jours restants avant son échéance,
    calculé par l'appelant : ce module reste ainsi indépendant de l'horloge, donc testable
    sans geler le temps. Des paires plutôt qu'un dictionnaire indexé sur l'action, car deux
    engagements peuvent porter le même libellé.
    """
    summary = CommitmentSummary()
    for item, days_left in pairs:
        summary.total += 1
        if item.status == CommitmentStatus.DONE.value:
            summary.done += 1
        if item.status == CommitmentStatus.REARBITRATION_NEEDED.value:
            summary.rearbitration_needed += 1
        if not is_closed(item.status):
            summary.open_count += 1
        if alert_level(item.status, days_left) == OVERDUE:
            summary.overdue += 1
            if item.is_critical:
                summary.critical_overdue += 1
    return summary
