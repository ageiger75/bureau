"""Où en est le mois, et où en est l'objectif du mois. Deux taux, jamais un seul.

Le besoin B3 tient en une phrase du lecteur : « savoir où j'en suis dans le mois, pas
seulement à la fin ». Un seul nombre n'y répond pas, parce que la question en contient deux
et que leur écart *est* l'information. À 60 % du mois et 60 % du plan on est dans les
temps ; à 60 % du mois et 40 % du plan il reste 40 % du mois pour rattraper vingt points,
ce qui est une conversation.

**Où en est le mois** ne se calcule pas sur les jours écoulés. Un mois ne se vend pas à
plat : une campagne, une fête, un jour de paie concentrent le chiffre sur quelques jours, et
la moitié des jours ne fait pas la moitié du mois. Supposer le contraire est la faute la
plus commode de tout ce dossier — elle rend un nombre plausible et sans rapport avec le
commerce.

La forme vient donc d'un fichier écrit depuis l'entrepôt : la part de chaque semaine dans le
mois, telle que les années précédentes l'ont écrite, marché par marché.

**Et c'est ici que ce module a été refait, parce que la première version était fausse.**
Elle alignait les années par rang de semaine, ce qui corrige la dérive d'un jour ou deux et
ne corrige rien du tout quand la fête des mères passe de la deuxième à la troisième semaine,
ou quand Black Friday tombe en semaine 4 une année et en semaine 5 la suivante. Là, la
semaine est aussi fausse que la date. Recaler sur l'événement demanderait un calendrier des
dates mobiles, qui n'existe pas.

La sortie ne demande aucun calendrier : **au lieu d'affirmer une forme, mesurer si une forme
existe.** Avec plusieurs années, la dispersion d'une semaine dit tout. Une semaine qui a fait
vingt pour cent, puis cinquante-cinq, puis vingt-deux n'est pas une semaine dont on connaît
la part : c'est une semaine traversée par un événement qui bouge. Le module rend donc une
**fourchette** — « entre 45 % et 70 % du mois selon l'année de référence » — et non un point.
Quand les années s'accordent, la fourchette est étroite et se lit comme un point ; quand
elles ne s'accordent pas, le lecteur voit exactement pourquoi il ne peut pas conclure.

Deux conséquences tenues ici :

**Une seule année de référence ne vérifie rien.** Elle donne un point sans moyen de savoir
si ce point se reproduit. Le module le déclare plutôt que de laisser croire à une mesure.

**Le mois se découvre instable sans qu'on lui dise où sont les fêtes.** C'est un effet de
bord précieux : le fichier révèle de lui-même quels marchés et quels mois portent un
événement mobile, ce qu'aucun calendrier tenu à la main ne resterait à jour pour dire.

**Deux mesures, et aucune ne remplace l'autre.** La première version regardait l'étendue de
la part hebdomadaire, à une semaine fixée. Deux défauts s'y cachaient. L'un : l'avancement
est cumulé, donc un déplacement entre semaines voisines se compense en partie dans les parts
et disparaît dans la somme — la bonne mesure du déplacement est l'étendue du **cumul**,
balayée sur toutes les semaines. L'autre : la dernière semaine cumule à un par construction,
elle ne peut rien dire, et un mois entièrement remué en son milieu s'y lirait « stable ».
Mais le cumul, lui, ne voit pas ce qui bouge à l'intérieur du mois sans le déplacer — deux
événements qui se croisent, une promotion qui glisse et revient. Le module rend donc la
**mobilité cumulée** et la **variation totale** : la première dit de combien le mois se
déplace, la seconde de combien il remue. Un mois peut avoir l'une sans l'autre, et les deux
appellent des recherches différentes.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional, Sequence, Tuple

#: Les colonnes du fichier. `year` est obligatoire et c'est tout l'objet de la refonte :
#: sans plusieurs années, on ne peut pas savoir si la forme d'un mois se reproduit, et un
#: taux d'avancement tiré d'une seule année est une affirmation déguisée en mesure.
REQUIRED = ("market", "month", "week", "share", "year")

#: Tolérance sur la somme des parts d'une année. Une courbe qui ne somme pas à un décrirait
#: un mois dont une partie du chiffre n'existe pas, et le taux qu'elle produirait serait
#: faux d'exactement ce qui manque.
SUM_TOLERANCE = 0.01

#: Les blocs de sept jours pleins d'un mois. Le découpage qui produit ces fichiers — le
#: rang du jour divisé par sept, arrondi au-dessus — donne quatre blocs de sept jours puis
#: un reliquat de zéro à trois jours. Ce reliquat n'est pas une semaine : il contient un
#: samedi une année et pas la suivante, ce qui suffit à faire bouger sa part sans qu'aucun
#: commerce n'ait bougé. Il est donc exclu des deux mesures, qui ne comparent que des blocs
#: de même longueur.
FULL_BLOCS = 4

#: En dessous de ce nombre d'années, une forme n'est pas vérifiée : elle peut être vraie,
#: rien ne le dit. Deux est le minimum pour qu'une dispersion existe.
YEARS_TO_VERIFY = 2


class Band:
    """Un avancement tel que les années de référence le donnent : une fourchette.

    Un point unique serait plus commode et faux dès qu'un événement bouge. La largeur de la
    fourchette *est* la réponse à « peut-on conclure » : étroite, elle se lit comme un
    point ; large, elle dit que ce mois n'a pas de forme stable et que le lecteur ne doit
    rien en conclure.
    """

    __slots__ = ("low", "high", "years")

    def __init__(self, low: float, high: float, years: int) -> None:
        self.low = low
        self.high = high
        #: Combien d'années composent la fourchette. Une seule ne vérifie rien.
        self.years = years

    @property
    def spread(self) -> float:
        return self.high - self.low

    @property
    def middle(self) -> float:
        return (self.low + self.high) / 2.0

    @property
    def verified(self) -> bool:
        """Y a-t-il assez d'années pour qu'une dispersion veuille dire quelque chose ?"""
        return self.years >= YEARS_TO_VERIFY

    def __repr__(self) -> str:  # pragma: no cover - confort de mise au point
        return "Band(%.3f, %.3f, %d ans)" % (self.low, self.high, self.years)


class Curve:
    """La forme d'un mois pour un marché, année par année."""

    __slots__ = ("market", "month", "by_year")

    def __init__(self, market: str, month: str,
                 by_year: Dict[str, Sequence[float]]) -> None:
        self.market = market
        #: Le mois décrit, « 01 » à « 12 ». L'année n'entre pas dans la clé : c'est la
        #: répétition d'un mois d'une année sur l'autre qu'on cherche à mesurer.
        self.month = month
        #: Les parts de chaque semaine, pour chaque année de référence.
        self.by_year: Dict[str, List[float]] = {
            year: list(shares) for year, shares in by_year.items()
        }

    @property
    def years(self) -> List[str]:
        return sorted(self.by_year)

    @property
    def usable(self) -> bool:
        return bool(self.by_year)

    def elapsed(self, week: int, within: float = 1.0) -> Optional["Band"]:
        """Quelle part du mois est derrière nous, selon les années.

        `within` est la fraction de la semaine en cours déjà écoulée. Sans elle, le
        troisième jour du mois créditait la première semaine entière — et tous les marchés
        paraissaient en avance de dix points le même matin, ce qui n'ordonne rien. À
        l'intérieur d'une semaine la part est prise à plat : c'est une hypothèse, elle est
        déclarée ici, et elle vaut pour sept jours là où l'autre valait pour un mois.

        `None` quand aucune année ne décrit cette semaine. Une semaine au-delà de la courbe
        d'une année ne vaut pas cent pour cent pour cette année-là : un mois de cinq
        semaines lu sur une courbe de quatre annoncerait un mois fini la semaine où il reste
        précisément le plus à faire. Cette année-là ne participe simplement pas.
        """
        if week < 1:
            return None
        within = min(max(float(within), 0.0), 1.0)
        seen = [sum(shares[:week - 1]) + shares[week - 1] * within
                for shares in self.by_year.values() if week <= len(shares)]
        if not seen:
            return None
        return Band(min(seen), max(seen), len(seen))

    @property
    def span(self) -> int:
        """Le nombre de semaines que **toutes** les années décrivent.

        Au-delà, une année a une semaine et l'autre non : l'écart qu'on lirait là serait un
        écart de découpage, pas un déplacement de commerce.
        """
        if not self.by_year:
            return 0
        return min(len(shares) for shares in self.by_year.values())

    @property
    def has_remainder(self) -> bool:
        """Le mois déborde-t-il des quatre blocs pleins ?"""
        return self.span > FULL_BLOCS

    @property
    def full(self) -> int:
        """Les blocs de sept jours pleins, seuls comparables entre eux et d'une année sur
        l'autre. Le reliquat de fin de mois n'en est pas un — voir `FULL_BLOCS`."""
        return min(self.span, FULL_BLOCS)

    def mobility(self) -> Optional[Tuple[int, "Band"]]:
        """La semaine où le cumul s'écarte le plus d'une année sur l'autre, et de combien.

        Le balayage couvre tous les blocs pleins. **Le dernier ne peut rien dire quand le
        mois s'y termine : il cumule à un par construction**, son étendue est nulle et il
        s'exclut donc tout seul, sans qu'aucune règle n'ait à le retirer. Quand le mois
        déborde sur un reliquat, ce même bloc porte au contraire l'information la plus
        utile — c'est là que se lit un événement de fin de mois qui change de bloc.
        """
        worst: Optional[Tuple[int, "Band"]] = None
        for week in range(1, self.full + 1):
            band = self.elapsed(week)
            if band is None or not band.verified:
                continue
            if worst is None or band.spread > worst[1].spread:
                worst = (week, band)
        return worst

    @property
    def variation(self) -> Optional[float]:
        """Combien le mois remue en interne : la somme des étendues des parts semaine à
        semaine.

        Elle répond à une autre question que la mobilité, et aucune des deux ne remplace
        l'autre. Un événement qui se déplace de la deuxième à la troisième semaine déplace
        le cumul et remue les parts : les deux le voient. Un événement qui se déplace **à
        l'intérieur** d'une semaine, ou deux événements qui se compensent, ne déplacent
        aucun cumul et remuent quand même les parts : seule celle-ci le voit. Et l'inverse
        existe aussi — un mois qui glisse d'un bloc voit son cumul bouger sans que la
        forme des semaines change beaucoup.

        `None` sans deux années : une étendue sur un point n'existe pas.
        """
        full = self.full
        if full < 1 or len(self.by_year) < YEARS_TO_VERIFY:
            return None
        total = 0.0
        for index in range(full):
            values = [shares[index] for shares in self.by_year.values()]
            total += max(values) - min(values)
        return total

    def trending(self, week: int) -> bool:
        """La série des cumuls est-elle monotone d'une année sur l'autre ?

        Une date qui se déplace **oscille** : elle est tôt une année, tard la suivante, tôt
        encore ensuite. Une série qui monte ou descend trois années de suite décrit autre
        chose — une ouverture, une fermeture, une promotion arrêtée, un canal qui arrive.
        La distinction décide de la suite du travail : chercher une fête pour expliquer une
        tendance ne trouve rien, et coûte une recherche entière.

        Deux exercices ne suffisent pas : entre deux points, une droite passe toujours.
        """
        values = [sum(self.by_year[year][:week]) for year in self.years
                  if week <= len(self.by_year[year])]
        if len(values) < 3:
            return False
        pairs = list(zip(values, values[1:]))
        return all(b > a for a, b in pairs) or all(b < a for a, b in pairs)


