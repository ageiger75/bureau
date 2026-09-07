"""Ce qui a changé depuis lundi dernier : la mémoire, rendue visible.

Ces tests gardent la fenêtre — une semaine, jamais plus — et les cinq faits qu'elle
porte : ouvert, clos, lu, arbitré, à échéance. Valeurs inventées.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from app.domain import issues as I
from app.perf import changes as C

TODAY = datetime.date(2026, 9, 7)


def _issue(reference, opened_at, status=I.DETECTED, updated_at=""):
    issue = I.Issue(issue_id=reference, title="%s · écart" % reference, opened_at=opened_at,
                    updated_at=updated_at or opened_at)
    issue.record(I.Observation(kind="gap_to_plan", scope=reference, seen_at="2026-08-01"))
    if status != I.DETECTED:
        issue.status = status
    return issue


def test_only_the_last_week_counts_and_each_fact_has_its_line():
    fresh = _issue("ISS-010", "2026-09-03T10:00:00")
    stale = _issue("ISS-002", "2026-06-01T10:00:00")
    done = _issue("ISS-003", "2026-05-01T10:00:00", updated_at="2026-09-05T09:00:00")
    done.status = I.CLOSED
    done.closed_reason = "trois magasins mal codés"
    read = _issue("ISS-004", "2026-05-01T10:00:00")
    read.reinterpret("Cause comprise", at="2026-09-04")
    read.reinterpret("Cause revue", at="2026-08-01", because="plus ancienne")
    judged = _issue("ISS-005", "2026-05-01T10:00:00")
    judged.accept_variance(I.Arbitration(decided_by="Une dirigeante", at="2026-09-06",
                                         reason="fermeture connue", review_on="2026-11-30"))
    register = I.Register([fresh, stale, done, read, judged])

    changes = C.build(register, today=TODAY)

    assert [item.reference for item in changes.opened] == ["ISS-010"]
    assert [item.reference for item in changes.closed] == ["ISS-003"]
    assert "trois magasins mal codés" in changes.closed[0].text
    assert [item.text for item in changes.read] == ["ISS-004 : Cause comprise"]
    assert "réexamen le 2026-11-30" in changes.arbitrated[0].text
    assert changes.sentence == "1 sujet ouvert, 1 clos, 1 lecture portée, 1 arbitrage"


def test_commitments_due_this_week_and_overdue_are_named_and_settled_ones_are_not():
    soon = SimpleNamespace(status="open", due_date="2026-09-10", action="Relancer", owner_name="A", market="Northland")
    late = SimpleNamespace(status="in_progress", due_date="2026-09-01", action="Fermer", owner_name="B", market="Eastland")
    far = SimpleNamespace(status="open", due_date="2026-10-20", action="Loin", owner_name="C", market="")
    settled = SimpleNamespace(status="done", due_date="2026-09-08", action="Fait", owner_name="D", market="")

    changes = C.build(I.Register(), [soon, late, far, settled], today=TODAY)

    assert [item.text for item in changes.due] == ["Relancer — A, Northland"]
    assert [item.text for item in changes.overdue] == ["Fermer — B, Eastland"]
    assert changes.sentence == "1 engagement en retard, 1 engagement à échéance cette semaine"


def test_a_quiet_week_says_so():
    changes = C.build(I.Register(), today=TODAY)

    assert changes.is_quiet
    assert changes.sentence == "rien n'a bougé au registre depuis une semaine"


def test_the_persistence_stamps_reach_the_domain(db_session):
    from app.perf import memory

    register = I.Register()
    issue = register.observe(I.Observation(kind="gap_to_plan", scope="Northland", seen_at="2026-08-01"))
    memory.save(db_session, register)
    db_session.commit()

    loaded = memory.load(db_session).of(issue.issue_id)
    assert loaded.opened_at and loaded.updated_at
