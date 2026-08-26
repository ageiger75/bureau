"""Options : deux ou trois choix réellement distincts, statu quo compris (brief §4).

La limite haute n'est pas imposée à la saisie mais au passage en « Prêt à décider » :
on laisse le CEO poser quatre pistes en réfléchissant, et l'outil exige de trancher avant
de déclarer le dossier décidable.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..forms import parse_option
from ..models import Option, User
from ..services import find_option, next_option_ordinal
from ..web import flash, redirect
from .common import case_url, current_user, load_case

router = APIRouter()

ANCHOR = "options"


@router.post("/cases/{case_id}/options")
async def add_option(
    request: Request,
    case_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    case = load_case(session, case_id)
    form = await request.form()
    result = parse_option(form)

    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, ANCHOR))

    option = Option(
        case_id=case.id,
        ordinal=next_option_ordinal(case),
        created_by=user.display_name,
        **result.values,
    )
    session.add(option)
    session.commit()

    if len(case.options) > 3:
        flash(
            request,
            "Plus de trois options : le dossier ne pourra pas passer en « Prêt à décider » "
            "avant d'en écarter ou d'en fusionner.",
            "warning",
        )
    else:
        flash(request, "Option ajoutée.", "success")
    return redirect(case_url(case_id, ANCHOR))


@router.post("/cases/{case_id}/options/{option_id}")
async def update_option(
    request: Request,
    case_id: str,
    option_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    del user
    load_case(session, case_id)
    option = find_option(session, case_id, option_id)
    if option is None:
        flash(request, "Option introuvable dans ce dossier.", "error")
        return redirect(case_url(case_id, ANCHOR))

    form = await request.form()
    result = parse_option(form)
    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, ANCHOR))

    for name, value in result.values.items():
        setattr(option, name, value)
    session.commit()

    flash(request, "Option mise à jour.", "success")
    return redirect(case_url(case_id, ANCHOR))


@router.post("/cases/{case_id}/options/{option_id}/delete")
async def delete_option(
    request: Request,
    case_id: str,
    option_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    del user
    case = load_case(session, case_id)
    option = find_option(session, case_id, option_id)
    if option is None:
        flash(request, "Option introuvable dans ce dossier.", "error")
        return redirect(case_url(case_id, ANCHOR))

    # La recommandation pointe peut-être sur cette option : on détache le lien avant de
    # supprimer, sinon la contrainte de clé étrangère fait échouer l'opération.
    recommendation = case.recommendation
    detached = False
    if recommendation is not None and recommendation.option_id == option.id:
        recommendation.option_id = None
        detached = True

    session.delete(option)
    session.commit()

    if detached:
        flash(
            request,
            "Option supprimée. La recommandation ne désigne plus aucune option : "
            "elle doit être reprise.",
            "warning",
        )
    else:
        flash(request, "Option supprimée.", "info")
    return redirect(case_url(case_id, ANCHOR))
