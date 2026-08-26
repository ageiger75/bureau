"""Vocabulaire du domaine.

Les libellés français vivent ici et non dans les gabarits, afin qu'une valeur stockée
ne puisse jamais être affichée sans libellé, et qu'un renommage se fasse en un seul point.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Tuple


class CaseStatus(str, Enum):
    """États d'un dossier (brief §6).

    Le cycle complet est implémenté depuis la tranche 2. Les conditions d'entrée dans
    chaque état vivent dans `cases.py::transition`, pas ici.
    """

    DRAFT = "draft"
    ANALYSIS = "analysis"
    READY = "ready"
    DECIDED = "decided"
    EXECUTING = "executing"
    TO_REVIEW = "to_review"
    CLOSED = "closed"


CASE_STATUS_LABELS: Dict[str, str] = {
    CaseStatus.DRAFT.value: "Brouillon",
    CaseStatus.ANALYSIS.value: "En analyse",
    CaseStatus.READY.value: "Prêt à décider",
    CaseStatus.DECIDED.value: "Décidé",
    CaseStatus.EXECUTING.value: "En exécution",
    CaseStatus.TO_REVIEW.value: "À revoir",
    CaseStatus.CLOSED.value: "Clos",
}

CASE_STATUS_MEANINGS: Dict[str, str] = {
    CaseStatus.DRAFT.value: "Question créée, sources incomplètes.",
    CaseStatus.ANALYSIS.value: "Extraction, qualification et options en cours.",
    CaseStatus.READY.value: "Note, options, risques et recommandation disponibles.",
    CaseStatus.DECIDED.value: "Arbitrage et raisons enregistrés.",
    CaseStatus.EXECUTING.value: "Engagements et indicateurs suivis.",
    CaseStatus.TO_REVIEW.value: "Hypothèses et résultats à confronter.",
    CaseStatus.CLOSED.value: "Dossier archivé et retrouvable.",
}


class ClaimCategory(str, Enum):
    """Séparation non négociable du brief §4 : un élément non prouvé n'est pas un fait."""

    SOURCED_FACT = "sourced_fact"
    ASSUMPTION = "assumption"
    OPINION = "opinion"
    MISSING_VERIFICATION = "missing_verification"


CLAIM_CATEGORY_LABELS: Dict[str, str] = {
    ClaimCategory.SOURCED_FACT.value: "Fait sourcé",
    ClaimCategory.ASSUMPTION.value: "Hypothèse",
    ClaimCategory.OPINION.value: "Opinion",
    ClaimCategory.MISSING_VERIFICATION.value: "À vérifier",
}

CLAIM_CATEGORY_HINTS: Dict[str, str] = {
    ClaimCategory.SOURCED_FACT.value: "Vérifiable dans un document identifié.",
    ClaimCategory.ASSUMPTION.value: "Tenu pour vrai sans preuve ; à expliciter.",
    ClaimCategory.OPINION.value: "Jugement d'une personne, utile mais non probant.",
    ClaimCategory.MISSING_VERIFICATION.value: "Information manquante qui pèse sur la décision.",
}

# Ordre d'affichage : ce qui engage le plus la décision d'abord.
CLAIM_CATEGORY_ORDER: Tuple[str, ...] = (
    ClaimCategory.SOURCED_FACT.value,
    ClaimCategory.ASSUMPTION.value,
    ClaimCategory.MISSING_VERIFICATION.value,
    ClaimCategory.OPINION.value,
)


