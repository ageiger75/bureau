"""Sommes-nous en ligne avec le plan ? Deux réponses, le mois en cours et l'exercice à date.

C'est la question que le lecteur pose en ouvrant l'écran, et jusqu'ici l'écran y répondait
par des morceaux : un cumul publié en tête, un mois clos dessous, un avancement du mois par
marché plus bas. Ce module assemble les morceaux en deux verdicts, un par période, chacun
avec sa base écrite à côté.

**Le mois en cours** se lit dans l'entrepôt, en sell-out, marché par marché : ce qui est
vendu à date contre ce que la forme du mois attendait à cette date — le plan du mois
multiplié par la part du mois que ce marché fait d'ordinaire au jour où on lit. Une
fourchette quand les exercices passés ne s'accordent pas. Le sell-in n'y est pas : une
facture tombe quand elle tombe, et aucun calendrier d'expédition n'est connecté.

**L'exercice à date** additionne deux choses de deux origines, et les nomme : les mois clos
tels que la consolidation les a publiés — actual et budget sur le même périmètre, aux
mêmes taux — et le mois en cours tel que l'entrepôt le lit, des deux côtés en sell-out.
Sans fichier de consolidation, les mois clos viennent de l'entrepôt contre le classeur de
plan, ce qui est la lecture dégradée, et l'écran le dit. Si le dernier fichier publié
s'arrête avant le mois précédent, les mois manquants ne sont pas inventés : le verdict de
l'année est absent, avec la raison.

**Le verdict** est un mot — en ligne, en avance, en retard — et il ne se prononce que si
le réalisé sort de l'attendu de plus que la tolérance, écrite ici. Une fourchette
d'attendu qui contient le réalisé est « en ligne », quelle que soit sa largeur ; sa
largeur est affichée, parce que c'est elle qui dit si on peut conclure.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from . import month as month_module

#: Au-delà de cette part de l'attendu, l'écart devient un mot. En deçà, c'est du bruit
#: de calendrier, et le mot est « en ligne ». Un choix, écrit ici pour être discuté.
TOLERANCE = 0.02

IN_LINE = "en ligne"
AHEAD = "en avance"
BEHIND = "en retard"

MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre")

#: L'exercice ouvre en avril.
FISCAL_OPENS = 4


def _month_name(period: str) -> str:
    try:
        return MONTHS_FR[int(period[5:7]) - 1]
    except (ValueError, IndexError):
        return period


def _previous(period: str) -> str:
    """« 2026-09 » -> « 2026-08 »."""
    year, month = int(period[:4]), int(period[5:7])
    return "%04d-%02d" % ((year - 1, 12) if month == 1 else (year, month - 1))


def _fiscal_start(period: str) -> str:
    year, month = int(period[:4]), int(period[5:7])
    return "%04d-%02d" % (year if month >= FISCAL_OPENS else year - 1, FISCAL_OPENS)


class Verdict:
    """Un réalisé contre une fourchette d'attendu, et le mot qui en sort."""

    __slots__ = ("actual", "low", "high", "coverage", "basis", "absent")

    def __init__(self, actual: float = 0.0, low: float = 0.0, high: float = 0.0,
                 coverage: float = 1.0, basis: str = "", absent: str = "") -> None:
        self.actual = actual
        self.low = low
        self.high = high
        #: La part du plan que la lecture couvre — ce qui manque est nommé, pas comblé.
        self.coverage = coverage
        self.basis = basis
        self.absent = absent

    @property
    def usable(self) -> bool:
        return not self.absent and self.high > 0

    @property
    def middle(self) -> float:
        return (self.low + self.high) / 2

    @property
    def gap_low(self) -> float:
        """Réalisé moins le haut de l'attendu : le pire des cas. Positif : en avance."""
        return self.actual - self.high

    @property
    def gap_high(self) -> float:
        return self.actual - self.low

    @property
    def narrow(self) -> bool:
        return (self.high - self.low) <= TOLERANCE * self.middle if self.middle else True

    @property
    def label(self) -> str:
        if not self.usable:
            return ""
        margin = TOLERANCE * self.middle
        if self.gap_low > margin:
            return AHEAD
        if self.gap_high < -margin:
            return BEHIND
        return IN_LINE

    @property
    def pct_low(self) -> float:
        return self.gap_low / self.high if self.high else 0.0

    @property
    def pct_high(self) -> float:
        return self.gap_high / self.low if self.low else 0.0

    @property
    def gap_label(self) -> str:
        """« +1,2 % » ou « -3 à +1 % » — jamais un point quand l'attendu est une fourchette."""
        if not self.usable:
            return ""
        if self.narrow:
            pct = (self.gap_low + self.gap_high) / 2 / self.middle
            return "%+.1f %%" % (pct * 100)
        return "%+.1f à %+.1f %%" % (self.pct_low * 100, self.pct_high * 100)

    @property
    def coverage_label(self) -> str:
        return "%.0f %%" % (self.coverage * 100)


