"""Les engagements pris dans le cockpit : la mémoire des mots.

Le cockpit préparait l'appel et ne savait pas ce qui en sortait. Un engagement s'écrit
ici, sous la conversation, après l'appel : l'action, qui, pour quand, ce qu'on en attend.
Le lundi suivant le relit dans la conversation (« déjà engagé »), dans le tableau des
engagements (ouverts, en retard, à risque), et dans « ce qui a changé ». Quand il est
fait, on écrit ce qu'on a observé, et le tableau dit si cela a marché.

Un engagement porte l'interface que le reste du cockpit lit déjà sur les engagements
inventés du mode démonstration, pour que rien d'autre ne change. Rien n'est envoyé :
c'est une note que le lecteur se fait à lui-même, et qu'il tient.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.commitments import CommitmentInput
from ..models import Pledge as Row
from ..util import days_until, now_iso, today

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
    """Un engagement, tel que la conversation, le tableau et la semaine le lisent."""

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

    def as_input(self) -> CommitmentInput:
        return CommitmentInput(action=self.action, owner_name=self.owner_name,
                               due_date=self.due_date, status=self.status,
                               is_critical=self.is_critical, evidence=self.actual_impact)


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
    """Prendre un engagement. Rend l'objet écrit, référence comprise."""
    row = Row(reference=_next_reference(session), market=market.strip(), issue_ref=issue.strip(),
              action=action.strip(), owner_name=owner_name.strip(), due_date=due_date or None,
              expected_impact=expected_impact.strip(), status=OPEN, is_critical=is_critical)
    session.add(row)
    session.flush()
    return _to_domain(row)


def update(session: Session, reference: str, status: str = "", actual_impact: str = "",
           due_date: Optional[str] = None, notes: str = "") -> Optional[Pledge]:
    """Faire vivre un engagement : un statut, un résultat observé, une nouvelle échéance.

    Une échéance repoussée compte comme un report ; le second report est le signal.
    """
    row = session.scalars(select(Row).where(Row.reference == reference)).first()
    if row is None:
        return None
    if status and status in STATUSES:
        row.status = status
    if actual_impact.strip():
        row.actual_impact = actual_impact.strip()
    if due_date and due_date != row.due_date:
        if row.due_date and due_date > row.due_date:
            row.postponements = int(row.postponements or 0) + 1
        row.due_date = due_date
    if notes.strip():
        row.notes = (row.notes + "\n" if row.notes else "") + notes.strip()
    row.updated_at = now_iso()
    session.flush()
    return _to_domain(row)


def for_market(pledges: Sequence[Pledge], market: str) -> List[Pledge]:
    wanted = (market or "").strip().casefold()
    return [item for item in pledges if item.market.strip().casefold() == wanted]


def default_due() -> str:
    """Quatre semaines : l'échéance qu'on propose quand l'appel n'en a pas fixé."""
    import datetime

    return (today() + datetime.timedelta(days=28)).isoformat()
