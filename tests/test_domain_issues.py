"""L'identité d'un sujet, et ce que son absence coûterait.

Chaque test défend une règle du brief V6.1 §C, et chacune de ces règles répare un défaut
qui ne se signale pas tout seul : un doublon qui vieillit à côté de son jumeau, une
clôture effacée par une rechute, une conclusion remplacée sans qu'on sache pourquoi. Rien
ici ne sélectionne ni n'ordonne — le moteur vient après, et il viendra sur cette base.
"""

from __future__ import annotations

import pytest

from app.domain import issues as I


def _seen(kind="gap_to_plan", scope="Northland", at="2026-07-31", statement="",
          amount=None, confidence=I.ESTABLISHED):
    return I.Observation(kind=kind, scope=scope, seen_at=at, statement=statement,
                         amount=amount, confidence=confidence)


# --------------------------------------------------------------------------- identité


def test_a_second_reading_of_the_same_fact_joins_the_issue_it_already_has():
    """La règle « aucun issue_id recréé pour un sujet déjà ouvert ».

    Sans elle, chaque lecture hebdomadaire fabrique un jumeau : les deux vieillissent
    séparément, l'engagement pris sur l'un ne solde jamais l'autre, et le lecteur voit
    deux fois le même problème en croyant en voir deux.
    """
    register = I.Register()

    first = register.observe(_seen(at="2026-07-31"))
    second = register.observe(_seen(at="2026-08-31"))

    assert second is first
    assert len(register) == 1
    assert [o.seen_at for o in first.evidence] == ["2026-07-31", "2026-08-31"]


def test_two_different_measures_on_one_market_are_two_subjects():
    """Le périmètre ne fait pas l'identité. Un écart au plan et une donnée qui dérive sur
    le même marché appellent deux conversations, avec deux interlocuteurs possibles."""
    register = I.Register()

    gap = register.observe(_seen(kind="gap_to_plan", scope="Northland"))
    drift = register.observe(_seen(kind="divergence", scope="Northland"))

    assert gap is not drift
    assert len({gap.issue_id, drift.issue_id}) == 2


def test_one_conversation_can_cover_many_markets():
    """Le brief §C7 l'écrit contre l'évidence : l'unité d'un sujet est la décision qu'il
    appelle, pas la géographie. Un produit dégradé sur vingt-six marchés est un sujet — et
    le rattachement est un geste explicite, parce que c'est un jugement que la machine ne
    peut pas rendre à notre place."""
    register = I.Register()
    issue = register.observe(_seen(kind="hero_decline", scope="Northland"))

    register.attach(issue.issue_id, _seen(kind="hero_decline", scope="Eastland"))
    register.attach(issue.issue_id, _seen(kind="hero_decline", scope="Westland"))

    assert len(register) == 1
    assert issue.scopes == ["Northland", "Eastland", "Westland"]
    assert register.holding(("hero_decline", "Eastland")) is issue


def test_a_key_held_by_an_open_issue_cannot_be_given_to_another():
    """Deux sujets ouverts partageant une clé, c'est le doublon sous un autre nom. La
    réparation est la fusion, pas le partage."""
    register = I.Register()
    first = register.observe(_seen(kind="gap_to_plan", scope="Northland"))
    other = register.observe(_seen(kind="gap_to_plan", scope="Eastland"))

    with pytest.raises(I.TransitionRefused) as refused:
        register.attach(other.issue_id, _seen(kind="gap_to_plan", scope="Northland"))

    assert first.issue_id in str(refused.value)


# ---------------------------------------------------------------------------- rechute


def test_a_fact_landing_on_a_closed_issue_opens_a_new_one_that_names_the_old():
    """Rouvrir l'ancien effacerait sa clôture et son motif, que le brief exige de garder ;
    ne rien lier ferait d'une rechute une découverte. Le lien est aussi la seule façon de
    rendre calculable la répétition d'un problème déjà signalé — un critère de matérialité
    du §C8 qu'aucune donnée ne porte."""
    register = I.Register()
    first = register.observe(_seen(at="2026-04-30"))
    first.move_to(I.IN_ATTENTION)
    first.close(by="Une dirigeante", reason="Cause traitée, écart résorbé")

    again = register.observe(_seen(at="2026-08-31"))

    assert again is not first
    assert again.follows == first.issue_id
    assert first.status == I.CLOSED
    assert first.closed_reason == "Cause traitée, écart résorbé"
    assert register.repeated() == [again]


