"""Où en est le mois, et où en est l'objectif du mois. Deux taux, jamais un seul.

Le besoin B3 tient en une phrase du lecteur : « savoir où j'en suis dans le mois, pas
seulement à la fin ». Un seul nombre n'y répond pas, parce que la question en contient deux
et que leur écart *est* l'information.

**Où en est le mois** — quelle part de ce qui se vend en un mois est derrière nous. Ce n'est
pas la part des jours écoulés. Un mois ne se vend pas à plat : une campagne, une fête, un
jour de paie concentrent le chiffre sur quelques jours, et la moitié des jours ne fait pas
la moitié du mois. Supposer le contraire est la faute la plus commode de tout ce dossier —
elle rend un nombre plausible et sans rapport avec le commerce.

**Où en est l'objectif** — quelle part du plan du mois est réalisée.

Comparer les deux répond enfin à la question : à 60 % du mois et 60 % du plan, on est dans
les temps ; à 60 % du mois et 40 % du plan, il reste 40 % du mois pour rattraper 20 points,
ce qui est une conversation. Un seul des deux taux ne dit ni l'un ni l'autre.

**La forme du mois vient d'un fichier, jamais d'un calcul.** Elle est lue dans
`var/phasing.csv`, écrit depuis l'entrepôt : la part de chaque semaine dans le mois, telle
que le même mois de l'an dernier l'a écrite, marché par marché. Deux propriétés en découlent
et sont tenues ici.

**L'alignement se fait par semaine, pas par date.** Le 11.11, le nouvel an lunaire et les
soldes ne tombent pas le même jour d'une année sur l'autre ; comparer le 3 novembre au
3 novembre a déjà produit dans ce dossier une chute apparente de quarante pour cent qui
n'existait pas. La semaine est le grain le plus fin qui survive au décalage.

**Sans courbe, on ne devine pas.** Un marché sans forme connue n'obtient pas le taux des
jours écoulés en remplacement : il est **ABSENT**, nommé, avec son chiffre. Un taux plausible
et faux est pire qu'un trou, parce qu'il ne se signale pas.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional, Sequence, Tuple

#: Les colonnes que le fichier doit porter. `share` est la part du mois que cette semaine
#: a faite l'an dernier — un nombre entre 0 et 1, dont la somme par marché et par mois vaut
#: 1. `week` est le rang de la semaine dans le mois, de 1 à 5.
REQUIRED = ("market", "month", "week", "share")

#: Tolérance sur la somme des parts d'un mois. Une courbe qui ne somme pas à un n'est pas
#: une courbe : elle décrirait un mois dont une partie du chiffre n'existe pas, et le taux
#: qu'elle produirait serait faux d'exactement ce qui manque.
SUM_TOLERANCE = 0.01


class Curve:
    """La forme d'un mois pour un marché : la part faite à la fin de chaque semaine."""

    __slots__ = ("market", "month", "shares")

    def __init__(self, market: str, month: str, shares: Sequence[float]) -> None:
        self.market = market
        #: Le mois décrit, sous la forme « MM » — la forme se répète d'une année à l'autre,
        #: c'est même sa raison d'être ; l'année n'entre donc pas dans la clé.
        self.month = month
        #: Part de chaque semaine, dans l'ordre des semaines.
        self.shares: List[float] = list(shares)

    @property
    def total(self) -> float:
        return sum(self.shares)

    @property
    def usable(self) -> bool:
        return bool(self.shares) and abs(self.total - 1.0) <= SUM_TOLERANCE

    def elapsed(self, week: int) -> Optional[float]:
        """Quelle part du mois est derrière nous à la fin de la semaine donnée.

        `None` au-delà de ce que la courbe décrit : une semaine que la forme ne connaît pas
        ne vaut pas cent pour cent, elle vaut « je ne sais pas ». Un mois de cinq semaines
        lu sur une courbe de quatre rendrait un taux d'avancement complet la semaine où il
        reste précisément le plus à faire.
        """
        if not self.usable or week < 1 or week > len(self.shares):
            return None
        return sum(self.shares[:week])


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
        return self.curves.get((market.strip(), month.strip()[-2:]))


