"""La contribution réalisée à date par périmètre, lue au compte de gestion — le résultat
suit-il les ventes ?

La Finance ne produit pas d'EBITDA par BU au mois. Le compte de gestion de l'entrepôt porte
mieux que rien : un instantané par mois du réalisé cumulé depuis le 1er avril, par région et
par nature de coût — produits, distribution, marketing, administratif — contre un budget
phasé à date, jusqu'à la **contribution avant coûts internationaux**. L'agent entrepôt
l'écrit dans `var/pnl_bu.csv`, une ligne par région et par instantané, en milliers d'euros,
charges négatives, et la contribution est une somme qui ferme à la décimale.

Trois règles du fichier, tenues ici. `exchange_year` est une clé de filtre, jamais une
dimension d'agrégation : deux exercices de change ne se somment pas et ne se comparent pas
en niveau — seul le dernier est lu. `INT COST` n'est pas une région : ventes nulles, une
écriture unique plutôt qu'un cumul, et sur l'exercice en cours un produit financier non
récurrent ; il est nommé à part et n'entre dans aucun total. Et le montant `dpl308_exclu_keur`
a déjà été retiré de la distribution et de la contribution : il est rendu pour dire ce qui a
été écarté, jamais soustrait une seconde fois.

Le fichier a un mois de retard sur les ventes — le compte de gestion s'arrête un mois plus
tôt — et l'écran le dit avec la période couverte.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional, Sequence

THOUSANDS = 1_000.0

REQUIRED = ("exchange_year", "snapshot_date", "region", "ventes_keur", "contribution_keur",
            "budget_ventes_keur", "budget_contribution_keur")

#: Les natures de coût, dans l'ordre du compte de gestion, et leur nom à l'écran.
NATURES = (
    ("produits_keur", "produits"),
    ("autres_ppl_keur", "autres coûts produits"),
    ("distribution_keur", "distribution"),
    ("marketing_keur", "marketing"),
    ("administratif_keur", "administratif"),
    ("autres_keur", "autres"),
)

#: Les régions du compte de gestion, et le périmètre de l'annuaire que chacune rejoint.
REGION_PERIMETERS = {
    "N.AMERICA": "North America",
    "GREAT.EU. EXCL SPACE": "EMEA",
    "SPACE": "EMEA",
    "FRANCE TOTAL": "EMEA",
    "CHINA TOTAL": "Greater China",
    "APAC": "APAC",
    "WW TRAVEL RETAIL": "Travel Retail",
    "JAPAN": "Japan",
    "BRAZIL": "Brazil",
}

#: Ce qui n'est pas une région : nommé à part, hors de tout total et de tout classement.
NON_OPERATIONAL = frozenset({"INT COST"})

MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre")


def _key(value: str) -> str:
    return " ".join((value or "").strip().upper().split())


def _number(raw) -> Optional[float]:
    text = (raw or "").strip() if isinstance(raw, str) else raw
    if text in (None, "") or (isinstance(text, str) and text.upper() in ("NULL", "N/A", "NA")):
        return None
    try:
        return float(str(text).replace(",", "."))
    except ValueError:
        return None


class Line:
    """Une région à un instantané : ventes et contribution réalisées, et au budget phasé."""

    __slots__ = ("region", "sales", "contribution", "costs", "budget_sales",
                 "budget_contribution", "budget_costs", "excluded", "exclusion")

    def __init__(self, region: str, sales: float = 0.0, contribution: float = 0.0,
                 costs: Optional[Dict[str, float]] = None, budget_sales: float = 0.0,
                 budget_contribution: float = 0.0, excluded: float = 0.0,
                 exclusion: str = "", budget_costs: Optional[Dict[str, float]] = None) -> None:
        self.region = region
        self.sales = sales
        self.contribution = contribution
        self.costs = dict(costs or {})
        self.budget_sales = budget_sales
        self.budget_contribution = budget_contribution
        self.budget_costs = dict(budget_costs or {})
        self.excluded = excluded
        self.exclusion = exclusion

    def add(self, other: "Line") -> None:
        self.sales += other.sales
        self.contribution += other.contribution
        for name, value in other.costs.items():
            self.costs[name] = self.costs.get(name, 0.0) + value
        for name, value in other.budget_costs.items():
            self.budget_costs[name] = self.budget_costs.get(name, 0.0) + value
        self.budget_sales += other.budget_sales
        self.budget_contribution += other.budget_contribution
        self.excluded += other.excluded
        if other.exclusion and other.exclusion not in self.exclusion:
            self.exclusion = (self.exclusion + " · " + other.exclusion).strip(" ·")

    @property
    def rate(self) -> Optional[float]:
        return self.contribution / self.sales if self.sales else None

    @property
    def budget_rate(self) -> Optional[float]:
        return self.budget_contribution / self.budget_sales if self.budget_sales else None

    @property
    def gap(self) -> float:
        """Contribution réalisée moins contribution au budget phasé."""
        return self.contribution - self.budget_contribution

    @property
    def sales_gap(self) -> float:
        return self.sales - self.budget_sales

    @property
    def rate_label(self) -> str:
        return "—" if self.rate is None else "%.1f %%" % (self.rate * 100)

    @property
    def budget_rate_label(self) -> str:
        return "—" if self.budget_rate is None else "%.1f %%" % (self.budget_rate * 100)

    @property
    def sales_index_label(self) -> str:
        """Ventes réalisées en pour cent du budget phasé."""
        if not self.budget_sales:
            return "—"
        return "%.1f %%" % (self.sales / self.budget_sales * 100)


class Snapshot:
    """Un instantané du compte de gestion : l'exercice de change, la date, les mois cumulés."""

    __slots__ = ("exchange_year", "date", "months")

    def __init__(self, exchange_year: str, date: str, months: int) -> None:
        self.exchange_year = exchange_year
        self.date = date
        self.months = months

    @property
    def through(self) -> str:
        """« juin 2026 » : le dernier mois que le cumul couvre, celui de la date."""
        try:
            return "%s %s" % (MONTHS_FR[int(self.date[5:7]) - 1], self.date[:4])
        except (ValueError, IndexError):
            return self.date

    @property
    def period_label(self) -> str:
        try:
            month = int(self.date[5:7])
            first = MONTHS_FR[(month - self.months) % 12]
        except (ValueError, IndexError):
            return self.through
        return "%s à %s" % (first, self.through)