def test_a_closed_issue_refuses_new_evidence():
    register = I.Register()
    issue = register.observe(_seen())
    issue.move_to(I.WATCHED)
    issue.close(by="Une dirigeante", reason="Réglé")

    with pytest.raises(I.TransitionRefused):
        issue.record(_seen(at="2026-09-30"))


def test_an_identifier_is_never_reissued_after_a_closure():
    """Numéroter sur le nombre de sujets vivants redonnerait un numéro déjà porté. Deux
    sujets partageant un identifiant sont pires que deux sujets sans identifiant : un
    compte rendu qui cite ISS-002 devient impossible à relire."""
    register = I.Register()
    first = register.observe(_seen(scope="Northland"))
    second = register.observe(_seen(scope="Eastland"))
    second.move_to(I.WATCHED)
    second.close(by="Une dirigeante", reason="Réglé")

    third = register.observe(_seen(scope="Westland"))

    assert len({first.issue_id, second.issue_id, third.issue_id}) == 3
    assert third.issue_id == "ISS-003"


# ----------------------------------------------------------------------------- fusion


def test_merging_keeps_both_identifiers_and_orders_the_history():
    """Le sujet absorbé garde son identifiant : il a pu être cité ailleurs, et un
    identifiant qui disparaît transforme une trace en énigme. Ses preuves rejoignent
    l'autre dans l'ordre du temps, pas dans l'ordre de la fusion."""
    register = I.Register()
    keep = register.observe(_seen(kind="mix", scope="Northland", at="2026-06-30"))
    absorb = register.observe(_seen(kind="mix", scope="Eastland", at="2026-05-31"))

    merged = register.merge(keep.issue_id, absorb.issue_id,
                            because="Même décision, même interlocuteur")

    assert merged is keep
    assert [o.seen_at for o in keep.evidence] == ["2026-05-31", "2026-06-30"]
    assert keep.owns(("mix", "Eastland"))
    assert absorb.status == I.CLOSED
    assert absorb.merged_into == keep.issue_id
    # Une fusion n'est pas une rechute : `follows` regarde le passé, `merged_into` le
    # présent, et les confondre ferait compter un doublon réparé comme un problème répété.
    assert absorb.follows == ""
    assert register.repeated() == []


def test_a_merge_without_a_reason_is_refused():
    register = I.Register()
    keep = register.observe(_seen(scope="Northland"))
    absorb = register.observe(_seen(scope="Eastland"))

    with pytest.raises(ValueError):
        register.merge(keep.issue_id, absorb.issue_id, because="   ")


# ------------------------------------------------------------------------- trois états


def test_the_three_dimensions_move_independently_of_each_other():
    """Le brief §C2 refuse le statut unique, et voici le cas qu'un mot unique perdrait :
    un sujet calme dans son cycle de vie — délégué, suivi — dont le chiffre empire, et
    dont on n'est même pas sûr. Trois faits, trois réponses, aucune ne résume les autres.
    Le rendre « orange » forcerait le lecteur à deviner laquelle il regarde."""
    issue = I.Issue(issue_id="ISS-001", title="Un sujet", status=I.WATCHED,
                    trend=I.WORSENING, progress=I.ON_TRACK, confidence=I.UNCERTAIN)

    assert issue.is_open
    assert issue.trend == I.WORSENING
    assert issue.progress == I.ON_TRACK
    assert issue.confidence == I.UNCERTAIN
    # Le cycle de vie n'est pas la santé : `status` dit où en est le traitement dans le
    # processus, jamais si le sujet va bien. Les confondre est la faute que le §C2 vise.
    assert issue.status not in I.TRENDS


def test_confidence_follows_the_weakest_evidence():
    """Prendre la plus forte ferait passer pour établi un sujet dont la moitié des faits
    sont incertains — l'inverse exact du service rendu."""
    register = I.Register()
    issue = register.observe(_seen(confidence=I.ESTABLISHED))

    register.attach(issue.issue_id,
                    _seen(scope="Eastland", confidence=I.UNCERTAIN))
    register.attach(issue.issue_id,
                    _seen(scope="Westland", confidence=I.PROBABLE))

    assert issue.confidence == I.UNCERTAIN


# ------------------------------------------------------------------------ transitions


def test_the_machine_may_normalise_but_never_close():
    """« Le moteur peut désescalader et constater la normalisation ; la clôture
    managériale est humaine » (§C9). Une clôture sans nom est refusée, et le message dit
    la différence plutôt que de la faire deviner."""
    issue = I.Issue(issue_id="ISS-001", title="Un sujet")
    issue.move_to(I.IN_ATTENTION)
    issue.move_to(I.NORMALIZED)

    with pytest.raises(I.ClosureRefused):
        issue.move_to(I.CLOSED)

    issue.move_to(I.CLOSED, by="Une dirigeante")
    assert issue.status == I.CLOSED


