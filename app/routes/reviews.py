"""Revue : confronter les hypothèses d'origine aux résultats (brief §7 FR-14).

Deux gestes distincts, volontairement séparés :
  * **enregistrer** une revue en cours, autant de fois qu'on veut, sans contrainte ;
  * **clore** la revue, ce qui exige des résultats, une leçon et une suite décidée.

Clore la revue fait passer le dossier en « Clos », sauf si la suite décidée est un retour
en arrière ou un « pas encore » : dans ces deux cas le dossier repart en analyse, ce qui est
la réouverture explicite prévue par le brief §6.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain.cases import CaseStatus, TransitionRefused, transition
from ..domain.enums import NEXT_STEP_LABELS, NextStep, ReviewStatus
from ..domain.reviews import blocking_issues, check_review
from ..forms import parse_review
from ..models import Review, User
from ..services import find_review, to_review_input, transition_context
from ..util import today_iso
from ..web import flash, redirect
from .common import case_url, current_user, load_case

router = APIRouter()

ANCHOR = "revue"

# Suites qui rouvrent le dossier au lieu de le clore.
REOPENING_STEPS = (NextStep.REVERSE.value, NextStep.NOT_YET.value)


def _apply(item: Review, values: dict) -> None:
    for name, value in values.items():
        setattr(item, name, value)


@router.post("/cases/{case_id}/review/{review_id}")
async def save_review(
    request: Request,
    case_id: str,
    review_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    del user
    load_case(session, case_id)
    item = find_review(session, case_id, review_id)
    if item is None:
        flash(request, "Revue introuvable dans ce dossier.", "error")
        return redirect(case_url(case_id, ANCHOR))
    if item.is_completed:
        flash(
            request,
            "Cette revue est terminée. Ses conclusions ne se réécrivent pas : rouvrir le "
            "dossier crée une nouvelle décision et une nouvelle revue.",
            "warning",
        )
        return redirect(case_url(case_id, ANCHOR))

    form = await request.form()
    result = parse_review(form)
    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, ANCHOR))

    _apply(item, result.values)
    if item.status == ReviewStatus.PLANNED.value:
        item.status = ReviewStatus.IN_PROGRESS.value
    session.commit()

    flash(request, "Revue enregistrée.", "success")
    for item_warning in check_review(to_review_input(item)):
        if item_warning.is_serious:
            flash(request, "%s %s" % (item_warning.message, item_warning.fix), "warning")
    return redirect(case_url(case_id, ANCHOR))


@router.post("/cases/{case_id}/review/{review_id}/complete")
async def complete_review(
    request: Request,
    case_id: str,
    review_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    case = load_case(session, case_id)
    item = find_review(session, case_id, review_id)
    if item is None:
        flash(request, "Revue introuvable dans ce dossier.", "error")
        return redirect(case_url(case_id, ANCHOR))

    form = await request.form()
    result = parse_review(form)
    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, ANCHOR))

    _apply(item, result.values)

    issues = blocking_issues(to_review_input(item))
    if issues:
        session.commit()  # le travail saisi n'est pas perdu pour autant
        for issue in issues:
            flash(request, "%s %s" % (issue.message, issue.fix), "warning")
        return redirect(case_url(case_id, ANCHOR))

    item.status = ReviewStatus.COMPLETED.value
    item.completed_by_id = user.id
    item.held_date = item.held_date or today_iso()

    reopening = item.next_step in REOPENING_STEPS
    target = CaseStatus.ANALYSIS.value if reopening else CaseStatus.CLOSED.value
    try:
        case.status = transition(case.status, target, transition_context(case))
    except TransitionRefused as exc:
        session.rollback()
        flash(request, str(exc), "warning")
        return redirect(case_url(case_id, ANCHOR))

    session.commit()

    if reopening:
        flash(
            request,
            "Revue terminée : « %s ». Le dossier repart en analyse."
            % NEXT_STEP_LABELS.get(item.next_step, item.next_step),
            "success",
        )
    else:
        flash(
            request,
            "Revue terminée et dossier clos. Il reste retrouvable avec son contexte, "
            "ses raisons et ses leçons.",
            "success",
        )
    return redirect(case_url(case_id, ANCHOR))