class Statement:
    """Le fichier lu, réduit au dernier instantané du dernier exercice de change."""

    def __init__(self, path: str = "") -> None:
        self.path = path
        self.snapshot: Optional[Snapshot] = None
        self.previous: Optional[Snapshot] = None
        self.lines: List[Line] = []
        self.central: List[Line] = []
        self.faults: List[str] = []
        self.snapshots: List[Snapshot] = []
        #: Le même stade de l'exercice de change précédent — même mois, un an plus tôt —
        #: par région. Les niveaux ne s'y comparent pas ; les parts des ventes, oui.
        self.last_year: Dict[str, Line] = {}
        self.last_year_date: str = ""

    @property
    def usable(self) -> bool:
        return self.snapshot is not None and bool(self.lines)

    def perimeter(self, name: str) -> Optional[Line]:
        found = None
        for line in self.lines:
            if REGION_PERIMETERS.get(_key(line.region)) == name:
                found = found or Line(name)
                found.add(line)
        return found

    def perimeter_last_year(self, name: str) -> Optional[Line]:
        found = None
        for region, line in self.last_year.items():
            if REGION_PERIMETERS.get(_key(region)) == name:
                found = found or Line(name)
                found.add(line)
        return found

    @property
    def total_last_year(self) -> Optional[Line]:
        if not self.last_year:
            return None
        whole = Line("Régions")
        for line in self.last_year.values():
            whole.add(line)
        return whole

    @property
    def names(self) -> List[str]:
        seen: List[str] = []
        for line in self.lines:
            target = REGION_PERIMETERS.get(_key(line.region), line.region)
            if target not in seen:
                seen.append(target)
        return seen

    @property
    def total(self) -> Line:
        """Les régions opérationnelles sommées — jamais l'écriture centrale."""
        whole = Line("Régions")
        for line in self.lines:
            whole.add(line)
        return whole


