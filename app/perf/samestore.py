"""Le same-store sales, deuxième chiffre du board, lu dans ce que le cockpit lit déjà.

La requête des KPI rend chaque mois, au niveau du groupe et par pays, les ventes des
boutiques comparables — le drapeau « magasin comparable » de l'entrepôt, posé sur la
boutique, donc valable pour les deux exercices. Ce module en tire une croissance : le
dernier mois complet contre le même mois l'an dernier, et l'exercice à date contre les
mêmes mois de l'exercice précédent.

Ce qu'il ne fait pas, et le dit : le vrac n'est pas retiré (la clé « hors vrac » de la
requête porte sur toutes les ventes, pas sur les comparables), et « hors cleaning » au sens
du board demande une clé que l'entrepôt n'écrit pas encore. Le chiffre est donc « magasins
comparables, vrac compris », et il est nommé ainsi.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from . import kpi_registry
from .weekly import MONTHS_FR

KEY = "same_store_sales"

#: L'exercice ouvre en avril.
FISCAL_OPENS = 4


def _fiscal_year(period: str) -> int:
    year, month = int(period[:4]), int(period[5:7])
    return year + 1 if month >= FISCAL_OPENS else year


def _shift(period: str, months: int) -> str:
    year, month = int(period[:4]), int(period[5:7])
    index = year * 12 + (month - 1) + months
    return "%04d-%02d" % (index // 12, index % 12 + 1)


def _growth(now: float, before: Optional[float]) -> Optional[float]:
    if before is None or before == 0:
        return None
    return now / before - 1.0


def _label(value: Optional[float]) -> str:
    return "n/d" if value is None else "%+.1f %%" % (value * 100)


def _month_fr(period: str) -> str:
    try:
        return "%s %s" % (MONTHS_FR[int(period[5:7]) - 1], period[:4])
    except (ValueError, IndexError):
        return period


class Growth:
    """Un périmètre : le dernier mois complet et l'exercice à date, contre l'an dernier."""

    __slots__ = ("scope", "period", "sales", "last_year", "ytd_sales", "ytd_last_year",
                 "months", "missing")

    def __init__(self, scope: str, period: str, sales: float, last_year: Optional[float],
                 ytd_sales: float, ytd_last_year: Optional[float], months: int,
                 missing: Sequence[str] = ()) -> None:
        self.scope = scope
        self.period = period
        self.sales = sales
        self.last_year = last_year
        self.ytd_sales = ytd_sales
        self.ytd_last_year = ytd_last_year
        #: Les mois de l'exercice que le cumul porte.
        self.months = months
        #: Les mois de l'exercice sans lecture l'an dernier, donc hors du cumul comparé.
        self.missing = list(missing)

    @property
    def growth(self) -> Optional[float]:
        return _growth(self.sales, self.last_year)

    @property
    def ytd_growth(self) -> Optional[float]:
        return _growth(self.ytd_sales, self.ytd_last_year)

    @property
    def growth_label(self) -> str:
        return _label(self.growth)

    @property
    def ytd_growth_label(self) -> str:
        return _label(self.ytd_growth)

    @property
    def month_label(self) -> str:
        return _month_fr(self.period)

    @property
    def ytd_label(self) -> str:
        """« avril à août »."""
        first = "%04d-%02d" % (_fiscal_year(self.period) - 1, FISCAL_OPENS)
        return "%s à %s" % (MONTHS_FR[int(first[5:7]) - 1], MONTHS_FR[int(self.period[5:7]) - 1])

    @property
    def word(self) -> str:
        """Le chiffre de l'exercice, ou du mois quand l'exercice ne se compare pas."""
        return self.ytd_growth_label if self.ytd_growth is not None else self.growth_label

    @property
    def sentence(self) -> str:
        text = "%s en %s" % (self.growth_label, self.month_label)
        if self.ytd_growth is not None:
            text += ", %s sur l'exercice à date (%s)" % (self.ytd_growth_label, self.ytd_label)
        text += " · magasins comparables, sell-out, vrac compris"
        if self.missing:
            text += " · sans l'an dernier sur %s" % ", ".join(_month_fr(m) for m in self.missing)
        return text


def build(rows: Sequence, scope: str = kpi_registry.GROUP_SCOPE) -> Optional[Growth]:
    """La croissance à périmètre comparable d'un périmètre, ou None sans lecture.

    Le dernier mois est le plus récent que la requête porte ; le cumul va d'avril à ce
    mois, et ne compare que les mois qui existent des deux côtés.
    """
    readings = kpi_registry.readings_by_key(rows, scope=scope).get(KEY, [])
    by_period: Dict[str, float] = {}
    for reading in readings:
        period = str(reading.period)[:7]
        if len(period) == 7 and period[4] == "-":
            by_period[period] = reading.value
    if not by_period:
        return None
    latest = max(by_period)
    sales = by_period[latest]
    last_year = by_period.get(_shift(latest, -12))
    first = "%04d-%02d" % (_fiscal_year(latest) - 1, FISCAL_OPENS)
    ytd_sales, ytd_last, months, missing = 0.0, 0.0, 0, []
    period = first
    compared = False
    while period <= latest:
        value = by_period.get(period)
        before = by_period.get(_shift(period, -12))
        if value is not None:
            months += 1
            if before is not None:
                ytd_sales += value
                ytd_last += before
                compared = True
            else:
                missing.append(period)
        period = _shift(period, 1)
    return Growth(scope, latest, sales, last_year, ytd_sales,
                  ytd_last if compared else None, months, missing)


def by_scopes(rows: Sequence, scopes: Sequence[str]) -> List[Growth]:
    found = []
    for scope in scopes:
        grown = build(rows, scope=scope)
        if grown is not None:
            found.append(grown)
    return found
