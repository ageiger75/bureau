"""Challenge : contester le dossier avant de décider (brief §7 FR-07).

Même politique que pour les affirmations : une objection sans preuve est enregistrée et
signalée. Refuser pousserait à inventer une preuve pour faire passer le formulaire.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain.challenge import check_challenge
from ..domain.enums import CHALLENGE_VOICE_LABELS, ChallengeStatus
from ..forms import parse_challenge
from ..models import Challenge, User
from ..services import find_challenge, to_challenge_input
from ..util import now_iso
from ..web import flash, redirect
from .common import case_url, current_user, load_case

router = APIRouter()

ANCHOR = "challenge"


def _flash_warnings(request: Request, item: Challenge) -> None:
    for item_warning in check_challenge(to_challenge_input(item)):
        if item_warning.is_serious:
            flash(request, "%s %s" % (item_warning.message, item_warning.fix), "warning")


@router.post("/cases/{case_id}/challenges")
async def add_challenge(
    request: Request,
    case_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    case = load_case(session, case_id)
    form = await request.form()
    result = parse_challenge(form, [option.id for option in case.options])

    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, ANCHOR))

    values = dict(result.values)
    if values["status"] != ChallengeStatus.OPEN.value:
        values["answered_by"] = user.display_name
        values["answered_at"] = now_iso()

    item = Challenge(case_id=case.id, created_by=user.display_name, **values)
    session.add(item)
    session.commit()

    flash(
        request,
        "Objection de %s enregistrée."
        % CHALLENGE_VOICE_LABELS.get(item.voice, item.voice),
        "success",
    )
    _flash_warnings(request, item)
    return redirect(case_url(case_id, ANCHOR))


@router.post("/cases/{case_id}/challenges/{challenge_id}")
async def update_challenge(
    request: Request,
    case_id: str,
    challenge_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    case = load_case(session, case_id)
    item = find_challenge(session, case_id, challenge_id)
    if item is None:
        flash(request, "Objection introuvable dans ce dossier.", "error")
        return redirect(case_url(case_id, ANCHOR))

    form = await request.form()
    result = parse_challenge(form, [option.id for option in case.options])
    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, ANCHOR))

    was_open = item.status == ChallengeStatus.OPEN.value
    for name, value in result.values.items():
        setattr(item, name, value)

    # L'auteur de la réponse est horodaté au moment où l'objection sort de « sans réponse ».
    if was_open and item.status != ChallengeStatus.OPEN.value:
        item.answered_by = user.display_name
        item.answered_at = now_iso()

    session.commit()
    flash(request, "Objection mise à jour.", "success")
    _flash_warnings(request, item)
    return redirect(case_url(case_id, ANCHOR))


@router.post("/cases/{case_id}/challenges/{challenge_id}/delete")
async def delete_challenge(
    request: Request,
    case_id: str,
    challenge_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    del user
    load_case(session, case_id)
    item = find_challenge(session, case_id, challenge_id)
    if item is None:
        flash(request, "Objection introuvable dans ce dossier.", "error")
        return redirect(case_url(case_id, ANCHOR))

    session.delete(item)
    session.commit()
    flash(request, "Objection retirée du dossier.", "info")
    return redirect(case_url(case_id, ANCHOR))