def _read_line(record: Dict[str, str]) -> Line:
    costs = {}
    budget_costs = {}
    for column, label in NATURES:
        value = _number(record.get(column))
        if value is not None:
            costs[label] = value * THOUSANDS
        planned = _number(record.get("budget_" + column))
        if planned is not None:
            budget_costs[label] = planned * THOUSANDS
    return Line(
        (record.get("region") or "").strip(),
        (_number(record.get("ventes_keur")) or 0.0) * THOUSANDS,
        (_number(record.get("contribution_keur")) or 0.0) * THOUSANDS,
        costs,
        (_number(record.get("budget_ventes_keur")) or 0.0) * THOUSANDS,
        (_number(record.get("budget_contribution_keur")) or 0.0) * THOUSANDS,
        (_number(record.get("dpl308_exclu_keur")) or 0.0) * THOUSANDS,
        (record.get("exclusion") or "").strip(),
        budget_costs,
    )


def load(path: str) -> Statement:
    """Lire le fichier et ne garder que le dernier instantané du dernier exercice de change."""
    statement = Statement(str(path))
    if not path or not os.path.exists(path):
        statement.faults.append("%s absent" % path)
        return statement
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            statement.faults.append("colonnes manquantes : %s" % ", ".join(missing))
            return statement
        records = [dict(record) for record in reader]
    if not records:
        statement.faults.append("fichier vide")
        return statement
    years = sorted({(record.get("exchange_year") or "").strip() for record in records})
    year = years[-1]
    dated = {}
    for record in records:
        if (record.get("exchange_year") or "").strip() != year:
            continue
        date = (record.get("snapshot_date") or "").strip()
        months = int(_number(record.get("mois_cumules")) or 0)
        dated.setdefault(date, Snapshot(year, date, months))
    statement.snapshots = [dated[date] for date in sorted(dated)]
    if not statement.snapshots:
        statement.faults.append("aucun instantané pour %s" % year)
        return statement
    statement.snapshot = statement.snapshots[-1]
    statement.previous = statement.snapshots[-2] if len(statement.snapshots) > 1 else None
    for record in records:
        if ((record.get("exchange_year") or "").strip() != year
                or (record.get("snapshot_date") or "").strip() != statement.snapshot.date):
            continue
        line = _read_line(record)
        if not line.region:
            continue
        if _key(line.region) in NON_OPERATIONAL:
            statement.central.append(line)
        else:
            statement.lines.append(line)
    if len(years) > 1:
        # Même mois, un an plus tôt, dans l'exercice de change précédent : le seul point de
        # l'an dernier qui se compare — en parts des ventes, jamais en niveau.
        wanted = "%04d%s" % (int(statement.snapshot.date[:4]) - 1, statement.snapshot.date[4:])
        for record in records:
            if ((record.get("exchange_year") or "").strip() == years[-2]
                    and (record.get("snapshot_date") or "").strip() == wanted):
                line = _read_line(record)
                if line.region and _key(line.region) not in NON_OPERATIONAL:
                    statement.last_year[line.region] = line
                    statement.last_year_date = wanted
        statement.faults.append("%d exercices de change dans le fichier ; seul %s est lu en "
                                "niveau, %s sert de comparaison en parts des ventes au même stade"
                                % (len(years), year, years[-2]))
    return statement


def current(path: Optional[str] = None) -> Statement:
    from ..config import settings

    return load(path or str(settings.pnl_path))


# ------------------------------------------------------------- par nature de coût

#: Sous cet écart de part, deux références sont dites égales.
SHARE_TOLERANCE = 0.001

REALLY_LOWER = "coût réellement plus bas"
PHASING = "sous le budget mais plus lourd qu'au même stade l'an dernier : un phasage possible"
HEAVIER = "plus lourd que le budget et que l'an dernier"
LIGHTER_THAN_BUDGET_ONLY = "sous le budget ; pas d'an dernier comparable"
HEAVIER_THAN_BUDGET_ONLY = "plus lourd que le budget ; pas d'an dernier comparable"
AT_BUDGET = "au budget"


