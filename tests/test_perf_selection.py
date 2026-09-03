"""Trois créneaux, et ce qui n'a pas le droit d'y entrer.

Le plafond du brief n'est pas un réglage : un écran qui rend tout ce qu'il a trouvé rend
la sélection au lecteur, c'est-à-dire exactement le travail qu'il venait chercher. Chaque
test garde soit une contrainte du §C, soit un défaut vu en faisant tourner le moteur sur
de vraies données.
"""

from __future__ import annotations

from app.domain import issues as I
from app.perf import detection as D
from app.perf import selection as S


def _issue(reference="ISS-001", kind=D.GAP_TO_PLAN, scope="Northland", amount=-1000.0,
           readings=1, owner="Une dirigeante", confidence=I.ESTABLISHED, role=""):
    issue = I.Issue(issue_id=reference, title="%s · %s" % (scope, kind),
                    accountable=owner, confidence=confidence)
    if role:
        issue.role = role
        issue.role_set = True
    for index in range(readings):
        issue.record(I.Observation(kind=kind, scope=scope,
                                   seen_at="2026-0%d-01" % (index + 1),
                                   amount=amount, basis=I.STAKE,
                                   confidence=confidence))
    return issue


# ------------------------------------------------------------------------ plafonds


def test_nine_subjects_never_produce_nine_lines():
    """« Si le moteur trouve neuf sujets prioritaires, il regroupe ou hiérarchise, il
    n'affiche jamais neuf » (§C4). Le plafond est dur des deux côtés."""
    register = I.Register([_issue("ISS-%03d" % n, scope="Market%d" % n,
                                  amount=-1000.0 * n) for n in range(1, 10)])

    week = S.rank(register, "2026-09-01")

    assert len(week.attention) == S.ATTENTION_SLOTS
    assert len(week.watch) == S.WATCH_SLOTS
    assert len(week.annex) == 9 - S.ATTENTION_SLOTS - S.WATCH_SLOTS
    assert week.considered == 9


def test_the_biggest_subject_takes_the_first_slot():
    register = I.Register([_issue("ISS-001", scope="Small", amount=-100.0),
                           _issue("ISS-002", scope="Large", amount=-900_000.0)])

    week = S.rank(register, "2026-09-01")

    assert week.attention[0].issue.issue_id == "ISS-002"


# ---------------------------------------------------------------------------- rôles


def test_a_monitor_subject_never_takes_an_attention_slot():
    """Le plus gros écart du portefeuille, s'il n'appelle aucune intervention du lecteur,
    n'a rien à faire dans une liste de trois choses à faire. C'est ce qui empêche l'écran
    de dériver vers un palmarès des mauvaises nouvelles."""
    register = I.Register([
        _issue("ISS-001", kind=D.DIVERGENCE, scope="Huge", amount=-9_000_000.0,
               role=I.MONITOR),
        _issue("ISS-002", scope="Modest", amount=-1000.0),
    ])

    week = S.rank(register, "2026-09-01")

    assert [row.issue.issue_id for row in week.attention] == ["ISS-002"]
    assert [row.issue.issue_id for row in week.watch] == ["ISS-001"]


def test_each_rule_proposes_the_role_its_conversation_needs():
    """Un écart qui dure appelle une conversation, un plan intenable un alignement, un flux
    qu'on ne sait pas nommer une décision. Trois portes différentes."""
    assert S.role_of(_issue(kind=D.GAP_TO_PLAN)) == I.CHALLENGE
    assert S.role_of(_issue(kind=D.PLAN_VS_RECORD)) == I.ALIGN
    assert S.role_of(_issue(kind=D.PARTNER_UNNAMED)) == I.DECIDE
    assert S.role_of(_issue(kind=D.DIVERGENCE)) == I.MONITOR


def test_a_role_a_human_wrote_survives_the_rules():
    """Un humain qui a écrit DELEGATE ne veut pas qu'une règle le rende à CHALLENGE la
    semaine suivante."""
    issue = _issue(kind=D.GAP_TO_PLAN, role=I.DELEGATE)

    assert S.role_of(issue) == I.DELEGATE


# ------------------------------------------------------------------------- sommeil


def test_an_arbitrated_subject_does_not_come_back_the_following_week():
    """Sans cette règle, arbitrer ne servirait à rien : le sujet reviendrait le lundi
    suivant, le lecteur réarbitrerait, et ainsi de suite jusqu'à ce qu'il cesse de lire."""
    issue = _issue()
    issue.accept_variance(I.Arbitration(decided_by="Une dirigeante", at="2026-02-01",
                                        reason="Effet de calendrier"))
    week = S.rank(I.Register([issue]), "2026-09-01")

    assert week.attention == [] and week.watch == []
    assert [i.issue_id for i in week.sleeping] == ["ISS-001"]


def test_a_fact_after_the_arbitration_wakes_it_and_a_fact_before_does_not():
    """« Fait nouveau » veut dire postérieur à la décision. Une preuve d'avant n'est pas
    nouvelle : c'est ce sur quoi la décision a été prise."""
    issue = _issue(readings=2)   # preuves de janvier et février
    issue.accept_variance(I.Arbitration(decided_by="Une dirigeante", at="2026-03-01",
                                        reason="Écart accepté"))
    assert not S.awake(issue, "2026-09-01")

    issue.record(I.Observation(kind=D.GAP_TO_PLAN, scope="Northland", seen_at="2026-04-01"))

    assert S.awake(issue, "2026-09-01")