class Progress:
    """L'avancement d'un marché : deux taux, ou une absence nommée."""

    __slots__ = ("market", "month", "week", "through_month", "through_target",
                 "actual", "target", "absent")

    def __init__(self, market: str, month: str, week: int,
                 through_month: Optional[float], through_target: Optional[float],
                 actual: Optional[float], target: Optional[float],
                 absent: str = "") -> None:
        self.market = market
        self.month = month
        self.week = week
        #: Part du mois derrière nous, selon la forme de l'an dernier. `None` sans courbe.
        self.through_month = through_month
        #: Part de l'objectif réalisée. `None` sans objectif.
        self.through_target = through_target
        self.actual = actual
        self.target = target
        #: Ce qui manque pour répondre, nommé. Vide quand les deux taux existent.
        self.absent = absent

    @property
    def readable(self) -> bool:
        return self.through_month is not None and self.through_target is not None

    @property
    def points_behind(self) -> Optional[float]:
        """De combien de points l'objectif est en retard sur le mois.

        Positif : il reste à rattraper. Rendu seulement quand les deux taux existent — un
        écart calculé contre un taux supposé serait un chiffre inventé présenté comme une
        mesure.
        """
        if not self.readable:
            return None
        return self.through_month - self.through_target


def _number(raw: str) -> Optional[float]:
    text = (raw or "").strip().replace("%", "")
    if not text:
        return None
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return None
    # Une part écrite en pourcentage — « 23 » pour 23 % — se reconnaît à ce qu'elle sort de
    # l'intervalle des parts. Convertir plutôt que refuser, parce que les deux écritures
    # sont légitimes et que le fichier est tenu à la main.
    return value / 100.0 if value > 1.0 else value


def load(path: str) -> "Phasing":
    """Lire la forme des mois. Un fichier absent rend une lecture vide, pas une erreur."""
    if not path or not os.path.exists(path):
        return Phasing({}, [], path)

    weeks: Dict[Tuple[str, str], Dict[int, float]] = {}
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
            if not market or not month:
                faults.append("ligne %d : marché ou mois absent" % number)
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
            weeks.setdefault((market, month), {})[week] = share

    curves: Dict[Tuple[str, str], Curve] = {}
    for key, by_week in weeks.items():
        shares = [by_week[index] for index in sorted(by_week)]
        curve = Curve(key[0], key[1], shares)
        if not curve.usable:
            # Refusée et nommée, jamais normalisée en douce : une courbe remise à un
            # décrirait un mois que personne n'a mesuré, avec l'aplomb d'une mesure.
            faults.append("%s %s : les parts font %.3f au lieu de 1"
                          % (key[0], key[1], curve.total))
            continue
        curves[key] = curve
    return Phasing(curves, faults, path)


def current(path: Optional[str] = None) -> "Phasing":
    from ..config import settings

    return load(path or str(settings.phasing_path))


def progress(market: str, month: str, week: int, actual: Optional[float],
             target: Optional[float], phasing: Optional["Phasing"]) -> "Progress":
    """Les deux taux pour un marché, ou ce qui manque pour les donner.

    L'ordre des refus compte : sans courbe on ne remplace pas par les jours écoulés, et
    sans objectif on ne compare pas à zéro. Les deux absences se nomment séparément parce
    qu'elles appellent deux gestes différents — l'une une requête à l'entrepôt, l'autre une
    ligne au plan.
    """
    curve = phasing.of(market, month) if phasing is not None else None
    through_month = curve.elapsed(week) if curve is not None else None

    through_target = None
    if target:
        through_target = (actual or 0.0) / target

    absent = []
    if through_month is None:
        absent.append("forme du mois non mesurée pour ce marché")
    if through_target is None:
        absent.append("aucun objectif au plan pour ce mois")
    return Progress(market=market, month=month, week=week,
                    through_month=through_month, through_target=through_target,
                    actual=actual, target=target, absent=" · ".join(absent))
