"""Une frontière datée dans les comptes, lue sur les factures.

Une note de reclassement dit : le plan et les comptes rangent ce chiffre sous des segments
différents. Le cockpit la croit — c'est une décision du lecteur, avec sa source — et sort
le sujet des conversations commerciales. Mais une note n'a pas de fin : écrite en
septembre sur un centre de profit, elle éteignait encore le canal en août suivant, alors
que le centre nommé ne facturait plus depuis le printemps et que le même partenaire était
passé sur un autre centre, dans le canal où le plan l'attendait. Le reste — un e-retailer
qui recule d'un an sur l'autre — dormait sous l'étiquette « aucune action du CEO ».

Ce module ne juge pas la note. Il la date : le centre de profit qu'elle nomme facture-t-il
encore sur le mois affiché ; sinon, depuis quand se tait-il, et le même partenaire
facture-t-il ailleurs, sur quel canal, pour combien ce mois. À partir du mois où le centre
se tait, la note cesse de s'appliquer : ce qui reste sur chaque canal est un écart au plan
par lui-même, quel que soit le côté où le plan range le partenaire — le chiffre déplacé est
entièrement d'un côté, et le canal qui garde un écart le garde pour ses propres raisons.

Et il signale ce que personne n'a noté : un centre de profit apparu cette année dans le même
canal, sans an dernier, est une seconde frontière sans note.

Les codes de centres de profit ne vivent qu'ici en tant que motif ; aucun n'est écrit dans
le dépôt. Les noms des partenaires viennent du fichier du lecteur, jamais du code.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

from .accounts import _mended, _shift, fiscal_start
from .analytics import format_eur
from .mapping import CHANNEL_NAMES

#: Un code de centre de profit tel que l'entrepôt les écrit : trois chiffres puis des
#: capitales. Lu dans le texte ou la source d'une note.
CODE = re.compile(r"\b\d{3}[A-Z][A-Z0-9]{3,}\b")

#: Un centre de destination dont la première facture tombe au plus tard ce nombre de mois
#: avant que l'ancien se taise est la suite du même partenaire ; plus tôt, ce sont deux
#: centres qui ont coexisté, et la migration n'en est pas une.
OVERLAP_MONTHS = 3


def codes_in(*texts: str) -> List[str]:
    found: List[str] = []
    for text in texts:
        for match in CODE.findall(text or ""):
            if match not in found:
                found.append(match)
    return found


class Centre:
    __slots__ = ("code", "label", "channel", "months", "by_country")

    def __init__(self, code: str, label: str, channel: str) -> None:
        self.code = code
        self.label = label
        self.channel = channel
        self.months: Dict[str, float] = {}
        #: Les mêmes mois, par pays de facturation : un centre facturé de deux pays est
        #: deux histoires, et une migration se lit sur le pays qui bouge.
        self.by_country: Dict[str, Dict[str, float]] = {}

    @property
    def countries(self) -> set:
        return set(self.by_country)

    def months_in(self, countries) -> Dict[str, float]:
        """Les mois, restreints à des pays de facturation ; tous sans restriction."""
        if not countries or not self.by_country:
            return self.months
        found: Dict[str, float] = {}
        for iso2 in countries:
            for period, value in self.by_country.get(iso2, {}).items():
                found[period] = found.get(period, 0.0) + value
        return found

    @staticmethod
    def _active(months: Dict[str, float]) -> List[str]:
        return sorted(m for m, v in months.items() if v > 0)

    @property
    def active(self) -> List[str]:
        return self._active(self.months)

    @property
    def first(self) -> str:
        active = self.active
        return active[0] if active else ""

    @property
    def last(self) -> str:
        active = self.active
        return active[-1] if active else ""

    def first_in(self, countries) -> str:
        active = self._active(self.months_in(countries))
        return active[0] if active else ""

    def identity(self, names: Dict[str, str]) -> str:
        known = names.get(self.code.upper())
        if known:
            return known.strip().lower()
        return _mended(self.label or "").strip().lower()


class Reading:
    """Ce que les factures disent d'une note : le centre nommé, et ce qu'il est devenu."""

    __slots__ = ("code", "channel", "period", "last", "closed_since", "destination",
                 "destination_channel", "destination_since", "moved", "newcomers")

    def __init__(self, code: str, channel: str, period: str, last: str) -> None:
        self.code = code
        self.channel = channel
        self.period = period
        self.last = last
        #: Le premier mois sans facture sur ce centre, quand il précède le mois affiché.
        self.closed_since = ""
        self.destination = ""
        self.destination_channel = ""
        self.destination_since = ""
        self.moved: Optional[float] = None
        #: (code, libellé, montant du mois) des centres apparus cette année dans le canal.
        self.newcomers: List[tuple] = []

    @property
    def closed(self) -> bool:
        return bool(self.closed_since)

    @property
    def sentence(self) -> str:
        if not self.closed:
            return ""
        text = "le centre %s ne facture plus depuis %s" % (self.code, _month(self.closed_since))
        if self.destination:
            text += " ; le même partenaire facture sur le centre %s en %s depuis %s" % (
                self.destination, CHANNEL_NAMES.get(self.destination_channel,
                                                    self.destination_channel.upper()),
                _month(self.destination_since))
            if self.moved:
                text += ", %s sur %s" % (format_eur(self.moved), _month(self.period))
        text += (". La frontière est datée dans les comptes : à partir de là, ce qui reste "
                 "sur chaque canal s'écarte du plan par lui-même")
        if self.newcomers:
            listed = ", ".join("%s (%s, %s)" % (code, label or "sans libellé", format_eur(amount))
                               for code, label, amount in self.newcomers[:3])
            text += (". Et dans le même canal, sans note : %s, apparu cette année sans an "
                     "dernier" % listed)
        return text


def _month(period: str) -> str:
    months = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
              "septembre", "octobre", "novembre", "décembre"]
    try:
        return "%s %s" % (months[int(period[5:7]) - 1], period[:4])
    except (ValueError, IndexError):
        return period


def _centres(rows: Sequence[dict], before: str) -> Dict[str, Centre]:
    centres: Dict[str, Centre] = {}
    for row in rows:
        period = str(row.get("period") or "").strip()[:7]
        code = str(row.get("code") or "").strip().upper()
        if not period or not code or (before and period >= before):
            continue
        try:
            value = float(row.get("net_eur") or 0.0)
        except (TypeError, ValueError):
            continue
        centre = centres.get(code)
        if centre is None:
            centre = centres[code] = Centre(code, str(row.get("label") or ""),
                                            str(row.get("channel") or "").strip().lower())
        centre.months[period] = centre.months.get(period, 0.0) + value
        iso2 = str(row.get("iso2") or "").strip().upper()
        if iso2:
            country = centre.by_country.setdefault(iso2, {})
            country[period] = country.get(period, 0.0) + value
    return centres


def read(code: str, centres: Dict[str, Centre], names: Dict[str, str], period: str
         ) -> Optional[Reading]:
    """Ce que les factures disent d'un centre nommé, sur le mois affiché."""
    centre = centres.get(code.upper())
    if centre is None or not centre.last:
        return None
    reading = Reading(centre.code, centre.channel, period, centre.last)
    if centre.months.get(period, 0.0) > 0 or centre.last >= period:
        return reading
    reading.closed_since = _shift(centre.last, 1)
    identity = centre.identity(names)
    # La migration se lit sur les pays de facturation du centre qui s'est tu : le centre
    # de destination peut facturer un autre pays depuis des années, et ce n'est pas lui
    # qui a bougé.
    countries = centre.countries
    threshold = _shift(reading.closed_since, -OVERLAP_MONTHS)
    candidates = []
    for other in centres.values():
        if other.code == centre.code or other.channel == centre.channel:
            continue
        if other.identity(names) != identity:
            continue
        first = other.first_in(countries)
        amount = other.months_in(countries).get(period, 0.0)
        if first and first >= threshold and amount > 0:
            candidates.append((amount, first, other))
    if candidates:
        amount, first, best = max(candidates, key=lambda item: item[0])
        reading.destination = best.code
        reading.destination_channel = best.channel
        reading.destination_since = first
        reading.moved = amount
    start = fiscal_start(period)
    for other in centres.values():
        if other.code == centre.code or other.channel != centre.channel:
            continue
        if other.identity(names) == identity:
            continue
        first = other.first_in(countries)
        amount = other.months_in(countries).get(period, 0.0)
        if first and first >= start and amount > 0:
            reading.newcomers.append((other.code, _mended(other.label or "").title(), amount))
    reading.newcomers.sort(key=lambda item: -item[2])
    return reading


