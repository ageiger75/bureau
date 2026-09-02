"""Les signaux de distribution, et les deux conditions qu'un classement doit tenir.

Ce lecteur est né de trois classements faux d'affilée, et chacun s'était trompé d'une
façon différente. Le premier ordonnait par nombre de signaux déclenchés : il rendait le
palmarès des plus gros magasins du monde, parce que les signaux bâtis sur un maximum ou un
décompte grandissent avec le trafic. Le deuxième ordonnait par ratio d'unités gratuites :
il rendait les plus petits comptes, parce qu'un rapport dont le dénominateur vaut quelques
centaines d'unités explose. Le troisième ordonnait par valeur absolue de marchandise : il
rendait un seul marché, qui portait quatre cinquièmes du total.

Trois erreurs, une seule leçon : **un classement à un critère mesure toujours autre chose
que ce qu'on cherche.** Il faut deux conditions, et elles répondent à deux questions
différentes. *Qui est anormal* — l'entité dépasse la norme de son canal dans son marché.
*Combien ça pèse* — parmi celles-là seulement, on classe en euros. Aucune des deux ne
remplace l'autre, et ce module refuse structurellement d'en appliquer une seule.

Trois autres règles viennent du même parcours.

**Les signaux ne sont pas écrits en dur.** Ils sont découverts par convention : toute
colonne `x` accompagnée d'une colonne `x_norm` est un signal. La liste est passée de six à
sept puis à huit en trois jours ; un lecteur qui les nommait aurait cassé au neuvième, et
plus vraisemblablement se serait tu en n'en lisant que huit.

**Une part dont le dénominateur varie ne se classe pas.** Une entité dont deux signaux
seulement sont calculables affiche 100 % en en déclenchant deux, et coiffe celle qui en a
franchi cinq sur sept. Ce n'est pas un signal, c'est un petit dénominateur.

**Un total dont on ne connaît pas la couverture est un plancher.** Un cinquième des lignes
n'a pas de valeur calculable. Le total qu'on en tire n'est pas faux, il est incomplet — et
la différence disparaît dès qu'on l'affiche sans le dire.

Comme le plan, l'annuaire et les partenaires, la source vit hors du dépôt.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional, Sequence, Tuple

#: Les deux bases, jamais additionnées — la règle vaut ici comme partout ailleurs.
SELL_IN = "sell_in"
SELL_OUT = "sell_out"
BASES = (SELL_IN, SELL_OUT)

#: Ce qu'il faut pour que le fichier dise quelque chose d'utilisable.
REQUIRED = ("base", "market", "entity_id")

#: Suffixe qui fait d'une colonne le seuil d'une autre. C'est toute la convention de
#: découverte : `hero_share` et `hero_share_norm` forment un signal, et le lecteur n'a
#: jamais besoin de savoir ce que « hero » veut dire.
NORM_SUFFIX = "_norm"

#: Les signaux où c'est la valeur **basse** qui s'éloigne de la norme. Vide aujourd'hui, et
#: déclaré quand même : sans cette liste, « au-dessus du seuil » serait une hypothèse
#: implicite, et le jour où un signal s'inverse il se déclencherait à l'envers en silence.
INVERTED: Tuple[str, ...] = ()

#: Part des signaux du fichier qu'une entité doit avoir calculables pour que sa **part**
#: soit comparable à celle d'une autre. Une proportion et non un nombre : le plancher a
#: d'abord été écrit à cinq, pendant que la source portait huit signaux — sur un fichier
#: qui n'en porte que quatre, plus rien n'était classable et le lecteur rendait une liste
#: vide sans rien dire. Un seuil absolu ne survit pas au fichier qui change de forme, et
#: cette source en a changé trois fois en trois jours.
COMPUTABLE_SHARE = 0.6

#: Et jamais moins de deux : une part sur un seul signal vaut zéro ou cent pour cent, ce
#: qui n'est pas une mesure.
MIN_COMPUTABLE = 2

#: Ce qu'une source écrit quand elle n'a pas d'identifiant. Ce ne sont pas des identités :
#: soixante lignes portaient « N/A » dans la vraie source, et la règle de doublon les a
#: toutes rejetées comme des répétitions les unes des autres. Le dépôt connaissait déjà ce
#: défaut — un `any_value` sur une clé « N/A » avait un jour attribué le pool mondial à un
#: seul pays — et le lecteur y est retombé. Une ligne sans identifiant garde sa place ; ce
#: qu'on perd, c'est le droit de la comparer à une autre, pas son existence.
PLACEHOLDER_IDS = ("", "n/a", "na", "-", "—", "null", "none", "#n/a")

#: Part de couverture en dessous de laquelle un montant par marché ne se lit pas comme un
#: montant. Un marché mesuré à zéro pour cent affiche zéro euro, et zéro euro se lit comme
#: « rien à signaler » alors qu'il veut dire « je n'ai pas regardé ».
COVERAGE_FLOOR = 0.5

#: Les canaux qui ne sont pas du retail et ne se comparent pas à lui. Un outlet vend des
#: héros en profondeur à des acheteurs par lots — c'est sa définition, pas une anomalie —
#: et comparé au magasin médian de son marché il sortira toujours en tête. Deux outlets
#: américains et un anglais occupaient le classement pendant que la maison les tenait pour
#: sains ; c'est le groupe témoin qui l'a montré.
#:
#: Séparés et non supprimés : un outlet reste mesuré, contre d'autres outlets. Retirer des
#: lignes d'un fichier pour faire taire un signal est la façon la plus rapide de rendre un
#: détecteur inutile.
OUTLET_MARKERS = ("OUTLET",)

#: Les trois lectures du fichier. `ALL` reste le défaut des fonctions de lecture : changer
#: un défaut change silencieusement ce que tous les appelants existants demandaient.
RETAIL = "retail"
OUTLET = "outlet"
ALL = "all"


def _number(text) -> Optional[float]:
    value = ("%s" % (text or "")).strip().replace(" ", "").replace(" ", "")
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _flag(text) -> bool:
    return ("%s" % (text or "")).strip().lower() in ("1", "true", "vrai", "oui", "yes")


class Entity:
    """Une entité mesurée sur une fenêtre : un compte client, ou un magasin."""

    __slots__ = ("base", "window", "market", "entity_id", "entity_name", "channel",
                 "country_is", "revenue", "values", "norms", "norm_level",
                 "not_computable", "note", "is_internal", "extras")

    def __init__(self, base, window, market, entity_id, entity_name, channel,
                 country_is, revenue, values, norms, norm_level, not_computable,
                 note, is_internal, extras) -> None:
        self.base = base
        self.window = window
        self.market = market
        self.entity_id = entity_id
        self.entity_name = entity_name
        self.channel = channel
        self.country_is = country_is
        self.revenue = revenue
        #: Signal → valeur mesurée. Absente quand la source laisse la cellule vide.
        self.values: Dict[str, Optional[float]] = dict(values)
        #: Signal → seuil de comparaison, tel que la source l'a calculé.
        self.norms: Dict[str, Optional[float]] = dict(norms)
        #: À quel niveau le seuil a été calculé — marché × canal, canal, ou aucun. Un seuil
        #: dont on ignore l'origine est un seuil qu'on ne peut pas contester.
        self.norm_level = norm_level
        self.not_computable = not_computable
        self.note = note
        self.is_internal = is_internal
        #: Les colonnes qui ne sont ni un signal ni une identité — montants, couvertures.
        self.extras: Dict[str, Optional[float]] = dict(extras)

    @property
    def label(self) -> str:
        return self.entity_name or self.entity_id

    @property
    def is_outlet(self) -> bool:
        """Reconnu sur le libellé du canal, en cherchant le mot plutôt qu'en exigeant
        l'égalité : la source écrit « OUTLET » seul ici et « FACTORY OUTLET » ailleurs, et
        une comparaison stricte laisserait le second dans le retail sans rien dire."""
        channel = (self.channel or "").upper()
        return any(marker in channel for marker in OUTLET_MARKERS)

    def computable(self) -> List[str]:
        """Les signaux que la source a su calculer **et** comparer pour cette entité.

        Les deux, pas l'un : une valeur sans seuil ne se juge pas, et un seuil sans valeur
        ne juge rien. Compter l'un des deux ferait passer une mesure incomplète pour un
        signal au repos.
        """
        return [name for name in sorted(self.values)
                if self.values.get(name) is not None and self.norms.get(name) is not None]

    def fired(self) -> List[str]:
        """Les signaux dont l'entité s'écarte de sa norme, dans le sens qui compte."""
        out: List[str] = []
        for name in self.computable():
            value, norm = self.values[name], self.norms[name]
            if (value < norm) if name in INVERTED else (value > norm):
                out.append(name)
        return out

    @property
    def fired_share(self) -> Optional[float]:
        """Part des signaux calculables qui se déclenchent, ou `None`.

        `None` plutôt que zéro quand rien n'est calculable : une entité qu'on n'a pas su
        mesurer n'est pas une entité sage.
        """
        possible = self.computable()
        return (len(self.fired()) / float(len(possible))) if possible else None

    def is_rankable(self, floor: int) -> bool:
        """Une part ne se compare qu'à dénominateur suffisant.

        Une entité dont deux signaux sont calculables affiche 100 % en en déclenchant deux
        et coiffe celle qui en a franchi cinq sur sept. Ce n'est pas un signal, c'est un
        petit dénominateur — et il occupait six des vingt premières places.

        Le plancher est passé en argument plutôt que lu ici : il dépend du nombre de
        signaux que porte le fichier, que l'entité ne connaît pas.
        """
        return len(self.computable()) >= floor

    def distance(self) -> Optional[float]:
        """De combien de fois l'entité dépasse ses seuils, en moyenne sur ceux qu'elle
        franchit.

        Sert à départager deux entités à égalité de signaux : une entité à trois fois son
        seuil sur cinq signaux n'est pas une entité qui les frôle tous. `None` quand rien
        ne se déclenche — l'absence de dépassement n'est pas un dépassement de zéro.
        """
        ratios = []
        for name in self.fired():
            norm = self.norms[name]
            if norm:
                ratios.append(self.values[name] / norm)
        return (sum(ratios) / len(ratios)) if ratios else None

    def amount(self, column: str) -> Optional[float]:
        return self.extras.get(column)


class Distribution:
    """Le fichier lu, ses signaux découverts, et les seuls classements qui tiennent."""

    __slots__ = ("entities", "signals", "columns", "faults", "path")

    def __init__(self, entities, signals, columns, faults, path: str = "") -> None:
        self.entities = list(entities)
        #: Les signaux trouvés dans l'en-tête, par convention et non par liste écrite.
        self.signals = list(signals)
        self.columns = list(columns)
        self.faults = list(faults)
        self.path = path

    def __len__(self) -> int:
        return len(self.entities)

    @property
    def usable(self) -> bool:
        return bool(self.entities) and not self.faults

    @property
    def floor(self) -> int:
        """Combien de signaux calculables une entité doit porter pour être classée par part.

        Calculé sur ce que le fichier offre, jamais posé en dur. Sur huit signaux le
        plancher vaut cinq — ce qui était la valeur écrite à la main ; sur quatre il vaut
        trois. La règle est la même, elle ne dépend plus de la forme du fichier du jour.
        """
        # Arrondi vers le haut, pas au plus proche : « au moins soixante pour cent »
        # veut dire au moins, et un arrondi au plus proche rendrait deux sur quatre —
        # c'est-à-dire la moitié — pour une règle qui en demande trois cinquièmes.
        import math

        wanted = int(math.ceil(COMPUTABLE_SHARE * len(self.signals)))
        return max(MIN_COMPUTABLE, min(wanted, len(self.signals)))

    def of_base(self, base: str, perimeter: str = ALL) -> List["Entity"]:
        """Les entités d'une base, éventuellement d'un seul périmètre.

        Le périmètre est demandé, jamais supposé : `ALL` reste le défaut parce que changer
        un défaut change silencieusement ce que tous les appelants existants demandaient.
        """
        if base not in BASES:
            raise ValueError("Base inconnue : %s. Les deux bases sont %s."
                             % (base, " et ".join(BASES)))
        if perimeter not in (RETAIL, OUTLET, ALL):
            raise ValueError("Périmètre inconnu : %s." % perimeter)
        rows = [item for item in self.entities if item.base == base]
        if perimeter == RETAIL:
            return [item for item in rows if not item.is_outlet]
        if perimeter == OUTLET:
            return [item for item in rows if item.is_outlet]
        return rows

    def markets(self, base: str, perimeter: str = ALL) -> List[str]:
        seen: List[str] = []
        for item in self.of_base(base, perimeter):
            if item.market and item.market not in seen:
                seen.append(item.market)
        return sorted(seen)

    # ------------------------------------------------------------------ couverture

    def coverage(self, base: str, column: str,
                 perimeter: str = ALL) -> Tuple[int, int]:
        """Combien de lignes portent une valeur pour cette colonne, sur combien.

        Rendu comme un couple et non comme un pourcentage : « 4 428 sur 5 636 » se
        conteste, « 78,6 % » s'accepte. Et un total dont on ignore la couverture est un
        plancher, pas une mesure.
        """
        rows = self.of_base(base, perimeter)
        return sum(1 for item in rows if item.amount(column) is not None), len(rows)

    def total(self, base: str, column: str, perimeter: str = ALL) -> float:
        """La somme d'une colonne sur une base. Toujours un plancher — voir `coverage`."""
        return sum(item.amount(column) or 0.0
                   for item in self.of_base(base, perimeter))

    def by_market(self, base: str, column: str,
                  perimeter: str = ALL) -> List[Tuple[str, float, int, int]]:
        """Le montant par marché, avec sa couverture, du plus gros au plus petit.

        C'est la vue qui rend une moyenne mondiale lisible : treize pour cent en moyenne ne
        décrit aucun marché réel quand un seul en porte quatre cinquièmes.

        La couverture voyage **avec** le montant et non à côté, parce que sans elle un
        marché mesuré à zéro pour cent affiche zéro euro — et zéro euro se lit comme « rien
        à signaler » alors qu'il veut dire « je n'ai pas regardé ». Sept marchés sont dans
        ce cas dans la vraie source, dont un qui pèse plus de vingt millions.
        """
        sums: Dict[str, float] = {}
        valued: Dict[str, int] = {}
        rows: Dict[str, int] = {}
        for item in self.of_base(base, perimeter):
            amount = item.amount(column)
            sums[item.market] = sums.get(item.market, 0.0) + (amount or 0.0)
            valued[item.market] = valued.get(item.market, 0) + (1 if amount is not None
                                                                else 0)
            rows[item.market] = rows.get(item.market, 0) + 1
        out = [(market, sums[market], valued[market], rows[market]) for market in sums]
        out.sort(key=lambda row: row[1], reverse=True)
        return out

    @staticmethod
    def measured(valued: int, rows: int) -> bool:
        """Ce montant se lit-il comme un montant, ou comme une absence de mesure ?"""
        return bool(rows) and (valued / float(rows)) >= COVERAGE_FLOOR

    # ------------------------------------------------------------------ classements

    def abnormal(self, base: str, perimeter: str = ALL) -> List["Entity"]:
        """Les entités qui s'écartent de leur propre norme, comptes internes exclus.

        La première des deux conditions, et elle répond à *qui*. Les comptes internes
        restent dans le fichier et sortent du classement : un compte d'échantillons et de
        testeurs a par fonction un volume gratuit énorme, et il remonterait chaque mois
        sans que personne ait rien à en faire.
        """
        return [item for item in self.of_base(base, perimeter)
                if item.fired() and not item.is_internal]

    def by_exposure(self, base: str, column: str,
                    perimeter: str = ALL) -> List["Entity"]:
        """Les entités anormales, classées sur ce qu'elles pèsent en euros.

        Les deux conditions dans l'ordre : anormale d'abord, matérielle ensuite. Classer
        directement sur le montant rendrait le plus gros marché, qu'il soit anormal ou non.
        """
        rows = [item for item in self.abnormal(base, perimeter)
                if item.amount(column) is not None]
        rows.sort(key=lambda item: item.amount(column), reverse=True)
        return rows

    def by_distance(self, base: str, column: str = "", floor: float = 0.0,
                    perimeter: str = ALL) -> List["Entity"]:
        """Les entités anormales, classées sur de combien elles dépassent leurs seuils.

        L'autre lecture, et elle ne recouvre pas la première : elle trouve les petites
        entités très déviantes que le classement en euros n'atteindra jamais. Un plancher
        de matérialité l'accompagne pour la même raison inverse — sans lui elle rendrait
        les plus petites, ce qui était le deuxième classement faux.
        """
        # Deux planchers, et ils ne mesurent pas la même chose : l'un compte des signaux,
        # l'autre des euros. La première version les appelait tous les deux `floor` et le
        # second écrasait le premier dès la première ligne — le plancher de matérialité
        # était donc inopérant, ce qui a laissé remonter une entité à deux mille fois ses
        # seuils pour deux cent trente-six euros.
        enough_signals = self.floor
        rows = [item for item in self.abnormal(base, perimeter)
                if item.is_rankable(enough_signals) and item.distance() is not None]
        if floor:
            rows = [item for item in rows
                    if ((item.amount(column) if column else item.revenue) or 0.0) >= floor]
        rows.sort(key=lambda item: item.distance(), reverse=True)
        return rows

    def unrankable(self, base: str, perimeter: str = ALL) -> List["Entity"]:
        """Les entités écartées faute de signaux calculables en nombre suffisant.

        Rendues plutôt que tues. Elles sont la trace des marchés trop petits pour porter
        un seuil, et les compter dit quelle part du monde le détecteur ne juge pas.
        """
        enough_signals = self.floor
        return [item for item in self.of_base(base, perimeter)
                if item.fired() and not item.is_internal
                and not item.is_rankable(enough_signals)]

    def internal(self, base: str, perimeter: str = ALL) -> List["Entity"]:
        return [item for item in self.of_base(base, perimeter) if item.is_internal]


