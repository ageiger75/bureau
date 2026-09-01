"""Ce que les sources ont à dire, avant que quiconque décide si c'est important.

Entre la mémoire et le moteur de sélection il manquait le producteur : le registre tenait
ses règles et n'avait rien à retenir, parce que seul un geste humain pouvait y déposer un
fait. Ce module est ce producteur. Il lit ce que le cockpit lit déjà et rend des
observations avec des clés stables — rien d'autre.

**Il ne classe pas, ne compte pas les créneaux, ne dit pas ce qui est grave.** Le brief
V6.1 construit l'identité avant la sélection, et ce module est du côté de l'identité. Un
détecteur qui trierait déjà aurait tranché la matérialité sans le dire, et le « pourquoi
ce sujet » du §C6 n'aurait plus rien à montrer.

**Chaque détecteur est une règle fermée, nommée, et vraie ou fausse.** Pas un seuil sur un
score : une condition qu'on peut lire à voix haute et contester. « Trois mois consécutifs
sous le plan » se discute ; « au-dessus du 80e centile de gravité » ne se discute pas, il
s'accepte ou se subit. C'est aussi ce qui permet à un détecteur de **cesser de produire**
quand sa condition redevient fausse — un sujet devient silencieux au lieu d'être
« résolu », et c'est le premier pas honnête vers la normalisation.

**La clé porte l'identité, et elle survit aux lectures.** `("gap_to_plan", "Brazil")` est
la même en juillet et en octobre : c'est ce qui fait qu'un écart qui dure est un sujet qui
dure, et non douze découvertes. Le périmètre est le marché et non le couple marché ×
canal : deux canaux d'un même marché appellent le même interlocuteur, donc la même
conversation, et le brief §C7 range la conversation avant la géographie.

Ce module ne touche pas au registre. Il rend des observations ; `Register.observe` décide
si elles rejoignent un sujet ou en ouvrent un, et c'est là que vit la règle.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from ..domain.issues import ESTABLISHED, PROBABLE, UNCERTAIN, Observation

#: Les types d'observation. Ce sont les préfixes des clés, donc ils ne changent jamais
#: sans casser l'identité de tous les sujets ouverts : renommer `gap_to_plan` rouvrirait
#: un jumeau de chaque écart en cours. À traiter comme un schéma, pas comme un libellé.
GAP_TO_PLAN = "gap_to_plan"
DIVERGENCE = "divergence"
PLAN_VS_RECORD = "plan_vs_record"
NOT_MEASURED = "not_measured"
PARTNER_UNNAMED = "partner_unnamed"
PARTNER_RATE = "partner_rate"

#: Trois mois consécutifs sous le plan. En dessous, c'est un mois — et un mois qui ouvre un
#: sujet donne un cockpit qui trouve trente marchés chaque lundi et n'en suit aucun.
PERSISTENT_MONTHS = 3

#: Part d'une base au-delà de laquelle une ligne sans marque commerciale devient un sujet.
#: Un pour cent : assez bas pour que rien de matériel passe, assez haut pour que la queue
#: de distribution — des dizaines de lignes minuscules — n'ouvre pas des dizaines de sujets.
UNNAMED_SHARE = 0.01


def _amount(value: Optional[float]) -> Optional[float]:
    return None if value is None else float(value)


def dated(unit_period: str, fallback: str, today: str) -> str:
    """La date d'une observation, et jamais rien.

    Le mois mesuré quand la source le porte, la période de la lecture sinon, et la date du
    jour en dernier recours. Une observation sans date est un fait qui ne peut pas
    vieillir : l'ordre des preuves d'un sujet s'effondre, et « vu pour la dernière fois »
    devient un tiret sur l'écran qui existe pour dire depuis quand ça dure.
    """
    return unit_period or fallback or today


def from_units(units: Sequence, period: str = "", today: str = "") -> List["Observation"]:
    """Les observations que porte l'écran de performance.

    Trois règles, et chacune décrit une conversation différente. Un écart qui dure est une
    question au marché ; une donnée qui dérive est une question à l'entrepôt ; un plan que
    l'historique ne soutient pas est une question à la Finance. Les fondre en « ce marché
    va mal » enverrait les trois au même interlocuteur, dont deux pour rien.
    """
    seen: List[Observation] = []
    for unit in units:
        if getattr(unit, "is_aggregate", False):
            # Un agrégat n'a pas d'interlocuteur. Lui ouvrir un sujet donnerait une ligne
            # que personne ne peut porter, et elle prendrait la place d'un marché dont
            # quelqu'un répond.
            continue
        market = getattr(unit, "market", "") or ""
        if not market:
            continue
        when = dated(getattr(unit, "period", "") or "", period, today)

        if (getattr(unit, "budget_known", True)
                and getattr(unit, "is_below_budget", False)
                and getattr(unit, "months_below_budget", 0) >= PERSISTENT_MONTHS):
            months = unit.months_below_budget
            seen.append(Observation(
                kind=GAP_TO_PLAN, scope=market, seen_at=when,
                statement="%d mois consécutifs sous le plan" % months,
                amount=_amount(unit.gap_vs_budget),
                # La confiance du fait suit la vitesse à laquelle l'écran a le droit de
                # tourner sur ce marché : un écart mesuré là où les deux systèmes ne
                # s'accordent pas est un écart dont on ne sait pas encore la taille.
                confidence=_confidence_of(getattr(unit, "divergence_grade", "")),
                measure="sales_actual",
            ))

        if getattr(unit, "divergence_grade", "") == "UNSTABLE":
            seen.append(Observation(
                kind=DIVERGENCE, scope=market, seen_at=when,
                statement="l'entrepôt et la consolidation ne s'accordent pas d'un mois "
                          "sur l'autre",
                confidence=ESTABLISHED,
                measure="sales_history",
            ))

        chronic = getattr(unit, "chronic_plan", "") or ""
        if chronic:
            seen.append(Observation(
                kind=PLAN_VS_RECORD, scope=market, seen_at=when,
                statement=chronic,
                amount=_amount(getattr(unit, "gap_vs_budget", None)),
                confidence=ESTABLISHED,
                measure="plan_reference",
            ))

        reason = getattr(unit, "not_read_reason", "") or ""
        if reason:
            seen.append(Observation(
                kind=NOT_MEASURED, scope=market, seen_at=when,
                statement=reason,
                # Une absence est un fait établi sur l'absence, jamais sur le montant :
                # ce sujet parle de ce qu'on ne sait pas, et le dire avec assurance est
                # exactement ce qui est demandé.
                confidence=ESTABLISHED,
                measure="sales_actual",
            ))

    return _deduplicated(seen)


def _confidence_of(grade: str) -> str:
    """La confiance d'un fait, tirée de la vitesse accordée à son marché.

    Trois grades, trois réponses, et la quatrième — un marché non noté — vaut « incertain »
    et non « établi ». Un marché absent du fichier de mesure n'est pas un marché mesuré
    d'accord : c'est le défaut d'absence qui ressemble à un feu vert, et il a déjà été payé
    une fois dans ce dépôt.
    """
    if grade == "ALIGNED":
        return ESTABLISHED
    if grade == "OFFSET":
        return PROBABLE
    return UNCERTAIN


def from_partners(read, period: str, today: str = "") -> List["Observation"]:
    """Ce que le fichier des partenaires signale de lui-même.

    Deux règles, et les deux portent sur ce que la donnée **ne dit pas** plutôt que sur ce
    qu'elle dit. Un montant sans nom de partenaire n'est pas une erreur de lecture, c'est
    un flux que personne ne peut piloter ; un taux retenu n'est pas un taux manquant, c'est
    deux définitions qu'on a rapprochées. Aucun des deux ne se voit dans un total.
    """
    if read is None or not getattr(read, "usable", False):
        return []
    when = dated("", period, today)

    from . import partners as partners_module

    seen: List[Observation] = []
    for base in partners_module.BASES:
        total = read.total(base)
        if not total:
            continue
        for line in read.unnamed(base):
            if abs(line.revenue) < abs(total) * UNNAMED_SHARE:
                continue
            seen.append(Observation(
                kind=PARTNER_UNNAMED, scope=line.profit_centre, seen_at=when,
                statement=line.note or "flux sans marque commerciale attribuable",
                amount=_amount(line.revenue),
                confidence=ESTABLISHED,
                measure="partners",
            ))

    for line in read.withheld():
        if not line.revenue:
            # Une règle qui se déclenche sur une ligne à zéro euro fabrique du bruit qui
            # a l'air d'un signal. La leçon vient d'ailleurs et coûtait un tiers d'un
            # résultat : une règle de profondeur d'achat comptait des sacs cadeaux, gratuits
            # et pris par quinze, et déclarait acheteur en gros quiconque emballait ses
            # achats. Un défaut de méthode sur un flux qui ne vaut rien ne se traite pas.
            continue
        seen.append(Observation(
            kind=PARTNER_RATE, scope=line.profit_centre, seen_at=when,
            statement="taux non calculable : %s" % line.rate_withheld,
            amount=_amount(line.revenue),
            confidence=ESTABLISHED,
            measure="partners",
        ))
    return _deduplicated(seen)


def _deduplicated(seen: Sequence["Observation"]) -> List["Observation"]:
    """Une clé, une observation par passage.

    Deux observations de même clé dans un même passage viendraient de deux canaux d'un même
    marché. Elles décrivent la même conversation ; les garder toutes les deux doublerait la
    preuve sans rien ajouter, et gonflerait un sujet à mesure qu'un marché a des canaux.
    La première est retenue et l'autre écartée plutôt que fusionnée : additionner deux
    montants dont on n'a pas vérifié qu'ils portent la même base est précisément la faute
    que ce dépôt refuse partout ailleurs.
    """
    kept: Dict[tuple, Observation] = {}
    for item in seen:
        if item.key not in kept:
            kept[item.key] = item
    return list(kept.values())


def title_for(item: "Observation") -> str:
    """Le titre d'un sujet naissant : son périmètre, puis ce qu'on a vu.

    Le périmètre en tête et non en suffixe. Sans lui, deux marchés en retard depuis des
    mois s'appellent tous les deux « N mois consécutifs sous le plan » et la liste devient
    illisible à l'endroit exact où elle devait servir. Écrit une fois, à l'ouverture : un
    sujet peut ensuite couvrir d'autres périmètres, et son titre reste celui sous lequel
    il a été cité.
    """
    if not item.statement:
        return "%s · %s" % (item.scope, item.kind)
    return "%s · %s" % (item.scope, item.statement)


def post(register, seen: Sequence["Observation"]) -> Dict[str, List]:
    """Déposer les observations dans le registre, et dire ce qui a été fait de chacune.

    Rend trois listes : les sujets ouverts, ceux qui ont reçu une preuve de plus, et les
    réapparitions — un sujet clos que le même fait vient rouvrir sous une identité neuve.
    La troisième est celle qui mérite un œil : elle dit qu'on a déjà cru régler ça.
    """
    opened: List = []
    grew: List = []
    returning: List = []
    for item in seen:
        known = register.holding(item.key) is not None
        issue = register.observe(item, title=title_for(item))
        if known:
            grew.append(issue)
        elif issue.follows:
            returning.append(issue)
        else:
            opened.append(issue)
    return {"opened": opened, "grew": grew, "returning": returning}


def silent(register, seen: Sequence["Observation"]) -> List:
    """Les sujets ouverts qu'aucune règle n'a fait parler ce passage-ci.

    Rendus, et rien de plus. Le brief autorise la machine à constater la normalisation, et
    exige pour cela un retour à la normale confirmé sur deux périodes de publication —
    donc une cadence, que ce module ne connaît pas. Faire taire un sujet parce qu'il s'est
    tu une fois transformerait un mois calme en problème réglé, ce qui est la façon la plus
    discrète de perdre un sujet.
    """
    firing = {item.key for item in seen}
    return [issue for issue in register.open_issues()
            if issue.covers and not any(key in firing for key in issue.covers)]
