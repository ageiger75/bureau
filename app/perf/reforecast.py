"""Le dernier reforecast de la Finance, lu comme un millésime — jamais comme le plan.

Le plan de cet écran est le budget : il ne bouge pas quand l'année devient dure, et c'est
ce qui le rend mesurable (`provenance.py`). Un reforecast est autre chose : l'avis de la
Finance, à une date, sur la fin de l'exercice — réalisé jusqu'à un mois, figé sur le
dernier, prévu ensuite. Il est lu ici pour être posé à côté du plan, entité par entité et
canal par canal, et pour une chose que le cumul ne dit pas : la Finance phase l'année, et
un second semestre peut s'inverser derrière un premier semestre fort.

Ce que le fichier dit et ne dit pas, appris sur le reforecast 2 (26 octobre 2026) : sa
feuille `DATABASE REF2` a les colonnes du classeur du plan, mais ses mois s'écrivent
autrement (`BUDGET - 2026 APR`, `REF2 - 2026 APR`, `ACT - 2025 APR`), avec des
irrégularités — l'espace manque avant le tiret (`BUDGET- 2026 SEP`), le budget de janvier
à mars s'écrit `2027.JAN - 2027 JAN` sans le mot budget, le mois figé s'écrit `REF2 - SEPT
FY27` sans année — et l'en-tête ne distingue pas un mois réalisé d'un mois figé ni d'une
prévision : tous s'appellent `REF2`. Le partage est donc une règle de ce lecteur, dite à
l'écran : un reforecast numéro n couvre 3n mois réalisés, dont le dernier est figé à la
date du reforecast et n'est pas le réel publié ; le reste est prévision.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from . import memo
from .budget import (BRAND_COLUMNS, MONTHS, THOUSANDS, channel_of, entity_code,
                     normalise_market, perimeter_of)
from .track import FISCAL_OPENS
from .xlsx import Workbook, WorkbookError

#: La feuille utile commence par ce mot : `DATABASE REF2`, `DATABASE REF3` un jour.
SHEET_PREFIX = "DATABASE"

BUDGET = "budget"
FORECAST = "reforecast"
ACTUAL = "actual"

#: Les mois tels que le fichier les écrit — trois formes, et les deux du classeur du plan.
_WORDED = re.compile(r"^(BUDGET|ACT|REF\d*)\s*-\s*(\d{4})\s+([A-Z]{3,9})$")
_FISCAL = re.compile(r"^(REF\d*)\s*-\s*([A-Z]{3,9})\s+FY\s?(\d{2,4})$")
_DOTTED = re.compile(r"^(\d{4})\.([A-Z]{3})\s*-\s*\d{4}\s+[A-Z]{3,9}$")
_PLAN_FORM = re.compile(r"^BUDGET\s+(\d{4})\.([A-Z]{3})$")
_ACTUAL_FORM = re.compile(r"^(\d{4})\.([A-Z]{3})$")

MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre")

#: Le réalisé d'un reforecast numéro n : 3n mois, le dernier figé. Appris sur le deuxième.
MONTHS_PER_REFORECAST = 3


def _clean(text) -> str:
    return " ".join(str(text or "").replace("\xa0", " ").split()).strip()


def _month(token: str) -> Optional[int]:
    return MONTHS.get(token[:3].upper())


def fiscal_start(period: str) -> str:
    year, month = int(period[:4]), int(period[5:7])
    return "%04d-%02d" % (year if month >= FISCAL_OPENS else year - 1, FISCAL_OPENS)


def fiscal_periods(start: str) -> List[str]:
    year, month = int(start[:4]), int(start[5:7])
    return ["%04d-%02d" % (year + (month + offset - 1) // 12, (month + offset - 1) % 12 + 1)
            for offset in range(12)]


def column_meaning(name) -> Optional[Tuple[str, str, str]]:
    """`(sorte, mois, millésime)` d'un en-tête de colonne, ou None quand ce n'est pas un
    mois — un trimestre, un total, un écart. La sorte est budget, reforecast ou actual ;
    le millésime est le mot du fichier (`REF2`) sur les colonnes du reforecast."""
    text = _clean(name).upper()
    found = _WORDED.match(text)
    if found:
        word, year, month = found.groups()
        number = _month(month)
        if number is None:
            return None
        period = "%s-%02d" % (year, number)
        if word == "BUDGET":
            return (BUDGET, period, "")
        if word == "ACT":
            return (ACTUAL, period, "")
        return (FORECAST, period, word)
    found = _FISCAL.match(text)
    if found:
        word, month, fiscal = found.groups()
        number = _month(month)
        if number is None:
            return None
        end = int(fiscal) if len(fiscal) == 4 else 2000 + int(fiscal)
        year = end - 1 if number >= FISCAL_OPENS else end
        return (FORECAST, "%04d-%02d" % (year, number), word)
    found = _DOTTED.match(text) or _PLAN_FORM.match(text)
    if found:
        number = _month(found.group(2))
        return None if number is None else (BUDGET, "%s-%02d" % (found.group(1), number), "")
    found = _ACTUAL_FORM.match(text)
    if found:
        number = _month(found.group(2))
        return None if number is None else (ACTUAL, "%s-%02d" % (found.group(1), number), "")
    return None


def _number(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) * THOUSANDS
    try:
        return float(str(value).replace(",", ".")) * THOUSANDS
    except ValueError:
        return None


class Line:
    """Une entité, un segment, un mois : le budget, l'avis de la Finance, l'an dernier."""

    __slots__ = ("market", "region", "segment", "channel", "entity", "period", "budget",
                 "forecast", "last_year")

    def __init__(self, market: str, region: str, segment: str, period: str,
                 budget: Optional[float], forecast: Optional[float],
                 last_year: Optional[float], entity: str = "") -> None:
        self.market = market
        self.region = region
        self.segment = segment
        self.channel = channel_of(segment)
        self.entity = entity
        self.period = period
        self.budget = budget
        self.forecast = forecast
        self.last_year = last_year

    @property
    def perimeter(self) -> str:
        return perimeter_of(self.segment)


class Reforecast:
    """Ce que le classeur dit, avec le partage des mois que ce lecteur pose."""

    def __init__(self, path: str, sheet: str, vintage: str, lines: Sequence[Line],
                 header: Sequence[str], ignored: Sequence[str], brands: Sequence[str],
                 faults: Sequence[str]) -> None:
        self.path = path
        self.sheet = sheet
        #: Le mot du fichier : `REF2`. Le numéro en sort, et avec lui le partage des mois.
        self.vintage = vintage or "reforecast"
        self.lines = list(lines)
        self.header = list(header)
        self.ignored = list(ignored)
        self.brands = list(brands)
        self.faults = list(faults)
        periods = sorted({line.period for line in self.lines if line.forecast is not None})
        self.fiscal_start = fiscal_start(periods[0]) if periods else ""
        self.periods = fiscal_periods(self.fiscal_start) if self.fiscal_start else []
        digits = "".join(ch for ch in self.vintage if ch.isdigit())
        self.number = int(digits) if digits else None
        realised = min(12, MONTHS_PER_REFORECAST * self.number) if self.number else 0
        #: Réalisés, le dernier figé à la date du reforecast, puis la prévision.
        self.closed = self.periods[:max(0, realised - 1)]
        self.frozen = self.periods[realised - 1] if realised else ""
        self.ahead = self.periods[realised:]
        if self.periods and not self.number:
            self.faults.append("millésime sans numéro (%s) : aucun mois n'est tenu pour "
                               "réalisé, tout est lu comme prévision" % self.vintage)

    @property
    def usable(self) -> bool:
        return bool(self.lines) and bool(self.periods)

    @property
    def markets(self) -> List[str]:
        return sorted({line.market for line in self.lines})

    @property
    def fiscal_label(self) -> str:
        if not self.fiscal_start:
            return ""
        return "exercice %s-%s" % (self.fiscal_start[:4], str(int(self.fiscal_start[:4]) + 1)[2:])

    def months_label(self, periods: Sequence[str]) -> str:
        names = [MONTHS_FR[int(p[5:7]) - 1] for p in periods]
        if not names:
            return "aucun mois"
        if len(names) == 1:
            return names[0]
        return "%s à %s" % (names[0], names[-1])

    @property
    def split_sentence(self) -> str:
        """Le partage des mois, tel que ce lecteur le pose — jamais tel que le fichier le
        dit, parce que le fichier ne le dit pas."""
        if not self.periods:
            return ""
        parts = []
        if self.closed:
            parts.append("%s réalisés" % self.months_label(self.closed))
        if self.frozen:
            parts.append("%s figé à la date du reforecast, pas le réel publié"
                         % self.months_label([self.frozen]))
        if self.ahead:
            parts.append("%s en prévision" % self.months_label(self.ahead))
        return "millésime %s de la Finance, %s : %s" % (self.vintage, self.fiscal_label,
                                                        ", ".join(parts))

    def outlook(self, name: str, markets: Optional[Sequence[str]] = None,
                perimeter: str = "") -> "Outlook":
        """La somme des lignes de marchés donnés (tous quand None), et d'un périmètre de
        segments quand il est nommé (`sell-in`, `own`…)."""
        wanted = set(markets) if markets is not None else None
        found = Outlook(name, self)
        for line in self.lines:
            if wanted is not None and line.market not in wanted:
                continue
            if perimeter and line.perimeter != perimeter:
                continue
            found.add(line)
        return found


class Outlook:
    """Un ensemble de lignes du reforecast, sommé par mois : ce que la Finance attend."""

    __slots__ = ("name", "vintage", "budget_by", "forecast_by", "last_year_by", "count")

    def __init__(self, name: str, vintage: Reforecast) -> None:
        self.name = name
        self.vintage = vintage
        self.budget_by: Dict[str, float] = {}
        self.forecast_by: Dict[str, float] = {}
        self.last_year_by: Dict[str, float] = {}
        self.count = 0

    def add(self, line: Line) -> None:
        self.count += 1
        for bucket, value in ((self.budget_by, line.budget), (self.forecast_by, line.forecast),
                              (self.last_year_by, line.last_year)):
            if value is not None:
                bucket[line.period] = bucket.get(line.period, 0.0) + value

    def _sum(self, bucket: Dict[str, float], periods: Sequence[str]) -> float:
        return sum(bucket.get(period, 0.0) for period in periods)

    @property
    def usable(self) -> bool:
        return self.count > 0 and self.full_budget > 0 and self.full_year > 0

    # ---- l'exercice entier
    @property
    def full_year(self) -> float:
        return self._sum(self.forecast_by, self.vintage.periods)

    @property
    def full_budget(self) -> float:
        return self._sum(self.budget_by, self.vintage.periods)

    @property
    def full_last_year(self) -> float:
        return self._sum(self.last_year_by, self.vintage.periods)

    @property
    def gap(self) -> float:
        """Ce que la Finance attend, contre le plan : négatif quand elle attend moins."""
        return self.full_year - self.full_budget

    @property
    def growth(self) -> Optional[float]:
        return _growth(self.full_year, self.full_last_year)

    @property
    def plan_growth(self) -> Optional[float]:
        return _growth(self.full_budget, self.full_last_year)

    # ---- les trois morceaux du lecteur
    @property
    def closed(self) -> float:
        return self._sum(self.forecast_by, self.vintage.closed)

    @property
    def closed_budget(self) -> float:
        return self._sum(self.budget_by, self.vintage.closed)

    @property
    def frozen(self) -> float:
        return self._sum(self.forecast_by, [self.vintage.frozen]) if self.vintage.frozen else 0.0

    @property
    def ahead(self) -> float:
        return self._sum(self.forecast_by, self.vintage.ahead)

    @property
    def ahead_budget(self) -> float:
        return self._sum(self.budget_by, self.vintage.ahead)

    @property
    def ahead_last_year(self) -> float:
        return self._sum(self.last_year_by, self.vintage.ahead)

    @property
    def ahead_gap(self) -> float:
        return self.ahead - self.ahead_budget

    @property
    def ahead_growth(self) -> Optional[float]:
        """La prévision contre l'an dernier des mêmes mois : ce que la Finance attend du
        reste de l'exercice, le chiffre que le cumul ne montre jamais."""
        return _growth(self.ahead, self.ahead_last_year)

    @property
    def ahead_plan_growth(self) -> Optional[float]:
        return _growth(self.ahead_budget, self.ahead_last_year)

    # ---- les deux semestres
    def _half(self, second: bool) -> List[str]:
        periods = self.vintage.periods
        return periods[6:] if second else periods[:6]

    @property
    def first_half_growth(self) -> Optional[float]:
        return _growth(self._sum(self.forecast_by, self._half(False)),
                       self._sum(self.last_year_by, self._half(False)))

    @property
    def second_half_growth(self) -> Optional[float]:
        return _growth(self._sum(self.forecast_by, self._half(True)),
                       self._sum(self.last_year_by, self._half(True)))

    @property
    def first_half_plan_growth(self) -> Optional[float]:
        return _growth(self._sum(self.budget_by, self._half(False)),
                       self._sum(self.last_year_by, self._half(False)))

    @property
    def second_half_plan_growth(self) -> Optional[float]:
        return _growth(self._sum(self.budget_by, self._half(True)),
                       self._sum(self.last_year_by, self._half(True)))

    # ---- les libellés
    @property
    def growth_label(self) -> str:
        return _label(self.growth)

    @property
    def plan_growth_label(self) -> str:
        return _label(self.plan_growth)

    @property
    def ahead_growth_label(self) -> str:
        return _label(self.ahead_growth)

    @property
    def ahead_plan_growth_label(self) -> str:
        return _label(self.ahead_plan_growth)

    @property
    def first_half_label(self) -> str:
        return _label(self.first_half_growth)

    @property
    def second_half_label(self) -> str:
        return _label(self.second_half_growth)

    @property
    def first_half_plan_label(self) -> str:
        return _label(self.first_half_plan_growth)

    @property
    def second_half_plan_label(self) -> str:
        return _label(self.second_half_plan_growth)

    @property
    def halves_sentence(self) -> str:
        """Les deux semestres sur l'an dernier, l'avis de la Finance puis le plan : c'est
        là qu'une année phasée se voit, et qu'un cumul se tait."""
        if self.first_half_growth is None or self.second_half_growth is None:
            return ""
        return ("premier semestre %s, second semestre %s sur l'an dernier (le plan disait "
                "%s puis %s)" % (self.first_half_label, self.second_half_label,
                                 self.first_half_plan_label, self.second_half_plan_label))

    @property
    def sentence(self) -> str:
        from .analytics import format_eur

        if not self.usable:
            return ""
        text = "%s attendus sur l'exercice, soit %s contre le plan" % (
            format_eur(self.full_year), _signed(self.gap))
        if self.ahead_growth is not None:
            text += " · %s en prévision, %s sur l'an dernier des mêmes mois" % (
                self.vintage.months_label(self.vintage.ahead), self.ahead_growth_label)
            if self.ahead_plan_growth is not None:
                text += " quand le plan disait %s" % self.ahead_plan_growth_label
        return text


