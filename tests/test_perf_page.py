"""Une page par périmètre — B1. Le même squelette pour tous, filtré sur les marchés du MD.

Ces tests gardent l'atterrissage, qui est un calcul à deux hypothèses et jamais une
prévision, et le filtrage : un sujet ou un feu d'un autre périmètre n'apparaît pas.
Toutes les valeurs sont inventées.
"""

from __future__ import annotations

from app.perf import actuals, page as P


class _Line:
    def __init__(self, market, period, budget, last_year=None):
        self.market, self.period, self.budget, self.last_year = market, period, budget, last_year


class _Budget:
    def __init__(self, lines):
        self.lines = lines


def _published(lines):
    return actuals.Actuals(lines, [], year=2026, month=8)


def _pl(market, actual, budget, last_year=0.0):
    return actuals.Line(market, "R", "retail", actuals.SOLD, actual, last_year, budget)


def test_slugs_are_ascii_and_stable():
    assert P.slug("Greater China") == "greater-china"
    assert P.slug("Japon") == "japon"
    assert P.slug("Amérique du Nord") == "amerique-du-nord"


def test_the_landing_reads_two_hypotheses_and_calls_neither_a_forecast():
    """Cinq mois clos à 95 % du plan, sept mois de plan devant. Si le reste tient le
    plan, l'année manque de ce que les mois clos ont manqué ; à ce rythme, elle manque
    5 % de tout."""
    budget = _Budget([_Line("Northland", "2026-%02d" % m, 100.0) for m in range(4, 13)]
                     + [_Line("Northland", "2027-%02d" % m, 100.0) for m in range(1, 4)]
                     + [_Line("Southland", "2026-05", 999.0)])
    published = _published([_pl("Northland", 475.0, 500.0)])
    land = P.landing(["Northland"], published, budget, "2026-09", "2026-08")

    assert land.usable
    assert land.full_plan == 1200.0
    assert land.months_left == 7
    assert abs(land.at_plan - (475.0 + 700.0)) < 1e-9
    assert abs(land.gap_at_plan - (-25.0)) < 1e-9
    assert abs(land.at_pace - (475.0 + 700.0 * 0.95)) < 1e-9
    assert abs(land.gap_at_pace - (-60.0)) < 1e-9
    assert land.pace_label == "-5.0 %"


def test_the_weighted_landing_lets_the_remaining_months_weigh_what_they_weighed():
    """Cinq mois clos à +10 % sur l'an dernier et à 95 % d'un plan plat ; l'an dernier des
    sept mois restants est lourd (la saison). À ce rythme sur le plan, l'année manque ; à
    la croissance tenue, elle dépasse — et l'écart entre les deux est le phasage."""
    budget = _Budget([_Line("Northland", "2026-%02d" % m, 100.0, 80.0) for m in range(4, 9)]
                     + [_Line("Northland", "2026-%02d" % m, 100.0, 120.0) for m in range(9, 13)]
                     + [_Line("Northland", "2027-%02d" % m, 100.0, 120.0) for m in range(1, 4)])
    published = _published([_pl("Northland", 440.0, 500.0, 400.0)])
    land = P.landing(["Northland"], published, budget, "2026-09", "2026-08")

    assert land.weighted_usable and land.growth_label == "+10.0 %"
    assert land.remaining_last_year == 840.0
    assert abs(land.at_growth - (440.0 + 840.0 * 1.1)) < 1e-9
    assert abs(land.at_pace - (440.0 + 700.0 * 0.88)) < 1e-9
    assert land.low == land.at_pace and land.high == land.at_growth
    assert abs(land.phasing_gap - (land.at_growth - land.at_pace)) < 1e-9
    assert land.moved_events == []


def test_without_last_year_the_landing_keeps_its_two_hypotheses_and_no_range():
    budget = _Budget([_Line("Northland", "2026-%02d" % m, 100.0) for m in range(4, 13)])
    land = P.landing(["Northland"], _published([_pl("Northland", 475.0, 500.0)]), budget, "2026-09", "2026-08")
    assert not land.weighted_usable and land.low == land.at_pace == land.high


def test_a_moved_weighed_event_in_the_remaining_months_is_named_never_weighted():
    import datetime

    class _Event:
        def __init__(self, name, market, start, measured_on, share):
            self.name, self.market, self.start, self.measured_on, self.share = name, market, start, measured_on, share

    class _Calendar:
        events = [
            _Event("Fête mobile", "Northland", datetime.date(2026, 11, 3), "2025-10-28..2025-10-30", 0.31),
            _Event("Fête fixe", "Northland", datetime.date(2026, 12, 25), "2025-12-25..2025-12-26", 0.4),
            _Event("Ailleurs", "Southland", datetime.date(2026, 11, 3), "2025-10-28..2025-10-30", 0.5),
            _Event("Petite", "Northland", datetime.date(2026, 10, 3), "2025-09-28..2025-09-30", None),
        ]

    moved = P.moved_events(_Calendar(), ["Northland"], ["2026-09", "2026-10", "2026-11", "2026-12"])
    assert moved == ["Fête mobile en novembre (octobre l'an dernier) : Northland 31 % du mois",
                     "Petite en octobre (septembre l'an dernier) : Northland"]
    assert P.moved_events(None, ["Northland"], ["2026-11"]) == []
    # Le groupe voit tous les marchés ; au-delà de cinq, on compte.
    everything = P.moved_events(_Calendar(), None, ["2026-10", "2026-11"])
    assert len(everything) == 3 and everything[0].startswith("Ailleurs en novembre (octobre l'an dernier) : Southland 50 %")


