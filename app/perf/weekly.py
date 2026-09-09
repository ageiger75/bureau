"""La semaine : ce qui a bougé depuis lundi, marché par marché — piloter le commerce à la
semaine, pas seulement au mois.

Trois chiffres par marché et par périmètre, tous sur des semaines pleines, du lundi au
dimanche : la dernière semaine complète lue, la semaine d'avant, et la même semaine de l'an
dernier — 364 jours en arrière, pour que lundi tombe sur lundi et qu'un week-end de plus ou
de moins ne fasse pas une croissance. Aucun taux de change : l'entrepôt convertit au taux
budget, comme le plan et la consolidation.

Ce que ce module refuse. Une semaine entamée n'est pas comptée : trois jours contre sept
disent que la semaine est courte, rien d'autre. Un marché dont le 1er du mois encaisse une
campagne de plateforme est nommé quand le 1er tombe dans l'une des semaines comparées : ce
paquet est du chiffre réel versé un seul jour, et il fait une semaine « en avance » de
vingt points sans que rien n'ait bougé. Et rien n'est comparé au plan ici : le plan est
mensuel, la semaine se lit contre elle-même et contre l'an dernier.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Sequence

from .budget import normalise_market

MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre")

#: Le nombre de marchés portés par périmètre avant de replier le reste.
MOST_MARKETS = 6


def _day(text) -> Optional[datetime.date]:
    raw = str(text or "")[:10]
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        return None


def _number(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Span:
    """Une semaine pleine, du lundi au dimanche."""

    __slots__ = ("start", "end")

    def __init__(self, end: datetime.date) -> None:
        self.end = end
        self.start = end - datetime.timedelta(days=6)

    def holds(self, day: datetime.date) -> bool:
        return self.start <= day <= self.end

    @property
    def first_of_month(self) -> Optional[datetime.date]:
        """Le 1er d'un mois que la semaine contient, s'il y en a un."""
        for offset in range(7):
            day = self.start + datetime.timedelta(days=offset)
            if day.day == 1:
                return day
        return None

    @property
    def label(self) -> str:
        if self.start.month == self.end.month:
            return "du %d au %d %s" % (self.start.day, self.end.day, MONTHS_FR[self.end.month - 1])
        return "du %d %s au %d %s" % (self.start.day, MONTHS_FR[self.start.month - 1],
                                      self.end.day, MONTHS_FR[self.end.month - 1])

    def back(self, days: int) -> "Span":
        return Span(self.end - datetime.timedelta(days=days))


def _pct(now: float, before: Optional[float]) -> Optional[float]:
    if before is None or before <= 0:
        return None
    return now / before - 1.0


def _pct_label(value: Optional[float]) -> str:
    return "—" if value is None else "%+.0f %%" % (value * 100)


class Line:
    """Un marché ou un périmètre : la semaine, la précédente, la même l'an dernier."""

    __slots__ = ("name", "week", "previous", "last_year", "campaign", "markets")

    def __init__(self, name: str, week: float = 0.0, previous: float = 0.0,
                 last_year: Optional[float] = None, campaign: bool = False) -> None:
        self.name = name
        self.week = week
        self.previous = previous
        #: None quand l'an dernier n'a rien sur ces dates : un marché ouvert depuis.
        self.last_year = last_year
        #: Le 1er d'un mois est dans l'une des semaines comparées et ce marché y encaisse
        #: une campagne : la comparaison porte un paquet, et l'écran le dit.
        self.campaign = campaign
        self.markets: List["Line"] = []

    def add(self, other: "Line") -> None:
        self.week += other.week
        self.previous += other.previous
        if other.last_year is not None:
            self.last_year = (self.last_year or 0.0) + other.last_year
        self.campaign = self.campaign or other.campaign
        self.markets.append(other)

    @property
    def wow(self) -> Optional[float]:
        return _pct(self.week, self.previous)

    @property
    def yoy(self) -> Optional[float]:
        return _pct(self.week, self.last_year)

    @property
    def wow_label(self) -> str:
        return _pct_label(self.wow)

    @property
    def yoy_label(self) -> str:
        return _pct_label(self.yoy)

    @property
    def shown(self) -> List["Line"]:
        return sorted(self.markets, key=lambda line: -line.week)[:MOST_MARKETS]

    @property
    def rest(self) -> List["Line"]:
        return sorted(self.markets, key=lambda line: -line.week)[MOST_MARKETS:]

    @property
    def sentence(self) -> str:
        from .analytics import format_eur

        text = "%s, %s sur la semaine précédente" % (format_eur(self.week), self.wow_label)
        if self.last_year is not None:
            text += ", %s sur la même semaine l'an dernier" % self.yoy_label
        else:
            text += ", pas d'an dernier sur ces dates"
        return text