class Nature:
    """Une nature de coût d'un périmètre : son écart au budget phasé, et ce qu'il vaut une
    fois la part des ventes comparée au budget et au même stade de l'exercice précédent."""

    __slots__ = ("name", "actual", "budget", "sales", "budget_sales", "last_year",
                 "last_year_sales")

    def __init__(self, name: str, actual: float, budget: float, sales: float,
                 budget_sales: float, last_year: Optional[float],
                 last_year_sales: float) -> None:
        self.name = name
        self.actual = actual
        self.budget = budget
        self.sales = sales
        self.budget_sales = budget_sales
        self.last_year = last_year
        self.last_year_sales = last_year_sales

    @property
    def gap(self) -> float:
        """Réalisé moins budget : les charges sont négatives, un écart positif est favorable."""
        return self.actual - self.budget

    @property
    def share(self) -> Optional[float]:
        return -self.actual / self.sales if self.sales else None

    @property
    def budget_share(self) -> Optional[float]:
        return -self.budget / self.budget_sales if self.budget_sales else None

    @property
    def last_year_share(self) -> Optional[float]:
        if self.last_year is None or not self.last_year_sales:
            return None
        return -self.last_year / self.last_year_sales

    @property
    def verdict(self) -> str:
        share, budget, before = self.share, self.budget_share, self.last_year_share
        if share is None or budget is None:
            return ""
        below_budget = share < budget - SHARE_TOLERANCE
        above_budget = share > budget + SHARE_TOLERANCE
        if before is None:
            if below_budget:
                return LIGHTER_THAN_BUDGET_ONLY
            return HEAVIER_THAN_BUDGET_ONLY if above_budget else AT_BUDGET
        below_before = share < before - SHARE_TOLERANCE
        if below_budget and below_before:
            return REALLY_LOWER
        if below_budget:
            return PHASING
        if above_budget and not below_before:
            return HEAVIER
        return AT_BUDGET

    @property
    def sentence(self) -> str:
        from .analytics import format_eur

        if self.share is None or self.budget_share is None:
            return ""
        text = "%s %s%s (%s : %.1f %% des ventes contre %.1f %% au budget" % (
            self.name, "+" if self.gap > 0 else "", format_eur(self.gap), self.verdict,
            self.share * 100, self.budget_share * 100)
        if self.last_year_share is not None:
            text += " et %.1f %% au même stade l'an dernier" % (self.last_year_share * 100)
        return text + ")"


def natures(line: Line, before: Optional[Line]) -> List[Nature]:
    """Chaque nature de coût du périmètre, la plus favorable d'abord."""
    found = []
    for _column, label in NATURES:
        if not line.costs.get(label) and not line.budget_costs.get(label):
            # Rien de réalisé ni de budgété : pas une nature de ce périmètre.
            continue
        found.append(Nature(
            label, line.costs.get(label, 0.0), line.budget_costs.get(label, 0.0),
            line.sales, line.budget_sales,
            before.costs.get(label) if before is not None else None,
            before.sales if before is not None else 0.0))
    found.sort(key=lambda item: -item.gap)
    return found


def breakdown_sentence(line: Line, before: Optional[Line]) -> str:
    """L'écart de contribution, poste par poste, avec le verdict de chaque poste."""
    from .analytics import format_eur

    items = [item for item in natures(line, before) if item.sentence]
    if not items:
        return ""
    head = "Écart de contribution %s%s au budget phasé" % (
        "+" if line.gap > 0 else "", format_eur(line.gap))
    if line.sales_gap:
        head += ", dont ventes %s%s" % ("+" if line.sales_gap > 0 else "", format_eur(line.sales_gap))
    return head + " : " + " ; ".join(item.sentence for item in items) + "."


# ------------------------------------------------------------------------- la revue


