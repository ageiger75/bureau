"""Trois sujets, cinq en surveillance, et le reste en annexe.

Le brief V6.1 §C4 pose un plafond dur et il faut le lire comme une contrainte, pas comme
un réglage : *« si le moteur trouve neuf sujets prioritaires, il regroupe ou hiérarchise,
il n'affiche jamais neuf »*. Un écran qui rend tout ce qu'il a trouvé rend la sélection au
lecteur, c'est-à-dire exactement le travail qu'il venait chercher.

**Le score reste dedans.** §C6 l'exige, et la raison est de confiance, pas d'esthétique :
un « 87 » affiché à côté d'un marché invite à discuter le 87, alors que ce qui se discute
est la matérialité, l'urgence, l'irréversibilité, la fiabilité. Le moteur ordonne avec un
nombre et s'explique avec des mots — les facteurs qui se sont appliqués, nommés un par un.

**Le rôle décide de la porte, pas le classement.** Un créneau d'attention n'accepte que
DECIDE, CHALLENGE et ALIGN. Un sujet MONITOR va en surveillance quelle que soit sa taille :
le plus gros écart du portefeuille, s'il n'appelle aucune intervention du lecteur, n'a rien
à faire dans une liste de trois choses à faire. C'est ce qui empêche l'écran de dériver
vers un palmarès des mauvaises nouvelles.

**Un sujet endormi reste endormi.** Une variance acceptée ne remonte que sur un fait
nouveau postérieur à l'arbitrage, ou à sa date de réexamen. Sans cette règle, arbitrer ne
servirait à rien : le sujet reviendrait le lundi suivant, et le lecteur réarbitrerait, et
ainsi de suite jusqu'à ce qu'il cesse de lire.

Ce module lit le registre et ne le modifie jamais. Il rend un classement ; ce que le
lecteur en fait — porter un sujet en attention, l'arbitrer, le déléguer — passe par le
domaine, qui tient les règles.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from ..domain.issues import (ALIGN, ATTENTION_ROLES, CHALLENGE, DECIDE, DELEGATE,
                             ESTABLISHED, MONITOR, PROBABLE, VARIANCE_ACCEPTED,
                             WATCHED)
from . import detection

#: Ce que chaque règle demande au lecteur, par défaut. Un défaut et non une vérité : le
#: rôle est stocké sur le sujet et un humain le corrige. Écrit ici plutôt que laissé vide
#: parce qu'un sujet sans rôle tombe en surveillance, et qu'un écart qui dure depuis
#: quatre mois rangé en veille est une façon polie de ne rien faire.
ROLE_FOR: Dict[str, str] = {
    #: Un écart qui dure appelle une conversation avec celui qui en répond.
    detection.GAP_TO_PLAN: CHALLENGE,
    #: Un plan que l'historique ne soutient pas oppose deux lectures d'une même référence.
    #: Ce n'est pas une contestation, c'est un désaccord à trancher entre deux fonctions.
    detection.PLAN_VS_RECORD: ALIGN,
    #: Un flux qu'on ne sait pas nommer ne se pilote pas. Tant que personne n'a tranché ce
    #: qu'il est, aucune conversation n'est possible à son sujet — donc une décision.
    detection.PARTNER_UNNAMED: DECIDE,
    #: Les deux suivantes sont des questions à la donnée, pas au lecteur. Elles se suivent
    #: et se corrigent ; les porter en attention prendrait la place d'un sujet de métier.
    detection.DIVERGENCE: MONITOR,
    detection.NOT_MEASURED: MONITOR,
    detection.PARTNER_RATE: MONITOR,
}

#: Plafonds durs du §C4.
ATTENTION_SLOTS = 3
WATCH_SLOTS = 5

#: Les facteurs de matérialité, nommés. Ce sont eux qui s'affichent ; le poids qu'ils
#: portent dans l'ordre reste interne. Les libellés sont ce que le lecteur lira dans
#: « pourquoi ce sujet », donc ils disent le fait et non la catégorie.
MONEY = "montant en jeu"
#: Un flux passe par ce sujet, sans qu'on sache combien est en jeu. Nommé pour que le
#: lecteur voie la matérialité, jamais compté pour ordonner.
FLOW_SEEN = "flux important, enjeu non chiffré"
PERSISTENCE = "dure depuis plusieurs lectures"
REPETITION = "déjà signalé une fois, et revenu"
NO_OWNER = "personne n'en répond"
UNRELIABLE = "la donnée n'est pas sûre"
DUE = "date de réexamen atteinte"
SPREAD = "touche plusieurs périmètres"


class Ranked:
    """Un sujet, sa place, et les mots qui la justifient."""

    __slots__ = ("issue", "role", "factors", "weight", "_score")

    def __init__(self, issue, role: str, factors: Sequence[str], weight: float,
                 score: float) -> None:
        self.issue = issue
        self.role = role
        #: Les facteurs qui se sont appliqués, dans l'ordre où on les lit.
        self.factors = list(factors)
        #: Le poids stratégique du périmètre. Affichable : c'est un jugement écrit par le
        #: lecteur dans un fichier qu'il tient, pas une sortie de modèle.
        self.weight = weight
        self._score = score

    @property
    def why(self) -> str:
        """« Pourquoi ce sujet », en une phrase, sans nombre inventé."""
        return " · ".join(self.factors) if self.factors else "aucun facteur particulier"


class Week:
    """Ce que la lecture propose : trois interventions, cinq veilles, le reste en annexe."""

    __slots__ = ("attention", "watch", "annex", "sleeping", "weights_read")

    def __init__(self, attention, watch, annex, sleeping, weights_read: bool) -> None:
        self.attention = list(attention)
        self.watch = list(watch)
        self.annex = list(annex)
        #: Les sujets arbitrés qui dorment. Comptés, jamais montrés parmi les vivants :
        #: leur nombre dit ce que le lecteur a déjà écarté, et c'est une information.
        self.sleeping = list(sleeping)
        #: Faux quand le fichier de poids est absent. Le moteur tourne quand même, et le
        #: dit — tous les périmètres pèsent alors pareil, et le classement redevient un
        #: classement par taille, ce que le lecteur doit savoir avant de le lire.
        self.weights_read = weights_read

    @property
    def considered(self) -> int:
        return len(self.attention) + len(self.watch) + len(self.annex)


def assign_owners(register, org, markets=(), directory=None) -> int:
    """Donner à chaque sujet de marché le MD qui en répond, quand la source le place.

    Sans cette étape, « personne n'en répond » se déclenchait sur tous les sujets à la
    fois : un facteur qui s'applique partout n'ordonne rien et ne dit rien, il ajoute une
    ligne à chaque explication. Un facteur ne vaut que par les sujets où il **ne** vaut
    pas.

    Les sujets qui ne portent pas un marché — un centre de profit, un code magasin — ne
    reçoivent rien, et c'est la bonne réponse : personne ne répond du seau de canal, et
    c'est précisément ce qu'il faut voir.

    Rend le nombre de sujets nouvellement rattachés.
    """
    from . import perimeter as perimeter_module

    scopes = list(markets) or _scopes_of(register)
    placed = {}
    if org is not None and getattr(org, "usable", False):
        placed = perimeter_module.place(org, scopes)
    given = 0
    for issue in register.open_issues():
        if issue.accountable:
            continue
        for scope in issue.scopes:
            name = placed.get(scope)
            lead = org.lead_for(name) if (name and org is not None) else None
            who = lead.name if lead is not None else ""
            # L'annuaire nomme chaque pays avec son MD ; l'organigramme nomme des zones.
            # Quand la zone ne s'ouvre pas, le pays répond quand même — par l'annuaire.
            if not who and directory is not None and len(directory):
                entry = directory.entry_for(scope)
                who = entry.name if entry is not None else ""
            if who:
                issue.accountable = who
                given += 1
                break
    return given


def _scopes_of(register) -> List[str]:
    seen: List[str] = []
    for issue in register.open_issues():
        for scope in issue.scopes:
            if scope not in seen:
                seen.append(scope)
    return seen


def role_of(issue) -> str:
    """Le rôle porté par le sujet, ou celui que ses règles proposent.

    Le sujet gagne, toujours : un humain qui a écrit DELEGATE ne veut pas qu'une règle le
    rende à CHALLENGE la semaine suivante. Le défaut ne sert qu'au sujet que personne n'a
    encore qualifié.
    """
    if issue.role and issue.role != MONITOR:
        return issue.role
    proposed = [ROLE_FOR.get(kind, MONITOR) for kind, _scope in issue.covers]
    for wanted in (DECIDE, CHALLENGE, ALIGN, DELEGATE):
        if wanted in proposed:
            return wanted
    return MONITOR


def awake(issue, today: str) -> bool:
    """Un sujet arbitré dort-il encore ?

    Deux réveils, et pas un de plus : une preuve postérieure à l'arbitrage, ou la date de
    réexamen atteinte. Le premier est ce que « fait nouveau » veut dire concrètement — une
    preuve d'avant la décision n'est pas nouvelle, elle est ce sur quoi la décision a été
    prise.
    """
    if issue.status != VARIANCE_ACCEPTED:
        return True
    arbitration = issue.arbitration
    if arbitration is None:
        return True
    if arbitration.review_on and arbitration.review_on <= today:
        return True
    return any(item.seen_at > arbitration.at for item in issue.evidence)


def _stake(issue) -> bool:
    """Le dernier montant porté par ce sujet est-il un enjeu comparable ?

    Faux quand la preuve ne le dit pas : un montant dont on ignore le sens ne peut pas
    décider de l'ordre du jour d'un lecteur, et le supposer comparable est précisément la
    faute qu'on ferme ici.
    """
    from ..domain import issues as domain

    for observation in reversed(issue.evidence):
        if observation.amount:
            return observation.basis == domain.STAKE
    return False


def _latest_amount(issue) -> Optional[float]:
    """Le montant de la preuve la plus récente qui en porte un.

    La plus récente et non la plus grosse : un sujet se juge sur ce qu'il coûte
    aujourd'hui, et prendre le maximum historique le laisserait haut dans le classement
    longtemps après s'être refermé.
    """
    for item in reversed(issue.evidence):
        if item.amount is not None:
            return item.amount
    return None


def factors_of(issue, today: str, weight: float) -> Tuple[List[str], float]:
    """Les facteurs qui s'appliquent, et l'ordre interne qu'ils produisent.

    Le nombre rendu ici ne sort jamais du module. Il sert à trancher entre deux sujets, ce
    qu'il faut bien faire pour n'en garder que trois ; les mots servent à l'expliquer.
    """
    factors: List[str] = []
    amount = _latest_amount(issue)
    money = abs(amount) if amount else 0.0
    # Seul un enjeu ordonne. Un flux — le chiffre d'affaires d'un partenaire qu'on ne sait
    # pas nommer — est matériel et souvent le plus gros nombre de l'écran, mais il n'est pas
    # comparable à un écart au plan : un flux vaut structurellement dix à cent fois un
    # écart, et le classer sur le même axe le met devant tous les marchés, à jamais. Le
    # défaut était réel et occupait le premier créneau. Le montant reste affiché ; ce qu'il
    # perd, c'est le droit de décider de la semaine.
    if money and _stake(issue):
        factors.append(MONEY)
    else:
        if money:
            factors.append(FLOW_SEEN)
        money = 0.0

    #: La matérialité au-delà des euros (§C8). Chaque facteur multiplie plutôt qu'il
    #: n'additionne : deux faiblesses sur le même sujet se composent — un écart qui dure
    #: *et* dont personne ne répond est pire que la somme des deux séparément.
    score = max(money, 1.0) * max(weight, 0.1)

    readings = len(issue.evidence)
    if readings >= 3:
        factors.append(PERSISTENCE)
        score *= 1.5
    if issue.follows:
        factors.append(REPETITION)
        score *= 2.0
    if not issue.accountable:
        factors.append(NO_OWNER)
        score *= 1.3
    if issue.confidence not in (ESTABLISHED, PROBABLE):
        # Une fiabilité rompue monte, elle ne descend pas : un chiffre dont on n'est pas
        # sûr est un sujet, et l'écarter pour cette raison reviendrait à ne jamais
        # regarder ce qu'on mesure mal.
        factors.append(UNRELIABLE)
        score *= 1.2
    if len(issue.scopes) > 1:
        factors.append(SPREAD)
        score *= 1.2
    arbitration = issue.arbitration
    if arbitration is not None and arbitration.review_on and arbitration.review_on <= today:
        factors.append(DUE)
        score *= 3.0
    return factors, score


def rank(register, today: str, weights=None) -> "Week":
    """Classer ce que la mémoire porte, et le couper aux plafonds du brief.

    Les sujets endormis sortent avant tout classement plutôt qu'en fin de liste : un sujet
    arbitré n'est pas un sujet de rang faible, c'est un sujet que le lecteur a écarté, et
    le laisser concourir le ferait revenir dès qu'un autre se referme.
    """
    ranked: List[Ranked] = []
    sleeping: List = []

    for issue in register.open_issues():
        if not awake(issue, today):
            sleeping.append(issue)
            continue
        scope = issue.scopes[0] if issue.scopes else ""
        weight = weights.weight_for(scope) if weights is not None else 1.0
        factors, score = factors_of(issue, today, weight)
        ranked.append(Ranked(issue, role_of(issue), factors, weight, score))

    ranked.sort(key=lambda row: row._score, reverse=True)

    attention: List[Ranked] = []
    watch: List[Ranked] = []
    annex: List[Ranked] = []
    for row in ranked:
        # Le rôle décide de la porte avant le classement. Un sujet MONITOR ne prend jamais
        # un créneau d'attention, même premier du classement : une liste de trois choses à
        # faire n'est pas un palmarès des mauvaises nouvelles.
        eligible = row.role in ATTENTION_ROLES or (
            row.role == DELEGATE and row.issue.status != WATCHED)
        if eligible and len(attention) < ATTENTION_SLOTS:
            attention.append(row)
        elif len(watch) < WATCH_SLOTS:
            watch.append(row)
        else:
            annex.append(row)

    return Week(attention, watch, annex, sleeping,
                weights_read=weights is not None and getattr(weights, "usable", True))