class Movement:
    """Un mois qui ne se reproduit pas, avec les deux façons de le dire.

    Les deux mesures sont portées ensemble parce qu'elles se contredisent utilement, et
    qu'une seule d'entre elles ferait passer pour stable la moitié des cas.
    """

    __slots__ = ("curve", "week", "band", "variation")

    def __init__(self, curve: "Curve", week: int, band: Optional["Band"],
                 variation: Optional[float]) -> None:
        self.curve = curve
        #: La semaine où le cumul s'écarte le plus. `0` quand seule la variation parle.
        self.week = week
        #: L'écart des cumuls à cette semaine. `None` quand seule la variation parle.
        self.band = band
        self.variation = variation

    @property
    def market(self) -> str:
        return self.curve.market

    @property
    def month(self) -> str:
        return self.curve.month

    @property
    def mobility(self) -> float:
        """De combien le mois se déplace. Zéro quand il remue sans se déplacer."""
        return self.band.spread if self.band is not None else 0.0

    @property
    def years(self) -> int:
        return len(self.curve.by_year)

    @property
    def trending(self) -> bool:
        return self.week > 0 and self.curve.trending(self.week)

    @property
    def on_remainder(self) -> bool:
        """La mobilité s'appuie-t-elle sur le reliquat de fin de mois ?

        Quand elle tombe au dernier bloc plein d'un mois qui déborde, l'étendue mesurée
        **est** celle de la part du reliquat — le cumul de fin de quatrième bloc vaut un
        moins elle. Or ce reliquat contient un samedi une année et pas la suivante. La
        ligne reste vraie et elle reste utile : c'est là que se lit une fête qui passe du
        28 au 29. Mais elle est confondue avec la position d'un week-end, et le seul moyen
        de les séparer est un marché témoin — même calendrier, pas la même fête.
        """
        return self.week == self.curve.full and self.curve.has_remainder

    @property
    def thin(self) -> bool:
        """Deux exercices seulement : une étendue entre deux points, pas une dispersion.

        Le mois entre quand même — il a bougé — mais il ne peut pas ouvrir une recherche à
        lui seul : deux années suffisent à voir un écart et jamais à voir s'il se répète.
        """
        return self.years < 3


