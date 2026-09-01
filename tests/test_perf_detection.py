"""Ce que les sources ont le droit de dire, et ce qu'elles n'ont pas le droit de trancher.

La détection est du côté de l'identité, pas de la sélection. Chaque test ci-dessous garde
soit une règle fermée — lisible à voix haute et contestable — soit un refus : ne pas
classer, ne pas conclure qu'un sujet est réglé, ne pas ouvrir un sujet que personne ne
pourrait porter.
"""

from __future__ import annotations

from app.domain import issues as I
from app.perf import detection as D


class _Unit:
    """Une unité de l'écran, réduite à ce que la détection lui demande."""

    def __init__(self, market="Northland", months_below=0, gap=-1000.0,
                 below=True, budget_known=True, grade="ALIGNED", chronic="",
                 not_read="", aggregate=False, period="2026-07"):
        self.market = market
        self.months_below_budget = months_below
        self.is_below_budget = below
        self.budget_known = budget_known
        self.divergence_grade = grade
        self.chronic_plan = chronic
        self.not_read_reason = not_read
        self.is_aggregate = aggregate
        self.period = period
        self._gap = gap

    @property
    def gap_vs_budget(self):
        return self._gap


# ------------------------------------------------------------------ règles fermées


def test_one_bad_month_is_not_a_subject():
    """Un mois qui ouvre un sujet donne un cockpit qui trouve trente marchés chaque lundi
    et n'en suit aucun. La règle est « trois mois consécutifs », et elle se discute — c'est
    ce qu'on attend d'une règle, contre un seuil sur un score qui ne se discute pas."""
    assert D.from_units([_Unit(months_below=1)]) == []
    assert D.from_units([_Unit(months_below=2)]) == []

    seen = D.from_units([_Unit(months_below=3)])
    assert [item.kind for item in seen] == [D.GAP_TO_PLAN]
    assert seen[0].key == (D.GAP_TO_PLAN, "Northland")


def test_a_market_without_a_plan_produces_no_gap():
    """Un plan absent n'est pas un plan à zéro. L'écart vaudrait alors la totalité des
    ventes, et le marché sans plan deviendrait le pire du portefeuille."""
    assert D.from_units([_Unit(months_below=6, budget_known=False)]) == []


def test_an_aggregate_never_opens_a_subject():
    """« Reste du monde » n'a pas d'interlocuteur. Lui ouvrir un sujet donnerait une ligne
    que personne ne peut porter, et elle prendrait la place d'un marché dont quelqu'un
    répond."""
    assert D.from_units([_Unit(months_below=6, aggregate=True)]) == []


def test_three_conditions_on_one_market_are_three_conversations():
    """Un écart qui dure est une question au marché, une donnée qui dérive une question à
    l'entrepôt, un plan que l'historique ne soutient pas une question à la Finance. Les
    fondre en « ce marché va mal » enverrait les trois au même interlocuteur, dont deux
    pour rien."""
    seen = D.from_units([_Unit(months_below=4, grade="UNSTABLE",
                               chronic="le plan demande plus que l'historique n'a livré")])

    assert sorted(item.kind for item in seen) == sorted(
        [D.GAP_TO_PLAN, D.DIVERGENCE, D.PLAN_VS_RECORD])
    assert len({item.key for item in seen}) == 3


def test_an_absence_is_reported_as_a_fact_and_not_as_a_gap():
    """Ce sujet parle de ce qu'on ne sait pas. Le dire avec assurance est exactement ce
    qu'on demande — et le ranger parmi les écarts ferait d'un trou de mesure un problème
    commercial."""
    seen = D.from_units([_Unit(not_read="le canal ne remonte que les ventes")])

    assert [item.kind for item in seen] == [D.NOT_MEASURED]
    assert seen[0].confidence == I.ESTABLISHED
    assert seen[0].amount is None


# ------------------------------------------------------------------------ confiance


def test_a_gap_measured_where_the_two_systems_disagree_is_less_certain():
    """Un écart mesuré là où l'entrepôt et la consolidation ne s'accordent pas est un écart
    dont on ne sait pas encore la taille."""
    aligned = D.from_units([_Unit(months_below=4, grade="ALIGNED")])[0]
    offset = D.from_units([_Unit(months_below=4, grade="OFFSET")])[0]
    unstable = [item for item in D.from_units([_Unit(months_below=4, grade="UNSTABLE")])
                if item.kind == D.GAP_TO_PLAN][0]

    assert aligned.confidence == I.ESTABLISHED
    assert offset.confidence == I.PROBABLE
    assert unstable.confidence == I.UNCERTAIN


