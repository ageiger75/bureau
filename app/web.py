"""Couche de présentation : gabarits Jinja2, messages éphémères, contexte commun.

Module séparé de `main.py` pour que les routeurs puissent l'importer sans cycle.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from starlette.responses import RedirectResponse

from . import __version__
from .config import ROOT, settings
from .db import database_label
from .domain.enums import (
    CASE_STATUS_LABELS,
    CASE_STATUS_MEANINGS,
    CHALLENGE_KIND_LABELS,
    CHALLENGE_STATUS_LABELS,
    CHALLENGE_VOICE_LABELS,
    CHALLENGE_VOICE_ORDER,
    CHALLENGE_VOICE_QUESTIONS,
    CLAIM_CATEGORY_HINTS,
    CLAIM_CATEGORY_LABELS,
    CLAIM_CATEGORY_ORDER,
    COMMITMENT_STATUS_LABELS,
    CONFIDENTIALITY_LABELS,
    MATERIALITY_LABELS,
    NEXT_STEP_LABELS,
    REVERSIBILITY_LABELS,
    REVIEW_STATUS_LABELS,
    SEVERITY_LABELS,
    CaseStatus,
    ChallengeStatus,
    ClaimCategory,
    CommitmentStatus,
    Confidentiality,
    Materiality,
    NextStep,
    Reversibility,
    ReviewStatus,
    Severity,
)
from .domain.commitments import ALERT_LABELS

templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))


def paragraphs(value: Optional[str]) -> Markup:
    """Rend un texte multi-lignes en paragraphes, en échappant d'abord.

    Écrit à la main plutôt qu'avec un moteur Markdown : accepter du balisage dans un champ
    alimenté par des documents externes ouvrirait une porte d'injection (brief §13).
    """
    if not value or not value.strip():
        return Markup("")
    blocks = [block.strip() for block in value.strip().split("\n\n") if block.strip()]
    rendered = []
    for block in blocks:
        lines = [escape(line) for line in block.split("\n")]
        rendered.append("<p>%s</p>" % Markup("<br>").join(lines))
    return Markup("".join(rendered))


def bullets(value: Optional[str]) -> Markup:
    """Rend un texte ligne par ligne en liste à puces. Les tirets de tête sont retirés."""
    if not value or not value.strip():
        return Markup("")
    items = []
    for line in value.strip().split("\n"):
        cleaned = line.strip().lstrip("-•*").strip()
        if cleaned:
            items.append("<li>%s</li>" % escape(cleaned))
    if not items:
        return Markup("")
    return Markup("<ul class=\"bullets\">%s</ul>" % "".join(items))


templates.env.filters["paragraphs"] = paragraphs
templates.env.filters["bullets"] = bullets

templates.env.globals.update(
    {
        "app_version": __version__,
        # Déduit de la version : le bandeau ne doit pas annoncer une tranche périmée.
        "tranche_label": __version__.split("-")[-1].replace("tranche", "tranche "),
        "env_name": settings.env,
        "autonomy_level": settings.autonomy_level,
        "database_label": database_label(),
        "CASE_STATUS_LABELS": CASE_STATUS_LABELS,
        "CASE_STATUS_MEANINGS": CASE_STATUS_MEANINGS,
        "CLAIM_CATEGORY_LABELS": CLAIM_CATEGORY_LABELS,
        "CLAIM_CATEGORY_HINTS": CLAIM_CATEGORY_HINTS,
        "CLAIM_CATEGORY_ORDER": CLAIM_CATEGORY_ORDER,
        "MATERIALITY_LABELS": MATERIALITY_LABELS,
        "REVERSIBILITY_LABELS": REVERSIBILITY_LABELS,
        "CONFIDENTIALITY_LABELS": CONFIDENTIALITY_LABELS,
        "CHALLENGE_VOICE_LABELS": CHALLENGE_VOICE_LABELS,
        "CHALLENGE_VOICE_QUESTIONS": CHALLENGE_VOICE_QUESTIONS,
        "CHALLENGE_VOICE_ORDER": CHALLENGE_VOICE_ORDER,
        "CHALLENGE_KIND_LABELS": CHALLENGE_KIND_LABELS,
        "CHALLENGE_STATUS_LABELS": CHALLENGE_STATUS_LABELS,
        "SEVERITY_LABELS": SEVERITY_LABELS,
        "COMMITMENT_STATUS_LABELS": COMMITMENT_STATUS_LABELS,
        "COMMITMENT_ALERT_LABELS": ALERT_LABELS,
        "REVIEW_STATUS_LABELS": REVIEW_STATUS_LABELS,
        "NEXT_STEP_LABELS": NEXT_STEP_LABELS,
        "CaseStatus": CaseStatus,
        "ChallengeStatus": ChallengeStatus,
        "CommitmentStatus": CommitmentStatus,
        "NextStep": NextStep,
        "ReviewStatus": ReviewStatus,
        "Severity": Severity,
        "ClaimCategory": ClaimCategory,
        "Materiality": Materiality,
        "Reversibility": Reversibility,
        "Confidentiality": Confidentiality,
    }
)


# --------------------------------------------------------------------------- messages

FLASH_KEY = "flashes"


def flash(request: Request, message: str, kind: str = "info") -> None:
    """Message affiché une fois, après une redirection.

    `kind` : info | success | warning | error.
    """
    bucket: List[Dict[str, str]] = request.session.setdefault(FLASH_KEY, [])
    bucket.append({"message": message, "kind": kind})


def pop_flashes(request: Request) -> List[Dict[str, str]]:
    return request.session.pop(FLASH_KEY, [])


# --------------------------------------------------------------------------- rendu


def render(
    request: Request,
    template_name: str,
    context: Optional[Dict[str, Any]] = None,
    status_code: int = 200,
):
    payload: Dict[str, Any] = {"flashes": pop_flashes(request)}
    payload.update(context or {})
    return templates.TemplateResponse(
        request, template_name, payload, status_code=status_code
    )


def redirect(url: str) -> RedirectResponse:
    """Redirection après écriture (POST → 303 → GET), pour qu'un rafraîchissement de page
    ne rejoue pas l'écriture."""
    return RedirectResponse(url=url, status_code=303)
