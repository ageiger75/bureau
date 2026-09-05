"""Le plan EBITDA par périmètre, tel que la Finance l'a budgété — et rien de plus.

Le classeur « BUDGET FY27 EBITDA CONSO BY BU » porte trois choses que le cockpit lit sur
sa feuille de synthèse : la contribution EBITDA de chaque BU au budget, avec son taux ; les
lignes que le budget nomme lui-même comme des flux à nettoyer, tenues à part du « healthy
business » ; et le pont vers l'EBITDA consolidé ajusté — coûts industriels, distribution
internationale, coûts globaux, réserve. Une quatrième chose vient d'une autre feuille : la
marge opérationnelle de contribution (COP) par région, budget contre dernière prévision de
l'exercice précédent — le pas que le plan demande à chaque périmètre.

Ce que ce module ne fait pas : convertir un écart de ventes en EBITDA. Le taux moyen d'une
BU dit ce qu'elle a rapporté, pas ce que son prochain euro rapporte — un réseau de
boutiques perd plus d'un euro de contribution par euro de vente perdu, un partenaire en
rapporte trente centimes, et le compte de gestion l'a mesuré. Sans EBITDA réel par BU au
mois, que la Finance ne produit pas aujourd'hui, le cockpit montre le plan et dit que le
réel n'est pas lu. Les montants du classeur sont en millions d'euros.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .xlsx import Workbook, WorkbookError

MILLIONS = 1_000_000.0

#: Les BU de la feuille de synthèse, et le périmètre du cockpit que chacune rejoint. Deux
#: BU du fichier font un périmètre de l'annuaire ; deux autres n'en ont pas et restent
#: nommées telles quelles, hors des pages.
BU_PERIMETERS = {
    "JAPAN": "Japan",
    "CHINA": "Greater China",
    "APAC": "APAC",
    "NA": "North America",
    "EMEA COUNTRIES": "EMEA",
    "EMEA DISTRIBUTORS": "EMEA",
    "BRASIL": "Brazil",
    "BRAZIL": "Brazil",
    "WW TR": "Travel Retail",
    "OTHER": "Autres",
}

#: Les régions de la feuille COP, dont les libellés ne sont pas ceux de la synthèse.
REGION_PERIMETERS = {
    "N.AMERICA": "North America",
    "GREATER EUROPE": "EMEA",
    "FRANCE TOTAL": "EMEA",
    "BRAZIL": "Brazil",
    "JAPAN": "Japan",
    "CHINA TOTAL": "Greater China",
    "APAC": "APAC",
    "WW TRAVEL RETAIL": "Travel Retail",
}

HEALTHY = "HEALTHY BUSINESS CONTRIBUTION"
UNHEALTHY = "NON HEALTHY BUSINESS CONTRIBUTION"
TOTAL = "TOTAL BUSINESS CONTRIBUTION"
ADJUSTED = "CONSO EBITDA ADJUSTED"
COUNTRIES = "TOTAL COUNTRIES"

UNREAD_NOTE = ("L'EBITDA réel par BU n'est pas lu : la Finance ne le produit pas au mois. "
               "Ce panneau montre le plan, jamais un atterrissage.")


def _text(value) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _key(value) -> str:
    return " ".join(_text(value).upper().split())


def _number(value) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


class Line:
    """Des ventes et un EBITDA, en euros, pour un nom du fichier."""

    __slots__ = ("name", "sales", "ebitda")

    def __init__(self, name: str, sales: float = 0.0, ebitda: float = 0.0) -> None:
        self.name = name
        self.sales = sales
        self.ebitda = ebitda

    @property
    def rate(self) -> Optional[float]:
        return self.ebitda / self.sales if self.sales else None

    @property
    def rate_label(self) -> str:
        return "—" if self.rate is None else "%.1f %%" % (self.rate * 100)

    def add(self, other: "Line") -> None:
        self.sales += other.sales
        self.ebitda += other.ebitda


class Step:
    """La marge opérationnelle de contribution, avant et au budget, pour une région."""

    __slots__ = ("name", "sales_before", "op_before", "sales_budget", "op_budget")

    def __init__(self, name: str, sales_before=0.0, op_before=0.0, sales_budget=0.0,
                 op_budget=0.0) -> None:
        self.name = name
        self.sales_before = sales_before
        self.op_before = op_before
        self.sales_budget = sales_budget
        self.op_budget = op_budget

    @property
    def margin_before(self) -> Optional[float]:
        return self.op_before / self.sales_before if self.sales_before else None

    @property
    def margin_budget(self) -> Optional[float]:
        return self.op_budget / self.sales_budget if self.sales_budget else None

    @property
    def points(self) -> Optional[float]:
        if self.margin_before is None or self.margin_budget is None:
            return None
        return (self.margin_budget - self.margin_before) * 100

    @property
    def sentence(self) -> str:
        if self.points is None:
            return ""
        return ("marge opérationnelle de contribution : %.1f %% → %.1f %%, soit %+.1f point%s "
                "entre la dernière prévision de l'exercice précédent et le budget"
                % (self.margin_before * 100, self.margin_budget * 100, self.points,
                   "" if abs(self.points) < 1.5 else "s"))

    def add(self, other: "Step") -> None:
        self.sales_before += other.sales_before
        self.op_before += other.op_before
        self.sales_budget += other.sales_budget
        self.op_budget += other.op_budget


class Plan:
    """Ce que le classeur dit, tel qu'il le dit."""

    def __init__(self, path: str = "") -> None:
        self.path = path
        self.bus: List[Line] = []
        self.healthy: Optional[Line] = None
        self.unhealthy: List[Line] = []
        self.unhealthy_total: Optional[Line] = None
        self.total: Optional[Line] = None
        self.bridge: List[Tuple[str, float]] = []
        self.adjusted: Optional[Line] = None
        self.regions: List[Step] = []
        self.countries: Optional[Step] = None
        self.faults: List[str] = []

    @property
    def usable(self) -> bool:
        return bool(self.bus) and self.total is not None

    def perimeter(self, name: str) -> Optional["Perimeter"]:
        """Les BU du fichier que l'annuaire range sous ce périmètre, sommées."""
        line = None
        for bu in self.bus:
            if BU_PERIMETERS.get(_key(bu.name)) == name:
                line = line or Line(name)
                line.add(bu)
        if line is None:
            return None
        step = None
        for region in self.regions:
            if REGION_PERIMETERS.get(_key(region.name)) == name:
                step = step or Step(name)
                step.add(region)
        return Perimeter(name, line, step)

    @property
    def names(self) -> List[str]:
        """Les périmètres que le fichier connaît, dans l'ordre du fichier, sans doublon."""
        seen: List[str] = []
        for bu in self.bus:
            target = BU_PERIMETERS.get(_key(bu.name), bu.name)
            if target not in seen:
                seen.append(target)
        return seen


