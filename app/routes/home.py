"""Accueil : la liste des dossiers de décision.

Le brief §8 décrit une page filtrée par ce qui demande attention, pas un tableau de bord.
Les dossiers sont donc triés par urgence puis par fragilité, et non par date de création.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..services import (
    due_and_upcoming_reviews,
    list_case_rows,
    overdue_commitments,
    resolve_current_user,
)
from ..web import render

router = APIRouter()


@router.get("/")
def home(request: Request, session: Session = Depends(get_session)):
    try:
        user = resolve_current_user(session)
    except LookupError:
        # Base vide : on l'annonce au lieu d'afficher une page qui semble fonctionner.
        return render(request, "empty_state.html", {"user": None})

    rows = list_case_rows(session)
    return render(
        request,
        "home.html",
        {
            "user": user,
            "rows": rows,
            "attention_rows": [row for row in rows if row.needs_attention],
            # Brief §8 : l'accueil montre les engagements en retard et les revues à venir,
            # pas seulement la liste des dossiers.
            "overdue_commitments": overdue_commitments(session),
            "review_lines": due_and_upcoming_reviews(session),
        },
    )


@router.get("/health")
def health(session: Session = Depends(get_session)):
    """Sonde locale. Ne révèle aucun contenu métier."""
    from sqlalchemy import text

    session.execute(text("SELECT 1"))
    return {"status": "ok"}
