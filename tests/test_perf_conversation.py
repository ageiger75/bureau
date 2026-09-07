"""Trois conversations préparées, pas huit fiches.

Les fiches disaient toutes « montant en jeu · dure depuis plusieurs lectures » — vrai, et
inutile pour un appel. Ces tests gardent ce qu'une conversation doit porter : l'écart et
ses canaux, le sens sur les derniers mois, ce qui est déjà engagé, une seule question dans
un ordre qui se lit à voix haute — et ce qu'elle ne doit jamais faire : inventer une ligne
quand la source manque.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.domain import issues as I
from app.perf import conversation as C
from app.perf import detection as D
from app.perf import selection as S
from app.perf.analytics import format_eur


def _issue(reference="ISS-001", scope="Northland", amount=-1000.0, owner="Une dirigeante",
           readings=1):
    issue = I.Issue(issue_id=reference, title="%s · écart" % scope, accountable=owner)
    for index in range(readings):
        issue.record(I.Observation(kind=D.GAP_TO_PLAN, scope=scope,
                                   seen_at="2026-0%d-01" % (index + 4), amount=amount,
                                   basis=I.STAKE, statement="%d mois consécutifs sous le plan"
                                   % (index + 3)))
    return issue


def _unit(channel, gap, history, months=3):
    return SimpleNamespace(market="Northland", channel_label=channel, gap_vs_budget=gap,
                           gap_history=tuple(history), months_below_budget=months,
                           is_aggregate=False, budget_known=True)


class _Dataset:
    def __init__(self, units):
        self.units = units

    def by_market(self):
        grouped = {}
        for unit in self.units:
            grouped.setdefault(unit.market, []).append(unit)
        return grouped


def _week(issues):
    register = I.Register(list(issues))
    return S.rank(register, "2026-09-01")


def test_the_gap_names_its_channels_and_the_trend_names_its_direction():
    """Un écart de marché est la somme de ses canaux, et la tendance additionne leurs
    mois — alignés par la fin, pour qu'un canal à l'historique plus court ne compte jamais
    pour zéro sur les mois qu'il n'a pas."""
    units = [_unit("E-commerce", -1200.0, (-410.0, -780.0, -1200.0)),
             _unit("Retail", -700.0, (-450.0, -700.0), months=2)]
    prepared = C.build(_week([_issue()]), dataset=_Dataset(units))

    talk = prepared.conversations[0]
    assert talk.gap == -1900.0
    assert talk.stake.startswith("%s sous le plan ce mois, 3 mois consécutifs" % format_eur(1900.0))
    assert "E-commerce %s" % format_eur(-1200.0) in talk.stake
    assert "Retail %s" % format_eur(-700.0) in talk.stake
    assert talk.series == [-410.0, -1230.0, -1900.0]
    assert talk.direction == C.WIDENING
    assert talk.trend.startswith("l'écart se creuse")


def test_a_closing_gap_and_a_steady_one_are_told_apart_from_noise():
    assert C._direction([-1000.0, -800.0, -500.0]) == C.CLOSING
    assert C._direction([-1000.0, -1010.0, -990.0]) == C.STEADY
    assert C._direction([-1000.0]) == ""


def test_the_question_puts_a_late_commitment_before_the_levers():
    """La promesse déjà faite passe avant la décomposition : un engagement en retard est
    la première chose à demander, et la question des leviers vient sinon."""
    fire = SimpleNamespace(unit=SimpleNamespace(market="Northland"), gap=-1200.0,
                           diagnosis="Environ la moitié de l'écart vient de la conversion.",
                           question="La conversion baisse : qu'est-ce qui a changé en magasin ?")
    late = SimpleNamespace(market="Northland", status="open", action="Relancer le plan",
                           owner_name="Une dirigeante", due_date="2026-08-31", days_left=-6)

    with_commitment = C.build(_week([_issue()]), fires=[fire], commitments=[late])
    talk = with_commitment.conversations[0]
    assert talk.question.startswith("L'engagement « Relancer le plan » était dû le 31 août 2026")
    assert "en retard de 6 jours" in talk.engaged

    without = C.build(_week([_issue()]), fires=[fire]).conversations[0]
    assert without.question == fire.question
    assert without.diagnosis == fire.diagnosis

    blocked = SimpleNamespace(market="Northland", status="blocked", action="Relancer le plan",
                              owner_name="", due_date=None, days_left=None)
    stuck = C.build(_week([_issue()]), commitments=[blocked]).conversations[0]
    assert stuck.question.startswith("L'engagement « Relancer le plan » est bloqué")


def test_without_any_source_the_lines_stay_empty_rather_than_invented():
    """Une conversation préparée sur des chiffres devinés est pire qu'une fiche muette."""
    talk = C.build(_week([_issue(readings=3)])).conversations[0]

    assert talk.gap == -1000.0                     # la dernière preuve, faute de lecture
    assert talk.trend == ""
    assert talk.diagnosis == ""
    assert talk.engaged == ""
    assert talk.ahead == ""
    assert talk.last_reading == ""
    assert "qui tranche" in talk.question or "engagé" in talk.question
    assert talk.retained_for == talk.row.why