def _growth(now: float, before: float) -> Optional[float]:
    if before <= 0:
        return None
    return now / before - 1.0


def _label(value: Optional[float]) -> str:
    return "—" if value is None else "%+.1f %%" % (value * 100)


def _signed(amount: float) -> str:
    from .analytics import format_eur

    text = format_eur(amount)
    return text if amount < 0 or text.startswith("-") else "+" + text


# ------------------------------------------------------------------------- lecture


def sheet_for(names: Sequence[str]) -> str:
    """La feuille utile : celle dont le nom commence par `DATABASE`, celle qui nomme un
    reforecast d'abord. `DATA BASE`, avec l'espace, est le budget tel quel."""
    candidates = [name for name in names if _clean(name).upper().startswith(SHEET_PREFIX)]
    for name in candidates:
        if "REF" in _clean(name).upper():
            return name
    if candidates:
        return candidates[0]
    raise WorkbookError("Aucune feuille « %s… » dans ce classeur. Feuilles présentes : %s"
                        % (SHEET_PREFIX, ", ".join(names)))


@memo.by_file
def load(path, sheet: str = "") -> Reforecast:
    """Lit le classeur. Lève plutôt que de rendre un millésime vide."""
    with Workbook(path) as book:
        sheet = sheet or sheet_for(book.sheet_names)
        rows = list(book.rows(sheet))
    if not rows:
        raise WorkbookError("La feuille %r est vide." % sheet)
    header = [_clean(cell) for cell in rows[0]]
    upper = [cell.upper() for cell in header]
    try:
        country_at = upper.index("COUNTRY")
        segment_at = upper.index("SEGMENT")
    except ValueError as exc:
        raise WorkbookError("La feuille %r doit porter les colonnes Country et Segment. "
                            "Trouvé : %s" % (sheet, ", ".join(h for h in header if h))) from exc
    region_at = upper.index("REGION") if "REGION" in upper else None
    entity_at = upper.index("ENTITY") if "ENTITY" in upper else None
    brand_at = next((i for i, name in enumerate(header) if name.lower() in BRAND_COLUMNS), None)

    budget_at: Dict[str, int] = {}
    forecast_at: Dict[str, int] = {}
    actual_at: Dict[str, int] = {}
    vintages: List[str] = []
    ignored: List[str] = []
    keys = {country_at, segment_at, region_at, entity_at, brand_at}
    for position, name in enumerate(header):
        if position in keys or not name:
            continue
        meaning = column_meaning(name)
        if meaning is None:
            ignored.append(name)
            continue
        kind, period, vintage = meaning
        if kind == BUDGET:
            budget_at[period] = position
        elif kind == FORECAST:
            forecast_at[period] = position
            if vintage and vintage not in vintages:
                vintages.append(vintage)
        else:
            actual_at[period] = position
    if not forecast_at:
        raise WorkbookError("Aucune colonne de reforecast (« REF… - 2026 APR ») dans la "
                            "feuille %r. Colonnes lues : %s" % (sheet, ", ".join(header)))

    faults: List[str] = []
    if len(vintages) > 1:
        faults.append("plusieurs millésimes dans la même feuille : %s" % ", ".join(vintages))
    without_budget = sorted(p for p in forecast_at if p not in budget_at)
    if without_budget:
        faults.append("mois du reforecast sans colonne budget : %s" % ", ".join(without_budget))

    lines: List[Line] = []
    brands: List[str] = []
    for row in rows[1:]:
        def cell(position):
            return row[position] if position is not None and position < len(row) else None

        country = _clean(cell(country_at))
        if not country:
            continue
        market = normalise_market(country)
        region = _clean(cell(region_at))
        segment = _clean(cell(segment_at))
        entity = entity_code(_clean(cell(entity_at)))
        brand = _clean(cell(brand_at))
        if brand and brand not in brands:
            brands.append(brand)
        for period in sorted(set(budget_at) | set(forecast_at)):
            year, month = period.split("-")
            twin = "%d-%s" % (int(year) - 1, month)
            budget = _number(cell(budget_at.get(period)))
            forecast = _number(cell(forecast_at.get(period)))
            last_year = _number(cell(actual_at.get(twin)))
            if budget is None and forecast is None and last_year is None:
                continue
            lines.append(Line(market, region, segment, period, budget, forecast, last_year,
                              entity=entity))
    return Reforecast(str(path), sheet, vintages[0] if vintages else "", lines, header,
                      ignored, brands, faults)


