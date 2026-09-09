"""Ce qui arrive : les temps forts de gifting des six prochaines semaines, par périmètre,
avec le poids que chacun a pesé l'an dernier.

Un calendrier seul ne pilote rien : « Singles Day le 11 novembre » est une date. « Singles
Day : tant pour cent du mois de novembre en Chine l'an dernier, tant de millions » est un
enjeu, et il dit à qui parler et quand. Le poids est **mesuré** par l'agent entrepôt sur le sell-out de l'an
dernier, marché par marché — la part du mois que la fenêtre de l'événement a portée, et le
surcroît par jour contre les semaines qui l'entourent — jamais écrit de mémoire.

Le fichier vit dans `var/gifting.csv`, un événement par marché et par ligne, avec sa fenêtre
de cette année et sa mesure de l'an dernier. Un événement sans mesure est porté avec sa
date et dit qu'il n'est pas pesé ; un événement sans date de cette année n'est pas porté.
Rien ici n'est un objectif ni un plan : c'est ce que le calendrier commercial va faire
vivre, et ce qu'il a fait vivre la dernière fois.
"""

from __future__ import annotations

import csv
import datetime
import io
import os
from typing import Dict, List, Optional, Sequence

from .budget import normalise_market

REQUIRED = ("event", "market", "start", "end")

#: Combien de jours devant soi l'écran regarde.
HORIZON_DAYS = 42

#: Le nombre d'événements portés par périmètre avant de replier le reste.
MOST = 5

MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre")


def _day(text) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(str(text or "").strip()[:10])
    except ValueError:
        return None