class Phasing:
    """Les courbes lues, et ce que le fichier a de faux."""

    __slots__ = ("curves", "faults", "path")

    def __init__(self, curves: Dict[Tuple[str, str], "Curve"],
                 faults: Sequence[str], path: str = "") -> None:
        self.curves = dict(curves)
        self.faults = list(faults)
        self.path = path

    def __len__(self) -> int:
        return len(self.curves)

    @property
    def usable(self) -> bool:
        return bool(self.curves)

    def of(self, market: str, month: str) -> Optional["Curve"]:
        """La courbe d'un marché pour un mois. Le marché se compare sans sa casse : le
        fichier l'écrit comme l'entrepôt, en capitales, et l'écran comme le plan."""
        return self.curves.get(self._key(market, month))

    @staticmethod
    def _key(market: str, month: str) -> Tuple[str, str]:
        return ((market or "").strip().upper(), (month or "").strip()[-2:])

    def moving(self, spread: float, variation: Optional[float] = None) -> List["Movement"]:
        """Les mois dont la forme ne se reproduit pas, sur l'un ou l'autre des deux motifs.

        **Toutes les semaines sont balayées, jamais une seule.** L'avancement est cumulé :
        un événement qui passe de la deuxième à la troisième semaine ne change presque rien
        au cumul de fin de troisième semaine — il est dedans dans les deux cas — mais il
        change tout à celui de fin de deuxième. Fixer une semaine d'avance revient donc à
        choisir quels déplacements on accepte de ne pas voir.

        **Et le cumul ne voit pas tout non plus.** Un déplacement qui se compense à
        l'intérieur du mois laisse le cumul intact et remue les parts ; c'est ce que la
        variation totale attrape, et le second seuil est là pour qu'un tel mois entre.

        Se lit comme une découverte plutôt que comme un défaut : ce sont les marchés et les
        mois traversés par quelque chose qui bouge, et le fichier les désigne sans qu'aucun
        calendrier de dates ait été tenu à la main.
        """
        found: List["Movement"] = []
        for curve in self.curves.values():
            worst = curve.mobility()
            churn = curve.variation
            moved = worst is not None and worst[1].spread > spread
            churned = (variation is not None and churn is not None
                       and churn > variation)
            if not moved and not churned:
                continue
            week, band = worst if worst is not None else (0, None)
            if not moved:
                week, band = 0, None
            found.append(Movement(curve, week, band, churn))
        return sorted(found, key=lambda item: (-item.mobility, -(item.variation or 0.0)))


