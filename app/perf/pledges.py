"""Les engagements pris dans le cockpit avant le 9 novembre 2026, gelés.

Le cockpit mesure, il ne suit pas : depuis cette date, un engagement d'owner se prend dans
le cabinet du lecteur, hors de ce dépôt. Ce qui avait été pris ici reste lisible, tel
quel, pour `manage.py engagements` et la section du même nom de l'export du cabinet, le
temps que le cabinet le reprenne. Aucune surface n'écrit plus dans cette table.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Pledge as Row
from ..util import days_until

PREFIX = "ENG"
OPEN = "open"
IN_PROGRESS = "in_progress"
BLOCKED = "blocked"
DONE = "done"
CANCELLED = "cancelled"
STATUSES = (OPEN, IN_PROGRESS, BLOCKED, DONE, CANCELLED)
LIVE = (OPEN, IN_PROGRESS, BLOCKED)
STATUS_WORDS = {OPEN: "ouvert", IN_PROGRESS: "en cours", BLOCKED: "bloqué", DONE: "fait",
                CANCELLED: "abandonné"}


class Pledge:
    """Un engagement, tel que le terminal et l'export du cabinet le lisent."""

    __slots__ = ("reference", "market", "issue", "action", "owner_name", "due_date",
                 "expected_impact", "actual_impact", "status", "is_critical", "postponements",
                 "notes", "created_at", "updated_at")

    def __init__(self, reference: str, market: str, action: str, owner_name: str = "",
                 due_date: Optional[str] = None, expected_impact: str = "",
                 actual_impact: str = "", status: str = OPEN, is_critical: bool = False,
                 postponements: int = 0, notes: str = "", issue: str = "",
                 created_at: str = "", updated_at: str = "") -> None:
        self.reference = reference
        self.market = market
        self.issue = issue
        self.action = action
        self.owner_name = owner_name
        self.due_date = due_date
        self.expected_impact = expected_impact
        self.actual_impact = actual_impact
        self.status = status
        self.is_critical = is_critical
        self.postponements = postponements
        self.notes = notes
        self.created_at = created_at
        self.updated_at = updated_at

    #: Ce que les règles de suivi lisent ; vide ici, la preuve est le résultat observé.
    evidence = ""

    @property
    def days_left(self) -> Optional[int]:
        return days_until(self.due_date)

    @property
    def is_live(self) -> bool:
        return self.status in LIVE

    @property
    def status_word(self) -> str:
        return STATUS_WORDS.get(self.status, self.status)


def _to_domain(row: Row) -> Pledge:
    return Pledge(row.reference, row.market, row.action, row.owner_name, row.due_date,
                  row.expected_impact, row.actual_impact, row.status, bool(row.is_critical),
                  int(row.postponements or 0), row.notes, row.issue_ref, row.created_at,
                  row.updated_at)


def load(session: Session) -> List[Pledge]:
    """Tous les engagements, du plus récent au plus ancien."""
    rows = session.scalars(select(Row).order_by(Row.reference)).all()
    return [_to_domain(row) for row in reversed(rows)]


def _next_reference(session: Session) -> str:
    rows = session.scalars(select(Row.reference)).all()
    highest = 0
    for reference in rows:
        try:
            highest = max(highest, int(str(reference).split("-")[-1]))
        except ValueError:
            continue
    return "%s-%03d" % (PREFIX, highest + 1)


def create(session: Session, market: str, action: str, owner_name: str = "",
           due_date: Optional[str] = None, expected_impact: str = "", issue: str = "",
           is_critical: bool = False) -> Pledge:
    """Écrire un engagement. Plus aucune surface ne l'appelle depuis le gel ; la suite s'en
    sert pour poser une ligne et vérifier que les écrans la laissent intacte."""
    row = Row(reference=_next_reference(session), market=market.strip(), issue_ref=issue.strip(),
              action=action.strip(), owner_name=owner_name.strip(), due_date=due_date or None,
              expected_impact=expected_impact.strip(), status=OPEN, is_critical=is_critical)
    session.add(row)
    session.flush()
    return _to_domain(row)
