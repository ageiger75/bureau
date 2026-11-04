"""La balance comptable, lue comme mois clos provisoire.

Le mois précédent n'est publié par la Finance que dans la deuxième semaine, et la
consolidation n'arrive dans l'entrepôt que vers la fin du mois suivant. Entre les deux,
l'écran n'avait rien de clos à dire. La balance comptable porte pourtant le réalisé du
mois dès la fin du mois, entité par entité, canal par canal, au compte parent des ventes
nettes : mesurée sur septembre et octobre 2026 par l'agent entrepôt, elle retrouve le
fichier publié à moins d'un pour cent, les absents nommés.

Ce que ce lecteur fait, et ne fait pas :

* il somme les mois de l'exercice jusqu'au mois précédent, au taux annuel de la maison,
  par marché et canal, et pose en face le plan et l'an dernier du classeur de plan sur
  les mêmes mois et les mêmes entités — jamais le plan d'une entité que la balance ne
  porte pas, pour ne pas compter en écart ce qui n'est pas lu ;
* il dit « provisoire » tant que le mois n'a pas sept jours ouvrés derrière lui — la
  règle a été mesurée sur un seul mois clos, et elle est écrite ici pour être contestée —
  et il date la lecture au dernier rechargement de la table ;
* il nomme les entités du plan que la balance ne porte pas, avec leur plan ;
* il s'efface devant le fichier publié dès que celui-ci parle du mois précédent.

Il ne lit pas le budget ni le reforecast de la balance : le plan est le classeur.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from . import actuals as actuals_module
from .actuals import CHANNELS, HOSPITALITY, SHIPPED, SOLD
from .budget import perimeter_of, segment_code

#: Le mois est tenu pour figé à partir de ce jour ouvré du mois suivant, au matin.
#: Mesuré sur septembre 2026 : figé au soir du sixième. À vérifier sur chaque mois.
FROZEN_FROM_BUSINESS_DAY = 7

#: L'exercice ouvre en avril.
FISCAL_OPENS = 4

MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre")


def _month_name(period: str) -> str:
    try:
        return MONTHS_FR[int(period[5:7]) - 1]
    except (ValueError, IndexError):
        return period


def fiscal_start(period: str) -> str:
    year, month = int(period[:4]), int(period[5:7])
    return "%04d-%02d" % (year if month >= FISCAL_OPENS else year - 1, FISCAL_OPENS)


def months_through(period: str) -> List[str]:
    """Les mois de l'exercice d'avril jusqu'au mois donné, inclus."""
    start = fiscal_start(period)
    year, month = int(start[:4]), int(start[5:7])
    found: List[str] = []
    cursor = start
    while cursor <= period and len(found) < 12:
        found.append(cursor)
        month += 1
        if month > 12:
            year, month = year + 1, 1
        cursor = "%04d-%02d" % (year, month)
    return found


def entity_prefix(code: str) -> str:
    """`M_901_TRA` → `M_901` : l'entité de la balance, sans la pseudo-entité du plan."""
    parts = (code or "").strip().upper().split("_")
    return "_".join(parts[:2]) if len(parts) >= 2 else (code or "").strip().upper()