class Progress:
    """L'avancement d'un marché : deux taux, ou une absence nommée."""

    __slots__ = ("market", "month", "week", "through_month", "through_target",
                 "actual", "target", "absent")

    def __init__(self, market: str, month: str, week: int,
                 through_month: Optional["Band"], through_target: Optional[float],
                 actual: Optional[float], target: Optional[float],
                 absent: str = "") -> None:
        self.market = market
        self.month = month
        self.week = week
        #: La part du mois derrière nous, en fourchette. `None` sans courbe.
        self.through_month = through_month
        #: Part de l'objectif réalisée. Un point, celui-là : il ne dépend d'aucune année de
        #: référence, seulement du plan et du réalisé.
        self.through_target = through_target
        self.actual = actual
        self.target = target
        #: Ce qui manque pour répondre, nommé. Vide quand les deux taux existent.
        self.absent = absent

    @property
    def readable(self) -> bool:
        return self.through_month is not None and self.through_target is not None

    @property
    def ahead(self) -> Optional["Band"]:
        """De combien de points le réalisé dépasse ce que la forme du mois attendait.

        **Positif : en avance. Négatif : en retard.** C'est le sens naturel — réalisé
        moins attendu — et la première version l'avait inversé, ce qui se lit comme une
        faute de signe sur chaque ligne. La fourchette se propage : un attendu connu à
        vingt-cinq points près donne un écart connu à vingt-cinq points près, et c'est
        cette largeur qui dit si le lecteur peut conclure quelque chose.
        """
        if not self.readable:
            return None
        band = self.through_month
        return Band(self.through_target - band.high,
                    self.through_target - band.low, band.years)


