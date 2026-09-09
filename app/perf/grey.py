"""Le gris et le vrac : est-on en ligne, d'où ça vient, comment ça évolue.

Trois sources disent trois choses différentes du même argent, et le bloc les pose côte à
côte sans les additionner.

**L'entrepôt** marque le vrac ligne à ligne — `FLAG_BULK` 2 à 5, la définition de la vue —
et le cockpit tient déjà, marché par marché et mois par mois, les ventes avec et sans. La
différence est le vrac lu : d'où il vient (les marchés qui le portent), comment il évolue
(l'exercice à date contre l'an dernier, les trois derniers mois contre les mêmes), et ce
qu'il pèse dans chaque marché. Ce que l'entrepôt ne marque pas — le daigou, un groupe
facturé plutôt que vendu — n'y est pas, et le bloc le dit.

**Le budget** nomme lui-même des flux à nettoyer, avec leurs ventes et leur EBITDA sur
l'exercice. C'est la seule ligne de plan qui existe pour ce sujet, et elle est plus large
que le vrac de l'entrepôt : « en ligne avec le plan » se lit donc en ordre de grandeur —
le prorata des mois écoulés contre le vrac lu — jamais au million près.

**L'entrepôt, ligne à ligne.** Le même drapeau, rendu avec ce qui le porte : la valeur du
drapeau (l'entrepôt ne la nomme pas, le cockpit non plus), le point de vente et son
sous-canal, la gamme. C'est la réponse à « d'où ça vient » quand « la Chine » ne suffit
plus : trois comptes font le vrac, ou trente, et ce n'est pas la même conversation.

**Le registre** garde ce que le cockpit a déjà dit du gris : les sujets dont le titre ou
une preuve parle de gris, de vrac, de daigou, de duty free. Une recherche sur les mots,
nommée comme telle — le registre n'a pas de clé « gris », et en inventer une ferait
croire à une détection que personne n'a écrite.

**La Finance** clôt un trimestre avec sa feuille grise (vrac Chine, vrac Hong Kong, daigou,
un groupe facturé) ; elle se rapproche en ligne de commande, `manage.py reconcile`, contre le
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


#: Les comptes nommés ligne à ligne, et les gammes.
MOST_ACCOUNTS = 8
MOST_RANGES = 6
#: La part du vrac lu qu'il faut réunir pour dire « concentré » : le nombre de comptes qui
#: y suffisent est la phrase.
CONCENTRATION = 0.80

#: Les mots qui font entrer un sujet du registre dans le dossier gris.
GREY_WORDS = ("gris", "grey", "vrac", "bulk", "daigou", "duty free", "duty-free",
              "parallèle", "parallel")


def _growth(now: float, before: Optional[float]) -> Optional[float]:
    if before is None or before <= 0:
        return None
    return now / before - 1.0


def _word(year: Optional[float], recent: Optional[float]) -> str:
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
        return _word(self.growth, self.growth_recent)

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


class Line:
    """Une tranche du vrac ligne à ligne : un type, un compte ou une gamme."""

    __slots__ = ("label", "market", "months", "ytd", "ytd_ly", "recent", "recent_ly", "total")

    def __init__(self, label: str, market: str = "") -> None:
        self.label = label
        self.market = market
        self.months: Dict[str, float] = {}
        self.ytd = 0.0
        self.ytd_ly: Optional[float] = None
        self.recent = 0.0
        self.recent_ly: Optional[float] = None
        #: Le vrac lu en entier sur la fenêtre, pour la part.
        self.total = 0.0

    @property
    def share(self) -> Optional[float]:
        return self.ytd / self.total if self.total > 0 else None

    @property
    def growth(self) -> Optional[float]:
        return _growth(self.ytd, self.ytd_ly)

    @property
    def growth_recent(self) -> Optional[float]:
        return _growth(self.recent, self.recent_ly)

    @property
    def word(self) -> str:
        return _word(self.growth, self.growth_recent)

    @property
    def ytd_label(self) -> str:
        return format_eur(self.ytd)

    @property
    def share_label(self) -> str:
        share = self.share
        return "—" if share is None else "%d %%" % round(share * 100)

    @property
    def growth_label(self) -> str:
        return "n/d" if self.growth is None else format_pct(self.growth)

    @property
    def growth_recent_label(self) -> str:
        return "n/d" if self.growth_recent is None else format_pct(self.growth_recent)


class Detail:
    """Le vrac ligne à ligne : par type de drapeau, par compte, par gamme."""

    def __init__(self, kinds: Sequence[Line] = (), accounts: Sequence[Line] = (),
                 ranges: Sequence[Line] = (), start: str = "", through: str = "",
                 total: float = 0.0, note: str = "") -> None:
        self.kinds = list(kinds)
        self.accounts = list(accounts)
        self.ranges = list(ranges)
        self.start = start
        self.through = through
        self.total = total
        self.note = note

    @property
    def usable(self) -> bool:
        return self.total > 0 and bool(self.accounts)

    @property
    def window_label(self) -> str:
        if not self.start or not self.through:
            return ""
        from .accounts import _span

        return "exercice à date, %s" % _span(self.start, self.through)

    @property
    def concentration(self) -> int:
        """Combien de comptes suffisent à quatre cinquièmes du vrac lu."""
        run = 0.0
        for index, line in enumerate(self.accounts, start=1):
            run += line.ytd
            if self.total > 0 and run / self.total >= CONCENTRATION:
                return index
        return len(self.accounts)

    @property
    def headline(self) -> str:
        if not self.usable:
            return ""
        count = self.concentration
        first = self.accounts[0]
        text = ("%s de vrac lu ligne à ligne ; %s en %s %d %%" % (
            format_eur(self.total), "un compte" if count == 1 else "%d comptes" % count,
            "fait" if count == 1 else "font", round(CONCENTRATION * 100)))
        text += ", le premier %s (%s) à %s" % (first.label, first.word, first.share_label)
        if self.kinds:
            kinds = ", ".join("%s %s" % (line.label, line.share_label) for line in self.kinds)
            text += " ; par type, %s" % kinds
        return text

    @property
    def question(self) -> str:
        movers = [line for line in self.accounts if line.growth is not None
                  and abs(line.growth) >= NOTICED]
        if not movers:
            return ""
        top = max(movers, key=lambda line: abs(line.ytd - (line.ytd_ly or 0.0)))
        return ("%s : %s de vrac à date, %s sur l'an dernier. Qui est ce compte, et "
                "qu'est-ce qu'on lui vend ?"
                % (top.label, top.ytd_label, top.growth_label))


class Review:
    def __init__(self, group: Optional[Market], markets: Sequence[Market], start: str = "",
                 through: str = "", budget_lines: Sequence = (), budget_total: float = 0.0,
                 months_elapsed: int = 0, note: str = "", detail: Optional[Detail] = None) -> None:
        self.group = group
        self.markets = list(markets)
        self.start = start
        self.through = through
        self.budget_lines = list(budget_lines)
        self.budget_total = budget_total
        self.months_elapsed = months_elapsed
        self.note = note
        self.detail = detail if detail is not None else Detail(note="le vrac ligne à ligne n'est pas lu")
        #: Ce que le registre dit déjà du gris — posé par la surface, qui tient le registre.
        self.dossier: List = []

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


def _line_key(kind: str, row: dict) -> tuple:
    if kind == "kind":
        return ("type %s" % row.get("flag"), "")
    if kind == "range":
        return (str(row.get("range_name") or "(sans gamme)"), "")
    from .budget import normalise_market

    market = normalise_market(str(row.get("market") or "(sans pays)"))
    return ("%s · %s · %s" % (market, row.get("store") or "(sans code)",
                              row.get("sub_channel") or "N/A"), market)


def _lines(rows: Sequence[dict], kind: str, ytd_months, recent_months, total: float) -> List[Line]:
    lines: Dict[str, Line] = {}
    for row in rows:
        label, market = _line_key(kind, row)
        line = lines.get(label)
        if line is None:
            line = lines[label] = Line(label, market)
            line.total = total
        period = str(row.get("period") or "")
        line.months[period] = line.months.get(period, 0.0) + float(row.get("net_eur") or 0.0)
    ly = [_shift(m, -12) for m in ytd_months]
    ly_recent = [_shift(m, -12) for m in recent_months]
    for line in lines.values():
        line.ytd = sum(line.months.get(m, 0.0) for m in ytd_months)
        line.recent = sum(line.months.get(m, 0.0) for m in recent_months)
        if any(m in line.months for m in ly):
            line.ytd_ly = sum(line.months.get(m, 0.0) for m in ly)
        if any(m in line.months for m in ly_recent):
            line.recent_ly = sum(line.months.get(m, 0.0) for m in ly_recent)
    kept = [line for line in lines.values() if line.ytd > 0]
    kept.sort(key=lambda line: -line.ytd)
    return kept


def detail(rows: Sequence[dict], through: str = "", note: str = "") -> Detail:
    """Le vrac ligne à ligne, sur la dernière lecture de l'entrepôt.

    `through` borne la fenêtre au dernier mois que les relevés KPI tiennent, pour que les
    deux lectures parlent du même exercice à date ; sans lui, le dernier mois lu.
    """
    rows = [row for row in rows if row.get("period")]
    if not rows:
        return Detail(note=note or "le vrac ligne à ligne n'est pas encore lu")
    periods = sorted(set(str(row["period"]) for row in rows))
    last = periods[-1] if not through else min(periods[-1], through)
    start = fiscal_start(last)
    ytd_months = [m for m in _months_between(start, last) if m in periods]
    if not ytd_months:
        return Detail(note=note or "le vrac ligne à ligne ne couvre pas l'exercice à date")
    recent_months = ytd_months[-RECENT:]
    total = sum(float(row.get("net_eur") or 0.0) for row in rows
                if str(row["period"]) in ytd_months)
    return Detail(
        kinds=_lines(rows, "kind", ytd_months, recent_months, total),
        accounts=_lines(rows, "account", ytd_months, recent_months, total)[:MOST_ACCOUNTS],
        ranges=_lines(rows, "range", ytd_months, recent_months, total)[:MOST_RANGES],
        start=start, through=last, total=total, note=note)


class Mention:
    """Un sujet du registre qui parle du gris, tel que le dossier le cite."""

    __slots__ = ("issue_id", "title", "status", "last_seen", "conclusion")

    def __init__(self, issue) -> None:
        self.issue_id = issue.issue_id
        self.title = issue.title
        self.status = issue.status
        self.last_seen = getattr(issue, "last_seen", "") or ""
        self.conclusion = getattr(issue, "conclusion", "") or ""

    @property
    def status_word(self) -> str:
        from ..domain import issues as domain

        return {domain.CLOSED: "clos", domain.IN_ATTENTION: "en attention",
                domain.WATCHED: "en veille"}.get(self.status, "détecté")


def mentions_grey(issue) -> bool:
    texts = [issue.title or ""]
    texts.extend(getattr(item, "statement", "") or "" for item in getattr(issue, "evidence", []) or [])
    texts.extend(getattr(item, "conclusion", "") or "" for item in getattr(issue, "readings", []) or [])
    blob = " ".join(texts).lower()
    return any(word in blob for word in GREY_WORDS)


def dossier(register) -> List[Mention]:
    """Les sujets du registre qui parlent du gris — ouverts d'abord, puis clos, les plus
    récents en tête. Une recherche sur les mots : elle trouve ce qui a été écrit, pas ce
    qui a été mesuré."""
    from ..domain import issues as domain

    found = [issue for issue in getattr(register, "issues", []) or [] if mentions_grey(issue)]
    found.sort(key=lambda issue: (issue.status == domain.CLOSED, issue.last_seen), reverse=False)
    found.sort(key=lambda issue: issue.status == domain.CLOSED)
    return [Mention(issue) for issue in found]


def build(rows: Sequence, plan=None, note: str = "", bulk_rows: Sequence[dict] = (),
          bulk_note: str = "") -> Review:
    """La lecture, sur les relevés KPI déjà tenus, le budget EBITDA déjà lu, et la dernière
    lecture du vrac ligne à ligne."""
    group_readings = kpi_registry.readings_by_key(rows, scope=GROUP)
    periods = sorted(set(r.period for r in group_readings.get(bulk_module.SALES_KEY) or [])
                     & set(r.period for r in group_readings.get(bulk_module.EX_BULK_KEY) or []))
    if not periods:
        return Review(None, [], note=note or "les deux bases du groupe ne sont pas lues",
                      detail=detail(bulk_rows, note=bulk_note))
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
                  len(ytd_months), note, detail=detail(bulk_rows, through, bulk_note))