class Review:
    """La contribution à date, découpée sur les périmètres que l'écran connaît."""

    def __init__(self, statement: Optional[Statement], known: Sequence[str],
                 period: str = "") -> None:
        self.statement = statement
        #: Le mois que l'écran lit pour les ventes, « 2026-09 », pour dire l'âge du cumul.
        self.period = period
        self.absent: List[str] = []
        self.perimeters: List[Line] = []
        self.others: List[Line] = []
        if statement is None:
            from ..config import DEFAULT_PNL_FILE

            self.absent.append("%s absent : la contribution réalisée par BU n'est pas lue"
                               % DEFAULT_PNL_FILE)
            return
        self.absent.extend(statement.faults)
        if not statement.usable:
            return
        for name in known:
            line = statement.perimeter(name)
            if line is not None:
                line.region = name
                self.perimeters.append(line)
        for name in statement.names:
            if name not in known:
                line = statement.perimeter(name)
                if line is None:
                    line = next(item for item in statement.lines
                                if REGION_PERIMETERS.get(_key(item.region), item.region) == name)
                self.others.append(line)
        missing = [name for name in known if statement.perimeter(name) is None]
        if missing:
            self.absent.append("sans ligne au compte de gestion : %s" % ", ".join(missing))

    @property
    def usable(self) -> bool:
        return (self.statement is not None and self.statement.usable
                and bool(self.perimeters or self.others))

    def for_name(self, name: str) -> Optional[Line]:
        return next((line for line in self.perimeters + self.others if line.region == name), None)

    def breakdown(self, name: str) -> str:
        """L'écart d'un périmètre, poste par poste — vide sans fichier ou sans ligne."""
        if not self.statement or not self.statement.usable:
            return ""
        line = self.for_name(name)
        if line is None:
            return ""
        return breakdown_sentence(line, self.statement.perimeter_last_year(name))

    @property
    def total_breakdown(self) -> str:
        if not self.statement or not self.statement.usable:
            return ""
        return breakdown_sentence(self.statement.total, self.statement.total_last_year)

    @property
    def caveat(self) -> str:
        months = self.snapshot.months if self.snapshot is not None else 0
        return ("%s de cumul ne séparent pas une économie d'une dépense décalée : un poste sous "
                "le budget mais plus lourd qu'au même stade l'an dernier se relit à "
                "l'instantané suivant." % ("%d mois" % months if months else "Quelques mois"))

    @property
    def snapshot(self) -> Optional[Snapshot]:
        return self.statement.snapshot if self.statement else None

    @property
    def total(self) -> Optional[Line]:
        return self.statement.total if self.statement and self.statement.usable else None

    @property
    def title(self) -> str:
        if self.snapshot is None:
            return "Contribution à date"
        return "Contribution à fin %s" % self.snapshot.through

    @property
    def central_note(self) -> str:
        """L'écriture centrale, nommée et tenue hors de tout total."""
        if not self.statement or not self.statement.central:
            return ""
        from .analytics import format_eur

        return "hors %s, écriture centrale et produit financier non récurrent, tenue à part" % (
            ", ".join("%s %s" % (line.region, format_eur(line.contribution))
                      for line in self.statement.central))

    @property
    def excluded_note(self) -> str:
        if not self.statement:
            return ""
        excluded = sum(line.excluded for line in self.statement.lines)
        if not excluded:
            return ""
        from .analytics import format_eur

        labels = {line.exclusion for line in self.statement.lines if line.exclusion}
        return "%s écartés du compte de gestion : %s" % (format_eur(excluded), " · ".join(sorted(labels)))

    @property
    def lag_months(self) -> Optional[int]:
        """Combien de mois séparent le dernier mois du cumul du mois que l'écran lit."""
        if self.snapshot is None or len(self.period) < 7:
            return None
        try:
            year, month = int(self.snapshot.date[:4]), int(self.snapshot.date[5:7])
            now_year, now_month = int(self.period[:4]), int(self.period[5:7])
        except ValueError:
            return None
        return (now_year - year) * 12 + (now_month - month)

    @property
    def note(self) -> str:
        """Ce que le chiffre est, et son âge — calculé, jamais affirmé : le compte de gestion
        ne publie ni avril ni juillet seuls, donc l'écart avec les ventes varie."""
        text = ("Contribution avant coûts internationaux, au compte de gestion : le réalisé "
                "cumulé contre le budget phasé à date.")
        lag = self.lag_months
        if lag is None or self.snapshot is None:
            return text
        if lag <= 0:
            return text + " Le cumul est au mois que l'écran lit."
        return text + (" Le cumul s'arrête à fin %s quand les ventes sont lues à %s : %d mois "
                       "d'écart. Avril et juillet ne sont jamais publiés seuls, ils arrivent "
                       "dans le cumul suivant."
                       % (self.snapshot.through, _month_label(self.period), lag))


def _month_label(period: str) -> str:
    try:
        return "%s %s" % (MONTHS_FR[int(period[5:7]) - 1], period[:4])
    except (ValueError, IndexError):
        return period


def build(statement: Optional[Statement], known: Sequence[str], period: str = "") -> Review:
    return Review(statement, list(known), period)