def test_a_normalised_figure_can_degrade_again_before_any_closure():
    issue = I.Issue(issue_id="ISS-001", title="Un sujet", status=I.NORMALIZED)

    issue.move_to(I.IN_ATTENTION)

    assert issue.status == I.IN_ATTENTION


def test_an_illegal_transition_names_the_ones_that_exist():
    issue = I.Issue(issue_id="ISS-001", title="Un sujet")

    with pytest.raises(I.TransitionRefused) as refused:
        issue.move_to(I.NORMALIZED)

    assert I.IN_ATTENTION in str(refused.value)


# --------------------------------------------------------------- variance acceptée


def test_deciding_to_do_nothing_is_a_decision_and_it_is_written_down():
    """Le comportement par défaut de toutes les revues est l'inverse : un sujet regardé et
    laissé passer disparaît sans trace, et resurgit le mois suivant comme s'il était
    neuf."""
    issue = I.Issue(issue_id="ISS-001", title="Un sujet")

    issue.accept_variance(I.Arbitration(
        decided_by="Une dirigeante", at="2026-08-31",
        reason="Effet de calendrier, rattrapage attendu au T3",
        review_on="2026-11-30"))

    assert issue.status == I.VARIANCE_ACCEPTED
    assert issue.arbitration is not None
    assert issue.arbitration.reason.startswith("Effet de calendrier")


def test_an_accepted_variance_without_a_reason_is_refused():
    """Sans raison, le sujet reviendra et personne ne saura pourquoi il avait été écarté —
    ce qui est exactement l'état d'avant."""
    issue = I.Issue(issue_id="ISS-001", title="Un sujet")

    with pytest.raises(ValueError):
        issue.accept_variance(I.Arbitration(
            decided_by="Une dirigeante", at="2026-08-31", reason=""))

    assert issue.status == I.DETECTED


def test_a_sleeping_subject_wakes_on_its_own_review_date():
    """« On accepte l'écart et on revoit en janvier » est une phrase qui ne se produit
    jamais : personne ne tient la liste. Ici quelqu'un la tient."""
    register = I.Register()
    early = register.observe(_seen(scope="Northland"))
    late = register.observe(_seen(scope="Eastland"))
    never = register.observe(_seen(scope="Westland"))

    for issue, when in ((early, "2026-11-30"), (late, "2027-02-28"), (never, None)):
        issue.accept_variance(I.Arbitration(
            decided_by="Une dirigeante", at="2026-08-31", reason="Écart accepté",
            review_on=when))

    assert register.due_for_review("2026-12-01") == [early]
    assert register.due_for_review("2027-03-01") == [early, late]


def test_a_sleeping_subject_also_wakes_on_a_new_fact():
    """L'autre réveil du §C1. Le sujet dort, il ne meurt pas : une preuve nouvelle le
    rejoint sous son identité, sans effacer l'arbitrage qui l'avait endormi."""
    register = I.Register()
    issue = register.observe(_seen(at="2026-08-31"))
    issue.accept_variance(I.Arbitration(
        decided_by="Une dirigeante", at="2026-08-31", reason="Écart accepté"))

    again = register.observe(_seen(at="2026-09-30"))

    assert again is issue
    assert issue.arbitration is not None
    assert len(issue.evidence) == 2


# ------------------------------------------------------- mémoire d'interprétation


def test_a_conclusion_that_replaces_another_says_why():
    """« Une correction de mapping n'efface pas le diagnostic opérationnel antérieur »
    (§C1). Sans le motif, la conclusion précédente reste visible mais inexplicable, et le
    lecteur ne peut pas distinguer une correction de donnée d'un retournement du métier.
    Ce sont deux nouvelles opposées."""
    issue = I.Issue(issue_id="ISS-001", title="Un sujet")
    issue.reinterpret("La demande recule", at="2026-06-30")

    with pytest.raises(ValueError):
        issue.reinterpret("Trois magasins étaient mal codés", at="2026-07-31")

    issue.reinterpret("Trois magasins étaient mal codés", at="2026-07-31",
                      because="Codification réparée à la source en avril")

    assert issue.conclusion == "Trois magasins étaient mal codés"
    assert issue.previous_conclusion == "La demande recule"
    assert issue.readings[-1].because.startswith("Codification réparée")


def test_the_first_conclusion_needs_no_reason():
    issue = I.Issue(issue_id="ISS-001", title="Un sujet")

    issue.reinterpret("La demande recule", at="2026-06-30")

    assert issue.previous_conclusion == ""
