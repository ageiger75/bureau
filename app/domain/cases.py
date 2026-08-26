"""Cycle de vie d'un dossier de décision et calcul de l'état « prêt à décider ».

Module sans dépendance ORM ni HTTP : les règles se testent seules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .enums import CASE_STATUS_LABELS, CaseStatus
from .warnings import QualityWarning, blocker as _blocker, warning as _warning

# Cycle de vie complet (brief §6). Le retour en arrière est permis à chaque étape :
# découvrir une inconnue après coup doit pouvoir ramener le dossier en analyse, et le brief
# exige que la réouverture d'un dossier clos soit possible mais explicite.
ALLOWED_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    CaseStatus.DRAFT.value: (CaseStatus.ANALYSIS.value,),
    CaseStatus.ANALYSIS.value: (CaseStatus.DRAFT.value, CaseStatus.READY.value),
    CaseStatus.READY.value: (CaseStatus.ANALYSIS.value, CaseStatus.DECIDED.value),
    CaseStatus.DECIDED.value: (CaseStatus.EXECUTING.value,),
    CaseStatus.EXECUTING.value: (CaseStatus.TO_REVIEW.value,),
    CaseStatus.TO_REVIEW.value: (CaseStatus.CLOSED.value, CaseStatus.ANALYSIS.value),
    CaseStatus.CLOSED.value: (CaseStatus.ANALYSIS.value,),
}

# À partir de « Décidé », un dossier ne se juge plus sur sa maturité mais sur son
# exécution : son échéance de décision est derrière lui, et la rappeler indéfiniment
# noierait les vrais signaux — engagements en retard et revue échue.
DECIDED_STATUSES: Tuple[str, ...] = (
    CaseStatus.DECIDED.value,
    CaseStatus.EXECUTING.value,
    CaseStatus.TO_REVIEW.value,
    CaseStatus.CLOSED.value,
)


class TransitionRefused(ValueError):
    """Transition d'état illégale. Message destiné à être affiché à l'utilisateur."""


@dataclass(frozen=True)
class TransitionContext:
    """Ce dont dépend l'autorisation d'un changement d'état.

    Un objet plutôt qu'une liste d'arguments qui s'allonge : chaque nouvel état de la
    tranche 2 a sa propre condition, et une signature à six paramètres optionnels devient
    illisible au premier oubli.
    """

    readiness: Optional["Readiness"] = None
    has_decision: bool = False
    commitment_count: int = 0
    has_planned_review: bool = False
    review_completed: bool = False


@dataclass(frozen=True)
class CaseSnapshot:
    """Ce que le domaine a besoin de savoir d'un dossier pour juger sa maturité."""

    question: str = ""
    real_decision: str = ""
    option_count: int = 0
    status_quo_present: bool = False
    sourced_fact_count: int = 0
    assumption_count: int = 0
    missing_verification_count: int = 0
    unsourced_fact_count: int = 0
    has_recommendation: bool = False
    recommendation_has_change_conditions: bool = False
    # Tranche 2 : un dossier jamais contesté ne peut pas être déclaré prêt.
    challenge_count: int = 0
    unanswered_blocking_challenges: int = 0
    premise_tested: bool = False
    challenges_without_evidence: int = 0
    missing_voice_labels: Tuple[str, ...] = ()


@dataclass
class Readiness:
    """Résultat du diagnostic : ce qui empêche de décider, et ce qui doit être vu quand même."""

    blockers: List[QualityWarning] = field(default_factory=list)
    warnings: List[QualityWarning] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        return not self.blockers

    @property
    def serious_warning_count(self) -> int:
        return sum(1 for w in self.warnings if w.is_serious)


