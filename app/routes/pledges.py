"""Les gestes qui ferment la boucle : prendre un engagement, le faire vivre, porter une
lecture.

Le cockpit préparait l'appel et ne savait pas ce qui en sortait. Trois formulaires, sous
chaque conversation et dans le tableau des engagements. Aucun envoi, aucune notification :
le lecteur écrit pour lui-même, et le lundi suivant relit.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..forms import parse_pledge, parse_pledge_update, parse_reading
from ..perf import memory, pledges
from ..web import flash, redirect

router = APIRouter()


def _back(request: Request) -> str:
    """Revenir à la page d'où le geste est parti ; l'écran du jour sinon."""
    target = str(request.headers.get("referer") or "")
    if target.startswith(("http://127.0.0.1", "http://localhost", "http://testserver")):
        return target
    return "/"


@router.post("/engagements")
async def take_pledge(request: Request, session: Session = Depends(get_session)):
    result = parse_pledge(await request.form())
    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(_back(request))
    taken = pledges.create(
        session, market=result.values["market"], action=result.values["action"],
        owner_name=result.values["owner_name"], due_date=result.values["due_date"],
        expected_impact=result.values["expected_impact"], issue=result.values["issue"],
        is_critical=result.values["is_critical"],
    )
    session.commit()
    flash(request, "%s pris : %s — %s%s." % (
        taken.reference, taken.action, taken.owner_name,
        ", pour le %s" % taken.due_date if taken.due_date else ""), "success")
    return redirect(_back(request))


@router.post("/engagements/{reference}/update")
async def update_pledge(request: Request, reference: str,
                        session: Session = Depends(get_session)):
    result = parse_pledge_update(await request.form())
    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(_back(request))
    changed = pledges.update(session, reference, status=result.values["status"],
                             actual_impact=result.values["actual_impact"],
                             due_date=result.values["due_date"], notes=result.values["notes"])
    if changed is None:
        flash(request, "Aucun engagement %s." % reference, "error")
        return redirect(_back(request))
    session.commit()
    flash(request, "%s : %s." % (changed.reference, changed.status_word), "success")
    return redirect(_back(request))


@router.post("/issues/{reference}/read")
async def carry_reading(request: Request, reference: str,
                        session: Session = Depends(get_session)):
    """La lecture portée après l'appel : la conclusion, et pourquoi elle change la
    précédente. Elle s'empile, elle ne remplace pas."""
    register = memory.load(session)
    issue = register.of(reference)
    if issue is None:
        flash(request, "Aucun sujet %s." % reference, "error")
        return redirect(_back(request))
    result = parse_reading(await request.form())
    if not result.ok:
        flash(request, result.error_summary(), "error")
        return redirect(_back(request))
    try:
        issue.reinterpret(result.values["conclusion"],
                          at=result.values["at"] or date.today().isoformat(),
                          because=result.values["because"])
    except ValueError as refused:
        flash(request, str(refused), "error")
        return redirect(_back(request))
    memory.save(session, register)
    session.commit()
    flash(request, "Lecture portée sur %s." % issue.issue_id, "success")
    return redirect(_back(request))