def test_a_market_that_was_never_graded_is_uncertain_and_never_established():
    """L'absence qui ressemble à un feu vert. Elle a déjà été payée une fois dans ce
    dépôt : un marché absent du fichier de mesure n'est pas un marché mesuré d'accord."""
    ungraded = D.from_units([_Unit(months_below=4, grade="")])[0]

    assert ungraded.confidence == I.UNCERTAIN


# ------------------------------------------------------------------ une clé, un fait


def test_two_channels_of_one_market_do_not_double_the_evidence():
    """Elles décrivent la même conversation. Les garder toutes les deux gonflerait un sujet
    à mesure qu'un marché a des canaux, sans rien ajouter à ce qu'on en sait."""
    seen = D.from_units([_Unit(market="Northland", months_below=4, gap=-1000.0),
                         _Unit(market="Northland", months_below=5, gap=-800.0)])

    assert len(seen) == 1
    # La première est retenue, la seconde écartée — jamais additionnée : sommer deux
    # montants sans avoir vérifié qu'ils portent la même base est la faute que ce dépôt
    # refuse partout ailleurs.
    assert seen[0].amount == -1000.0


# ----------------------------------------------------------------------- partenaires


class _Line:
    def __init__(self, centre, revenue, note="", withheld=""):
        self.profit_centre = centre
        self.revenue = revenue
        self.note = note
        self.rate_withheld = withheld


class _Partners:
    usable = True

    def __init__(self, unnamed, total, withheld=()):
        self._unnamed = list(unnamed)
        self._total = total
        self._withheld = list(withheld)

    def total(self, base):
        from app.perf import partners as P
        return self._total if base == P.SELL_IN else 0.0

    def unnamed(self, base):
        from app.perf import partners as P
        return self._unnamed if base == P.SELL_IN else []

    def withheld(self):
        return self._withheld


def test_a_nameless_flow_below_one_percent_stays_out():
    """La queue de distribution compte des dizaines de lignes minuscules. Chacune ouvrant
    son sujet, la mémoire se remplirait de bruit et le lecteur cesserait de la lire."""
    read = _Partners([_Line("999AAA", 500.0)], total=100000.0)

    assert D.from_partners(read, "2026-07") == []


def test_a_material_nameless_flow_opens_a_subject_with_its_reason():
    read = _Partners([_Line("999AAA", 20000.0, note="entité facturée un opérateur")],
                     total=100000.0)

    seen = D.from_partners(read, "2026-07")

    assert [item.key for item in seen] == [(D.PARTNER_UNNAMED, "999AAA")]
    assert seen[0].statement == "entité facturée un opérateur"
    assert seen[0].measure == "partners"


def test_a_withheld_rate_is_a_subject_whatever_its_size():
    """Un taux retenu n'est pas un taux manquant : c'est deux définitions rapprochées. Le
    montant en jeu ne dit rien de la gravité du défaut, qui est de méthode."""
    read = _Partners([], total=100000.0,
                     withheld=[_Line("24OCMP002", 12.0, withheld="net hors intervalle")])

    seen = D.from_partners(read, "2026-07")

    assert [item.kind for item in seen] == [D.PARTNER_RATE]
    assert "net hors intervalle" in seen[0].statement


def test_a_rule_never_fires_on_a_line_worth_nothing():
    """Une règle qui se déclenche à zéro euro fabrique du bruit qui a l'air d'un signal.
    La leçon vient d'une autre analyse et coûtait un tiers d'un résultat : une règle de
    profondeur d'achat comptait des sacs cadeaux, gratuits et pris par quinze, et déclarait
    acheteur en gros quiconque emballait ses achats."""
    read = _Partners([], total=100000.0,
                     withheld=[_Line("EMBALLAGE", 0.0, withheld="net hors intervalle"),
                               _Line("24OCMP002", 12.0, withheld="net hors intervalle")])

    seen = D.from_partners(read, "2026-07")

    assert [item.scope for item in seen] == ["24OCMP002"]


