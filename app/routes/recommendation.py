"""Recommandation : la position de l'outil, distincte de la décision de l'humain.

Le brief §4 exige une position nette et les conditions qui l'invalideraient. Ces deux
champs sont obligatoires : une recommandation sans position n'est pas une recommandation
fragile, c'est une absence de recommandation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..forms import parse_recommendation
from ..models import User
from ..services import get_or_create_recommendation
from ..web import flash, redirect
from .common import case_url, current_user, load_case

router = APIRouter()

ANCHOR = "recommandation"


@router.post("/cases/{case_id}/recommendation")
async def save_recommendation(
    request: Request,
    case_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    case = load_case(session, case_id)
    form = await request.form()
    result = parse_recommendation(form, [option.id for option in case.options])

    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, ANCHOR))

    recommendation = get_or_create_recommendation(session, case)
    for name, value in result.values.items():
        setattr(recommendation, name, value)
    recommendation.author = user.display_name
    session.commit()

    if result.values["option_id"] is None:
        flash(
            request,
            "Position enregistrée, mais elle ne désigne aucune des options : "
            "le lecteur ne saura pas ce que vous feriez concrètement.",
            "warning",
        )
    else:
        flash(request, "Recommandation enregistrée.", "success")
    return redirect(case_url(case_id, ANCHOR))