class Scope:
    """Un périmètre — ou le groupe — avec ses deux verdicts."""

    __slots__ = ("name", "lead", "month", "year")

    def __init__(self, name: str, lead: str, month: Verdict, year: Verdict) -> None:
        self.name = name
        self.lead = lead
        self.month = month
        self.year = year


class Track:
    """Les deux réponses, pour le groupe et pour chaque périmètre."""

    def __init__(self, period: str, day: int, closed_through: str, group: Scope,
                 perimeters: Sequence[Scope], caveats: Sequence[str],
                 absent: Sequence[str]) -> None:
        self.period = period
        self.day = day
        #: Le dernier mois que la consolidation a publié, ou vide.
        self.closed_through = closed_through
        self.group = group
        self.perimeters = list(perimeters)
        self.caveats = list(caveats)
        self.absent = list(absent)

    @property
    def usable(self) -> bool:
        return self.group.month.usable or self.group.year.usable

    @property
    def month_title(self) -> str:
        return "%s à date, jour %d" % (_month_name(self.period).capitalize(), self.day)

    @property
    def year_title(self) -> str:
        start = _month_name(_fiscal_start(self.period))
        return "Exercice à date, %s à %s" % (start, _month_name(self.period))

    @property
    def tolerance_label(self) -> str:
        return "%.0f %%" % (TOLERANCE * 100)


# --------------------------------------------------------------------- le mois


def month_verdict(lines: Sequence["month_module.Line"]) -> Verdict:
    """Le verdict du mois sur un ensemble de marchés : ceux qui se lisent, sommés.

    Un marché sans plan ou sans forme de mois n'entre ni au réalisé ni à l'attendu — les
    deux termes portent sur les mêmes marchés — et la couverture dit ce qu'ils pèsent.
    """
    # Un marché dont le 1er encaisse une campagne de plateforme sort du verdict : son
    # avancement au 3 compare un jour d'encaissement à des exercices sans. Il reste à
    # l'écran, avec sa part du 1er, et la couverture dit ce qu'il pèse.
    readable = [line for line in lines
                if line.readable and line.target > 0 and not line.lumpy]
    plan = sum(line.target for line in lines if line.target > 0)
    if not readable:
        return Verdict(absent="aucun marché lisible sur les deux taux", coverage=0.0)
    actual = sum(line.progress.actual or 0.0 for line in readable)
    low = sum(line.target * line.progress.through_month.low for line in readable)
    high = sum(line.target * line.progress.through_month.high for line in readable)
    covered = sum(line.target for line in readable)
    return Verdict(actual, low, high, covered / plan if plan else 0.0,
                   basis="entrepôt, sell-out, %d marché%s" % (len(readable),
                                                              "s" if len(readable) > 1 else ""))


# -------------------------------------------------------------------- l'année


def _closed_for(published, markets: Optional[Sequence[str]]):
    """Actual et budget publiés, sur tout le fichier ou sur des marchés nommés."""
    from . import actuals as actuals_module

    if markets is None:
        totals = published.totals()
        return totals["actual"], totals["budget"]
    wanted = set(markets)
    actual = budget = 0.0
    for line in actuals_module.by_scope(published).values():
        if line.market in wanted:
            actual += line.actual
            budget += line.budget
    return actual, budget


def year_verdict(month: Verdict, closed_actual: float, closed_budget: float,
                 basis: str) -> Verdict:
    """Les mois clos, entiers, plus le mois en cours tel qu'il se lit."""
    if not closed_budget:
        return Verdict(absent="aucun mois clos publié sur ce périmètre")
    if not month.usable:
        return Verdict(closed_actual, closed_budget, closed_budget, 1.0, basis)
    return Verdict(closed_actual + month.actual, closed_budget + month.low,
                   closed_budget + month.high, 1.0, basis)