def assess_readiness(snapshot: CaseSnapshot) -> Readiness:
    """Diagnostic d'un dossier au regard des exigences du brief §6, §7 et §15.

    Bloquant : ce qui rend la décision impossible à prendre proprement.
    Avertissement : ce qui la rend fragile mais reste un choix assumé du CEO.
    """
    result = Readiness()

    if not snapshot.question.strip():
        result.blockers.append(
            _blocker(
                "no_question",
                "Aucune question de décision formulée.",
                "Écrire la question à trancher, en une phrase.",
            )
        )

    if snapshot.option_count < 2:
        result.blockers.append(
            _blocker(
                "too_few_options",
                "Moins de deux options : il n'y a pas d'arbitrage, seulement une intention.",
                "Ajouter une option réellement distincte, y compris le statu quo.",
            )
        )
    elif snapshot.option_count > 3:
        result.blockers.append(
            _blocker(
                "too_many_options",
                "Plus de trois options : le brief interdit les listes interminables.",
                "Fusionner ou écarter les options qui ne sont pas de vraies alternatives.",
            )
        )

    # « Les inconnues critiques sont explicites » (brief §6, passage en Prêt à décider).
    if snapshot.assumption_count == 0 and snapshot.missing_verification_count == 0:
        result.blockers.append(
            _blocker(
                "no_declared_uncertainty",
                "Aucune hypothèse ni inconnue déclarée : improbable sur une vraie décision.",
                "Nommer au moins l'hypothèse sur laquelle repose l'option préférée.",
            )
        )

    if not snapshot.has_recommendation:
        result.blockers.append(
            _blocker(
                "no_recommendation",
                "Aucune position prise.",
                "Rédiger la recommandation : l'option, les raisons, ce qui ferait changer d'avis.",
            )
        )
    elif not snapshot.recommendation_has_change_conditions:
        result.blockers.append(
            _blocker(
                "recommendation_without_change_conditions",
                "Recommandation sans conditions d'invalidation.",
                "Préciser ce qui ferait changer l'avis (brief §4).",
            )
        )

    # « Ne cherche pas à plaire au CEO » (brief §9). Un dossier que personne n'a contesté
    # est un dossier qui confirme l'intuition de départ : c'est le risque principal du
    # produit, donc c'est un bloquant et non un avertissement.
    if snapshot.challenge_count == 0:
        result.blockers.append(
            _blocker(
                "never_challenged",
                "Le dossier n'a jamais été contesté.",
                "Lancer le challenge : au moins une prémisse doit être testée avant de décider.",
            )
        )
    else:
        if snapshot.unanswered_blocking_challenges > 0:
            count = snapshot.unanswered_blocking_challenges
            result.blockers.append(
                _blocker(
                    "unanswered_blocking_challenge",
                    "Une objection bloquante est sans réponse."
                    if count == 1
                    else "%d objections bloquantes sont sans réponse." % count,
                    "Y répondre, les accepter comme réserves, ou les écarter en expliquant.",
                )
            )
        if not snapshot.premise_tested:
            result.blockers.append(
                _blocker(
                    "no_premise_tested",
                    "Aucune prémisse n'a été testée : les objections sont posées, pas traitées.",
                    "Répondre à au moins une prémisse contestée (brief §15).",
                )
            )

    # --- Avertissements : visibles, non bloquants ---

    if snapshot.challenges_without_evidence > 0:
        count = snapshot.challenges_without_evidence
        result.warnings.append(
            _warning(
                "objections_without_evidence",
                "Une objection ne s'appuie sur aucun élément concret."
                if count == 1
                else "%d objections ne s'appuient sur aucun élément concret." % count,
                "Une objection sans preuve est une impression : la fonder ou l'écarter.",
            )
        )

    if snapshot.challenge_count > 0 and snapshot.missing_voice_labels:
        result.warnings.append(
            _warning(
                "voices_not_heard",
                "Voix qui ne se sont pas exprimées : %s."
                % ", ".join(snapshot.missing_voice_labels),
                "Les interroger, ou assumer de décider sans leur avis.",
                severity="minor",
            )
        )

    if snapshot.unsourced_fact_count > 0:
        # Les messages sont lus par le CEO : « 1 fait(s) » n'est pas acceptable.
        count = snapshot.unsourced_fact_count
        message = (
            "Un fait est présenté comme établi sans source."
            if count == 1
            else "%d faits sont présentés comme établis sans source." % count
        )
        result.warnings.append(
            _warning(
                "unsourced_facts",
                message,
                "Relier chaque fait matériel à un document, ou le reclasser.",
            )
        )

    if snapshot.sourced_fact_count == 0:
        result.warnings.append(
            _warning(
                "no_sourced_fact",
                "Le dossier ne contient aucun fait sourcé.",
                "Ajouter au moins un élément vérifiable, sinon la décision est une intuition.",
            )
        )

    if not snapshot.real_decision.strip():
        result.warnings.append(
            _warning(
                "real_decision_not_reframed",
                "La vraie décision n'a pas été reformulée.",
                "Écrire ce qui se joue réellement, et ce qui n'est pas en jeu.",
            )
        )

    if snapshot.option_count >= 2 and not snapshot.status_quo_present:
        result.warnings.append(
            _warning(
                "no_status_quo",
                "Le statu quo n'est pas évalué : ne rien faire est pourtant une option.",
                "Ajouter le statu quo, ou écrire pourquoi il est exclu.",
                severity="minor",
            )
        )

    return result