def test_the_landing_is_absent_without_closed_months_or_a_plan():
    assert "mois clos" in P.landing(["Northland"], None, _Budget([]), "2026-09", "").absent
    published = _published([_pl("Northland", 1.0, 1.0)])
    assert "classeur" in P.landing(["Northland"], published, None, "2026-09", "2026-08").absent
    assert "aucun plan" in P.landing(["Elsewhere"], published, _Budget([]), "2026-09",
                                     "2026-08").absent


class _Issue:
    def __init__(self, title, scopes):
        self.title, self.scopes, self.issue_id, self.readings = title, scopes, "ISS-1", []


class _Row:
    def __init__(self, title, scopes):
        self.issue, self.role, self.why = _Issue(title, scopes), "CHALLENGE", "x"


class _Week:
    def __init__(self, attention, watch):
        self.attention, self.watch = attention, watch


class _Unit:
    def __init__(self, market):
        self.market = market


class _Fire:
    def __init__(self, market, question):
        self.unit, self.question, self.gap = _Unit(market), question, -1.0


class _Track:
    period, closed_through, perimeters = "2026-09", "", []


class _Dataset:
    units, period_label, as_of, period = [], "", "", "2026-09"


def test_subjects_and_fires_of_other_perimeters_stay_out():
    week = _Week([_Row("Northland retail slips", ["Northland/retail"]),
                  _Row("Elsewhere", ["Southland"])],
                 [_Row("Watch Northland", ["Northland"])])
    fires = [_Fire("Southland", "why?"), _Fire("Northland", "what moves it?")]
    page = P.build("Nord", "Personne N", ["Northland"], _Dataset(), None, _Track(),
                   week=week, fires=fires)

    assert [row.issue.title for row in page.subjects] == ["Northland retail slips"]
    assert [row.issue.title for row in page.watched] == ["Watch Northland"]
    assert [fire.unit.market for fire in page.fires] == ["Northland"]
    assert page.question == "Northland retail slips"
    assert page.slug == "nord"


def test_the_question_falls_back_to_the_biggest_fire_then_to_the_verdict():
    fires = [_Fire("Northland", "what moves it?")]
    page = P.build("Nord", "", ["Northland"], _Dataset(), None, _Track(), fires=fires)
    assert page.question == "what moves it?"

    empty = P.build("Nord", "", ["Northland"], _Dataset(), None, _Track())
    assert empty.question == ""
    assert any("verdict" in reason for reason in empty.absent)


class _Segment:
    def __init__(self, market, period, segment, budget):
        self.market, self.period, self.segment, self.budget = market, period, segment, budget


class _Billed:
    def __init__(self, current, share):
        self.current, self.share_by_now = current, share


def test_sell_in_and_sell_out_together_read_against_the_plan_at_last_years_shape():
    from app.perf import track

    budget = _Budget([_Segment("Northland", "2026-09", "RET - Retail", 1_000.0),
                      _Segment("Northland", "2026-09", "TRA - Travel retail", 600.0),
                      _Segment("Northland", "2026-09", "DIS - Distributors", 400.0),
                      _Segment("Southland", "2026-09", "DIS - Distributors", 999.0),
                      _Segment("Northland", "2026-08", "DIS - Distributors", 999.0)])
    assert P.sell_in_plan_for(budget, ["Northland"], "2026-09") == 1_000.0

    # Sell-out seul : 440 contre 500 à 580 attendus, en retard. Le sell-in facturé à date
    # est 560 contre 1 000 × 46 % = 460 attendus : ensemble, 1 000 contre 960 à 1 040 — en ligne.
    sell_out = track.Verdict(440.0, 500.0, 580.0, 1.0)
    assert sell_out.label == "en retard"
    together = P.Together(sell_out, _Billed(560.0, 0.46), 1_000.0)
    assert together.usable and together.verdict.label == "en ligne"
    assert abs(together.verdict.actual - 1_000.0) < 1e-9
    assert abs(together.verdict.low - 960.0) < 1e-9 and abs(together.verdict.high - 1_040.0) < 1e-9
    assert "46 % du plan du mois" in together.basis and "jamais par canal" in together.basis

    without_plan = P.Together(sell_out, _Billed(560.0, 0.46), 0.0)
    assert not without_plan.usable and "aucune ligne sell-in" in without_plan.basis
    without_shape = P.Together(sell_out, _Billed(560.0, None), 1_000.0)
    assert not without_shape.usable and "forme de mois" in without_shape.basis