def _number(text) -> Optional[float]:
    raw = str(text or "").strip().replace("%", "").replace(",", ".")
    if not raw or raw.upper() in ("NULL", "N/A", "NA"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _span(start: datetime.date, end: datetime.date) -> str:
    if start == end:
        return "le %d %s" % (start.day, MONTHS_FR[start.month - 1])
    if start.month == end.month:
        return "du %d au %d %s" % (start.day, end.day, MONTHS_FR[end.month - 1])
    return "du %d %s au %d %s" % (start.day, MONTHS_FR[start.month - 1], end.day,
                                  MONTHS_FR[end.month - 1])


class Event:
    """Un temps fort sur un marché : sa fenêtre cette année, son poids l'an dernier."""

    __slots__ = ("name", "market", "start", "end", "share", "uplift", "sales", "measured_on",
                 "note", "line")

    def __init__(self, name: str, market: str, start: datetime.date, end: datetime.date,
                 share: Optional[float], uplift: Optional[float], sales: Optional[float],
                 measured_on: str, note: str, line: int) -> None:
        self.name = name
        self.market = market
        self.start = start
        self.end = end
        #: La part du mois de l'an dernier que la fenêtre a portée, en fraction.
        self.share = share
        #: Le surcroît par jour contre les semaines qui entourent la fenêtre, en fraction.
        self.uplift = uplift
        #: Le sell-out de la fenêtre l'an dernier, en euros.
        self.sales = sales
        self.measured_on = measured_on
        self.note = note
        self.line = line

    @property
    def measured(self) -> bool:
        return self.share is not None or self.uplift is not None or self.sales is not None

    def days_until(self, today: datetime.date) -> int:
        return (self.start - today).days

    @property
    def when(self) -> str:
        return _span(self.start, self.end)

    @property
    def weight(self) -> str:
        """« x % du mois l'an dernier, N, +y % par jour » — ou « non pesé »."""
        from .analytics import format_eur

        if not self.measured:
            return "non pesé"
        parts = []
        if self.share is not None:
            parts.append("%.0f %% du mois l'an dernier" % (self.share * 100))
        if self.sales is not None:
            parts.append(format_eur(self.sales))
        if self.uplift is not None:
            parts.append("%+.0f %% par jour contre les semaines autour" % (self.uplift * 100))
        return ", ".join(parts)

    @property
    def sentence(self) -> str:
        return "%s, %s, %s : %s" % (self.name, self.market, self.when, self.weight)


class Calendar:
    """Le fichier lu : les événements, et ce qui n'a pas pu l'être."""

    def __init__(self, events: Sequence[Event], faults: Sequence[str], path: str = "") -> None:
        self.events = list(events)
        self.faults = list(faults)
        self.path = path

    @property
    def is_empty(self) -> bool:
        return not self.events

    def upcoming(self, today: datetime.date, horizon: int = HORIZON_DAYS) -> List[Event]:
        """Ce qui arrive ou est en cours dans l'horizon, le plus proche d'abord."""
        limit = today + datetime.timedelta(days=horizon)
        found = [event for event in self.events if event.end >= today and event.start <= limit]
        return sorted(found, key=lambda event: (event.start, -(event.sales or 0.0)))

    def next_beyond(self, today: datetime.date, horizon: int = HORIZON_DAYS) -> List[Event]:
        """Le premier temps fort au-delà de l'horizon, avec ceux qui ouvrent le même jour —
        pour qu'un horizon vide dise quand même ce qui vient, et dans combien de jours."""
        limit = today + datetime.timedelta(days=horizon)
        later = sorted((event for event in self.events if event.start > limit),
                       key=lambda event: (event.start, -(event.sales or 0.0)))
        if not later:
            return []
        first = later[0].start
        return [event for event in later if event.start == first]


def load(path: str) -> Calendar:
    if not path or not os.path.exists(path):
        return Calendar([], [], path)
    events: List[Event] = []
    faults: List[str] = []
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            return Calendar([], ["colonnes manquantes : %s" % ", ".join(missing)], path)
        for number, record in enumerate(reader, start=2):
            name = (record.get("event") or "").strip()
            market = normalise_market((record.get("market") or "").strip())
            start, end = _day(record.get("start")), _day(record.get("end"))
            if not name or not market:
                faults.append("ligne %d : événement ou marché absent" % number)
                continue
            if start is None or end is None or end < start:
                faults.append("ligne %d : fenêtre illisible pour « %s »" % (number, name))
                continue
            share = _number(record.get("share_of_month_pct"))
            uplift = _number(record.get("uplift_pct"))
            events.append(Event(
                name, market, start, end,
                share / 100.0 if share is not None else None,
                uplift / 100.0 if uplift is not None else None,
                _number(record.get("sales_last_year_eur")),
                (record.get("measured_on") or "").strip(), (record.get("note") or "").strip(),
                number))
    return Calendar(events, faults, path)


def current() -> Calendar:
    from ..config import settings

    return load(str(settings.gifting_path))


class Group:
    """Un périmètre et ce qui y arrive."""

    __slots__ = ("name", "events")

    def __init__(self, name: str, events: Sequence[Event]) -> None:
        self.name = name
        self.events = list(events)

    @property
    def shown(self) -> List[Event]:
        return self.events[:MOST]

    @property
    def rest(self) -> List[Event]:
        return self.events[MOST:]


class Review:
    """Ce qui arrive, rangé par périmètre, et ce qui manque pour le dire."""

    def __init__(self, today: datetime.date, groups: Sequence[Group], absent: Sequence[str],
                 loose: Optional[Group] = None, horizon: int = HORIZON_DAYS,
                 beyond: Sequence[Event] = ()) -> None:
        self.today = today
        self.groups = list(groups)
        self.absent = list(absent)
        self.loose = loose
        self.horizon = horizon
        #: Le premier temps fort au-delà de l'horizon, quand l'horizon est vide ou non.
        self.beyond = list(beyond)

    @property
    def beyond_note(self) -> str:
        if not self.beyond:
            return ""
        first = self.beyond[0]
        days = first.days_until(self.today)
        text = "le prochain au-delà : %s, dans %d jours" % (first.sentence, days)
        if len(self.beyond) > 1:
            text += " · et %d autre%s" % (len(self.beyond) - 1, "s" if len(self.beyond) > 2 else "")
        return text

    @property
    def usable(self) -> bool:
        return bool(self.groups) or self.loose is not None

    @property
    def title(self) -> str:
        return "Ce qui arrive dans les %d semaines" % (self.horizon // 7)

    def for_name(self, name: str) -> Optional[Group]:
        return next((group for group in self.groups if group.name == name), None)

    @property
    def count(self) -> int:
        return sum(len(group.events) for group in self.groups) + (
            len(self.loose.events) if self.loose else 0)

    @property
    def unmeasured_note(self) -> str:
        names = sorted({event.name for group in self.groups + ([self.loose] if self.loose else [])
                        for event in group.events if not event.measured})
        if not names:
            return ""
        return "non pesés, portés avec leur date seule : %s" % ", ".join(names)


def build(calendar: Optional[Calendar], org=None, directory=None,
          today: Optional[datetime.date] = None, horizon: int = HORIZON_DAYS) -> Review:
    from .month import place_markets

    today = today or datetime.date.today()
    absent: List[str] = []
    if calendar is None:
        from ..config import DEFAULT_GIFTING_FILE

        return Review(today, [], ["%s absent : les temps forts à venir ne sont pas lus" % DEFAULT_GIFTING_FILE])
    absent.extend("calendrier des temps forts, %s" % fault for fault in calendar.faults)
    upcoming = calendar.upcoming(today, horizon)
    beyond = calendar.next_beyond(today, horizon)
    if not upcoming:
        absent.append("aucun temps fort dans les %d prochaines semaines" % (horizon // 7))
        return Review(today, [], absent, horizon=horizon, beyond=beyond)
    markets = sorted({event.market for event in upcoming})
    placed, _leads = place_markets(markets, org, directory)
    by_name: Dict[str, List[Event]] = {}
    loose: List[Event] = []
    for event in upcoming:
        name = placed.get(event.market)
        if name:
            by_name.setdefault(name, []).append(event)
        else:
            loose.append(event)
    groups = [Group(name, events) for name, events in by_name.items()]
    groups.sort(key=lambda group: -sum(event.sales or 0.0 for event in group.events))
    return Review(today, groups, absent, Group("Sans périmètre", loose) if loose else None,
                  horizon, beyond)
