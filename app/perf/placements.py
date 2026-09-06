"""Les placements décidés : un marché rangé sous un périmètre par décision, pour un temps.

L'annuaire dit l'organisation telle qu'elle est ; le compte de gestion, telle qu'il la
mesure ; et les deux ne bougent pas le même jour. Quand le CEO décide qu'un marché reste
sous son ancien périmètre jusqu'à la fin de l'exercice — pour comparer à périmètre
constant — cette décision n'a sa place ni dans le classeur de l'annuaire, qu'on ne réécrit
pas pour un temps, ni dans le code, qui ne porte aucun nom réel. Elle vit dans
`var/placements.csv` : un marché, un périmètre, une date de fin, une raison.

Le fichier s'applique par-dessus l'annuaire et l'organigramme, jamais à leur place : il ne
dit rien des marchés qu'il ne nomme pas. Une ligne dont la date est passée ne s'applique
plus et l'écran le dit, pour que la décision ne survive pas en silence à son échéance.
"""

from __future__ import annotations

import csv
import io
import os
from datetime import date
from typing import Dict, List, Optional

REQUIRED = ("market", "perimeter")


class Rule:
    __slots__ = ("market", "perimeter", "until", "reason", "line")

    def __init__(self, market: str, perimeter: str, until: str, reason: str, line: int) -> None:
        self.market = market
        self.perimeter = perimeter
        self.until = until
        self.reason = reason
        self.line = line

    def active(self, today: date) -> bool:
        if not self.until:
            return True
        try:
            return today <= date.fromisoformat(self.until)
        except ValueError:
            return False

    @property
    def label(self) -> str:
        text = "%s → %s" % (self.market, self.perimeter)
        if self.until:
            text += " jusqu'au %s" % self.until
        if self.reason:
            text += " (%s)" % self.reason
        return text


class Placements:
    """Le fichier lu : les règles en vigueur, celles qui ont expiré, les défauts."""

    def __init__(self, rules: List[Rule], faults: List[str], today: date, path: str = "") -> None:
        self.rules = rules
        self.faults = faults
        self.today = today
        self.path = path

    @property
    def active(self) -> Dict[str, Rule]:
        return {rule.market: rule for rule in self.rules if rule.active(self.today)}

    @property
    def expired(self) -> List[Rule]:
        return [rule for rule in self.rules if not rule.active(self.today)]

    @property
    def is_empty(self) -> bool:
        return not self.rules

    def perimeter_of(self, market: str) -> Optional[str]:
        rule = self.active.get(market)
        return rule.perimeter if rule is not None else None

    def apply(self, placed: Dict[str, str]) -> Dict[str, str]:
        """Le dictionnaire marché → périmètre, avec les décisions par-dessus."""
        for market, rule in self.active.items():
            placed[market] = rule.perimeter
        return placed

    @property
    def notes(self) -> List[str]:
        """Ce que l'écran dit : les décisions en vigueur, puis celles qui ont expiré."""
        said = ["Placement décidé : %s." % rule.label for rule in self.active.values()]
        said.extend("Placement expiré, plus appliqué : %s." % rule.label for rule in self.expired)
        return said


def load(path: str, today: Optional[date] = None) -> Placements:
    today = today or date.today()
    if not path or not os.path.exists(path):
        return Placements([], [], today, path)
    rules: List[Rule] = []
    faults: List[str] = []
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            return Placements([], ["colonnes manquantes : %s" % ", ".join(missing)], today, path)
        for number, record in enumerate(reader, start=2):
            market = (record.get("market") or "").strip()
            perimeter = (record.get("perimeter") or "").strip()
            if not market or not perimeter:
                faults.append("ligne %d : marché ou périmètre absent" % number)
                continue
            until = (record.get("until") or "").strip()
            if until:
                try:
                    date.fromisoformat(until)
                except ValueError:
                    faults.append("ligne %d : date « %s » illisible, attendu AAAA-MM-JJ"
                                  % (number, until))
                    continue
            rules.append(Rule(market, perimeter, until, (record.get("reason") or "").strip(),
                              number))
    return Placements(rules, faults, today, path)


_loaded: Optional[Placements] = None
_loaded_from = None


def current() -> Placements:
    """Le fichier en vigueur, relu quand il a changé ou quand le jour a changé."""
    global _loaded, _loaded_from
    from ..config import settings

    path = settings.placements_path
    today = date.today()
    try:
        stamp = (str(path), path.stat().st_mtime if path.exists() else None, today)
    except OSError:
        stamp = (str(path), None, today)
    if _loaded is None or stamp != _loaded_from:
        _loaded = load(str(path), today) if stamp[1] is not None else Placements([], [], today, str(path))
        _loaded_from = stamp
    return _loaded


def reset() -> None:
    global _loaded, _loaded_from
    _loaded = None
    _loaded_from = None
