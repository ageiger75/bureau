"""Dépendances partagées par les routeurs."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import DecisionCase, User
from ..services import find_case, resolve_current_user


def current_user(session: Session = Depends(get_session)) -> User:
    try:
        return resolve_current_user(session)
    except LookupError as exc:
        # 503 et non 500 : la base est saine, il manque seulement les données de départ.
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def load_case(session: Session, case_id: str) -> DecisionCase:
    case = find_case(session, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")
    return case


def case_url(case_id: str, anchor: str = "") -> str:
    return "/cases/%s%s" % (case_id, "#" + anchor if anchor else "")


async def form_data(request: Request):
    return await request.form()
