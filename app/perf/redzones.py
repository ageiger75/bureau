"""Les zones rouges : cinq fronts nommés par le lecteur, une ligne chacun, à tenir.

Le moteur de sélection découvre ; il trouve un marché de cent mille euros pendant que le
Japon est le périmètre le plus en retard de l'exercice et que le Travel Retail n'est pas
une ligne de la table. Les zones rouges ne se découvrent pas : le lecteur les a écrites
dans son tableau de suivi, et l'écran les tient, avec le chiffre qu'il sait mesurer.

Elles vivent dans `var/red_zones.csv`, une ligne par zone : le nom, le marché ou le
périmètre, la mesure, une cible facultative, une note. Au plus cinq, et chacune porte une
mesure que le cockpit connaît — sinon elle entre avec la mention « à brancher », jamais
avec un chiffre deviné. Le lecteur en ajoute, en retire ; l'écran suit au chargement.

Les mesures, par leur code dans le fichier :

* `samestore` — le same-store sales du marché, dernier mois et exercice à date ;
* `distribution_cost` — le coût de distribution en part des ventes, contre le budget et le
  même stade l'an dernier, au compte de gestion ;
* `sell_in_channel:<canal>` — le sell-in du canal facturé à date, à jours ouvrés égaux ;
* `retail_ex_bulk` — le marché hors vrac contre tout compris, sur la lecture des KPI ;
* `year_gap` — le verdict de l'exercice à date du périmètre, et celui du mois ;
* `profit_centre:<code>` — un centre de profit en sell-in : pas encore lu, dit tel quel.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional, Sequence

from .analytics import format_eur
from .budget import normalise_market

REQUIRED = ("zone", "scope", "measure")

#: Au plus cinq. Une sixième ligne est lue et dite en trop, jamais rendue.
MOST = 5

SAMESTORE = "samestore"
DISTRIBUTION_COST = "distribution_cost"
SELL_IN_CHANNEL = "sell_in_channel"
RETAIL_EX_BULK = "retail_ex_bulk"
YEAR_GAP = "year_gap"
PROFIT_CENTRE = "profit_centre"
KNOWN = (SAMESTORE, DISTRIBUTION_COST, SELL_IN_CHANNEL, RETAIL_EX_BULK, YEAR_GAP,
         PROFIT_CENTRE)

#: Ce qu'une mesure non branchée dit d'elle-même.
NOT_WIRED = "à brancher"


class Zone:
    """Une ligne du fichier : le front, son périmètre, ce qu'on y mesure."""

    __slots__ = ("name", "scope", "measure", "argument", "target", "note", "line")

    def __init__(self, name: str, scope: str, measure: str, argument: str = "",
                 target: str = "", note: str = "", line: int = 0) -> None:
        self.name = name
        self.scope = scope
        self.measure = measure
        #: Ce qui suit les deux-points dans le code de mesure : un canal, un centre de profit.
        self.argument = argument
        self.target = target
        self.note = note
        self.line = line


class Reading:
    """Une zone rendue : le chiffre en un mot, la phrase, et le sens quand il se lit."""

    __slots__ = ("zone", "word", "sentence", "direction", "wired")

    def __init__(self, zone: Zone, word: str = "", sentence: str = "", direction: str = "",
                 wired: bool = True) -> None:
        self.zone = zone
        self.word = word
        self.sentence = sentence
        #: « en retard », « en avance », vide quand la mesure ne se juge pas.
        self.direction = direction
        self.wired = wired

    @property
    def name(self) -> str:
        return self.zone.name

    @property
    def note(self) -> str:
        return self.zone.note


class Board:
    """Le fichier lu, et ce qu'il n'a pas pu lire."""

    def __init__(self, zones: Sequence[Zone], faults: Sequence[str], path: str = "") -> None:
        self.zones = list(zones)
        self.faults = list(faults)
        self.path = path

    @property
    def is_empty(self) -> bool:
        return not self.zones

    @property
    def shown(self) -> List[Zone]:
        return self.zones[:MOST]