def current() -> Reforecast:
    from ..config import settings

    return load(settings.reforecast_path)


# ------------------------------------------------------------------------- la revue


class PerimeterLine:
    """Un périmètre de l'écran : tout, et le sell-in seul."""

    __slots__ = ("name", "all", "sell_in")

    def __init__(self, name: str, all_lines: Outlook, sell_in: Outlook) -> None:
        self.name = name
        self.all = all_lines
        self.sell_in = sell_in

    @property
    def usable(self) -> bool:
        return self.all.usable


class Review:
    """Le millésime découpé sur les périmètres que l'écran connaît, le groupe, et ce
    qu'aucun périmètre ne porte."""

    def __init__(self, vintage: Optional[Reforecast], known: Dict[str, dict]) -> None:
        self.vintage = vintage
        self.absent: List[str] = []
        self.lines: List[PerimeterLine] = []
        self.group: Optional[Outlook] = None
        self.group_sell_in: Optional[Outlook] = None
        self.unplaced: List[Tuple[str, float]] = []
        if vintage is None:
            from ..config import DEFAULT_REFORECAST_FILE

            self.absent.append("%s absent : le dernier reforecast de la Finance n'est pas lu"
                               % DEFAULT_REFORECAST_FILE)
            return
        self.absent.extend(vintage.faults)
        if not vintage.usable:
            self.absent.append("le reforecast ne porte aucun mois lisible")
            return
        self.group = vintage.outlook("Groupe")
        self.group_sell_in = vintage.outlook("Groupe", perimeter="sell-in")
        placed = set()
        for name, item in known.items():
            markets = list(item.get("markets", []) or [])
            if name == "Sans périmètre" or not markets:
                continue
            placed.update(markets)
            line = PerimeterLine(name, vintage.outlook(name, markets),
                                 vintage.outlook(name, markets, perimeter="sell-in"))
            if line.all.count:
                self.lines.append(line)
        for market in vintage.markets:
            if market in placed:
                continue
            amount = vintage.outlook(market, [market]).full_year
            if amount:
                self.unplaced.append((market, amount))
        self.unplaced.sort(key=lambda item: -abs(item[1]))

    @property
    def usable(self) -> bool:
        return self.vintage is not None and self.group is not None and self.group.usable

    def for_name(self, name: str) -> Optional[PerimeterLine]:
        return next((line for line in self.lines if line.name == name), None)

    @property
    def note(self) -> str:
        if self.vintage is None:
            return ""
        return ("%s. Le plan reste le budget : ceci est l'avis daté de la Finance, posé à "
                "côté, jamais à sa place" % self.vintage.split_sentence)

    @property
    def unplaced_note(self) -> str:
        """La part de l'exercice au reforecast que les périmètres de l'écran ne portent pas
        — une ligne sans pays, un axe renommé — nommée, jamais répartie."""
        if not self.unplaced or self.group is None or not self.group.full_year:
            return ""
        share = sum(amount for _m, amount in self.unplaced) / self.group.full_year
        names = ", ".join(market for market, _a in self.unplaced[:6])
        if len(self.unplaced) > 6:
            names += ", %d autres" % (len(self.unplaced) - 6)
        return ("%.0f %% de l'exercice au reforecast sur des lignes qu'aucun périmètre de "
                "l'écran ne porte : %s" % (share * 100, names))


def build(vintage: Optional[Reforecast], known: Dict[str, dict]) -> Review:
    return Review(vintage, dict(known))