def test_the_last_reading_and_the_kpis_and_the_calendar_reach_the_conversation():
    issue = _issue()
    issue.reinterpret("Trois magasins mal codés", at="2026-08-15")
    kpi = SimpleNamespace(scope="Northland", label="Nouveaux clients", status="alert")
    event = SimpleNamespace(market="Northland", name="Fête des mères", when="du 1 au 7 mai",
                            weight="non pesé")
    gifting = SimpleNamespace(groups=[SimpleNamespace(events=[event])], loose=None)

    talk = C.build(_week([issue]), kpis=[kpi], gifting=gifting).conversations[0]

    assert talk.last_reading == "Trois magasins mal codés (15 août 2026)"
    assert talk.engaged == "côté clients, Nouveaux clients en alerte"
    assert talk.ahead == "Fête des mères du 1 au 7 mai : non pesé"


def test_a_watched_subject_is_one_line_with_who_and_the_next_date():
    # Une question à la donnée : le moteur la range en surveillance, jamais en attention.
    watched = I.Issue(issue_id="ISS-002", title="Eastland · divergence", accountable="")
    watched.record(I.Observation(kind=D.DIVERGENCE, scope="Eastland", seen_at="2026-08-01",
                                 amount=-500.0, basis=I.STAKE,
                                 statement="l'entrepôt et la consolidation ne s'accordent pas"))
    # Arbitré avec une date de réexamen déjà atteinte : le sujet est réveillé, et la ligne
    # porte la date qui l'a réveillé.
    watched.accept_variance(I.Arbitration(decided_by="Une dirigeante", at="2026-08-01",
                                          reason="Fermeture connue", review_on="2026-08-15"))
    prepared = C.build(_week([_issue(), watched]))

    assert [item.issue.issue_id for item in prepared.watch] == ["ISS-002"]
    line = prepared.watch[0].line
    assert format_eur(-500.0) in line
    assert "personne n'en répond" in line
    assert "réexamen le 15 août 2026" in line


def test_the_role_is_read_aloud_in_french():
    talk = C.build(_week([_issue()])).conversations[0]
    assert talk.role == "Challenger"
    assert C.ROLE_WORDS[I.DECIDE] == "Décider"


def test_dates_and_months_are_written_in_french():
    assert C.date_fr("2026-11-30") == "30 novembre 2026"
    assert C.date_fr("n'importe quoi") == "n'importe quoi"
    assert C.month_fr("2026-08") == "août 2026"


def test_the_stake_opens_on_the_fiscal_year_to_date_when_the_units_carry_it():
    """Le lecteur lit l'exercice dans la table juste au-dessus : la conversation le dit
    d'abord, le mois ensuite."""
    units = [_unit("E-commerce", -1200.0, (-410.0, -780.0, -1200.0)),
             _unit("Retail", -700.0, (-450.0, -700.0), months=2)]
    units[0].gap_year_to_date = -4000.0
    units[1].gap_year_to_date = -2300.0
    talk = C.build(_week([_issue()]), dataset=_Dataset(units)).conversations[0]

    assert talk.year_gap == -6300.0
    assert talk.stake.startswith("%s sous le plan sur l'exercice à date, %s sous le plan ce mois"
                                 % (format_eur(6300.0), format_eur(1900.0)))



def test_the_watch_line_counts_months_like_the_detection_and_says_the_year_first():
    """Un sujet ouvert pour « 3 mois consécutifs » ne peut pas être suivi en « 2 mois » :
    la ligne compte comme la détection, sur le marché somme de ses canaux."""
    watched = I.Issue(issue_id="ISS-002", title="Northland · divergence", accountable="")
    watched.record(I.Observation(kind=D.DIVERGENCE, scope="Northland", seen_at="2026-08-01",
                                 amount=-500.0, basis=I.STAKE))
    units = [_unit("E-commerce", -1200.0, (-410.0, -780.0, -1200.0), months=2),
             _unit("Retail", -700.0, (-450.0, -700.0), months=5)]
    units[0].gap_year_to_date = -4000.0
    units[1].gap_year_to_date = -2300.0
    line = C.build(_week([watched]), dataset=_Dataset(units)).watch[0]

    assert line.months == 5
    assert line.line.startswith("%s sur l'exercice · %s ce mois · 5 mois sous le plan"
                                % (format_eur(-6300.0), format_eur(-1900.0)))