def load(path: str) -> Board:
    """Lire le fichier. Absent : une lecture vide, pas une erreur."""
    if not path or not os.path.exists(path):
        return Board([], [], path)
    zones: List[Zone] = []
    faults: List[str] = []
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            return Board([], ["colonnes manquantes : %s" % ", ".join(missing)], path)
        for number, record in enumerate(reader, start=2):
            name = (record.get("zone") or "").strip()
            scope = (record.get("scope") or "").strip()
            code = (record.get("measure") or "").strip()
            if not name or not scope or not code:
                faults.append("ligne %d : zone, périmètre ou mesure absent" % number)
                continue
            measure, _sep, argument = code.partition(":")
            measure = measure.strip().lower()
            if measure not in KNOWN:
                faults.append("ligne %d : mesure « %s » inconnue du cockpit" % (number, code))
                continue
            zones.append(Zone(name, scope, measure, argument.strip(),
                              (record.get("target") or "").strip(),
                              (record.get("note") or "").strip(), number))
    if len(zones) > MOST:
        faults.append("%d zones dans le fichier : les %d premières sont tenues, le reste attend"
                      % (len(zones), MOST))
    return Board(zones, faults, path)


def current(path: Optional[str] = None) -> Board:
    from ..config import settings

    return load(path or str(settings.red_zones_path))


# ------------------------------------------------------------------------- lecture


def _pct(value: Optional[float]) -> str:
    return "n/d" if value is None else "%+.1f %%" % (value * 100)


def _direction(value: Optional[float], tolerance: float = 0.02) -> str:
    if value is None:
        return ""
    if value < -tolerance:
        return "en retard"
    if value > tolerance:
        return "en avance"
    return "en ligne"


def _samestore(zone: Zone, kpi_rows: Sequence) -> Reading:
    from . import samestore as samestore_module

    grown = samestore_module.build(kpi_rows, scope=zone.scope) if kpi_rows else None
    if grown is None:
        return Reading(zone, "—", "pas de lecture des magasins comparables sur %s" % zone.scope,
                       wired=False)
    reference = grown.ytd_growth if grown.ytd_growth is not None else grown.growth
    text = "same-store sales %s" % grown.sentence
    if zone.target:
        text += " · cible %s" % zone.target
    return Reading(zone, grown.word, text, _direction(reference))


def _distribution_cost(zone: Zone, pnl) -> Reading:
    from . import pnl as pnl_module

    if pnl is None or not getattr(pnl, "usable", False) or pnl.statement is None:
        return Reading(zone, "—", "coût de distribution : compte de gestion non lu", wired=False)
    line = pnl.for_name(zone.scope)
    if line is None:
        return Reading(zone, "—", "coût de distribution : %s sans ligne au compte de gestion"
                       % zone.scope, wired=False)
    before = pnl.statement.perimeter_last_year(zone.scope)
    nature = next((item for item in pnl_module.natures(line, before)
                   if item.name == "distribution"), None)
    if nature is None or nature.share is None:
        return Reading(zone, "—", "coût de distribution : pas de nature distribution sur %s"
                       % zone.scope, wired=False)
    text = ("coût de distribution %s des ventes, contre %s au budget et %s l'an dernier au "
            "même stade : %s (%s)" % (nature.share_label, nature.budget_share_label,
                                       nature.last_year_share_label, nature.cell,
                                       pnl.snapshot.period_label))
    direction = "en retard" if nature.unfavourable else "en ligne"
    return Reading(zone, nature.share_label, text, direction)


