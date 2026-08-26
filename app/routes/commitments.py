"""Engagements : rendre le retard visible, sans jamais agir à l'extérieur (brief §7 FR-10).

Aucune route de ce module n'envoie de message, ne crée de tâche dans un outil externe ni ne
relance qui que ce soit. Le suivi est manuel et assumé comme tel (brief §14).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain.commitments import check_commitment
from ..domain.enums import CommitmentStatus
from ..forms import parse_commitment
from ..models import Commitment, User
from ..services import commitment_days_left, find_commitment, to_commitment_input
from ..web import flash, redirect
from .common import case_url, current_user, load_case

router = APIRouter()

ANCHOR = "suivi"


def _flash_warnings(request: Request, item: Commitment) -> None:
    warnings = check_commitment(
        to_commitment_input(item), commitment_days_left(item)
    )
    for item_warning in warnings:
        if item_warning.is_serious:
            flash(request, "%s %s" % (item_warning.message, item_warning.fix), "warning")


@router.post("/cases/{case_id}/commitments")
async def add_commitment(
    request: Request,
    case_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    case = load_case(session, case_id)
    form = await request.form()
    result = parse_commitment(form)

    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, ANCHOR))

    item = Commitment(case_id=case.id, created_by=user.display_name, **result.values)
    session.add(item)
    session.commit()

    flash(request, "Engagement ajouté. Aucun message n'a été envoyé.", "success")
    _flash_warnings(request, item)
    return redirect(case_url(case_id, ANCHOR))


@router.post("/cases/{case_id}/commitments/{commitment_id}")
async def update_commitment(
    request: Request,
    case_id: str,
    commitment_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    del user
    load_case(session, case_id)
    item = find_commitment(session, case_id, commitment_id)
    if item is None:
        flash(request, "Engagement introuvable dans ce dossier.", "error")
        return redirect(case_url(case_id, ANCHOR))

    form = await request.form()
    result = parse_commitment(form)
    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, ANCHOR))

    for name, value in result.values.items():
        setattr(item, name, value)
    session.commit()

    if item.status == CommitmentStatus.REARBITRATION_NEEDED.value:
        flash(
            request,
            "Engagement marqué « à ré-arbitrer ». La décision d'origine est en cause : "
            "la revue est le bon endroit pour la reprendre.",
            "warning",
        )
    else:
        flash(request, "Engagement mis à jour.", "success")
    _flash_warnings(request, item)
    return redirect(case_url(case_id, ANCHOR))


@router.post("/cases/{case_id}/commitments/{commitment_id}/delete")
async def delete_commitment(
    request: Request,
    case_id: str,
    commitment_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    del user
    load_case(session, case_id)
    item = find_commitment(session, case_id, commitment_id)
    if item is None:
        flash(request, "Engagement introuvable dans ce dossier.", "error")
        return redirect(case_url(case_id, ANCHOR))

    session.delete(item)
    session.commit()
    flash(request, "Engagement retiré du dossier.", "info")
    return redirect(case_url(case_id, ANCHOR))
