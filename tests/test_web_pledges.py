"""Fermer la boucle : un engagement pris après l'appel, tenu jusqu'à sa date, relu le lundi.

Le cockpit préparait l'appel et ne savait pas ce qui en sortait. Ces tests gardent le
chemin entier : le geste sous la conversation, la relecture dans la conversation, dans le
tableau des engagements et dans « ce qui a changé » ; le résultat observé exigé quand c'est
fait ; la lecture portée qui s'empile. Marchés et personnes inventés.
"""

from __future__ import annotations

from app.domain import issues as I
from app.perf import memory, pledges
from tests.conftest import page_text


def _subject(db_session, scope="Northland"):
    register = I.Register()
    issue = register.observe(I.Observation(
        kind="gap_to_plan", scope=scope, seen_at="2026-08-01",
        statement="Un écart qui ne se referme pas", amount=-900_000.0, basis=I.STAKE))
    issue.accountable = "Une dirigeante"
    memory.save(db_session, register)
    db_session.commit()
    return issue.issue_id


def test_a_pledge_taken_under_a_conversation_is_read_back_everywhere(client, db_session):
    reference = _subject(db_session)

    response = client.post("/engagements", data={
        "market": "Northland", "issue": reference, "owner_name": "Une dirigeante",
        "action": "Relancer le plan de conversion", "due_date": "2099-01-31",
        "expected_impact": "un point de conversion",
    }, follow_redirects=False)
    assert response.status_code == 303

    taken = pledges.load(db_session)
    assert [item.reference for item in taken] == ["ENG-001"]
    assert taken[0].market == "Northland" and taken[0].issue == reference
    assert taken[0].status == "open" and taken[0].days_left > 0

    page = page_text(client.get("/"))
    assert "ENG-001" in page
    assert "Relancer le plan de conversion" in page
    assert "Aucun engagement pris encore" not in page


def test_a_pledge_without_a_person_or_an_action_is_refused(client, db_session):
    for data in ({"market": "Northland", "action": "Faire", "owner_name": ""},
                 {"market": "Northland", "action": "", "owner_name": "Quelqu'un"}):
        client.post("/engagements", data=data, follow_redirects=False)
    assert pledges.load(db_session) == []


def test_done_requires_what_was_observed_and_a_postponement_is_counted(client, db_session):
    taken = pledges.create(db_session, market="Northland", action="Tenir la promotion",
                           owner_name="Une dirigeante", due_date="2099-01-31")
    db_session.commit()

    client.post("/engagements/%s/update" % taken.reference, data={"status": "done"},
                follow_redirects=False)
    db_session.expire_all()
    assert pledges.load(db_session)[0].status == "open"          # refusé : rien d'observé

    client.post("/engagements/%s/update" % taken.reference,
                data={"status": "", "due_date": "2099-03-31"}, follow_redirects=False)
    client.post("/engagements/%s/update" % taken.reference,
                data={"status": "done", "actual_impact": "La promotion a tenu, +2 points"},
                follow_redirects=False)
    db_session.expire_all()
    done = pledges.load(db_session)[0]
    assert done.status == "done" and done.postponements == 1
    assert done.actual_impact.startswith("La promotion a tenu")


def test_a_reading_carried_after_the_call_stacks_and_asks_why_it_changes(client, db_session):
    reference = _subject(db_session)

    client.post("/issues/%s/read" % reference, data={"conclusion": "Trois magasins mal codés"},
                follow_redirects=False)
    db_session.expire_all()
    issue = memory.load(db_session).of(reference)
    assert [item.conclusion for item in issue.readings] == ["Trois magasins mal codés"]

    # Une seconde conclusion sans motif est refusée ; avec, elle s'empile.
    client.post("/issues/%s/read" % reference, data={"conclusion": "Un vrai recul"},
                follow_redirects=False)
    db_session.expire_all()
    assert len(memory.load(db_session).of(reference).readings) == 1
    client.post("/issues/%s/read" % reference,
                data={"conclusion": "Un vrai recul", "because": "les magasins ont été recodés"},
                follow_redirects=False)
    db_session.expire_all()
    assert len(memory.load(db_session).of(reference).readings) == 2


def test_the_day_keeps_three_changes_and_sends_the_channel_table_to_analyses(client):
    today = page_text(client.get("/"))
    analyses = page_text(client.get("/analyses"))

    assert "Ce qui a changé depuis lundi dernier" in today
    assert "en entier" in analyses
    assert "par canal" in analyses