def _split_columns(header: Sequence[str]):
    """Séparer l'en-tête en signaux, identités et montants, par convention seule."""
    names = list(header)
    signals = [name[:-len(NORM_SUFFIX)] for name in names
               if name.endswith(NORM_SUFFIX) and name[:-len(NORM_SUFFIX)] in names]
    known = set(signals) | {name + NORM_SUFFIX for name in signals}
    identity = {"base", "window", "market", "entity_id", "entity_name", "channel",
                "country_is", "norm_level", "not_computable", "note", "is_internal",
                "signals_computable", "signals_fired", "signals_fired_share"}
    extras = [name for name in names if name not in known and name not in identity]
    return sorted(signals), extras


def load(path: str) -> "Distribution":
    """Lire la source, en découvrant ses signaux plutôt qu'en les supposant.

    Un défaut de ligne écarte la ligne ; un défaut d'en-tête rend le fichier inutilisable.
    La différence tient à ce qu'on peut encore affirmer : une ligne illisible laisse le
    reste vrai, un en-tête illisible laisse tout douteux.
    """
    if not os.path.exists(path):
        return Distribution([], [], [], ["Fichier absent : %s" % path], path)

    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            return Distribution([], [], header,
                                ["Colonnes manquantes : %s" % ", ".join(missing)], path)
        signals, extras = _split_columns(header)
        if not signals:
            return Distribution(
                [], [], header,
                ["Aucun signal : il faut des colonnes appariées « x » et « x%s »"
                 % NORM_SUFFIX], path)
        raw = list(reader)

    entities: List[Entity] = []
    faults: List[str] = []
    seen: Dict[str, int] = {}
    unnamed_rows = 0

    for number, record in enumerate(raw, start=2):
        base = (record.get("base") or "").strip()
        if not base:
            continue
        if base not in BASES:
            faults.append("ligne %d : base « %s » inconnue — les deux bases sont %s"
                          % (number, base, " et ".join(BASES)))
            continue

        entity_id = (record.get("entity_id") or "").strip()
        if entity_id.lower() not in PLACEHOLDER_IDS:
            identity = "%s|%s|%s" % (base, (record.get("window") or "").strip(), entity_id)
            if identity in seen:
                faults.append("ligne %d : %s figure déjà ligne %d — aucune des deux "
                              "retenue" % (number, entity_id, seen[identity]))
                continue
            seen[identity] = number
        else:
            # Sans identifiant, la ligne entre mais ne se compare à rien. La compter comme
            # un doublon la ferait disparaître avec toutes ses jumelles, et le total
            # rétrécirait sans que le lecteur voie autre chose qu'un avertissement.
            unnamed_rows += 1

        entities.append(Entity(
            base=base,
            window=(record.get("window") or "").strip(),
            market=(record.get("market") or "").strip(),
            entity_id=entity_id,
            entity_name=(record.get("entity_name") or "").strip(),
            channel=(record.get("channel") or "").strip(),
            country_is=(record.get("country_is") or "").strip(),
            revenue=_number(record.get("revenue_12m")),
            values={name: _number(record.get(name)) for name in signals},
            norms={name: _number(record.get(name + NORM_SUFFIX)) for name in signals},
            norm_level=(record.get("norm_level") or "").strip(),
            not_computable=(record.get("not_computable") or "").strip(),
            note=(record.get("note") or "").strip(),
            is_internal=_flag(record.get("is_internal")),
            extras={name: _number(record.get(name)) for name in extras},
        ))

    if unnamed_rows:
        # Dit une fois, avec son compte. Soixante avertissements identiques noient la
        # seule ligne qui portait une information.
        faults.append("%d ligne(s) sans identifiant : gardées, mais aucune n'est "
                      "comparable à une autre" % unnamed_rows)
    if not entities and not faults:
        faults.append("aucune entité dans %s" % path)
    return Distribution(entities, signals, extras, faults, path)


def current(path: Optional[str] = None) -> "Distribution":
    from ..config import settings

    return load(path or str(settings.distribution_path))
