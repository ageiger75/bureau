"""Qualification des affirmations : faits, hypothèses, opinions, éléments à vérifier.

C'est l'invariant central du produit (brief §4). La règle retenue est
**l'avertissement, pas le refus** : une affirmation incomplète est enregistrée, mais elle
est signalée en clair partout où elle apparaît. Un blocage à la saisie pousserait à
requalifier un fait douteux en « hypothèse » pour se débarrasser du message, ce qui
détruirait précisément l'information que l'on cherche à conserver.

Ce module ne connaît ni HTTP ni base de données : il se teste seul.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from .enums import ClaimCategory, Materiality
from .warnings import MINOR, SERIOUS, QualityWarning


@dataclass(frozen=True)
class ClaimInput:
    """Vue minimale d'une affirmation, indépendante de l'ORM."""

    text: str
    category: str
    source_ref: str = ""
    quote: str = ""
    rationale: str = ""
    best_test: str = ""
    materiality: str = Materiality.MEDIUM.value


def check_claim(claim: ClaimInput) -> List[QualityWarning]:
    """Avertissements portés par une affirmation prise isolément."""
    warnings: List[QualityWarning] = []
    category = claim.category
    has_source = bool(claim.source_ref.strip())

    if category == ClaimCategory.SOURCED_FACT.value and not has_source:
        warnings.append(
            QualityWarning(
                code="fact_without_source",
                severity=SERIOUS,
                message="Présenté comme un fait, mais relié à aucune source.",
                fix="Indiquer la source, ou reclasser en « Hypothèse » ou « À vérifier ».",
            )
        )
    elif category == ClaimCategory.SOURCED_FACT.value and not claim.quote.strip():
        warnings.append(
            QualityWarning(
                code="fact_without_quote",
                severity=MINOR,
                message="Source citée sans passage précis.",
                fix="Coller la phrase du document qui soutient l'affirmation.",
            )
        )

    if category == ClaimCategory.ASSUMPTION.value and not claim.rationale.strip():
        warnings.append(
            QualityWarning(
                code="assumption_without_rationale",
                severity=MINOR,
                message="Hypothèse sans justification.",
                fix="Écrire pourquoi elle est tenue pour vraie, et par qui.",
            )
        )

    if category == ClaimCategory.MISSING_VERIFICATION.value and not claim.best_test.strip():
        warnings.append(
            QualityWarning(
                code="missing_verification_without_test",
                severity=MINOR,
                message="Inconnue signalée sans moyen de la lever.",
                fix="Nommer le test le moins coûteux qui trancherait.",
            )
        )

    if (
        category == ClaimCategory.OPINION.value
        and claim.materiality == Materiality.HIGH.value
    ):
        warnings.append(
            QualityWarning(
                code="decisive_opinion",
                severity=SERIOUS,
                message="Une opinion porte un poids déterminant dans ce dossier.",
                fix="Chercher une source, ou assumer la décision comme un pari explicite.",
            )
        )

    if (
        claim.materiality == Materiality.HIGH.value
        and category == ClaimCategory.ASSUMPTION.value
        and not claim.best_test.strip()
    ):
        warnings.append(
            QualityWarning(
                code="decisive_assumption_untested",
                severity=SERIOUS,
                message="Hypothèse déterminante, sans test prévu.",
                fix="Définir le test qui la confirmerait ou l'infirmerait avant de décider.",
            )
        )

    return warnings


def resolve_category(requested_category: str, source_ref: str) -> str:
    """Catégorie effectivement enregistrée.

    La catégorie demandée est respectée telle quelle : c'est le choix « avertissement
    plutôt que refus ». Cette fonction existe pour que le point de bascule soit unique
    si la politique devait durcir — il suffirait de rétrograder ici.
    """
    del source_ref  # conservé dans la signature : la politique peut changer d'avis
    return requested_category


def unsourced_facts(claims: Iterable[ClaimInput]) -> List[ClaimInput]:
    """Faits annoncés sans source. Objectif du brief §3 : cette liste doit être vide."""
    return [
        claim
        for claim in claims
        if claim.category == ClaimCategory.SOURCED_FACT.value
        and not claim.source_ref.strip()
    ]


def source_coverage(claims: Sequence[ClaimInput]) -> Optional[float]:
    """Part des faits reliés à une source, entre 0 et 1.

    Retourne None s'il n'existe aucun fait : afficher « 100 % » sur un ensemble vide
    serait la fausse précision que le brief §10 interdit.
    """
    facts = [c for c in claims if c.category == ClaimCategory.SOURCED_FACT.value]
    if not facts:
        return None
    sourced = sum(1 for c in facts if c.source_ref.strip())
    return sourced / len(facts)


def count_by_category(claims: Iterable[ClaimInput]) -> dict:
    counts = {member.value: 0 for member in ClaimCategory}
    for claim in claims:
        if claim.category in counts:
            counts[claim.category] += 1
    return counts
