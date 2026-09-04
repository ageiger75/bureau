"""Une page par périmètre — B1. Le même squelette pour tous, filtré sur les marchés du MD.

Ces tests gardent l'atterrissage, qui est un calcul à deux hypothèses et jamais une
prévision, et le filtrage : un sujet ou un feu d'un autre périmètre n'apparaît pas.
Toutes les valeurs sont inventées.
"""

from __future__ import annotations

from app.perf import actuals, page as P


class _Line:
    def __init__(self, market, period, budget):
        self.market, self.period, self.budget = market, period, budget


class _Budget:
    def __init__(self, lines):
        self.lines = lines


def _published(lines):
    return actuals.Actuals(lines, [], year=2026, month=8)


def _pl(market, actual, budget):
    return actuals.Line(market, "R", "retail", actuals.SOLD, actual, 0.0, budget)


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