def build(review: "month_module.Review", published=None, warehouse_year=None,
          org=None, directory=None) -> Track:
    """Les deux verdicts pour le groupe et par périmètre.

    `published` est la lecture de l'exercice à date du fichier de consolidation, avec le
    mois qu'elle déclare ; `warehouse_year` est l'exercice à date assemblé depuis
    l'entrepôt, la lecture dégradée, prise seulement quand aucun fichier ne parle.
    """
    caveats: List[str] = []
    absent: List[str] = []
    if not review.usable:
        empty = Verdict(absent="mois en cours non lu")
        return Track("", 0, "", Scope("Groupe", "", empty, empty), [], [], list(review.absent))

    period = review.month
    groups = list(review.groups) + ([review.loose] if review.loose else [])
    every_line = [line for group in groups for line in group.lines]
    group_month = month_verdict(every_line)
    if not group_month.usable:
        absent.append("Mois en cours : %s." % group_month.absent)
    campaign = [line.market for line in every_line if line.lumpy and line.target > 0]
    if group_month.usable and group_month.coverage < 1.0:
        caveats.append("Le mois se lit sur %s du plan sell-out du mois ; le reste est sans "
                       "forme de mois, sans plan%s, et nommé plus bas."
                       % (group_month.coverage_label,
                          (", ou encaisse une campagne de plateforme le 1er (%s)"
                           % ", ".join(campaign)) if campaign else ""))
    caveats.append("Le sell-in n'entre pas dans le mois en cours : une facture tombe quand "
                   "elle tombe, et aucun calendrier d'expédition n'est connecté.")

    # Les mois clos : le fichier publié s'il parle du mois précédent, sinon rien.
    closed_through = ""
    closed_basis = ""
    closed_actual = closed_budget = 0.0
    year_absent = ""
    if published is not None and getattr(published, "lines", None):
        declared = published.period
        if not declared:
            year_absent = ("le fichier de consolidation ne déclare pas son mois : nommez-le "
                           "dans son nom de fichier, « … 2026 08.xlsx », et l'exercice se lira")
        elif declared != _previous(period):
            year_absent = ("la consolidation s'arrête à %s et l'entrepôt lit %s : les mois "
                           "entre les deux manquent, et ne sont pas inventés"
                           % (_month_name(declared), _month_name(period)))
        else:
            closed_through = declared
            closed_actual, closed_budget = _closed_for(published, None)
            closed_basis = ("consolidation d'%s à %s, tous canaux, à taux budget · entrepôt "
                            "sur %s à date, sell-out des deux côtés"
                            % (_month_name(_fiscal_start(period)), _month_name(declared),
                               _month_name(period)))
    elif warehouse_year is not None and getattr(warehouse_year, "budget", 0):
        last = getattr(warehouse_year, "last_period", "")
        if last == _previous(period):
            closed_through = last
            closed_actual = warehouse_year.actual
            closed_budget = warehouse_year.budget
            closed_basis = ("entrepôt contre classeur de plan d'%s à %s — lecture dégradée, "
                            "sans fichier de consolidation · entrepôt sur %s à date"
                            % (_month_name(_fiscal_start(period)), _month_name(last),
                               _month_name(period)))
        else:
            year_absent = ("l'exercice de l'entrepôt s'arrête à %s, pas au mois précédent"
                           % (_month_name(last) if last else "un mois inconnu"))
    else:
        year_absent = ("aucun mois clos lisible : ni fichier de consolidation, ni exercice "
                       "de l'entrepôt")
    if year_absent:
        absent.append("Exercice à date : %s." % year_absent)
    group_year = (year_verdict(group_month, closed_actual, closed_budget, closed_basis)
                  if not year_absent else Verdict(absent=year_absent))
    # Les deux morceaux de l'exercice sont au même taux : l'entrepôt convertit chaque
    # devise au taux budget FY27, figé, celui du classeur de plan et de la consolidation
    # « at budget rates ». Vérifié devise par devise, aucune réserve à porter.

    # Par périmètre : le mois sur les lignes du groupe, l'année sur les marchés publiés
    # que l'annuaire place dans ce périmètre — y compris ceux que le mois ne lit pas.
    perimeters: List[Scope] = []
    published_markets: Dict[str, str] = {}
    if closed_through and published is not None:
        from . import actuals as actuals_module

        markets = sorted({line.market for line in actuals_module.by_scope(published).values()})
        placed, _ = month_module.place_markets(markets, org, directory)
        for line in every_line:
            if line.perimeter:
                placed.setdefault(line.market, line.perimeter)
        published_markets = placed
        # Ce que le cumul publié porte et qu'aucun périmètre ne reçoit — travel retail,
        # distributeurs, une entité sans pays. Dans le groupe, hors des lignes : dit ici.
        loose = [market for market in markets if market not in placed]
        if loose:
            loose_actual, _ = _closed_for(published, loose)
            from .analytics import format_eur

            caveats.append("%s du cumul publié n'est dans aucun périmètre : %s."
                           % (format_eur(loose_actual), ", ".join(loose)))
    for group in review.groups:
        month = month_verdict(group.lines)
        if closed_through and published is not None:
            mine = [market for market, name in published_markets.items() if name == group.name]
            actual, budget = _closed_for(published, mine)
            year = year_verdict(month, actual, budget, closed_basis)
        elif closed_through:
            year = Verdict(absent="l'exercice par périmètre attend le fichier de consolidation")
        else:
            year = Verdict(absent=year_absent)
        perimeters.append(Scope(group.name, group.lead, month, year))
    if review.loose:
        loose_month = month_verdict(review.loose.lines)
        perimeters.append(Scope("Sans périmètre", "", loose_month,
                                Verdict(absent="marchés qu'aucun périmètre ne place")))

    return Track(period, review.day, closed_through,
                 Scope("Groupe", "", group_month, group_year), perimeters, caveats, absent)
