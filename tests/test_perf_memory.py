"""Ce qui doit survivre à un redémarrage, et ce qui n'a pas le droit de bouger.

Sans ces tests, le module se contenterait de « ça revient à peu près pareil ». Or ce qu'on
demande à une mémoire n'est pas d'être approximative : une référence citée dans un compte
rendu doit désigner le même sujet la semaine suivante, une preuve ne doit pas se dupliquer
à chaque sauvegarde, et un sujet endormi doit se réveiller à sa date même si personne n'a
touché à l'application entre-temps.
"""

from __future__ import annotations

import pytest

from app.domain import issues as I
from app.perf import memory


def _seen(kind="gap_to_plan", scope="Northland", at="2026-07-31", **rest):
    return I.Observation(kind=kind, scope=scope, seen_at=at, **rest)


def _round_trip(db_session, register):
    memory.save(db_session, register)
    db_session.commit()
    db_session.expire_all()
    return memory.load(db_session)


def test_a_subject_survives_the_process_that_found_it(db_session):
    """Le seul test qui compte vraiment. Tout le travail d'identité produit une mémoire qui
    dure le temps d'une commande tant que celui-ci échoue."""
    register = I.Register()
    issue = register.observe(_seen(statement="Écart au plan qui ne se referme pas"))
    issue.accountable = "Une dirigeante"
    issue.role = I.CHALLENGE
    issue.trend = I.WORSENING
    issue.progress = I.AT_RISK
    issue.move_to(I.IN_ATTENTION)

    again = _round_trip(db_session, register).of(issue.issue_id)

    assert again is not None
    assert again.title == "Écart au plan qui ne se referme pas"
    assert again.status == I.IN_ATTENTION
    assert again.role == I.CHALLENGE
    assert (again.trend, again.progress) == (I.WORSENING, I.AT_RISK)
    assert again.accountable == "Une dirigeante"


def test_the_reference_of_a_reloaded_subject_never_moves(db_session):
    """Une référence citée dans un compte rendu doit désigner le même sujet la semaine
    suivante. Un identifiant réattribué transforme une trace en énigme."""
    register = I.Register()
    first = register.observe(_seen(scope="Northland"))
    second = register.observe(_seen(scope="Eastland"))
    second.move_to(I.WATCHED)
    second.close(by="Une dirigeante", reason="Réglé")

    reloaded = _round_trip(db_session, register)
    third = reloaded.observe(_seen(scope="Westland"))
    memory.save(db_session, reloaded)
    db_session.commit()

    assert reloaded.of(first.issue_id) is not None
    assert third.issue_id == "ISS-003"
    assert third.issue_id not in (first.issue_id, second.issue_id)


def test_the_identity_rule_still_holds_after_a_reload(db_session):
    """La règle vit dans le domaine, et le rechargement doit la lui rendre intacte. Si
    `covers` ne revenait pas, chaque redémarrage rouvrirait un jumeau de chaque sujet — le
    doublon que tout ce travail existe pour empêcher, déclenché par un redémarrage."""
    register = I.Register()
    issue = register.observe(_seen(kind="hero_decline", scope="Northland"))
    register.attach(issue.issue_id, _seen(kind="hero_decline", scope="Eastland"))

    reloaded = _round_trip(db_session, register)
    same = reloaded.observe(_seen(kind="hero_decline", scope="Eastland", at="2026-08-31"))

    assert same.issue_id == issue.issue_id
    assert len(reloaded) == 1
    assert reloaded.of(issue.issue_id).scopes == ["Northland", "Eastland"]


def test_saving_twice_does_not_double_the_evidence(db_session):
    """Le piège de toute réécriture d'une collection enfant. Une preuve dupliquée ne se
    voit pas : le sujet a l'air plus documenté, et sa dernière lecture est la bonne."""
    register = I.Register()
    issue = register.observe(_seen(at="2026-07-31"))
    register.observe(_seen(at="2026-08-31"))

    memory.save(db_session, register)
    db_session.commit()
    memory.save(db_session, register)
    db_session.commit()
    db_session.expire_all()

    assert len(memory.load(db_session).of(issue.issue_id).evidence) == 2