class Review:
    """La semaine vue par l'écran : le groupe, les périmètres, ce qui manque."""

    def __init__(self, span: Optional[Span], read_through: Optional[datetime.date],
                 group: Optional[Line], perimeters: Sequence[Line], absent: Sequence[str],
                 loose: Optional[Line] = None) -> None:
        self.span = span
        self.read_through = read_through
        self.group = group
        self.perimeters = list(perimeters)
        self.absent = list(absent)
        self.loose = loose

    @property
    def usable(self) -> bool:
        return self.span is not None and self.group is not None and self.group.week > 0

    @property
    def title(self) -> str:
        if self.span is None:
            return "La semaine"
        return "Semaine %s" % self.span.label

    @property
    def days_note(self) -> str:
        """Les jours lus au-delà de la semaine pleine : entamés, pas comptés."""
        if self.span is None or self.read_through is None:
            return ""
        extra = (self.read_through - self.span.end).days
        if extra <= 0:
            return ""
        return ("%d jour%s entamé%s, non compté%s"
                % (extra, "s" if extra > 1 else "", "s" if extra > 1 else "",
                   "s" if extra > 1 else ""))

    @property
    def campaign_note(self) -> str:
        if self.span is None or self.group is None:
            return ""
        named = [line.name for perimeter in self.perimeters for line in perimeter.markets
                 if line.campaign]
        if self.loose is not None:
            named.extend(line.name for line in self.loose.markets if line.campaign)
        if not named:
            return ""
        return ("le 1er du mois tombe dans l'une des semaines comparées, et il porte une "
                "campagne de plateforme sur %s : la comparaison de ces marchés en dépend"
                % ", ".join(sorted(set(named))))

    def for_name(self, name: str) -> Optional[Line]:
        return next((line for line in self.perimeters if line.name == name), None)


def last_complete_week(read_through: datetime.date) -> Span:
    """La dernière semaine pleine lue : celle qui finit le dernier dimanche lu."""
    back = (read_through.weekday() + 1) % 7
    return Span(read_through - datetime.timedelta(days=back))


def build(rows: Sequence[dict], lumpy: Sequence[str] = (), org=None, directory=None,
          today: Optional[datetime.date] = None) -> Review:
    """La semaine, marché par marché, rangée par périmètre comme le mois l'est.

    `rows` est le contrat de `DAILY_SALES` : `market · iso2 · transaction_date ·
    net_sales_eur`. `lumpy` nomme les marchés dont le 1er du mois encaisse une campagne,
    tels que le mois les a reconnus.
    """
    from .month import place_markets

    absent: List[str] = []
    daily: Dict[str, Dict[datetime.date, float]] = {}
    for row in rows:
        market = normalise_market(str(row.get("market") or "").strip())
        day = _day(row.get("transaction_date"))
        amount = _number(row.get("net_sales_eur"))
        if not market or day is None or amount is None:
            continue
        daily.setdefault(market, {})[day] = daily.get(market, {}).get(day, 0.0) + amount
    if not daily:
        return Review(None, None, None, [], ["aucune vente au jour lue : la semaine ne se lit pas"])
    read_through = max(day for days in daily.values() for day in days
                       if today is None or day <= today)
    span = last_complete_week(read_through)
    previous = span.back(7)
    before = span.back(364)
    campaign_windows = [span, previous, before]
    lumpy_set = {normalise_market(name) for name in lumpy}

    lines: List[Line] = []
    for market, days in daily.items():
        week = sum(amount for day, amount in days.items() if span.holds(day))
        prev = sum(amount for day, amount in days.items() if previous.holds(day))
        has_before = any(before.holds(day) for day in days)
        last = sum(amount for day, amount in days.items() if before.holds(day)) if has_before else None
        if week == 0 and prev == 0 and not last:
            continue
        campaign = market in lumpy_set and any(window.first_of_month is not None
                                               for window in campaign_windows)
        lines.append(Line(market, week, prev, last, campaign))

    placed, leads = place_markets([line.name for line in lines], org, directory)
    perimeters: Dict[str, Line] = {}
    loose = Line("Sans périmètre")
    group = Line("Groupe")
    for line in lines:
        group.add(line)
        name = placed.get(line.name)
        if name:
            perimeters.setdefault(name, Line(name)).add(line)
        else:
            loose.add(line)
    ordered = sorted(perimeters.values(), key=lambda item: -item.week)
    if not placed:
        absent.append("ni annuaire ni organigramme : les marchés ne sont pas rangés par périmètre")
    return Review(span, read_through, group, ordered, absent,
                  loose if loose.markets else None)