def _sell_in_channel(zone: Zone, invoiced) -> Reading:
    wanted = (zone.argument or zone.scope).strip().lower()
    if invoiced is None or not getattr(invoiced, "usable", False):
        return Reading(zone, "—", "sell-in du canal : factures au jour non lues", wired=False)
    line = next((item for item in getattr(invoiced, "channels", ())
                 if item.name.strip().lower() == wanted), None)
    if line is None:
        return Reading(zone, "—", "sell-in du canal : « %s » absent des factures du mois"
                       % (zone.argument or zone.scope), wired=False)
    text = ("sell-in %s facturé à date, %s sur l'an dernier à jours ouvrés égaux (%s à dates "
            "égales)" % (format_eur(line.current), line.growth_label, line.same_dates_label))
    if zone.target:
        text += " · cible %s" % zone.target
    return Reading(zone, line.growth_label, text, _direction(line.growth))


def _retail_ex_bulk(zone: Zone, kpi_rows: Sequence) -> Reading:
    from . import bulk as bulk_module

    if not kpi_rows:
        return Reading(zone, "—", "hors vrac : pas de lecture des KPI", wired=False)
    reading = bulk_module.market_bulk(kpi_rows, zone.scope)
    if reading is None:
        return Reading(zone, "—", "hors vrac : %s absent de la lecture des KPI" % zone.scope,
                       wired=False)
    said = reading.sentence() if callable(reading.sentence) else reading.sentence
    if not reading.comparable:
        return Reading(zone, "—", said, wired=True)
    return Reading(zone, _pct(reading.growth_ex_bulk), said, _direction(reading.growth_ex_bulk))


def _year_gap(zone: Zone, track) -> Reading:
    scope = next((item for item in getattr(track, "perimeters", ()) if item.name == zone.scope),
                 None)
    if scope is None or not scope.year.usable:
        return Reading(zone, "—", "exercice à date : %s sans verdict" % zone.scope, wired=False)
    text = "%s sur l'exercice à date (%s)" % (scope.year.label, scope.year.gap_label)
    if scope.month.usable and not scope.month.early:
        text += ", %s sur le mois (%s)" % (scope.month.label, scope.month.gap_label)
    elif scope.month.usable:
        text += ", mois trop tôt"
    return Reading(zone, scope.year.gap_label, text, scope.year.label)


def _profit_centre(zone: Zone) -> Reading:
    return Reading(zone, NOT_WIRED,
                   "centre de profit %s en sell-in : la requête ne le lit pas encore"
                   % (zone.argument or zone.scope), wired=False)


def build(board: Optional[Board], kpi_rows: Sequence = (), pnl=None, invoiced=None,
          track=None) -> "Review":
    """Chaque zone avec son chiffre, dans l'ordre du fichier. Rien n'est relu ici."""
    if board is None:
        from ..config import DEFAULT_RED_ZONES_FILE

        return Review([], ["%s absent : les zones rouges ne sont pas tenues" % DEFAULT_RED_ZONES_FILE])
    readings: List[Reading] = []
    for zone in board.shown:
        if zone.measure == SAMESTORE:
            readings.append(_samestore(zone, kpi_rows))
        elif zone.measure == DISTRIBUTION_COST:
            readings.append(_distribution_cost(zone, pnl))
        elif zone.measure == SELL_IN_CHANNEL:
            readings.append(_sell_in_channel(zone, invoiced))
        elif zone.measure == RETAIL_EX_BULK:
            readings.append(_retail_ex_bulk(zone, kpi_rows))
        elif zone.measure == YEAR_GAP:
            readings.append(_year_gap(zone, track))
        else:
            readings.append(_profit_centre(zone))
    return Review(readings, list(board.faults))


class Review:
    """Ce que l'écran rend : une ligne par zone, et ce qui manque pour la lire."""

    def __init__(self, readings: Sequence[Reading], absent: Sequence[str]) -> None:
        self.readings = list(readings)
        self.absent = list(absent)

    @property
    def usable(self) -> bool:
        return bool(self.readings)

    @property
    def unwired(self) -> List[Reading]:
        return [item for item in self.readings if not item.wired]