def can_transition(current: str, target: str) -> Tuple[bool, str]:
    """Autorise ou non un changement d'état, sans regarder le contenu du dossier."""
    if current == target:
        return False, "Le dossier est déjà dans cet état."
    if target not in CASE_STATUS_LABELS:
        return False, "État inconnu."
    allowed = ALLOWED_TRANSITIONS.get(current, ())
    if target not in allowed:
        return False, "Passage de « %s » à « %s » non prévu." % (
            CASE_STATUS_LABELS.get(current, current),
            CASE_STATUS_LABELS.get(target, target),
        )
    return True, ""


def next_statuses(current: str) -> Sequence[str]:
    """États proposables depuis l'état courant."""
    return list(ALLOWED_TRANSITIONS.get(current, ()))


# Transitions déclenchées par un écran dédié plutôt que par un bouton d'état : proposer
# « Décidé » comme un simple changement de statut laisserait croire qu'on peut décider sans
# enregistrer le choix, les réserves et les critères de succès.
TRANSITIONS_VIA_SCREEN = {
    CaseStatus.DECIDED.value: "l'écran Décision",
    CaseStatus.CLOSED.value: "l'écran Revue",
}


def offered_statuses(current: str) -> Sequence[str]:
    """États proposés sous forme de bouton dans l'en-tête du dossier."""
    return [s for s in next_statuses(current) if s not in TRANSITIONS_VIA_SCREEN]


def transition(
    current: str, target: str, context: Optional[TransitionContext] = None
) -> str:
    """Applique une transition ou lève TransitionRefused.

    Chaque état de la boucle décisionnelle a sa condition d'entrée : elles sont ici, en un
    seul endroit, pour qu'aucune route ne puisse en inventer une autre.
    """
    ok, reason = can_transition(current, target)
    if not ok:
        raise TransitionRefused(reason)

    ctx = context or TransitionContext()

    if target == CaseStatus.READY.value:
        if ctx.readiness is None:
            raise TransitionRefused(
                "Impossible de déclarer le dossier prêt sans diagnostic de maturité."
            )
        if not ctx.readiness.is_ready:
            raise TransitionRefused(
                "Le dossier n'est pas prêt : %s"
                % " ".join(b.message for b in ctx.readiness.blockers)
            )

    elif target == CaseStatus.DECIDED.value and not ctx.has_decision:
        raise TransitionRefused(
            "Aucune décision enregistrée. Passer par l'écran Décision : le choix, les "
            "raisons, les réserves et la date de revue doivent être conservés."
        )

    elif target == CaseStatus.EXECUTING.value and ctx.commitment_count == 0:
        raise TransitionRefused(
            "Aucun engagement enregistré. Une décision sans engagement suivi ne s'exécute "
            "pas : elle s'oublie."
        )

    elif target == CaseStatus.TO_REVIEW.value and not ctx.has_planned_review:
        raise TransitionRefused(
            "Aucune revue planifiée : la date de revue est fixée au moment de la décision."
        )

    elif target == CaseStatus.CLOSED.value and not ctx.review_completed:
        raise TransitionRefused(
            "La revue n'est pas terminée. Clore un dossier sans confronter les hypothèses "
            "aux résultats fait perdre le seul enseignement réutilisable."
        )

    return target


def urgency(days_left: Optional[int]) -> str:
    """Classe d'urgence d'une échéance, pour le tri et l'affichage de l'accueil."""
    if days_left is None:
        return "none"
    if days_left < 0:
        return "overdue"
    if days_left <= 3:
        return "critical"
    if days_left <= 10:
        return "soon"
    return "later"