def apply(notes: Sequence, rows: Sequence[dict], names: Optional[Dict[str, str]],
          period: str, today=None) -> List[Reading]:
    """Dater chaque note de reclassement contre les factures, et le poser sur la note.

    `closed_since` fait cesser la note à partir de ce mois (voir `Note.applies_to`) ;
    `boundary` porte la lecture pour le panneau des frontières. Une note sans code, ou
    dont le code ne facture pas dans la lecture, reste ce qu'elle était.
    """
    import datetime

    from .context import RECLASSIFIED

    names = {str(k).strip().upper(): v for k, v in (names or {}).items()}
    current_month = (today or datetime.date.today()).strftime("%Y-%m")
    centres = _centres(rows, current_month) if rows else {}
    readings: List[Reading] = []
    for note in notes:
        if getattr(note, "kind", "") != RECLASSIFIED:
            continue
        note.closed_since = ""
        note.boundary = None
        if not centres or not period:
            continue
        # Le code vit où le lecteur l'a écrit : le texte, la source, ou « qui agit » —
        # la note américaine le portait dans ce dernier champ, et le panneau le lisait.
        for code in codes_in(note.text, note.source, getattr(note, "action_owner", ""),
                             getattr(note, "asked", "")):
            reading = read(code, centres, names, period)
            if reading is None:
                continue
            note.boundary = reading
            if reading.closed:
                note.closed_since = reading.closed_since
            readings.append(reading)
            break
    return readings