def test_the_question_of_the_day_names_both_words_when_sell_in_flips_the_month():
    from app.perf import track

    class _Scope:
        def __init__(self, month):
            self.month, self.year = month, None

    sell_out = track.Verdict(440.0, 500.0, 580.0, 1.0)
    page = P.Page("Nord", "", ["Northland"], _Scope(sell_out), P.landing([], None, None, "", ""),
                  None, None, [], [], [], [], together=P.Together(sell_out, _Billed(560.0, 0.46), 1_000.0))
    assert page.together.verdict.label == "en ligne" and sell_out.label == "en retard"
    assert page.question.startswith("Sell-out en retard ce mois-ci")
    assert "sell-in compris en ligne" in page.question and "se vend-il en face" in page.question

    same = P.Page("Nord", "", ["Northland"], _Scope(sell_out), P.landing([], None, None, "", ""),
                  None, None, [], [], [], [], together=P.Together(sell_out, _Billed(100.0, 0.46), 1_000.0))
    assert same.together.verdict.label == "en retard"
    assert same.question == "En retard ce mois-ci, sell-in compris, %s : qu'est-ce qui l'explique ?" % same.together.verdict.gap_label


def test_a_perimeter_without_sell_out_reads_its_month_on_sell_in_alone():
    # Une BU de canal, le travel retail : aucun sell-out, un plan sell-in, des factures.
    together = P.Together(None, _Billed(560.0, 0.46), 1_000.0)
    assert together.sell_in_only and together.usable
    assert together.verdict.label == "en avance" and "sell-in seul" in together.basis
    page = P.Page("Canal", "", ["Travel retail Asia"], None, P.landing([], None, None, "", ""),
                  None, None, [], [], [], [], together=together)
    assert page.question.startswith("En avance ce mois-ci sur le sell-in")


def test_the_month_with_sell_in_refuses_a_word_when_the_invoices_do_not_cover_the_perimeter():
    from app.perf import track

    class _Bill:
        def __init__(self, current, last_year_month):
            self.current, self.share_by_now, self.last_year_month = current, 0.9, last_year_month

    sell_out = track.Verdict(440.0, 500.0, 580.0, 1.0)
    # L'an dernier, le plan disait 1 000 de sell-in sur ces lignes ; les factures lues n'en
    # voyaient que 200 : ce périmètre facture hors de la source, le mot serait faux.
    thin = P.Together(sell_out, _Bill(300.0, 200.0), 1_000.0, plan_last_year=1_000.0)
    assert not thin.usable and thin.coverage == 0.2 and "ne couvrent que 20 %" in thin.absent
    # Trois fois l'an dernier du plan : des factures qui sont au plan d'un autre périmètre.
    fat = P.Together(sell_out, _Bill(3_000.0, 3_000.0), 1_000.0, plan_last_year=1_000.0)
    assert not fat.usable and "au plan d'un autre" in fat.absent
    fine = P.Together(sell_out, _Bill(900.0, 950.0), 1_000.0, plan_last_year=1_000.0)
    assert fine.usable and fine.coverage_label == "95 %"
    # Sans an dernier au plan, la couverture ne se juge pas et le mot reste.
    blind = P.Together(sell_out, _Bill(900.0, 950.0), 1_000.0)
    assert blind.usable and blind.coverage is None

    class _Line:
        def __init__(self, market, segment, budget, last_year):
            self.market, self.period, self.segment = market, "2026-09", segment
            self.budget, self.last_year = budget, last_year

    budget = _Budget([_Line("Northland", "DIS - Distributors", 1_000.0, 800.0),
                      _Line("Northland", "RET - Retail", 5_000.0, 4_000.0)])
    assert P.sell_in_plan_lines(budget, ["Northland"], "2026-09") == (1_000.0, 800.0)


def test_the_expected_sell_in_is_last_years_invoices_at_the_plans_pace_when_the_plan_has_a_last_year():
    """Une source qui voyait les trois quarts du sell-in l'an dernier n'est pas sommée d'en
    voir le tout : l'attendu est les factures de l'an dernier à jours ouvrés égaux, au rythme
    du plan sur son an dernier. Sans an dernier au plan, la part du plan facturée l'an dernier."""
    from app.perf import track

    class _Bill:
        current, share_by_now, aligned, last_year_month = 560.0, 0.46, 500.0, 950.0

    sell_out = track.Verdict(440.0, 500.0, 580.0, 1.0)
    paced = P.Together(sell_out, _Bill(), 1_000.0, plan_last_year=800.0)
    assert paced.at_plan_pace and abs(paced.expected_sell_in - 625.0) < 1e-9
    assert paced.plan_growth_label == "+25.0 %"
    assert "au rythme du plan" in paced.basis and "couvrait 119 %" in paced.basis
    shaped = P.Together(sell_out, _Bill(), 1_000.0)
    assert not shaped.at_plan_pace and abs(shaped.expected_sell_in - 460.0) < 1e-9
    assert "46 % du plan du mois" in shaped.basis
