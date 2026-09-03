"""Les deux gestes humains sur un sujet, depuis l'écran.

Le registre savait déjà tout retenir ; ce qui manquait était de pouvoir arbitrer sans
ligne de commande. Le lecteur de ce cockpit n'écrit pas de code — lui demander de composer
une commande pour dire « j'accepte cet écart » revient à ne pas lui offrir le geste.

Ces tests gardent ce que la doctrine réserve à un humain, et surtout ce qui n'est pas
offert : rouvrir.
"""

from __future__ import annotations

from app.domain import issues as I
from app.perf import memory
from tests.conftest import page_text


def _subject(db_session, statement="Un écart qui ne se referme pas"):
    register = I.Register()
    issue = register.observe(I.Observation(
        kind="gap_to_plan", scope="Northland", seen_at="2026-08-01",
        statement=statement, amount=-900_000.0, basis=I.STAKE))
    memory.save(db_session, register)
    db_session.commit()
    return issue.issue_id


def _reload(db_session, reference):
    db_session.expire_all()
    return memory.load(db_session).of(reference)


def test_accepting_a_variance_puts_the_subject_to_sleep(client, db_session):
    """Sans ce geste, le sujet reviendrait chaque lundi, le lecteur le réarbitrerait, et
    il cesserait de lire. Arbitrer doit servir à quelque chose."""
    reference = _subject(db_session)

    response = client.post("/issues/%s/accept" % reference, data={
        "decided_by": "Une dirigeante",
        "reason": "Effet de calendrier, la comparaison se referme au trimestre",
    }, follow_redirects=True)

    assert response.status_code == 200
    again = _reload(db_session, reference)
    assert again.status == I.VARIANCE_ACCEPTED
    assert again.arbitration.decided_by == "Une dirigeante"


def test_a_variance_accepted_by_nobody_is_refused(client, db_session):
    """Une décision sans nom n'est pas une décision. C'est la règle que la doctrine pose
    sur la clôture, et elle vaut autant ici : un écart accepté anonymement est un écart
    que personne n'assume."""
    reference = _subject(db_session)

    client.post("/issues/%s/accept" % reference,
                data={"decided_by": "", "reason": "Parce que"}, follow_redirects=True)

    # L'état est vérifié par l'arbitrage et non par le statut : la redirection rend
    # l'écran, et l'écran porte le sujet à son créneau. Ce qui doit être absent, c'est la
    # décision — pas le fait que le sujet ait été montré.
    again = _reload(db_session, reference)
    assert again.arbitration is None and again.status != I.VARIANCE_ACCEPTED


def test_a_variance_accepted_without_a_reason_is_refused(client, db_session):
    """C'est cette phrase qu'on relira dans six mois, quand le sujet remontera et que
    personne ne se souviendra pourquoi il dormait."""
    reference = _subject(db_session)

    client.post("/issues/%s/accept" % reference,
                data={"decided_by": "Une dirigeante", "reason": "  "},
                follow_redirects=True)

    again = _reload(db_session, reference)
    assert again.arbitration is None and again.status != I.VARIANCE_ACCEPTED


def test_the_review_date_is_kept_so_the_sleep_has_an_end(client, db_session):
    reference = _subject(db_session)

    client.post("/issues/%s/accept" % reference, data={
        "decided_by": "Une dirigeante",
        "reason": "Écart accepté jusqu'à la fin de la campagne",
        "review_on": "2026-11-30",
    }, follow_redirects=True)

    assert _reload(db_session, reference).arbitration.review_on == "2026-11-30"


def test_closing_requires_a_human_name(client, db_session):
    """§C9 : la machine peut constater qu'un chiffre est revenu dans sa zone, ce qui est
    réversible. Elle ne prononce pas qu'une cause est comprise."""
    reference = _subject(db_session)
    client.get("/")   # la lecture porte le sujet à son créneau : on ne clôt que ce qui a été porté

    client.post("/issues/%s/close" % reference,
                data={"closed_by": "", "reason": "Réglé"}, follow_redirects=True)

    assert _reload(db_session, reference).status != I.CLOSED

    client.post("/issues/%s/close" % reference, data={
        "closed_by": "Une dirigeante",
        "reason": "Trois magasins mal codés, recodés, l'écart a disparu deux mois de suite",
    }, follow_redirects=True)

    assert _reload(db_session, reference).status == I.CLOSED


def test_a_subject_the_screen_carried_is_in_attention_and_can_therefore_be_closed(
        client, db_session):
    """Le défaut que ce placement ferme : l'écran montrait des sujets en créneau
    d'attention dont l'état restait « détecté », et la clôture — permise seulement depuis
    un état porté — était refusée à vie. Un sujet qu'on met devant le lecteur est porté."""
    reference = _subject(db_session)

    assert _reload(db_session, reference).status == I.DETECTED

    client.get("/")

    assert _reload(db_session, reference).status == I.IN_ATTENTION


def test_an_inspection_that_only_looks_carries_nothing(db_session):
    """Regarder par-dessus l'épaule ne fait pas d'un sujet un sujet porté. Un écran de
    contrôle qui déplacerait des états en les affichant rendrait toute lecture
    destructrice."""
    from app.perf import week as week_module

    reference = _subject(db_session)

    class Dataset:
        units = ()
        period = "2026-08"

    week_module.read(db_session, "2026-09-01", dataset=Dataset())

    assert _reload(db_session, reference).status == I.DETECTED


def test_a_subject_can_be_arbitrated_by_the_key_it_covers(client, db_session):
    """Une référence est attribuée par machine et ne désigne pas le même sujet sur deux
    postes ; une clé d'observation désigne la même chose partout. Les deux formes valent
    ici comme en ligne de commande."""
    _subject(db_session)

    client.post("/issues/gap_to_plan:Northland/accept", data={
        "decided_by": "Une dirigeante",
        "reason": "Écart accepté",
    }, follow_redirects=True)

    held = memory.load(db_session).holding(("gap_to_plan", "Northland"))
    assert held.status == I.VARIANCE_ACCEPTED


def test_an_unknown_subject_says_so_instead_of_failing(client, db_session):
    response = client.post("/issues/ISS-999/accept", data={
        "decided_by": "Une dirigeante", "reason": "Peu importe",
    }, follow_redirects=True)

    assert response.status_code == 200
    assert "ISS-999" in page_text(response)


def test_the_screen_offers_no_way_to_reopen_a_closed_subject(client, db_session):
    """Rouvrir effacerait la clôture, son motif et sa dernière preuve — et surtout ferait
    d'une rechute une découverte, alors que la répétition est ce que ce registre existe
    pour rendre calculable. Un fait nouveau ouvre un autre sujet, qui déclare celui qu'il
    suit."""
    _subject(db_session)

    page = page_text(client.get("/"))

    assert "/accept" in page and "/close" in page
    assert "reopen" not in page and "rouvrir" not in page.lower()