def test_an_unusable_file_produces_nothing_rather_than_a_guess():
    class _Broken:
        usable = False

    assert D.from_partners(_Broken(), "2026-07") == []
    assert D.from_partners(None, "2026-07") == []


# ---------------------------------------------------------------- dépôt au registre


def test_the_same_condition_next_month_feeds_the_subject_it_already_opened():
    """Le but de tout l'exercice. Un écart qui dure est un sujet qui dure, pas douze
    découvertes."""
    register = I.Register()

    first = D.post(register, D.from_units([_Unit(months_below=3, period="2026-07")]))
    second = D.post(register, D.from_units([_Unit(months_below=4, period="2026-08")]))

    assert len(first["opened"]) == 1 and first["grew"] == []
    assert second["opened"] == [] and len(second["grew"]) == 1
    assert len(register) == 1
    assert len(register.issues[0].evidence) == 2


def test_a_condition_that_fires_again_after_a_closure_is_reported_as_a_return():
    """La liste qui mérite un œil : elle dit qu'on a déjà cru régler ça."""
    register = I.Register()
    D.post(register, D.from_units([_Unit(months_below=3, period="2026-04")]))
    issue = register.issues[0]
    issue.move_to(I.IN_ATTENTION)
    issue.close(by="Une dirigeante", reason="Cause traitée")

    result = D.post(register, D.from_units([_Unit(months_below=3, period="2026-08")]))

    assert result["opened"] == []
    assert [i.follows for i in result["returning"]] == [issue.issue_id]


def test_a_subject_is_titled_by_its_scope_first():
    """Sans le périmètre en tête, deux marchés en retard depuis des mois s'appellent tous
    les deux « N mois consécutifs sous le plan », et la liste devient illisible à l'endroit
    exact où elle devait servir."""
    register = I.Register()
    D.post(register, D.from_units([_Unit(market="Northland", months_below=3),
                                   _Unit(market="Eastland", months_below=4)]))

    titles = [issue.title for issue in register.issues]
    assert titles == ["Northland · 3 mois consécutifs sous le plan",
                      "Eastland · 4 mois consécutifs sous le plan"]


def test_an_observation_is_always_dated():
    """Une observation sans date est un fait qui ne peut pas vieillir : l'ordre des preuves
    s'effondre, et « vu pour la dernière fois » devient un tiret sur l'écran qui existe
    pour dire depuis quand ça dure."""
    assert D.dated("2026-07", "2026-08", "2026-09-01") == "2026-07"
    assert D.dated("", "2026-08", "2026-09-01") == "2026-08"
    assert D.dated("", "", "2026-09-01") == "2026-09-01"

    undated = _Unit(months_below=3, period="")
    seen = D.from_units([undated], period="", today="2026-09-01")

    assert seen[0].seen_at == "2026-09-01"


def test_a_subject_no_rule_fires_for_is_silent_and_not_resolved():
    """Faire taire un sujet parce qu'il s'est tu une fois transformerait un mois calme en
    problème réglé — la façon la plus discrète de perdre un sujet. Le brief exige deux
    périodes de publication conformes, donc une cadence que ce module ne connaît pas."""
    register = I.Register()
    D.post(register, D.from_units([_Unit(market="Northland", months_below=3)]))

    seen = D.from_units([_Unit(market="Eastland", months_below=3)])
    D.post(register, seen)
    quiet = D.silent(register, seen)

    assert [issue.scopes for issue in quiet] == [["Northland"]]
    assert all(issue.is_open for issue in quiet)
    assert all(issue.status == I.DETECTED for issue in quiet)


def test_a_subject_is_reachable_by_the_key_it_covers():
    """Une référence est attribuée par machine : ISS-004 ne désigne pas le même sujet sur
    deux postes qui n'ont pas lu les sources dans le même ordre. Une clé désigne la même
    chose partout, ce qui rend une instruction transmissible — « enregistrez cette
    décision » cesse d'exiger que le lecteur relise son écran pour trouver le bon numéro.
    """
    from app.cli import _issue_named

    register = I.Register()
    D.post(register, D.from_units([_Unit(market="Northland", months_below=3)]))
    issue = register.issues[0]

    assert _issue_named(register, issue.issue_id) is issue
    assert _issue_named(register, "gap_to_plan:Northland") is issue
    assert _issue_named(register, "gap_to_plan:Eastland") is None
    assert _issue_named(register, "ISS-999") is None
