"""Dossiers de décision : création, lecture, cadrage, changement d'état."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain.cases import TransitionRefused, offered_statuses, transition, urgency
from ..domain.enums import CASE_STATUS_LABELS, Confidentiality
from ..forms import parse_case_creation, parse_case_framing
from ..models import DecisionCase, User
from ..services import (
    active_review,
    challenge_summary,
    challenge_warnings,
    challenges_by_voice,
    claim_warnings,
    claims_by_category,
    commitment_alerts,
    commitment_summary,
    commitment_warnings,
    coverage_label,
    diagnose,
    list_archived_rows,
    next_reference,
    option_choices,
    recommendation_option_id,
    review_days_left,
    sorted_commitments,
    transition_context,
)
from ..util import days_until
from ..web import flash, redirect, render
from .common import case_url, current_user, load_case

router = APIRouter()


@router.get("/cases")
def archive(
    request: Request,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """Archive des dossiers clos, et des leçons qu'ils laissent derrière eux."""
    return render(
        request,
        "archive.html",
        {"user": user, "rows": list_archived_rows(session)},
    )


@router.get("/cases/new")
def new_case_form(request: Request, user: User = Depends(current_user)):
    return render(
        request,
        "case_new.html",
        {
            "user": user,
            "values": {"confidentiality": Confidentiality.CONFIDENTIAL.value},
            "errors": {},
        },
    )


@router.post("/cases")
async def create_case(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    form = await request.form()
    result = parse_case_creation(form)

    if not result.ok:
        return render(
            request,
            "case_new.html",
            {"user": user, "values": result.values, "errors": result.errors},
            status_code=400,
        )

    case = DecisionCase(
        reference=next_reference(session),
        owner_id=user.id,
        created_by_id=user.id,
        **result.values,
    )
    session.add(case)
    session.commit()

    flash(
        request,
        "Dossier %s créé. Prochaine étape : établir le socle factuel." % case.reference,
        "success",
    )
    return redirect(case_url(case.id))


@router.get("/cases/{case_id}")
def case_detail(
    request: Request,
    case_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    case = load_case(session, case_id)
    days_left = days_until(case.deadline)
    review = active_review(case)

    return render(
        request,
        "case_detail.html",
        {
            "user": user,
            "case": case,
            "readiness": diagnose(case),
            "grouped_claims": claims_by_category(case),
            "warnings_by_claim": claim_warnings(case.claims),
            "options": option_choices(case),
            "recommendation": case.recommendation,
            "coverage_label": coverage_label(case),
            "days_left": days_left,
            "urgency": urgency(days_left),
            "offered_statuses": offered_statuses(case.status),
            # Tranche 2
            "grouped_challenges": challenges_by_voice(case),
            "warnings_by_challenge": challenge_warnings(case),
            "challenge_summary": challenge_summary(case),
            "decision": case.decision,
            "recommended_option_id": recommendation_option_id(case),
            "commitments": sorted_commitments(case),
            "commitment_alerts": commitment_alerts(case),
            "warnings_by_commitment": commitment_warnings(case),
            "commitment_summary": commitment_summary(case),
            "review": review,
            "review_days_left": review_days_left(review) if review else None,
        },
    )


@router.post("/cases/{case_id}/framing")
async def update_framing(
    request: Request,
    case_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    del user
    case = load_case(session, case_id)
    form = await request.form()
    result = parse_case_framing(form)

    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, "cadrage"))

    for name, value in result.values.items():
        setattr(case, name, value)
    session.commit()

    flash(request, "Cadrage enregistré.", "success")
    return redirect(case_url(case_id, "cadrage"))


@router.post("/cases/{case_id}/status")
async def change_status(
    request: Request,
    case_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    del user
    case = load_case(session, case_id)
    form = await request.form()
    target = str(form.get("status", "")).strip()

    try:
        case.status = transition(case.status, target, transition_context(case))
    except TransitionRefused as exc:
        # Le refus est une information utile, pas une erreur technique : on l'affiche tel quel.
        flash(request, str(exc), "warning")
        return redirect(case_url(case_id))

    session.commit()
    flash(
        request,
        "Dossier passé en « %s »." % CASE_STATUS_LABELS.get(case.status, case.status),
        "success",
    )
    return redirect(case_url(case_id))