class Materiality(str, Enum):
    """Poids de l'affirmation dans la décision. Trois niveaux qualitatifs, jamais un score."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


MATERIALITY_LABELS: Dict[str, str] = {
    Materiality.HIGH.value: "Déterminante",
    Materiality.MEDIUM.value: "Notable",
    Materiality.LOW.value: "Secondaire",
}


class Reversibility(str, Enum):
    EASY = "easy"
    COSTLY = "costly"
    IRREVERSIBLE = "irreversible"


REVERSIBILITY_LABELS: Dict[str, str] = {
    Reversibility.EASY.value: "Réversible",
    Reversibility.COSTLY.value: "Réversible à un coût",
    Reversibility.IRREVERSIBLE.value: "Irréversible",
}


class Confidentiality(str, Enum):
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    STRICTLY_CONFIDENTIAL = "strictly_confidential"


CONFIDENTIALITY_LABELS: Dict[str, str] = {
    Confidentiality.INTERNAL.value: "Interne",
    Confidentiality.CONFIDENTIAL.value: "Confidentiel",
    Confidentiality.STRICTLY_CONFIDENTIAL.value: "Strictement confidentiel",
}


class UserRole(str, Enum):
    CEO = "ceo"
    CHIEF_OF_STAFF = "chief_of_staff"
    COMEX_CONTRIBUTOR = "comex_contributor"
    ADMINISTRATOR = "administrator"


# Pas de libellés de rôle : l'interface n'affiche jamais le rôle d'un utilisateur avant
# l'arrivée d'Entra ID et du RBAC (tranche 5).


# ---------------------------------------------------------------------------
# Tranche 2 — challenge, décision, engagements, revue
# ---------------------------------------------------------------------------


class ChallengeVoice(str, Enum):
    """Les voix qui contestent (brief §9 et §10).

    L'avocat du diable cherche les prémisses fragiles ; les voix fonctionnelles testent
    l'impact par domaine. Aucune ne prétend représenter une personne réelle : ce sont des
    angles d'analyse, pas des simulations de membres du COMEX (interdit par le brief §14).
    """

    DEVILS_ADVOCATE = "devils_advocate"
    FINANCE = "finance"
    BRAND = "brand"
    CLIENT = "client"
    PEOPLE = "people"
    OPERATIONS = "operations"
    REPUTATION = "reputation"
    LONG_TERM = "long_term"


CHALLENGE_VOICE_LABELS: Dict[str, str] = {
    ChallengeVoice.DEVILS_ADVOCATE.value: "Avocat du diable",
    ChallengeVoice.FINANCE.value: "Finance",
    ChallengeVoice.BRAND.value: "Marque",
    ChallengeVoice.CLIENT.value: "Client",
    ChallengeVoice.PEOPLE.value: "People",
    ChallengeVoice.OPERATIONS.value: "Opérations",
    ChallengeVoice.REPUTATION.value: "Réputation",
    ChallengeVoice.LONG_TERM.value: "Long terme",
}

# La question que chaque voix pose. Reprend la doctrine maison : la fleur (la marque),
# le nectar (ce qui fait revenir le client), la terre (ce qui tiendra dans le temps).
CHALLENGE_VOICE_QUESTIONS: Dict[str, str] = {
    ChallengeVoice.DEVILS_ADVOCATE.value: (
        "Sur quelle prémisse fragile tout cela repose-t-il ?"
    ),
    ChallengeVoice.FINANCE.value: "Revenus, marge, cash, coût d'opportunité, délai d'effet ?",
    ChallengeVoice.BRAND.value: "La fleur est-elle plus jolie ? Y a-t-il risque de dilution ?",
    ChallengeVoice.CLIENT.value: "Y a-t-il assez de nectar pour que le client revienne ?",
    ChallengeVoice.PEOPLE.value: "Quel leadership, quelle charge, quelles compétences ?",
    ChallengeVoice.OPERATIONS.value: "Faisabilité, capacités, dépendances, complexité ?",
    ChallengeVoice.REPUTATION.value: "Quel risque externe, partenaires, régulateurs ?",
    ChallengeVoice.LONG_TERM.value: "La terre tiendra-t-elle ? Quelle capacité créée ou détruite ?",
}

# Ordre d'affichage : l'avocat du diable d'abord, il conteste le cadrage lui-même.
CHALLENGE_VOICE_ORDER = tuple(CHALLENGE_VOICE_LABELS.keys())


class ChallengeKind(str, Enum):
    PREMISE = "premise"
    ADVERSE_SCENARIO = "adverse_scenario"
    IGNORED_SIGNAL = "ignored_signal"
    FUNCTIONAL_IMPACT = "functional_impact"


CHALLENGE_KIND_LABELS: Dict[str, str] = {
    ChallengeKind.PREMISE.value: "Prémisse contestée",
    ChallengeKind.ADVERSE_SCENARIO.value: "Scénario adverse",
    ChallengeKind.IGNORED_SIGNAL.value: "Signal ignoré",
    ChallengeKind.FUNCTIONAL_IMPACT.value: "Impact fonctionnel",
}


class Severity(str, Enum):
    BLOCKING = "blocking"
    SERIOUS = "serious"
    MINOR = "minor"


SEVERITY_LABELS: Dict[str, str] = {
    Severity.BLOCKING.value: "Bloquante",
    Severity.SERIOUS.value: "Sérieuse",
    Severity.MINOR.value: "Mineure",
}


class ChallengeStatus(str, Enum):
    OPEN = "open"
    ANSWERED = "answered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


CHALLENGE_STATUS_LABELS: Dict[str, str] = {
    ChallengeStatus.OPEN.value: "Sans réponse",
    ChallengeStatus.ANSWERED.value: "Répondue",
    ChallengeStatus.ACCEPTED.value: "Acceptée",
    ChallengeStatus.REJECTED.value: "Écartée",
}


class CommitmentStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    REARBITRATION_NEEDED = "rearbitration_needed"


COMMITMENT_STATUS_LABELS: Dict[str, str] = {
    CommitmentStatus.OPEN.value: "À lancer",
    CommitmentStatus.IN_PROGRESS.value: "En cours",
    CommitmentStatus.DONE.value: "Terminé",
    CommitmentStatus.BLOCKED.value: "Bloqué",
    CommitmentStatus.CANCELLED.value: "Annulé",
    CommitmentStatus.REARBITRATION_NEEDED.value: "À ré-arbitrer",
}

# Statuts qui ferment l'engagement : ils ne peuvent plus être « en retard ».
COMMITMENT_CLOSED_STATUSES = (
    CommitmentStatus.DONE.value,
    CommitmentStatus.CANCELLED.value,
)


class ReviewStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


REVIEW_STATUS_LABELS: Dict[str, str] = {
    ReviewStatus.PLANNED.value: "Planifiée",
    ReviewStatus.IN_PROGRESS.value: "En cours",
    ReviewStatus.COMPLETED.value: "Terminée",
}


class NextStep(str, Enum):
    """Ce que la revue conclut. « Pas encore » n'est pas une absence de décision :
    c'est une issue pleine, avec une condition nommée et une date (doctrine maison)."""

    KEEP = "keep"
    ADJUST = "adjust"
    REVERSE = "reverse"
    NOT_YET = "not_yet"


NEXT_STEP_LABELS: Dict[str, str] = {
    NextStep.KEEP.value: "Maintenir la décision",
    NextStep.ADJUST.value: "Ajuster",
    NextStep.REVERSE.value: "Revenir sur la décision",
    NextStep.NOT_YET.value: "Pas encore : condition nommée, à revoir",
}


def values(enum_cls) -> List[str]:
    return [member.value for member in enum_cls]
