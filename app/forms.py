"""Lecture et validation des formulaires HTML.

Toute donnée entrante passe par ici. Deux règles :
  * une valeur d'énumération absente de la liste attendue est refusée, jamais corrigée
    en silence — un champ falsifié doit produire une erreur visible ;
  * en cas d'erreur, les valeurs saisies sont renvoyées au gabarit pour que l'utilisateur
    ne perde pas son texte.

L'échappement HTML est fait par Jinja2 à l'affichage, pas ici.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence

from .domain.enums import (
    ChallengeKind,
    ChallengeStatus,
    ChallengeVoice,
    ClaimCategory,
    CommitmentStatus,
    Confidentiality,
    Materiality,
    NextStep,
    Reversibility,
    Severity,
    values,
)
from .util import clean_line, clean_text, parse_date

TITLE_MAX = 300
LINE_MAX = 500
TEXT_MAX = 20000


@dataclass
class FormResult:
    """Valeurs nettoyées et erreurs, indexées par nom de champ."""

    values: Dict[str, Any] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error_summary(self) -> str:
        return " ".join(self.errors.values())


def _get(form: Mapping[str, Any], name: str) -> str:
    raw = form.get(name)
    if raw is None:
        return ""
    return str(raw)


def _line(form: Mapping[str, Any], name: str, max_length: int = LINE_MAX) -> str:
    return clean_line(_get(form, name), max_length)


def _text(form: Mapping[str, Any], name: str) -> str:
    return clean_text(_get(form, name), TEXT_MAX)


def _checkbox(form: Mapping[str, Any], name: str) -> bool:
    return _get(form, name).lower() in ("1", "on", "true", "yes")


def _enum(
    result: FormResult,
    form: Mapping[str, Any],
    name: str,
    allowed: Sequence[str],
    default: str,
    label: str,
) -> str:
    raw = _get(form, name).strip()
    if not raw:
        return default
    if raw not in allowed:
        result.errors[name] = "Valeur inattendue pour « %s »." % label
        return default
    return raw


def _optional_date(
    result: FormResult, form: Mapping[str, Any], name: str, label: str
) -> Optional[str]:
    raw = _get(form, name).strip()
    if not raw:
        return None
    parsed = parse_date(raw)
    if parsed is None:
        result.errors[name] = "%s : date attendue au format AAAA-MM-JJ." % label
        return None
    return parsed.isoformat()


def _require(result: FormResult, name: str, value: str, message: str) -> None:
    if not value.strip():
        result.errors[name] = message


# --------------------------------------------------------------------------- dossier


def parse_case_creation(form: Mapping[str, Any]) -> FormResult:
    result = FormResult()
    title = _line(form, "title", TITLE_MAX)
    question = _text(form, "question")

    _require(result, "title", title, "Le titre est obligatoire.")
    _require(
        result,
        "question",
        question,
        "La question à trancher est obligatoire : sans elle, il n'y a pas de dossier.",
    )

    result.values = {
        "title": title,
        "question": question,
        "context": _text(form, "context"),
        "deadline": _optional_date(result, form, "deadline", "Échéance"),
        "confidentiality": _enum(
            result,
            form,
            "confidentiality",
            values(Confidentiality),
            Confidentiality.CONFIDENTIAL.value,
            "confidentialité",
        ),
    }
    return result


def parse_case_framing(form: Mapping[str, Any]) -> FormResult:
    """Cadrage : la question, le contexte, l'échéance et la reformulation de l'outil."""
    result = FormResult()
    title = _line(form, "title", TITLE_MAX)
    question = _text(form, "question")

    _require(result, "title", title, "Le titre est obligatoire.")
    _require(result, "question", question, "La question à trancher est obligatoire.")

    result.values = {
        "title": title,
        "question": question,
        "context": _text(form, "context"),
        "deadline": _optional_date(result, form, "deadline", "Échéance"),
        "confidentiality": _enum(
            result,
            form,
            "confidentiality",
            values(Confidentiality),
            Confidentiality.CONFIDENTIAL.value,
            "confidentialité",
        ),
        "real_decision": _text(form, "real_decision"),
        "scope_out": _text(form, "scope_out"),
        "constraints": _text(form, "constraints"),
        "blind_spot": _text(form, "blind_spot"),
        "executive_summary": _text(form, "executive_summary"),
    }
    return result


# --------------------------------------------------------------------------- affirmations


def parse_claim(form: Mapping[str, Any]) -> FormResult:
    result = FormResult()
    text = _text(form, "text")
    _require(result, "text", text, "L'affirmation ne peut pas être vide.")

    category = _enum(
        result,
        form,
        "category",
        values(ClaimCategory),
        ClaimCategory.ASSUMPTION.value,
        "catégorie",
    )

    result.values = {
        "text": text,
        "category": category,
        "source_ref": _line(form, "source_ref", LINE_MAX),
        "quote": _text(form, "quote"),
        "as_of_date": _optional_date(result, form, "as_of_date", "Date de validité"),
        "materiality": _enum(
            result,
            form,
            "materiality",
            values(Materiality),
            Materiality.MEDIUM.value,
            "matérialité",
        ),
        "rationale": _text(form, "rationale"),
        "best_test": _text(form, "best_test"),
    }
    return result


# --------------------------------------------------------------------------- options


def parse_option(form: Mapping[str, Any]) -> FormResult:
    result = FormResult()
    name = _line(form, "name", TITLE_MAX)
    _require(result, "name", name, "Le nom de l'option est obligatoire.")

    result.values = {
        "name": name,
        "description": _text(form, "description"),
        "is_status_quo": _checkbox(form, "is_status_quo"),
        "assumptions": _text(form, "assumptions"),
        "benefits": _text(form, "benefits"),
        "risks": _text(form, "risks"),
        "success_conditions": _text(form, "success_conditions"),
        "reversibility": _enum(
            result,
            form,
            "reversibility",
            values(Reversibility),
            Reversibility.COSTLY.value,
            "réversibilité",
        ),
        "reversibility_note": _text(form, "reversibility_note"),
        "time_to_effect": _line(form, "time_to_effect", LINE_MAX),
    }
    return result


# --------------------------------------------------------------------------- recommandation


def parse_recommendation(form: Mapping[str, Any], option_ids: Sequence[str]) -> FormResult:
    """La recommandation exige une position et ses conditions d'invalidation (brief §4).

    Ces deux champs sont obligatoires ici, et non signalés par un avertissement : une
    recommandation sans position n'est pas une recommandation fragile, c'est une absence
    de recommandation.
    """
    result = FormResult()
    position = _text(form, "position")
    would_change_if = _text(form, "would_change_if")

    _require(
        result,
        "position",
        position,
        "La position est obligatoire : dire ce que l'on ferait, et pourquoi.",
    )
    _require(
        result,
        "would_change_if",
        would_change_if,
        "Préciser ce qui ferait changer d'avis. Sans cela, ce n'est pas un raisonnement.",
    )

    option_id = _get(form, "option_id").strip() or None
    if option_id is not None and option_id not in option_ids:
        result.errors["option_id"] = "Option inconnue dans ce dossier."
        option_id = None

    result.values = {
        "option_id": option_id,
        "position": position,
        "reasons": _text(form, "reasons"),
        "success_conditions": _text(form, "success_conditions"),
        "would_change_if": would_change_if,
        "open_disagreements": _text(form, "open_disagreements"),
    }
    return result


# --------------------------------------------------------------------------- challenge


def parse_challenge(form: Mapping[str, Any], option_ids: Sequence[str]) -> FormResult:
    """Une objection.

    Seul le texte de l'objection est obligatoire. L'absence de preuve est **signalée**, pas
    refusée : même politique que pour un fait sans source. Refuser pousserait à inventer une
    preuve pour faire passer le formulaire.
    """
    result = FormResult()
    objection = _text(form, "objection")
    _require(result, "objection", objection, "L'objection ne peut pas être vide.")

    option_id = _get(form, "option_id").strip() or None
    if option_id is not None and option_id not in option_ids:
        result.errors["option_id"] = "Option inconnue dans ce dossier."
        option_id = None

    status = _enum(
        result, form, "status", values(ChallengeStatus), ChallengeStatus.OPEN.value, "statut"
    )

    result.values = {
        "objection": objection,
        "option_id": option_id,
        "voice": _enum(
            result, form, "voice", values(ChallengeVoice),
            ChallengeVoice.DEVILS_ADVOCATE.value, "voix",
        ),
        "kind": _enum(
            result, form, "kind", values(ChallengeKind),
            ChallengeKind.PREMISE.value, "nature",
        ),
        "evidence": _text(form, "evidence"),
        "severity": _enum(
            result, form, "severity", values(Severity), Severity.SERIOUS.value, "gravité"
        ),
        "response": _text(form, "response"),
        "status": status,
    }
    return result


# --------------------------------------------------------------------------- décision


def parse_decision(form: Mapping[str, Any], option_ids: Sequence[str]) -> FormResult:
    """L'arbitrage du CEO.

    Quatre champs sont obligatoires : l'option, les raisons, les critères de succès et la
    date de revue. Ce sont exactement les quatre éléments que le brief §2 décrit comme
    « rarement conservés » — c'est donc là qu'on refuse plutôt qu'on avertit.
    """
    result = FormResult()

    option_id = _get(form, "option_id").strip()
    if not option_id:
        result.errors["option_id"] = "Choisir l'option retenue."
    elif option_id not in option_ids:
        result.errors["option_id"] = "Option inconnue dans ce dossier."

    reasons = _text(form, "reasons")
    success_criteria = _text(form, "success_criteria")
    _require(result, "reasons", reasons, "Les raisons de l'arbitrage sont obligatoires.")
    _require(
        result,
        "success_criteria",
        success_criteria,
        "Les critères de succès sont obligatoires : sans eux la revue ne peut rien comparer.",
    )

    review_date = _optional_date(result, form, "review_date", "Date de revue")
    if review_date is None and "review_date" not in result.errors:
        result.errors["review_date"] = (
            "Fixer une date de revue. Une décision sans revue ne s'apprend jamais."
        )

    result.values = {
        "option_id": option_id if option_id in option_ids else "",
        "reasons": reasons,
        "reservations": _text(form, "reservations"),
        "success_criteria": success_criteria,
        "change_conditions": _text(form, "change_conditions"),
        "diverges_from_recommendation": _checkbox(form, "diverges_from_recommendation"),
        "divergence_reason": _text(form, "divergence_reason"),
        "review_date": review_date or "",
    }
    return result


# --------------------------------------------------------------------------- engagements


def parse_commitment(form: Mapping[str, Any]) -> FormResult:
    """Un engagement suivi dans le produit. Aucun envoi, aucune notification."""
    result = FormResult()
    action = _text(form, "action")
    _require(result, "action", action, "L'action à mener ne peut pas être vide.")

    result.values = {
        "action": action,
        "owner_name": _line(form, "owner_name", LINE_MAX),
        "due_date": _optional_date(result, form, "due_date", "Échéance"),
        "status": _enum(
            result, form, "status", values(CommitmentStatus),
            CommitmentStatus.OPEN.value, "statut",
        ),
        "is_critical": _checkbox(form, "is_critical"),
        "evidence": _text(form, "evidence"),
    }
    return result


# --------------------------------------------------------------------------- revue


def parse_review(form: Mapping[str, Any]) -> FormResult:
    """Une revue en cours de rédaction.

    Rien n'est obligatoire ici : une revue se remplit en plusieurs fois. Les exigences
    portent sur sa **clôture**, contrôlée par `domain/reviews.py::blocking_issues`.
    """
    result = FormResult()
    result.values = {
        "observed_results": _text(form, "observed_results"),
        "gaps": _text(form, "gaps"),
        "invalidated_assumptions": _text(form, "invalidated_assumptions"),
        "lessons": _text(form, "lessons"),
        "next_step": _enum(
            result, form, "next_step", values(NextStep) + [""], "", "suite"
        ),
        "next_step_note": _text(form, "next_step_note"),
        "held_date": _optional_date(result, form, "held_date", "Date de la revue"),
    }
    return result