def test_a_review_date_reached_wakes_the_subject_and_says_so():
    issue = _issue()
    issue.accept_variance(I.Arbitration(decided_by="Une dirigeante", at="2026-02-01",
                                        reason="Écart accepté", review_on="2026-08-31"))

    week = S.rank(I.Register([issue]), "2026-09-01")

    assert week.sleeping == []
    assert S.DUE in week.attention[0].factors


# --------------------------------------------------------------------- explication


def test_the_score_is_never_rendered_and_the_reasons_always_are():
    """§C6. Un « 87 » affiché à côté d'un marché invite à discuter le 87, alors que ce qui
    se discute est la matérialité, l'urgence, la fiabilité."""
    register = I.Register([_issue(readings=4, owner="", confidence=I.UNCERTAIN)])

    row = S.rank(register, "2026-09-01").attention[0]

    assert S.MONEY in row.factors
    assert S.PERSISTENCE in row.factors
    assert S.NO_OWNER in row.factors
    assert S.UNRELIABLE in row.factors
    assert "score" not in row.why.lower()
    assert not any(character.isdigit() for character in row.why)


def test_a_subject_that_already_came_back_once_outweighs_a_bigger_newcomer():
    """La répétition d'un problème déjà signalé est un critère de matérialité au-delà des
    euros (§C8), et il ne se lit dans aucune donnée : il se lit dans la mémoire."""
    returning = _issue("ISS-002", scope="Back", amount=-100_000.0)
    returning.follows = "ISS-001"
    newcomer = _issue("ISS-003", scope="New", amount=-150_000.0)

    week = S.rank(I.Register([newcomer, returning]), "2026-09-01")

    assert week.attention[0].issue.issue_id == "ISS-002"
    assert S.REPETITION in week.attention[0].factors


# ------------------------------------------------------------------ interlocuteurs


def test_a_factor_that_applies_everywhere_is_a_defect_and_owners_fix_it():
    """Vu en faisant tourner le moteur : « personne n'en répond » se déclenchait sur les
    six sujets à la fois. Un facteur qui s'applique partout n'ordonne rien et n'explique
    rien — il ne vaut que par les sujets où il ne vaut pas."""
    from app.perf import perimeter

    org = perimeter.Org([
        perimeter.Person("A", "LEAD", "MD", "Northland", "Northland", perimeter.MD, ""),
        perimeter.Person("B", "GM", "GM", "Northland", "Northland",
                         perimeter.COUNTRY_GM, "A LEAD"),
    ], [])
    register = I.Register([_issue("ISS-001", scope="Northland", owner=""),
                           _issue("ISS-002", scope="999AAAWP", owner="")])

    given = S.assign_owners(register, org)

    assert given == 1
    assert register.of("ISS-001").accountable == "A LEAD"
    # Le sujet du centre de profit reste sans interlocuteur, et c'est la bonne réponse :
    # personne ne répond du seau de canal, et c'est précisément ce qu'il faut voir.
    assert register.of("ISS-002").accountable == ""


def test_the_weights_are_optional_and_their_absence_is_declared():
    """Le moteur tourne sans le fichier de poids, et le dit. Tourner en silence ferait
    passer un classement par taille pour un classement par importance."""
    week = S.rank(I.Register([_issue()]), "2026-09-01", weights=None)

    assert not week.weights_read
    assert week.attention[0].weight == 1.0


def test_a_flow_never_outranks_a_gap_on_the_strength_of_being_bigger():
    """Le défaut, vu à l'écran sur de vraies données : deux règles portent le chiffre
    d'affaires entier d'un partenaire là où les autres portent un écart au plan. Un flux
    vaut structurellement dix à cent fois un écart, donc il occupait le premier créneau
    devant tous les marchés sous plan — et il l'aurait occupé à jamais.

    Les euros restent affichés. Ce qu'ils perdent, c'est le droit de décider de la semaine
    d'un lecteur qui a demandé à voir le plus gros écart au plan."""
    flow = I.Issue(issue_id="ISS-001", title="Un flux qu'on ne sait pas nommer",
                   accountable="Une dirigeante")
    flow.record(I.Observation(kind=D.PARTNER_UNNAMED, scope="999AAAWP",
                              seen_at="2026-08-01", amount=-34_000_000.0, basis=I.FLOW))
    gap = _issue("ISS-002", scope="Northland", amount=-900_000.0)

    week = S.rank(I.Register([flow, gap]), "2026-09-01")

    assert week.attention[0].issue.issue_id == "ISS-002"
    assert S.MONEY in week.attention[0].factors
    assert S.MONEY not in week.attention[1].factors
    assert S.FLOW_SEEN in week.attention[1].factors


def test_an_amount_that_does_not_say_what_it_measures_orders_nothing():
    """Un montant sans sens déclaré n'est pas un enjeu par défaut. Le supposer comparable
    est exactement la faute qu'on ferme ici, et elle serait invisible : le sujet monterait
    en tête sans que rien ne le signale."""
    silent = I.Issue(issue_id="ISS-001", title="Un montant sans base déclarée",
                     accountable="Une dirigeante")
    silent.record(I.Observation(kind="hand_written", scope="Northland",
                                seen_at="2026-08-01", amount=-34_000_000.0))
    gap = _issue("ISS-002", scope="Northland", amount=-900_000.0)

    week = S.rank(I.Register([silent, gap]), "2026-09-01")

    assert week.attention[0].issue.issue_id == "ISS-002"