def business_days_after(month: str, today: datetime.date) -> int:
    """Les jours ouvrés écoulés depuis la fin du mois, le jour même compris."""
    year, number = int(month[:4]), int(month[5:7])
    first_next = datetime.date(year + (number // 12), number % 12 + 1, 1)
    count = 0
    cursor = first_next
    while cursor <= today:
        if cursor.weekday() < 5:
            count += 1
        cursor += datetime.timedelta(days=1)
    return count


def _number(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _basis(code: str) -> str:
    kind = perimeter_of(code)
    if kind == "sell-in":
        return SHIPPED
    if kind == "b2b":
        return HOSPITALITY
    return SOLD


class Reading(actuals_module.Actuals):
    """La lecture, dans la forme du fichier publié, avec ce que le fichier n'a pas à dire :
    qu'elle est provisoire, de quand elle date, et qui manque."""

    __slots__ = ("months", "loaded_at", "status", "absent", "outside", "unplaced",
                 "provisional", "business_days")

    def __init__(self, lines, faults, year, month, months: Sequence[str], loaded_at: str,
                 business_days: int, absent: Sequence[Tuple[str, float]],
                 unplaced: Sequence[str], outside: Sequence[Tuple[str, float]] = ()) -> None:
        super().__init__(lines, faults, path="balance", sheet="", year=year, month=month)
        self.months = list(months)
        self.loaded_at = loaded_at
        self.business_days = business_days
        self.provisional = business_days < FROZEN_FROM_BUSINESS_DAY
        self.status = (("provisoire, %d jour%s ouvré%s après la fin du mois" % (
            business_days, "s" if business_days > 1 else "", "s" if business_days > 1 else ""))
            if self.provisional else
            "tenue pour figée, %d jours ouvrés après la fin du mois — règle mesurée sur un "
            "seul mois" % business_days)
        #: Les entités du plan que la balance ne porte pas sur ces mois alors qu'elle les a
        #: déjà portées : pas encore chargées, avec leur plan.
        self.absent = list(absent)
        #: Les entités du plan que la balance n'a jamais portées, sur aucun mois lu : hors
        #: de la balance, à lire dans le fichier publié ou la consolidation. Un marché tenu
        #: par un distributeur n'a pas ses comptes dans le grand livre du groupe.
        self.outside = list(outside)
        #: Les entités de la balance que le plan ne nomme pas, affichées sous leur code.
        self.unplaced = list(unplaced)

    @property
    def source_label(self) -> str:
        return "balance comptable"

    @property
    def caveat(self) -> str:
        from .analytics import format_eur

        if not self.months:
            return ""
        text = ("Mois clos lu dans la balance comptable, %s, rechargée le %s : %s"
                % (self.status, self.loaded_at or "à une heure inconnue",
                   "elle se lit comme un provisoire, le fichier publié la remplacera dès son dépôt"
                   if self.provisional else "le fichier publié la remplacera dès son dépôt"))
        if self.outside:
            text += " · hors de la balance, jamais chargés, à lire dans le fichier publié : %s" % ", ".join(
                "%s (%s au plan)" % (name, format_eur(amount)) for name, amount in self.outside)
        if self.absent:
            text += " · pas encore chargés pour %s : %s" % (_month_name(self.period), ", ".join(
                "%s (%s au plan)" % (name, format_eur(amount)) for name, amount in self.absent))
        if self.unplaced:
            text += " · sans ligne au plan, sous leur code : %s" % ", ".join(self.unplaced)
        return text + "."


def build(rows: Sequence[dict], budget, through: str,
          today: Optional[datetime.date] = None) -> Reading:
    """Lit la balance jusqu'au mois `through` (`AAAA-MM`), sur les mois de l'exercice.

    `rows` est le contrat de `BALANCE_MONTH` : `month · entity · channel · currency ·
    amount_local · amount_eur · loaded_at`. `budget` est le classeur de plan, qui donne le
    marché de chaque entité, le plan et l'an dernier.
    """
    today = today or datetime.date.today()
    year, month = int(through[:4]), int(through[5:7])
    wanted = months_through(through)
    present = {str(row.get("month") or "")[:7] for row in rows}
    faults: List[str] = []
    if through not in present:
        faults.append("la balance ne porte pas encore %s" % _month_name(through))
    missing = [m for m in wanted if m not in present and m != through]
    if missing:
        faults.append("mois sans ligne dans la balance : %s" % ", ".join(_month_name(m) for m in missing))
    loaded_at = ""
    for row in rows:
        stamp = str(row.get("loaded_at") or "")
        if stamp > loaded_at:
            loaded_at = stamp
    # Le plan sur ces mois : par entité, mois et segment, les marchés qu'il nomme et leur
    # plan. Au grain du mois, parce que la balance se remplit par paquets : une entité
    # présente en septembre et muette en octobre a un plan d'octobre qu'il ne faut pas lui
    # opposer.
    by_key: Dict[Tuple[str, str], Dict[str, Tuple[float, float]]] = {}
    plan_lines: List[Tuple[str, str, str, str, float, float]] = []
    plan_by_entity_month: Dict[Tuple[str, str], float] = {}
    market_of_entity: Dict[str, Dict[str, float]] = {}
    for line in getattr(budget, "lines", None) or ():
        period = getattr(line, "period", "")
        if period not in wanted:
            continue
        prefix = entity_prefix(getattr(line, "entity", "") or "")
        if not prefix:
            continue
        code = segment_code(str(getattr(line, "segment", "") or ""))
        planned = float(getattr(line, "budget", 0.0) or 0.0)
        last = float(getattr(line, "last_year", 0.0) or 0.0)
        held = by_key.setdefault((prefix, code), {}).get(line.market, (0.0, 0.0))
        by_key[(prefix, code)][line.market] = (held[0] + planned, held[1] + last)
        plan_lines.append((prefix, period, code, line.market, planned, last))
        plan_by_entity_month[(prefix, period)] = plan_by_entity_month.get((prefix, period), 0.0) + planned
        weights = market_of_entity.setdefault(prefix, {})
        weights[line.market] = weights.get(line.market, 0.0) + abs(planned)
    seen_entities = set()
    ever_seen = {entity_prefix(str(row.get("entity") or "")) for row in rows}
    entity_months_seen = {(entity_prefix(str(row.get("entity") or "")), str(row.get("month") or "")[:7])
                          for row in rows}
    actual_by: Dict[Tuple[str, str], float] = {}
    unplaced: List[str] = []
    for row in rows:
        period = str(row.get("month") or "")[:7]
        if period not in wanted:
            continue
        entity = entity_prefix(str(row.get("entity") or ""))
        code = str(row.get("channel") or "").strip().upper()
        amount = _number(row.get("amount_eur"))
        if not entity or amount is None:
            continue
        seen_entities.add(entity)
        candidates = by_key.get((entity, code)) or {}
        if candidates:
            market = max(candidates, key=lambda name: abs(candidates[name][0]))
        elif market_of_entity.get(entity):
            weights = market_of_entity[entity]
            market = max(weights, key=lambda name: weights[name])
        else:
            market = entity
            if entity not in unplaced:
                unplaced.append(entity)
        actual_by[(market, code)] = actual_by.get((market, code), 0.0) + amount
    # Le plan en face d'un marché présent est celui de ses entités, mois par mois, là où
    # la balance les porte. Une entité que la balance n'a jamais vue mais dont le marché
    # est présent — les boutiques d'aéroport sous la société mère — est comptée sur les
    # mois où le marché l'est, pas déclarée absente. Une entité déjà vue et muette sur un
    # mois est « pas encore chargée » pour ce mois, et son plan de ce mois n'est pas
    # opposé. Un marché que la balance n'a jamais porté n'entre pas au plan : hors de la
    # balance, nommé avec son plan.
    present_markets = {market for market, _code in actual_by}
    months_seen_for_market: Dict[str, set] = {}
    for prefix, period in entity_months_seen:
        if period not in wanted:
            continue
        for name in (market_of_entity.get(prefix) or {}):
            months_seen_for_market.setdefault(name, set()).add(period)
    plan_for: Dict[Tuple[str, str], Tuple[float, float]] = {}
    for prefix, period, code, market, planned, last in plan_lines:
        if prefix in ever_seen:
            counted = (prefix, period) in entity_months_seen
        else:
            counted = market in present_markets and period in months_seen_for_market.get(market, set())
        if not counted:
            continue
        held = plan_for.get((market, code), (0.0, 0.0))
        plan_for[(market, code)] = (held[0] + planned, held[1] + last)
    lines: List[actuals_module.Line] = []
    for (market, code), actual in sorted(actual_by.items()):
        planned, last = plan_for.get((market, code), (0.0, 0.0))
        lines.append(actuals_module.Line(market, "", CHANNELS.get(code, code.lower()),
                                         _basis(code), actual, last, planned))
    absent: List[Tuple[str, float]] = []
    outside: List[Tuple[str, float]] = []
    late: Dict[str, float] = {}
    never: Dict[str, float] = {}
    for (prefix, period), planned in plan_by_entity_month.items():
        if planned <= 0:
            continue
        weights = market_of_entity.get(prefix) or {}
        name = max(weights, key=lambda key: weights[key]) if weights else prefix
        if prefix in ever_seen:
            if (prefix, period) not in entity_months_seen:
                late[name] = late.get(name, 0.0) + planned
        elif name not in present_markets:
            never[name] = never.get(name, 0.0) + planned
    absent = sorted(late.items(), key=lambda item: -item[1])
    outside = sorted(never.items(), key=lambda item: -item[1])
    if not lines and not faults:
        faults.append("aucune ligne de la balance sur %s" % ", ".join(_month_name(m) for m in wanted))
    return Reading(lines, faults, year, month, [m for m in wanted if m in present], loaded_at,
                   business_days_after(through, today), absent, sorted(unplaced), outside=outside)


# ------------------------------------------------------------------- la vérification


class Check:
    """La requête du cockpit contre l'extrait de référence de l'agent entrepôt, au centime."""

    __slots__ = ("months", "same", "differing", "only_here", "only_there")

    def __init__(self) -> None:
        self.months: List[str] = []
        self.same: Dict[str, int] = {}
        self.differing: List[Tuple[str, str, str, float, float]] = []
        self.only_here: List[Tuple[str, str, str, float]] = []
        self.only_there: List[Tuple[str, str, str, float]] = []

    def identical(self, month: str) -> bool:
        return (self.same.get(month, 0) > 0
                and not any(item[0] == month for item in self.differing)
                and not any(item[0] == month for item in self.only_here)
                and not any(item[0] == month for item in self.only_there))

    def sentence(self, month: str) -> str:
        if self.identical(month):
            return "%s : identique au centime sur %d couples" % (_month_name(month), self.same[month])
        moved = [item for item in self.differing if item[0] == month]
        here = [item for item in self.only_here if item[0] == month]
        there = [item for item in self.only_there if item[0] == month]
        return ("%s : %d couples identiques, %d qui diffèrent, %d que le cockpit seul lit, %d que "
                "la référence seule porte" % (_month_name(month), self.same.get(month, 0),
                                              len(moved), len(here), len(there)))


def compare_reference(rows: Sequence[dict], reference: Sequence[dict]) -> Check:
    """`(month, entity, channel)` → `amount_eur`, des deux côtés, au centime."""
    def keyed(items):
        found: Dict[Tuple[str, str, str], float] = {}
        for item in items:
            key = (str(item.get("month") or "")[:7], entity_prefix(str(item.get("entity") or "")),
                   str(item.get("channel") or "").strip().upper())
            amount = _number(item.get("amount_eur"))
            if amount is not None:
                found[key] = found.get(key, 0.0) + amount
        return found

    here, there = keyed(rows), keyed(reference)
    # Un couple dont la somme est nulle n'est porté par aucun extrait de référence, qui
    # ne garde que les lignes non nulles : rien à comparer, d'un côté comme de l'autre.
    here = {key: amount for key, amount in here.items() if abs(amount) >= 0.005}
    there = {key: amount for key, amount in there.items() if abs(amount) >= 0.005}
    check = Check()
    # La référence est un extrait de quelques mois ; la comparaison porte sur ces mois-là,
    # jamais sur ce que le cockpit lit en plus.
    check.months = sorted({key[0] for key in there})
    for key, amount in sorted(there.items()):
        if key not in here:
            check.only_there.append((key[0], key[1], key[2], amount))
        elif abs(here[key] - amount) < 0.005:
            check.same[key[0]] = check.same.get(key[0], 0) + 1
        else:
            check.differing.append((key[0], key[1], key[2], here[key], amount))
    for key, amount in sorted(here.items()):
        if key[0] in check.months and key not in there:
            check.only_here.append((key[0], key[1], key[2], amount))
    return check
