"""The cockpit measures; it does not track (decided by the reader on 9 November 2026).

Commitments, conclusions on a subject, questions and decisions live in the reader's
cabinet, outside this repository. The screens therefore offer no gesture that writes: no
form, and no route that takes a pledge, carries a reading, accepts a gap or closes a
subject. The register and the pledges table stay readable and frozen until the cabinet has
taken them over. These tests guard the freeze.
"""

from __future__ import annotations

SCREENS = ("/", "/analyses", "/perimetres", "/marches", "/marche/china", "/system")


def test_no_screen_offers_a_form(client):
    for path in SCREENS:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "<form" not in response.text, path


def test_the_routes_that_wrote_are_gone(client):
    for path in ("/engagements", "/engagements/ENG-001/update", "/issues/ISS-001/read",
                 "/issues/ISS-001/accept", "/issues/ISS-001/close"):
        response = client.post(path, data={"action": "x"}, follow_redirects=False)
        assert response.status_code == 404, (path, response.status_code)


def test_the_screens_leave_the_register_and_the_pledges_frozen(client, db_session):
    """Before the freeze the day screen placed subjects into attention slots on every load.
    Now a screen is a reading: whatever the register and the pledges table hold, they hold
    the same after every page has rendered."""
    from app.domain import issues as I
    from app.perf import memory, pledges

    register = I.Register()
    register.observe(I.Observation(kind="gap_to_plan", scope="Japan", seen_at="2026-09-30",
                                   statement="Un écart qui dure", amount=-900_000.0,
                                   basis=I.STAKE))
    memory.save(db_session, register)
    pledges.create(db_session, market="Japan", action="Tenir la promesse",
                   owner_name="Quelqu'un", due_date="2026-12-31")
    db_session.commit()

    def snapshot():
        db_session.expire_all()
        issues = [(issue.issue_id, issue.status, len(issue.evidence), len(issue.readings),
                   issue.arbitration is None) for issue in memory.load(db_session).issues]
        taken = [(item.reference, item.status, item.due_date, item.updated_at)
                 for item in pledges.load(db_session)]
        return issues, taken

    before = snapshot()
    assert before[0] and before[1]
    for path in SCREENS:
        assert client.get(path).status_code == 200, path

    assert snapshot() == before