class Perimeter:
    """Le plan EBITDA d'un périmètre : son montant, son taux, et le pas demandé."""

    __slots__ = ("name", "line", "step")

    def __init__(self, name: str, line: Line, step: Optional[Step]) -> None:
        self.name = name
        self.line = line
        self.step = step

    @property
    def ebitda(self) -> float:
        return self.line.ebitda

    @property
    def sales(self) -> float:
        return self.line.sales

    @property
    def rate_label(self) -> str:
        return self.line.rate_label

    @property
    def step_sentence(self) -> str:
        return self.step.sentence if self.step is not None else ""


# ------------------------------------------------------------------------- lecture


def _sheet_named(book: Workbook, *needles: str, avoid: str = "") -> str:
    for name in book.sheet_names:
        key = _key(name)
        if all(needle in key for needle in needles) and (not avoid or avoid not in key):
            return name
    return ""


def _read_recap(rows: Sequence[Sequence[object]], plan: Plan) -> None:
    header = next((i for i, row in enumerate(rows)
                   if any(_key(cell) == "SALES" for cell in row)
                   and any(_key(cell).startswith("EBITDA") for cell in row)), None)
    if header is None:
        plan.faults.append("feuille de synthèse : aucune ligne d'en-tête « SALES · EBITDA »")
        return
    row = rows[header]
    sales_at = next(i for i, cell in enumerate(row) if _key(cell) == "SALES")
    ebitda_at = next(i for i, cell in enumerate(row) if _key(cell).startswith("EBITDA"))
    section = "bus"
    for raw in rows[header + 1:]:
        name = _text(raw[0]) if raw else ""
        if not name:
            continue
        key = _key(name)
        sales = _number(raw[sales_at]) if len(raw) > sales_at else None
        ebitda = _number(raw[ebitda_at]) if len(raw) > ebitda_at else None
        line = Line(name, (sales or 0.0) * MILLIONS, (ebitda or 0.0) * MILLIONS)
        if key == HEALTHY:
            plan.healthy = line
            section = "unhealthy"
        elif key == UNHEALTHY:
            plan.unhealthy_total = line
            section = "total"
        elif key == TOTAL or key.startswith("TOTAL BUSINESS CONTRIB"):
            plan.total = line
            section = "bridge"
        elif key == ADJUSTED:
            plan.adjusted = Line(name, plan.total.sales if plan.total else 0.0, line.ebitda)
            break
        elif section == "bus":
            plan.bus.append(line)
        elif section == "unhealthy":
            plan.unhealthy.append(line)
        elif section == "bridge" and ebitda is not None:
            plan.bridge.append((name, line.ebitda))
    if plan.total is None:
        plan.faults.append("feuille de synthèse : la ligne « %s » manque" % TOTAL)


