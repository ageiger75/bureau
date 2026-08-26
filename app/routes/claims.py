"""Affirmations : faits sourcés, hypothèses, opinions, éléments à vérifier.

Politique retenue : **avertissement, pas refus**. Un fait sans source est enregistré tel
quel, puis signalé en clair sur le dossier et sur l'accueil. Bloquer la saisie pousserait
à requalifier le fait douteux pour faire taire le message, ce qui effacerait justement
l'information à conserver.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..domain.claims import ClaimInput, check_claim
from ..forms import parse_claim
from ..models import Claim, User
from ..services import find_claim
from ..web import flash, redirect
from .common import case_url, current_user, load_case

router = APIRouter()

ANCHOR = "socle-factuel"


def _flash_warnings(request: Request, values: dict) -> None:
    """Remonte immédiatement les avertissements portés par la saisie."""
    warnings = check_claim(
        ClaimInput(
            text=values["text"],
            category=values["category"],
            source_ref=values["source_ref"],
            quote=values["quote"],
            rationale=values["rationale"],
            best_test=values["best_test"],
            materiality=values["materiality"],
        )
    )
    for warning in warnings:
        if warning.is_serious:
            flash(request, "%s %s" % (warning.message, warning.fix), "warning")


@router.post("/cases/{case_id}/claims")
async def add_claim(
    request: Request,
    case_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    case = load_case(session, case_id)
    form = await request.form()
    result = parse_claim(form)

    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, ANCHOR))

    claim = Claim(case_id=case.id, created_by=user.display_name, **result.values)
    session.add(claim)
    session.commit()

    flash(request, "Affirmation ajoutée.", "success")
    _flash_warnings(request, result.values)
    return redirect(case_url(case_id, ANCHOR))


@router.post("/cases/{case_id}/claims/{claim_id}")
async def update_claim(
    request: Request,
    case_id: str,
    claim_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    del user
    load_case(session, case_id)
    claim = find_claim(session, case_id, claim_id)
    if claim is None:
        flash(request, "Affirmation introuvable dans ce dossier.", "error")
        return redirect(case_url(case_id, ANCHOR))

    form = await request.form()
    result = parse_claim(form)
    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(case_url(case_id, ANCHOR))

    for name, value in result.values.items():
        setattr(claim, name, value)
    session.commit()

    flash(request, "Affirmation mise à jour.", "success")
    _flash_warnings(request, result.values)
    return redirect(case_url(case_id, ANCHOR))


@router.post("/cases/{case_id}/claims/{claim_id}/delete")
async def delete_claim(
    request: Request,
    case_id: str,
    claim_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    del user
    load_case(session, case_id)
    claim = find_claim(session, case_id, claim_id)
    if claim is None:
        flash(request, "Affirmation introuvable dans ce dossier.", "error")
        return redirect(case_url(case_id, ANCHOR))

    session.delete(claim)
    session.commit()
    flash(request, "Affirmation retirée du dossier.", "info")
    return redirect(case_url(case_id, ANCHOR))
