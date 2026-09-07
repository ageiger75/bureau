"""Ce qui a changé depuis lundi dernier : la mémoire, rendue visible.

Tout le reste de l'écran est recalculé à chaque lecture et présenterait les mêmes faits
chaque lundi comme des nouveautés. Ce bloc dit ce qui a **bougé** dans la semaine : les
sujets ouverts, ceux qui se sont clos, les lectures portées, les arbitrages, et les
engagements qui arrivent à échéance ou l'ont dépassée. Un lecteur qui n'a que cinq minutes
lit ce bloc en dernier et sait ce qu'il a manqué.

Une semaine, jamais plus : au-delà, ce n'est plus « ce qui a changé », c'est l'histoire,
et l'histoire vit dans le registre.
"""

from __future__ import annotations

import datetime
from typing import List, Optional, Sequence

from ..domain.issues import CLOSED, NORMALIZED

#: Une semaine de changements. Le lundi lit la semaine qui vient de finir.
DAYS = 7

#: Un engagement « bientôt dû » l'est dans la semaine qui vient.
DUE_WITHIN = 7

LIVE = ("open", "in_progress", "blocked")


def _day(text) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


class Change:
    """Un fait daté, en une ligne, avec le sujet ou l'engagement qu'il concerne."""

    __slots__ = ("kind", "when", "text", "reference")

    def __init__(self, kind: str, when: str, text: str, reference: str = "") -> None:
        self.kind = kind
        self.when = when
        self.text = text
        self.reference = reference


class Changes:
    """La semaine écoulée, en listes courtes."""

    def __init__(self, since: datetime.date, today: datetime.date,
                 opened: Sequence[Change] = (), closed: Sequence[Change] = (),
                 read: Sequence[Change] = (), arbitrated: Sequence[Change] = (),
                 due: Sequence[Change] = (), overdue: Sequence[Change] = (),
                 absent: Sequence[str] = ()) -> None:
        self.since = since
        self.today = today
        self.opened = list(opened)
        self.closed = list(closed)
        self.read = list(read)
        self.arbitrated = list(arbitrated)
        self.due = list(due)
        self.overdue = list(overdue)
        self.absent = list(absent)

    @property
    def items(self) -> List[Change]:
        return self.opened + self.closed + self.read + self.arbitrated + self.overdue + self.due

    #: Au-delà, la liste se compte : le jour où le registre est né, tout est « ouvert ».
    MOST = 10

    @property
    def shown(self) -> List[Change]:
        return self.items[:self.MOST]

    @property
    def hidden(self) -> int:
        return max(0, len(self.items) - self.MOST)

    @property
    def is_quiet(self) -> bool:
        return not self.items

    @property
    def sentence(self) -> str:
        """Le compte, en une phrase : « 2 sujets ouverts, 1 clos, 3 lectures portées »."""
        parts = []
        if self.opened:
            parts.append("%d sujet%s ouvert%s" % (len(self.opened), "s" if len(self.opened) > 1 else "",
                                                 "s" if len(self.opened) > 1 else ""))
        if self.closed:
            parts.append("%d clos" % len(self.closed))
        if self.read:
            parts.append("%d lecture%s portée%s" % (len(self.read), "s" if len(self.read) > 1 else "",
                                                    "s" if len(self.read) > 1 else ""))
        if self.arbitrated:
            parts.append("%d arbitrage%s" % (len(self.arbitrated), "s" if len(self.arbitrated) > 1 else ""))
        if self.overdue:
            parts.append("%d engagement%s en retard" % (len(self.overdue), "s" if len(self.overdue) > 1 else ""))
        if self.due:
            parts.append("%d engagement%s à échéance cette semaine" % (len(self.due), "s" if len(self.due) > 1 else ""))
        if not parts:
            return "rien n'a bougé au registre depuis une semaine"
        return ", ".join(parts)


def _issue_label(issue) -> str:
    return "%s %s" % (issue.issue_id, issue.title)


def build(register, commitments: Sequence = (), today: Optional[datetime.date] = None,
          days: int = DAYS) -> Changes:
    """La semaine écoulée, lue dans le registre et les engagements. Rien n'est relu."""
    today = today or datetime.date.today()
    since = today - datetime.timedelta(days=days)
    since_text = since.isoformat()
    opened, closed, read, arbitrated = [], [], [], []
    for issue in getattr(register, "issues", []) or []:
        opened_at = str(getattr(issue, "opened_at", "") or "")[:10]
        updated_at = str(getattr(issue, "updated_at", "") or "")[:10]
        if opened_at and opened_at >= since_text and issue.is_open:
            opened.append(Change("ouvert", opened_at, _issue_label(issue), issue.issue_id))
        if issue.status in (CLOSED, NORMALIZED) and updated_at and updated_at >= since_text:
            what = "clos" if issue.status == CLOSED else "normalisé"
            reason = " — %s" % issue.closed_reason if getattr(issue, "closed_reason", "") else ""
            closed.append(Change(what, updated_at, _issue_label(issue) + reason, issue.issue_id))
        for reading in getattr(issue, "readings", []) or []:
            if str(reading.at)[:10] >= since_text:
                read.append(Change("lecture", str(reading.at)[:10],
                                   "%s : %s" % (issue.issue_id, reading.conclusion), issue.issue_id))
        arbitration = getattr(issue, "arbitration", None)
        if arbitration is not None and str(arbitration.at)[:10] >= since_text:
            text = "%s accepté par %s — %s" % (issue.issue_id, arbitration.decided_by, arbitration.reason)
            if arbitration.review_on:
                text += " (réexamen le %s)" % arbitration.review_on
            arbitrated.append(Change("arbitrage", str(arbitration.at)[:10], text, issue.issue_id))

    due, overdue = [], []
    horizon = today + datetime.timedelta(days=DUE_WITHIN)
    for item in commitments or ():
        if getattr(item, "status", "") not in LIVE:
            continue
        when = _day(getattr(item, "due_date", None))
        if when is None:
            continue
        label = "%s — %s, %s" % (item.action, getattr(item, "owner_name", "") or "sans owner",
                                 getattr(item, "market", "") or "")
        if when < today:
            overdue.append(Change("en retard", when.isoformat(), label))
        elif when <= horizon:
            due.append(Change("échéance", when.isoformat(), label))
    return Changes(since, today, opened, closed, read, arbitrated, due, overdue)
