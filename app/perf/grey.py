"""Le gris et le vrac : est-on en ligne, d'où ça vient, comment ça évolue.

Trois sources disent trois choses différentes du même argent, et le bloc les pose côte à
côte sans les additionner.

**L'entrepôt** marque le vrac ligne à ligne — `FLAG_BULK` 2 à 5, la définition de la vue —
et le cockpit tient déjà, marché par marché et mois par mois, les ventes avec et sans. La
différence est le vrac lu : d'où il vient (les marchés qui le portent), comment il évolue
(l'exercice à date contre l'an dernier, les trois derniers mois contre les mêmes), et ce
qu'il pèse dans chaque marché. Ce que l'entrepôt ne marque pas — le daigou, le groupe JD
facturé plutôt que vendu — n'y est pas, et le bloc le dit.

**Le budget** nomme lui-même des flux à nettoyer, avec leurs ventes et leur EBITDA sur
l'exercice. C'est la seule ligne de plan qui existe pour ce sujet, et elle est plus large
que le vrac de l'entrepôt : « en ligne avec le plan » se lit donc en ordre de grandeur —
le prorata des mois écoulés contre le vrac lu — jamais au million près.

**La Finance** clôt un trimestre avec sa feuille grise (vrac Chine, vrac Hong Kong, daigou,
groupe JD) ; elle se rapproche en ligne de commande, `manage.py reconcile`, contre le
classeur déposé. Elle n'est pas relue ici : un classeur de la Finance n'a pas de chemin fixe.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from . import bulk as bulk_module
from . import kpi_registry
from .accounts import _months_between, _shift, fiscal_start
from .analytics import format_eur, format_pct

GROUP = kpi_registry.GROUP_SCOPE

#: Les marchés nommés dans la table : ceux qui portent au moins cette part du vrac lu.
LEAST_SHARE = 0.02
MOST = 8

#: Trois derniers mois contre les mêmes l'an dernier — la fenêtre qui alerte.
RECENT = 3

#: En deçà, le vrac « tient » ; au-delà il monte ou se tasse. Dix pour cent, parce qu'un
#: flux qui bouge par commandes bouge par paliers, pas par points.
NOTICED = 0.10


def _growth(now: float, before: Optional[float]) -> Optional[float]:
    if before is None or before <= 0:
        return None
    return now / before - 1.0


class Market:
    """Un marché : son vrac et ses ventes, sur l'exercice à date et trois mois."""

    __slots__ = ("scope", "bulk", "bulk_ly", "sales", "recent", "recent_ly", "months")

    def __init__(self, scope: str) -> None:
        from .budget import normalise_market

        #: Le nom tel que le cockpit l'écrit partout : l'entrepôt écrit les pays en
        #: capitales, et « CHINA » à l'écran est un code, pas un marché.
        self.scope = scope if scope.upper() == GROUP else normalise_market(scope)
        self.bulk = 0.0
        self.bulk_ly: Optional[float] = None
        self.sales = 0.0
        self.recent = 0.0
        self.recent_ly: Optional[float] = None
        self.months: Dict[str, float] = {}

    @property
    def share_of_market(self) -> Optional[float]:
        return self.bulk / self.sales if self.sales > 0 else None

    @property
    def growth(self) -> Optional[float]:
        return _growth(self.bulk, self.bulk_ly)

    @property
    def growth_recent(self) -> Optional[float]:
        return _growth(self.recent, self.recent_ly)

    @property
    def word(self) -> str:
        year, recent = self.growth, self.growth_recent
        if year is None:
            return "sans an dernier"
        if year >= NOTICED and (recent is None or recent >= 0):
            return "monte"
        if year <= -NOTICED and (recent is None or recent <= 0):
            return "se tasse"
        if recent is not None and recent >= NOTICED and year < NOTICED:
            return "repart"
        if recent is not None and recent <= -NOTICED and year > -NOTICED:
            return "s'arrête"
        return "tient"

    @property
    def bulk_label(self) -> str:
        return format_eur(self.bulk)

    @property
    def share_label(self) -> str:
        share = self.share_of_market
        return "—" if share is None else "%d %%" % round(share * 100)

    @property
    def growth_label(self) -> str:
        return "n/d" if self.growth is None else format_pct(self.growth)

    @property
    def growth_recent_label(self) -> str:
        return "n/d" if self.growth_recent is None else format_pct(self.growth_recent)