def _read_cop(rows: Sequence[Sequence[object]], plan: Plan) -> None:
    """Les régions de la feuille COP : ventes et résultat opérationnel, budget et
    dernière prévision de l'exercice précédent, aux taux réels des deux colonnes."""
    labels = next((i for i, row in enumerate(rows)
                   if any(_key(cell).startswith("BUD ") for cell in row)
                   and any(_key(cell).startswith("REF") for cell in row)), None)
    if labels is None:
        plan.faults.append("feuille COP : aucune colonne « BUD » et « REF » côte à côte")
        return
    budget_at = next(i for i, cell in enumerate(rows[labels]) if _key(cell).startswith("BUD "))
    before_at = next(i for i, cell in enumerate(rows[labels]) if _key(cell).startswith("REF"))
    header = next((i for i in range(labels + 1, min(labels + 4, len(rows)))
                   if any(_key(cell) == "SALES" for cell in rows[i])), None)
    if header is None:
        plan.faults.append("feuille COP : aucune ligne « Sales · OP » sous les colonnes")
        return
    head = rows[header]

    def offsets(start: int) -> Tuple[Optional[int], Optional[int]]:
        sales = next((i for i in range(start, len(head)) if _key(head[i]) == "SALES"), None)
        op = next((i for i in range(start, len(head)) if _key(head[i]) == "OP"), None)
        return sales, op

    b_sales, b_op = offsets(budget_at)
    r_sales, r_op = offsets(before_at)
    if None in (b_sales, b_op, r_sales, r_op):
        plan.faults.append("feuille COP : colonnes Sales/OP introuvables")
        return
    for raw in rows[header + 1:]:
        if len(raw) <= max(b_sales, b_op, r_sales, r_op):
            continue
        name = _text(raw[1]) if len(raw) > 1 else ""
        sub = _text(raw[2]) if len(raw) > 2 else ""
        if not name or sub:
            continue
        sales_budget = _number(raw[b_sales])
        if sales_budget is None:
            continue
        step = Step(name, (_number(raw[r_sales]) or 0.0) * MILLIONS,
                    (_number(raw[r_op]) or 0.0) * MILLIONS, sales_budget * MILLIONS,
                    (_number(raw[b_op]) or 0.0) * MILLIONS)
        if _key(name) == COUNTRIES:
            plan.countries = step
            break
        if _key(name).startswith("TOTAL"):
            break
        if _key(name).startswith("SUB-TOTAL"):
            # Un sous-total d'une région déjà comptée, pas une région.
            continue
        plan.regions.append(step)


def load(path) -> Plan:
    plan = Plan(str(path))
    try:
        with Workbook(path) as book:
            recap = _sheet_named(book, "RECAP", "EBITDA", "CONSO")
            cop = _sheet_named(book, "COP", avoid="CMOP")
            if not recap:
                plan.faults.append("aucune feuille « RECAP EBITDA CONSO » dans %s ; feuilles : %s"
                                   % (path, ", ".join(book.sheet_names)))
                return plan
            _read_recap(list(book.rows(recap)), plan)
            if cop:
                _read_cop(list(book.rows(cop)), plan)
            else:
                plan.faults.append("aucune feuille « COP » : le pas de marge demandé par le plan "
                                   "n'est pas lu")
    except (WorkbookError, OSError) as exc:
        plan.faults.append(str(exc))
    return plan


def current() -> Plan:
    from ..config import settings

    return load(settings.ebitda_path)


# ------------------------------------------------------------------------- la revue


class Review:
    """Le plan EBITDA, découpé sur les périmètres que l'écran connaît."""

    def __init__(self, plan: Optional[Plan], known: Sequence[str]) -> None:
        self.plan = plan
        self.absent: List[str] = []
        self.perimeters: List[Perimeter] = []
        self.others: List[Perimeter] = []
        if plan is None:
            from ..config import DEFAULT_EBITDA_FILE

            self.absent.append("%s absent : le plan EBITDA par BU n'est pas lu" % DEFAULT_EBITDA_FILE)
            return
        self.absent.extend(plan.faults)
        if not plan.usable:
            return
        for name in known:
            item = plan.perimeter(name)
            if item is not None:
                self.perimeters.append(item)
        for name in plan.names:
            if name not in known:
                item = plan.perimeter(name)
                if item is not None:
                    self.others.append(item)
        missing = [name for name in known if plan.perimeter(name) is None]
        if missing:
            self.absent.append("sans ligne EBITDA au budget : %s" % ", ".join(missing))

    @property
    def usable(self) -> bool:
        return self.plan is not None and self.plan.usable and bool(self.perimeters)

    def for_name(self, name: str) -> Optional[Perimeter]:
        return next((item for item in self.perimeters + self.others if item.name == name), None)

    @property
    def note(self) -> str:
        return UNREAD_NOTE

    @property
    def unhealthy_note(self) -> str:
        """Ce que le budget nomme lui-même comme flux à nettoyer, en une phrase."""
        plan = self.plan
        if plan is None or plan.unhealthy_total is None or not plan.unhealthy:
            return ""
        from .analytics import format_eur

        return ("dont %s d'EBITDA sur %s de ventes que le budget nomme lui-même comme des "
                "flux à nettoyer (%s)"
                % (format_eur(plan.unhealthy_total.ebitda), format_eur(plan.unhealthy_total.sales),
                   ", ".join(line.name for line in plan.unhealthy)))


def build(plan: Optional[Plan], known: Sequence[str]) -> Review:
    return Review(plan, list(known))
