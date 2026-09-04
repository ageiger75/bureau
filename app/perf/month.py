"""Où en est le mois, périmètre par périmètre — la pièce de B3 que le lecteur voit.

Le module `pace` sait calculer deux taux pour un marché : la part du mois derrière nous
selon la forme des années passées, et la part de l'objectif déjà faite. Il ne sait rien de
qui répond de quoi, ni d'où viennent les chiffres. Ce module fait la jointure et la rend
dans l'ordre où le lecteur la lit : par périmètre, le MD nommé, ses marchés dessous.

Trois absences y sont nommées plutôt que comblées, parce que chacune appelle un geste
différent : un marché sans forme de mois attend une ligne dans le fichier de phasage ; un
marché sans objectif attend une ligne au plan ; un marché qu'aucun périmètre ne place
attend une correction de l'organigramme. Les trois ressemblent à « rien à dire », et
aucune ne l'est.

Le sell-in n'y figure pas, et ce n'est pas un oubli : une facture tombe quand elle tombe,
un mois de livraisons n'avance pas en jours, et afficher un avancement dessus dirait une
chose que personne ne mesure.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Sequence

from . import pace as pace_module
from .budget import is_sell_out, normalise_market

#: Ce que l'écran dit du sell-in à la place d'un taux. Écrit une fois, ici.
SELL_IN_NOTE = ("Le sell-in n'avance pas en jours : une facture tombe quand elle tombe. "
                "Aucun calendrier d'expédition n'est connecté, donc pas d'avancement.")

#: Sous cette largeur, une fourchette se lit comme un point.
NARROW = 0.03


def week_of(day: int) -> int:
    """Le bloc de sept jours où tombe un jour du mois — la règle du fichier de phasage."""
    return (int(day) + 6) // 7


def _day(value) -> Optional[datetime.date]:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value or "").strip()[:10]
    try:
        return datetime.date(int(text[0:4]), int(text[5:7]), int(text[8:10]))
    except (TypeError, ValueError):
        return None


def _number(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Line:
    """Un marché : ses deux taux, ou ce qui manque pour les donner."""

    __slots__ = ("market", "progress", "perimeter")

    def __init__(self, market: str, progress: "pace_module.Progress",
                 perimeter: str = "") -> None:
        self.market = market
        self.progress = progress
        self.perimeter = perimeter

    @property
    def month_done(self) -> str:
        """« 45–70 % » quand les années ne s'accordent pas, « 62 % » quand elles
        s'accordent, et l'absence nommée sinon."""
        band = self.progress.through_month
        if band is None:
            return ""
        if band.spread <= NARROW:
            return "%.0f %%" % (band.middle * 100)
        return "%.0f–%.0f %%" % (band.low * 100, band.high * 100)

    @property
    def target_done(self) -> str:
        share = self.progress.through_target
        return "" if share is None else "%.0f %%" % (share * 100)

    @property
    def behind(self) -> str:
        """Les points de retard sur le mois, en fourchette. Positif : reste à rattraper."""
        band = self.progress.behind
        if band is None:
            return ""
        if band.spread <= NARROW:
            return "%+.0f pts" % (band.middle * 100)
        return "%+.0f à %+.0f pts" % (band.low * 100, band.high * 100)

    @property
    def readable(self) -> bool:
        return self.progress.readable

    @property
    def absent(self) -> str:
        return self.progress.absent


class Group:
    """Un périmètre : son MD, ses marchés."""

    __slots__ = ("name", "lead", "lines")

    def __init__(self, name: str, lead: str, lines: Sequence["Line"]) -> None:
        self.name = name
        self.lead = lead
        self.lines = list(lines)


class Review:
    """La lecture entière du mois, prête à rendre."""

    __slots__ = ("month", "week", "through", "groups", "unplaced", "absent", "sell_in")

    def __init__(self, month: str, week: int, through: str,
                 groups: Sequence["Group"], unplaced: Sequence["Line"],
                 absent: Sequence[str]) -> None:
        #: Le mois lu, « 2026-09 », et la semaine du mois où la lecture s'arrête.
        self.month = month
        self.week = week
        #: Le dernier jour lu, en ISO. C'est la date qui borne tout ce qui suit.
        self.through = through
        self.groups = list(groups)
        #: Les marchés qu'aucun périmètre ne place. Rendus à part, jamais rangés par
        #: ressemblance : un marché mal placé envoie une question à la mauvaise personne.
        self.unplaced = list(unplaced)
        #: Ce qui a manqué à la lecture, nommé.
        self.absent = list(absent)
        self.sell_in = SELL_IN_NOTE

    @property
    def usable(self) -> bool:
        return bool(self.groups or self.unplaced)

    @property
    def lines(self) -> List["Line"]:
        return [line for group in self.groups for line in group.lines] + self.unplaced

    @property
    def readable(self) -> int:
        return sum(1 for line in self.lines if line.readable)


def targets_from_budget(budget, period: str) -> Dict[str, Optional[float]]:
    """L'objectif sell-out du mois par marché, tel que le plan l'écrit.

    Sell-out seulement, pour la même raison que la requête : le sell-in n'a pas
    d'avancement. Un marché sans ligne n'est pas à zéro, il est absent du dictionnaire.
    """
    found: Dict[str, float] = {}
    for line in getattr(budget, "lines", ()) or ():
        if line.period != period or not is_sell_out(line.segment):
            continue
        if line.budget is None:
            continue
        found[line.market] = found.get(line.market, 0.0) + float(line.budget)
    return found


def build(rows: Sequence[dict], targets: Dict[str, Optional[float]],
          phasing: Optional["pace_module.Phasing"], org=None) -> "Review":
    """Joindre le réalisé du mois, le plan et la forme des mois, et ranger par périmètre.

    `rows` est le contrat de `MONTH_TO_DATE` : `market · iso2 · sales_to_date ·
    read_through`. `targets` est indexé par le nom de marché normalisé du plan.
    """
    from . import perimeter as perimeter_module

    absent: List[str] = []
    days = [_day(row.get("read_through")) for row in rows]
    days = [day for day in days if day is not None]
    if not days:
        return Review("", 0, "", [], [], ["aucune vente lue sur le mois en cours"])
    through = max(days)
    month = "%04d-%02d" % (through.year, through.month)
    week = week_of(through.day)

    if phasing is None or not phasing.usable:
        absent.append("forme des mois non déposée : aucun taux d'avancement du mois")
    if not targets:
        absent.append("aucun objectif sell-out au plan pour %s" % month)

    lines: List[Line] = []
    for row in rows:
        raw = str(row.get("market") or "").strip()
        if not raw:
            continue
        market = normalise_market(raw)
        actual = _number(row.get("sales_to_date")) or 0.0
        target = targets.get(market)
        progress = pace_module.progress(raw, month, week, actual, target, phasing)
        lines.append(Line(market, progress))

    placed: Dict[str, str] = {}
    leads: Dict[str, str] = {}
    if org is not None and getattr(org, "usable", False):
        placed = perimeter_module.place(org, [line.market for line in lines])
        for name, person in org.leads().items():
            leads[name] = person.name
    else:
        absent.append("organigramme absent : les marchés ne sont pas rangés par périmètre")

    by_perimeter: Dict[str, List[Line]] = {}
    unplaced: List[Line] = []
    for line in lines:
        name = placed.get(line.market)
        if name:
            line.perimeter = name
            by_perimeter.setdefault(name, []).append(line)
        else:
            unplaced.append(line)

    def order(items: List[Line]) -> List[Line]:
        # Le plus gros plan d'abord, les marchés sans plan à la fin : ce que le lecteur
        # cherche en premier est ce qui pèse, pas ce qui manque.
        return sorted(items, key=lambda line: -(line.progress.target or 0.0))

    groups = [Group(name, leads.get(name, ""), order(items))
              for name, items in by_perimeter.items()]
    groups.sort(key=lambda group: -sum(line.progress.target or 0.0
                                       for line in group.lines))
    return Review(month, week, through.isoformat(), groups, order(unplaced), absent)