class Review:
    def __init__(self, group: Optional[Market], markets: Sequence[Market], start: str = "",
                 through: str = "", budget_lines: Sequence = (), budget_total: float = 0.0,
                 months_elapsed: int = 0, note: str = "") -> None:
        self.group = group
        self.markets = list(markets)
        self.start = start
        self.through = through
        self.budget_lines = list(budget_lines)
        self.budget_total = budget_total
        self.months_elapsed = months_elapsed
        self.note = note

    @property
    def usable(self) -> bool:
        return self.group is not None

    @property
    def total_bulk(self) -> float:
        """Le vrac du groupe — ou la somme des marchés si elle le dépasse : une part ne
        peut pas faire plus de cent pour cent."""
        summed = sum(item.bulk for item in self.markets)
        return max(self.group.bulk, summed) if self.group else summed

    @property
    def shown(self) -> List[Market]:
        total = self.total_bulk
        if total <= 0:
            return []
        kept = [item for item in self.markets if item.bulk / total >= LEAST_SHARE]
        return kept[:MOST]

    @property
    def rest_total(self) -> float:
        return self.total_bulk - sum(item.bulk for item in self.shown)

    @property
    def window_label(self) -> str:
        if not self.start or not self.through:
            return ""
        from .accounts import _span

        return "exercice à date, %s" % _span(self.start, self.through)

    @property
    def series(self) -> List:
        """Les six derniers mois du vrac du groupe, (mois, vrac, vrac un an plus tôt)."""
        if self.group is None:
            return []
        months = sorted(self.group.months)[-6:]
        return [(m, self.group.months[m], self.group.months.get(_shift(m, -12)))
                for m in months]

    @property
    def expected_to_date(self) -> Optional[float]:
        """Le prorata du budget des flux à nettoyer sur les mois écoulés — un ordre de
        grandeur, pas une cible mensuelle."""
        if not self.budget_total or not self.months_elapsed:
            return None
        return self.budget_total * self.months_elapsed / 12.0

    @property
    def headline(self) -> str:
        if self.group is None:
            return ""
        group = self.group
        share = group.share_of_market
        text = "le vrac lu %s sur l'exercice à date : %s" % (group.word, group.bulk_label)
        if share is not None:
            text += ", %s des ventes" % ("%.1f %%" % (share * 100))
        if group.growth is not None:
            text += ", %s sur l'an dernier" % group.growth_label
        if group.growth_recent is not None:
            text += " (%s sur trois mois)" % group.growth_recent_label
        return text

    @property
    def origin_sentence(self) -> str:
        shown = self.shown
        total = self.total_bulk
        if not shown or total <= 0:
            return "aucun marché ne porte de vrac lisible"
        parts = ["%s %d %%" % (item.scope, round(100 * item.bulk / total)) for item in shown[:3]]
        return "il vient de %s" % ", ".join(parts)

    @property
    def plan_sentence(self) -> str:
        expected = self.expected_to_date
        if expected is None:
            return ("le budget ne nomme pas de flux à nettoyer, ou n'est pas déposé : "
                    "pas de ligne de plan à mettre en face")
        names = ", ".join(str(line.name) for line in self.budget_lines) or "sans détail"
        ratio = self.total_bulk / expected if expected > 0 else None
        text = ("le budget nomme %s de flux à nettoyer sur l'exercice (%s), soit %s à date au "
                "prorata de %d mois ; le vrac lu en est à %s"
                % (format_eur(self.budget_total), names, format_eur(expected),
                   self.months_elapsed, format_eur(self.total_bulk)))
        if ratio is not None:
            if ratio > 1.15:
                text += " — au-dessus de ce que le budget attendait"
            elif ratio < 0.85:
                text += " — en dessous, et le budget compte aussi ce que l'entrepôt ne marque pas"
            else:
                text += " — dans l'ordre de grandeur du budget"
        return text

    @property
    def question(self) -> str:
        movers = [item for item in self.shown if item.growth is not None
                  and abs(item.growth) >= NOTICED]
        if not movers:
            return ""
        top = max(movers, key=lambda item: abs(item.bulk - (item.bulk_ly or 0.0)))
        return ("%s : le vrac %s de %s sur l'exercice à date. Commandes attendues, "
                "ou flux qui change de nature ?"
                % (top.scope, top.word, format_pct(abs(top.growth or 0.0)).lstrip("+")))


def _market(rows, scope: str, ytd_months, recent_months, all_periods) -> Optional[Market]:
    readings = kpi_registry.readings_by_key(rows, scope=scope)
    sales = {r.period: r.value for r in readings.get(bulk_module.SALES_KEY) or []}
    clean = {r.period: r.value for r in readings.get(bulk_module.EX_BULK_KEY) or []}
    if not sales or not clean:
        return None
    market = Market(scope)
    for period in sales:
        if period in clean:
            market.months[period] = sales[period] - clean[period]
    if not any(m in market.months for m in ytd_months):
        return None
    market.bulk = sum(market.months.get(m, 0.0) for m in ytd_months)
    market.sales = sum(sales.get(m, 0.0) for m in ytd_months)
    market.recent = sum(market.months.get(m, 0.0) for m in recent_months)
    ly = [_shift(m, -12) for m in ytd_months]
    if all(m in market.months for m in ly):
        market.bulk_ly = sum(market.months[m] for m in ly)
    ly_recent = [_shift(m, -12) for m in recent_months]
    if all(m in market.months for m in ly_recent):
        market.recent_ly = sum(market.months[m] for m in ly_recent)
    return market


def build(rows: Sequence, plan=None, note: str = "") -> Review:
    """La lecture, sur les relevés KPI déjà tenus et le budget EBITDA déjà lu."""
    group_readings = kpi_registry.readings_by_key(rows, scope=GROUP)
    periods = sorted(set(r.period for r in group_readings.get(bulk_module.SALES_KEY) or [])
                     & set(r.period for r in group_readings.get(bulk_module.EX_BULK_KEY) or []))
    if not periods:
        return Review(None, [], note=note or "les deux bases du groupe ne sont pas lues")
    through = periods[-1]
    start = fiscal_start(through)
    ytd_months = [m for m in _months_between(start, through) if m in periods]
    recent_months = ytd_months[-RECENT:]
    group = _market(rows, GROUP, ytd_months, recent_months, periods)
    markets = []
    for scope in bulk_module.scopes(rows):
        if scope.upper() == GROUP:
            continue
        market = _market(rows, scope, ytd_months, recent_months, periods)
        if market is not None and market.bulk > 0:
            markets.append(market)
    markets.sort(key=lambda item: -item.bulk)
    budget_lines = list(getattr(plan, "unhealthy", []) or [])
    total_line = getattr(plan, "unhealthy_total", None)
    budget_total = float(getattr(total_line, "sales", 0.0) or 0.0) if total_line else (
        sum(float(getattr(line, "sales", 0.0) or 0.0) for line in budget_lines))
    return Review(group, markets, start, through, budget_lines, budget_total,
                  len(ytd_months), note)