def _number(raw: str) -> Optional[float]:
    text = (raw or "").strip().replace("%", "")
    if not text:
        return None
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return None
    # Une part écrite en pourcentage — « 23 » pour 23 % — se reconnaît à ce qu'elle sort de
    # l'intervalle des parts. Convertir plutôt que refuser : les deux écritures sont
    # légitimes et le fichier peut être repris à la main.
    return value / 100.0 if value > 1.0 else value


def load(path: str) -> "Phasing":
    """Lire la forme des mois. Un fichier absent rend une lecture vide, pas une erreur."""
    if not path or not os.path.exists(path):
        return Phasing({}, [], path)

    weeks: Dict[Tuple[str, str, str], Dict[int, float]] = {}
    faults: List[str] = []
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            return Phasing({}, ["colonnes manquantes : %s" % ", ".join(missing)], path)

        for number, record in enumerate(reader, start=2):
            market = (record.get("market") or "").strip()
            month = (record.get("month") or "").strip()[-2:]
            year = (record.get("year") or "").strip()
            if not market or not month or not year:
                faults.append("ligne %d : marché, mois ou année absent" % number)
                continue
            try:
                week = int((record.get("week") or "").strip())
            except ValueError:
                faults.append("ligne %d : semaine illisible" % number)
                continue
            share = _number(record.get("share") or "")
            if share is None:
                faults.append("ligne %d : part illisible" % number)
                continue
            weeks.setdefault((market, month, year), {})[week] = share

    by_key: Dict[Tuple[str, str], Dict[str, List[float]]] = {}
    for (market, month, year), by_week in weeks.items():
        shares = [by_week[index] for index in sorted(by_week)]
        total = sum(shares)
        if abs(total - 1.0) > SUM_TOLERANCE:
            # Refusée et nommée, jamais remise à l'échelle : une courbe normalisée en
            # douce décrirait un mois que personne n'a mesuré, avec l'aplomb d'une mesure.
            faults.append("%s %s %s : les parts font %.3f au lieu de 1"
                          % (market, month, year, total))
            continue
        by_key.setdefault((market, month), {})[year] = shares

    curves = {Phasing._key(key[0], key[1]): Curve(key[0], key[1], years)
              for key, years in by_key.items()}
    return Phasing(curves, faults, path)


def current(path: Optional[str] = None) -> "Phasing":
    from ..config import settings

    return load(path or str(settings.phasing_path))


def progress(market: str, month: str, week: int, actual: Optional[float],
             target: Optional[float], phasing: Optional["Phasing"],
             within: float = 1.0) -> "Progress":
    """Les deux taux pour un marché, ou ce qui manque pour les donner.

    L'ordre des refus compte : sans courbe on ne remplace pas par les jours écoulés, et
    sans objectif on ne compare pas à zéro. Les deux absences se nomment séparément parce
    qu'elles appellent deux gestes différents — l'une une requête à l'entrepôt, l'autre une
    ligne au plan.
    """
    curve = phasing.of(market, month) if phasing is not None else None
    through_month = curve.elapsed(week, within) if curve is not None else None

    through_target = None
    if target:
        through_target = (actual or 0.0) / target

    absent = []
    if through_month is None:
        absent.append("forme du mois non mesurée pour ce marché")
    elif not through_month.verified:
        absent.append("une seule année de référence : la forme n'est pas vérifiée")
    if through_target is None:
        absent.append("aucun objectif au plan pour ce mois")
    return Progress(market=market, month=month, week=week,
                    through_month=through_month, through_target=through_target,
                    actual=actual, target=target, absent=" · ".join(absent))
