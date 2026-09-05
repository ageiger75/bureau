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
                 "budget_contribution", "excluded", "exclusion")

    def __init__(self, region: str, sales: float = 0.0, contribution: float = 0.0,
                 costs: Optional[Dict[str, float]] = None, budget_sales: float = 0.0,
                 budget_contribution: float = 0.0, excluded: float = 0.0,
                 exclusion: str = "") -> None:
        self.region = region
        self.sales = sales
        self.contribution = contribution
        self.costs = dict(costs or {})
        self.budget_sales = budget_sales
        self.budget_contribution = budget_contribution
        self.excluded = excluded
        self.exclusion = exclusion

    def add(self, other: "Line") -> None:
        self.sales += other.sales
        self.contribution += other.contribution
        for name, value in other.costs.items():
            self.costs[name] = self.costs.get(name, 0.0) + value
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
    for column, label in NATURES:
        value = _number(record.get(column))
        if value is not None:
            costs[label] = value * THOUSANDS
    return Line(
        (record.get("region") or "").strip(),
        (_number(record.get("ventes_keur")) or 0.0) * THOUSANDS,
        (_number(record.get("contribution_keur")) or 0.0) * THOUSANDS,
        costs,
        (_number(record.get("budget_ventes_keur")) or 0.0) * THOUSANDS,
        (_number(record.get("budget_contribution_keur")) or 0.0) * THOUSANDS,
        (_number(record.get("dpl308_exclu_keur")) or 0.0) * THOUSANDS,
        (record.get("exclusion") or "").strip(),
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
        statement.faults.append("%d exercices de change dans le fichier ; seul %s est lu, "
                                "les niveaux ne se comparent pas entre exercices"
                                % (len(years), year))
    return statement


def current(path: Optional[str] = None) -> Statement:
    from ..config import settings

    return load(path or str(settings.pnl_path))


# ------------------------------------------------------------------------- la revue


class Review:
    """La contribution à date, découpée sur les périmètres que l'écran connaît."""

    def __init__(self, statement: Optional[Statement], known: Sequence[str]) -> None:
        self.statement = statement
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
    def note(self) -> str:
        return ("Contribution avant coûts internationaux, au compte de gestion : le réalisé "
                "cumulé contre le budget phasé à date. Un mois de retard sur les ventes.")


def build(statement: Optional[Statement], known: Sequence[str]) -> Review:
    return Review(statement, list(known))
