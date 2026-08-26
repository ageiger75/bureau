"""Décision : l'arbitrage assumé par l'humain (brief §7 FR-09).

Enregistrer la décision fait trois choses d'un seul geste : conserver le choix et ses
raisons, créer la revue à la date choisie, et faire passer le dossier en « Décidé ».
Les trois vont ensemble — une décision enregistrée sans revue planifiée ne s'apprend jamais,
et un dossier qui reste « prêt à décider » après un arbitrage ment sur son état.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain.cases import CaseStatus, TransitionRefused, transition
from ..forms import parse_decision
from ..models import User
from ..services import (
    diagnose,
    recommendation_option_id,
    record_decision,
    transition_context,
)
from ..web import flash, redirect
from .common import case_url, current_user, load_case

router = APIRouter()

ANCHOR = "decision"


@router.post("/cases/{case_id}/decision")
async def save_decision(
    request: Request,
    case_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    case = load_case(session, case_id)

    # Un dossier non mûr ne peut pas être décidé par ce formulaire : sinon le diagnostic
    # deviendrait un avis consultatif qu'il suffit de contourner en changeant d'écran.
    readiness = diagnose(case)
    if case.decision is None and not readiness.is_ready:
        flash(
            request,
            "Le dossier n'est pas prêt à décider : %s"
            % " ".join(b.message for b in readiness.blockers),
            "warning",
        )
        return redirect(case_url(case_id, "diagnostic"))

    form = await request.form()
    result = parse_decision(form, [option.id for option in case.options])
    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, ANCHOR))

    values = dict(result.values)

    # La divergence avec la recommandation est déduite, pas seulement déclarée : le CEO ne
    # doit pas avoir à cocher une case pour que l'écart soit visible à la revue.
    recommended = recommendation_option_id(case)
    if recommended is not None and values["option_id"] != recommended:
        values["diverges_from_recommendation"] = True

    was_already_decided = case.decision is not None
    record_decision(session, case, user, values)

    if not was_already_decided:
        try:
            case.status = transition(
                case.status, CaseStatus.DECIDED.value, transition_context(case)
            )
        except TransitionRefused as exc:
            session.rollback()
            flash(request, str(exc), "warning")
            return redirect(case_url(case_id, ANCHOR))

    session.commit()

    if was_already_decided:
        flash(request, "Décision mise à jour.", "success")
    else:
        flash(
            request,
            "Décision enregistrée. Revue planifiée au %s." % values["review_date"],
            "success",
        )

    if values["diverges_from_recommendation"] and not str(
        values["divergence_reason"]
    ).strip():
        flash(
            request,
            "La décision s'écarte de la recommandation sans que la raison soit écrite. "
            "C'est précisément ce qu'on voudra relire à la revue.",
            "warning",
        )

    return redirect(case_url(case_id, ANCHOR))