def test_two_measurements_of_the_same_day_both_survive(db_session):
    """Pourquoi les preuves sont réécrites en entier plutôt que rapprochées une à une :
    une clé naturelle sur une preuve aurait exigé de décider ce qui rend deux preuves
    identiques, et deux mesures du même jour sur le même périmètre existent."""
    register = I.Register()
    issue = register.observe(_seen(at="2026-07-31", statement="première lecture"))
    register.attach(issue.issue_id,
                    _seen(at="2026-07-31", statement="lecture corrigée le même jour"))

    kept = _round_trip(db_session, register).of(issue.issue_id)

    assert [item.statement for item in kept.evidence] == [
        "première lecture", "lecture corrigée le même jour"]


def test_the_order_of_the_evidence_is_the_one_that_was_written(db_session):
    """Trier sur la date au rechargement aurait suffi tant que les preuves arrivent dans
    l'ordre du temps. Une fusion les mêle, et l'histoire changerait de forme sans que rien
    n'ait changé."""
    register = I.Register()
    keep = register.observe(_seen(kind="mix", scope="Northland", at="2026-06-30"))
    absorb = register.observe(_seen(kind="mix", scope="Eastland", at="2026-05-31"))
    register.merge(keep.issue_id, absorb.issue_id, because="Même décision")

    kept = _round_trip(db_session, register).of(keep.issue_id)

    assert [item.seen_at for item in kept.evidence] == ["2026-05-31", "2026-06-30"]


def test_the_memory_of_interpretation_survives_with_its_reasons(db_session):
    """« Une correction de mapping n'efface pas le diagnostic opérationnel antérieur. »
    Une persistance qui ne garderait que la dernière conclusion le ferait, elle, et sans
    rien signaler."""
    register = I.Register()
    issue = register.observe(_seen())
    issue.reinterpret("La demande recule", at="2026-06-30")
    issue.reinterpret("Trois magasins étaient mal codés", at="2026-07-31",
                      because="Codification réparée à la source")

    kept = _round_trip(db_session, register).of(issue.issue_id)

    assert kept.conclusion == "Trois magasins étaient mal codés"
    assert kept.previous_conclusion == "La demande recule"
    assert kept.readings[-1].because == "Codification réparée à la source"


def test_a_sleeping_subject_wakes_at_its_date_after_a_restart(db_session):
    """« On accepte l'écart et on revoit en janvier » ne se produit que si quelqu'un tient
    la liste, et il faut qu'elle survive à l'arrêt du processus qui l'a écrite."""
    register = I.Register()
    issue = register.observe(_seen())
    issue.accept_variance(I.Arbitration(
        decided_by="Une dirigeante", at="2026-08-31",
        reason="Effet de calendrier, rattrapage attendu au trimestre suivant",
        review_on="2026-11-30"))

    reloaded = _round_trip(db_session, register)

    assert reloaded.due_for_review("2026-10-01") == []
    woken = reloaded.due_for_review("2026-12-01")
    assert [i.issue_id for i in woken] == [issue.issue_id]
    assert woken[0].arbitration.reason.startswith("Effet de calendrier")
    assert woken[0].arbitration.decided_by == "Une dirigeante"


def test_a_relapse_keeps_pointing_at_the_subject_it_follows(db_session):
    """Le lien qui rend calculable la répétition d'un problème déjà signalé. Il ne sert à
    rien s'il ne traverse pas le redémarrage : la répétition se compte sur des mois."""
    register = I.Register()
    first = register.observe(_seen(at="2026-04-30"))
    first.move_to(I.IN_ATTENTION)
    first.close(by="Une dirigeante", reason="Cause traitée")
    again = register.observe(_seen(at="2026-08-31"))

    reloaded = _round_trip(db_session, register)

    assert reloaded.of(again.issue_id).follows == first.issue_id
    assert reloaded.of(first.issue_id).closed_reason == "Cause traitée"
    assert [i.issue_id for i in reloaded.repeated()] == [again.issue_id]


def test_an_amount_that_cannot_be_read_comes_back_absent_and_never_zero(db_session):
    """Compté pour rien, un montant illisible ferait d'un sujet matériel un sujet sans
    enjeu — ce qui le sortirait de toute sélection sans que rien ne le dise."""
    register = I.Register()
    issue = register.observe(_seen(amount=1234.5))
    memory.save(db_session, register)
    db_session.commit()
    row = memory.load(db_session)  # relecture pour atteindre la ligne écrite
    assert row.of(issue.issue_id).evidence[0].amount == pytest.approx(1234.5)

    assert memory._amount("") is None
    assert memory._amount("pas un nombre") is None
    assert memory._amount("0") == 0.0
