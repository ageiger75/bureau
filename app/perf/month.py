"""Où en est le mois, périmètre par périmètre — la pièce de B3 que le lecteur voit.

Le module `pace` sait calculer deux taux pour un marché : la part du mois derrière nous
selon la forme des années passées, et la part de l'objectif déjà faite. Il ne sait rien de
qui répond de quoi, ni d'où viennent les chiffres. Ce module fait la jointure et la rend
dans l'ordre où le lecteur la lit : par périmètre, le MD nommé, ses marchés dessous.

Trois absences y sont nommées plutôt que comblées, parce que chacune appelle un geste
différent : un marché sans forme de mois attend une ligne dans le fichier de phasage ; un
marché sans objectif attend une ligne au plan ; un marché qu'aucun périmètre ne place
attend une correction de l'organigramme. Les trois ressemblent à « rien à dire », et
aucune ne l'est.

Le sell-in n'y figure pas, et ce n'est pas un oubli : une facture tombe quand elle tombe,
un mois de livraisons n'avance pas en jours, et afficher un avancement dessus dirait une
chose que personne ne mesure.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Sequence

from . import pace as pace_module
from .budget import is_sell_out, normalise_market

#: Ce que l'écran dit du sell-in à la place d'un taux. Écrit une fois, ici.
SELL_IN_NOTE = ("Le sell-in n'avance pas en jours : une facture tombe quand elle tombe. "
                "Aucun calendrier d'expédition n'est connecté, donc pas d'avancement.")

#: Sous cette largeur, une fourchette se lit comme un point.
NARROW = 0.03

#: Ce qu'un périmètre montre de ses marchés : ceux qui, du plus gros au plus petit, font
#: cette part de son plan — et jamais plus de `MOST` lignes. Le reste est replié en une
#: ligne qui garde son poids et son réalisé. Trente-quatre marchés à plat rendaient la
#: sélection au lecteur, c'est-à-dire le travail qu'il venait chercher.
COVERAGE = 0.80
MOST = 5

#: Au-delà de cette part du plan du mois versée le 1er, l'écran le dit. Un mois plat
#: fait trois pour cent par jour ; une campagne d'ouverture peut en faire dix. Quatre
#: dixièmes du mois en un jour n'est pas une vente, c'est un versement — le sell-out de
#: certains marchés arrive par paquets datés du 1er. La part est rendue telle quelle,
#: jamais retirée du réalisé : corriger en silence ferait disparaître le défaut au lieu
#: de le faire réparer. Le seuil est un choix, écrit ici pour être discuté.
FIRST_DAY_NOTE = 0.10


def week_of(day: int) -> int:
    """Le bloc de sept jours où tombe un jour du mois — la règle du fichier de phasage."""
    return (int(day) + 6) // 7


def within_week(day: datetime.date) -> float:
    """La fraction du bloc en cours déjà écoulée, ce jour compris.

    Le troisième jour du mois est au tiers de la première semaine, pas au bout. Le dernier
    bloc est plus court — les jours 29 à 31 — et sa longueur est celle du mois, pas sept.
    """
    import calendar

    week = week_of(day.day)
    first = 7 * (week - 1) + 1
    last = min(7 * week, calendar.monthrange(day.year, day.month)[1])
    length = max(last - first + 1, 1)
    return (day.day - first + 1) / float(length)


def _day(value) -> Optional[datetime.date]:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value or "").strip()[:10]
    try:
        return datetime.date(int(text[0:4]), int(text[5:7]), int(text[8:10]))
    except (TypeError, ValueError):
        return None


def _number(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _points(share: float) -> str:
    """« +4 », « -8 », « 0 » — jamais « -0 » : un signe sur rien est une affirmation."""
    points = int(round(share * 100))
    return "0" if points == 0 else "%+d" % points


class Line:
    """Un marché : ses deux taux, ou ce qui manque pour les donner."""

    __slots__ = ("market", "progress", "perimeter", "first_day")

    def __init__(self, market: str, progress: "pace_module.Progress",
                 perimeter: str = "", first_day: Optional[float] = None) -> None:
        self.market = market
        self.progress = progress
        self.perimeter = perimeter
        #: Ce que le 1er du mois a porté, en euros. `None` quand la lecture ne le dit pas.
        self.first_day = first_day

    @property
    def first_day_share(self) -> Optional[float]:
        """La part du plan du mois versée le 1er. `None` sans plan ou sans lecture."""
        if self.first_day is None or not self.target:
            return None
        return self.first_day / self.target

    @property
    def lumpy(self) -> bool:
        """Le 1er du mois porte-t-il plus que ce qu'un jour de vente peut porter ?"""
        share = self.first_day_share
        return share is not None and share >= FIRST_DAY_NOTE

    @property
    def first_day_note(self) -> str:
        share = self.first_day_share
        if share is None:
            return ""
        return "%.0f %% du plan du mois versés le 1er" % (share * 100)

    @property
    def expected(self) -> str:
        """La part du plan du mois que ce marché fait d'ordinaire à cette date.

        Ce n'est **pas** le temps écoulé — celui-là est le même pour tout le monde et
        s'écrit une fois, en tête du panneau. C'est la forme du mois de ce marché : un
        marché qui fait un tiers de son mois dans la première semaine est attendu à
        seize pour cent le troisième jour, et l'écrire « mois écoulé » se lisait comme
        une erreur de calendrier. « 45–70 % » quand les années ne s'accordent pas.
        """
        band = self.progress.through_month
        if band is None:
            return ""
        if band.spread <= NARROW:
            return "%.0f %%" % (band.middle * 100)
        return "%.0f–%.0f %%" % (band.low * 100, band.high * 100)

    @property
    def thin(self) -> bool:
        """La forme ne repose que sur deux exercices : un intervalle, pas une dispersion."""
        band = self.progress.through_month
        return band is not None and band.years < 3

    @property
    def done(self) -> str:
        share = self.progress.through_target
        return "" if share is None else "%.0f %%" % (share * 100)

    @property
    def gap(self) -> str:
        """Réalisé moins attendu, en points. Positif : en avance. Négatif : en retard."""
        band = self.progress.ahead
        if band is None:
            return ""
        if band.spread <= NARROW:
            return "%s pts" % _points(band.middle)
        return "%s à %s pts" % (_points(band.low), _points(band.high))

    @property
    def target(self) -> float:
        return self.progress.target or 0.0

    @property
    def readable(self) -> bool:
        return self.progress.readable

    @property
    def absent(self) -> str:
        return self.progress.absent


class Rest:
    """Les marchés repliés d'un périmètre, en une ligne qui garde leur poids."""

    __slots__ = ("count", "share", "done", "expected", "names")

    def __init__(self, count: int, share: float, done: str, expected: str,
                 names: Sequence[str]) -> None:
        self.count = count
        #: Leur part du plan du périmètre.
        self.share = share
        self.done = done
        self.expected = expected
        self.names = list(names)

    @property
    def label(self) -> str:
        if self.count == 1:
            return "1 autre marché · %.0f %% du plan" % (self.share * 100)
        return "%d autres marchés · %.0f %% du plan" % (self.count, self.share * 100)


class Group:
    """Un périmètre : son MD, les marchés qui pèsent, et le reste replié."""

    __slots__ = ("name", "lead", "lines", "shown", "rest")

    def __init__(self, name: str, lead: str, lines: Sequence["Line"]) -> None:
        self.name = name
        self.lead = lead
        self.lines = list(lines)
        self.shown, self.rest = _select(self.lines)

    @property
    def plan(self) -> float:
        return sum(line.target for line in self.lines)


def _select(lines: Sequence["Line"]):
    """Les marchés qui font `COVERAGE` du plan, du plus gros au plus petit, et le reste.

    Un marché sans plan ne pèse rien ici et part dans le reste : il n'a pas de quoi
    prendre une ligne, et son absence de plan est déjà nommée là où on le lira.
    """
    ordered = sorted(lines, key=lambda line: -line.target)
    total = sum(line.target for line in ordered)
    shown: List[Line] = []
    covered = 0.0
    for line in ordered:
        if shown and (len(shown) >= MOST or (total and covered / total >= COVERAGE)):
            break
        if line.target <= 0 and shown:
            break
        shown.append(line)
        covered += line.target
    rest_lines = [line for line in ordered if line not in shown]
    if not rest_lines:
        return shown, None
    plan = sum(line.target for line in rest_lines)
    actual = sum(line.progress.actual or 0.0 for line in rest_lines)
    done = "%.0f %%" % (actual / plan * 100) if plan else ""
    # L'attendu du reste : la moyenne des formes, pondérée par le plan, quand assez de
    # marchés en ont une pour que la moyenne parle ; sinon rien plutôt qu'un chiffre
    # assis sur la moitié du poids.
    shaped = [line for line in rest_lines
              if line.progress.through_month is not None and line.target > 0]
    weight = sum(line.target for line in shaped)
    expected = ""
    if plan and weight / plan >= COVERAGE:
        low = sum(line.progress.through_month.low * line.target for line in shaped) / weight
        high = sum(line.progress.through_month.high * line.target for line in shaped) / weight
        expected = ("%.0f %%" % (((low + high) / 2) * 100) if high - low <= NARROW
                    else "%.0f–%.0f %%" % (low * 100, high * 100))
    return shown, Rest(len(rest_lines), plan / total if total else 0.0, done, expected,
                       [line.market for line in rest_lines])


class Review:
    """La lecture entière du mois, prête à rendre."""

    __slots__ = ("month", "week", "day", "through", "groups", "unplaced", "absent",
                 "sell_in", "loose")

    def __init__(self, month: str, week: int, through: str,
                 groups: Sequence["Group"], unplaced: Sequence["Line"],
                 absent: Sequence[str], day: int = 0, loose=None) -> None:
        #: Les marchés sans périmètre, sélectionnés comme un périmètre : les gros
        #: d'abord, le reste replié.
        self.loose = loose
        #: Le mois lu, « 2026-09 », le jour et la semaine du mois où la lecture s'arrête.
        self.month = month
        self.week = week
        self.day = day
        #: Le dernier jour lu, en ISO. C'est la date qui borne tout ce qui suit.
        self.through = through
        self.groups = list(groups)
        #: Les marchés qu'aucun périmètre ne place. Rendus à part, jamais rangés par
        #: ressemblance : un marché mal placé envoie une question à la mauvaise personne.
        self.unplaced = list(unplaced)
        #: Ce qui a manqué à la lecture, nommé.
        self.absent = list(absent)
        self.sell_in = SELL_IN_NOTE

    @property
    def elapsed(self) -> float:
        """Le temps écoulé, le même pour tous : le jour lu sur les jours du mois."""
        import calendar

        try:
            year, month = int(self.month[:4]), int(self.month[5:7])
        except ValueError:
            return 0.0
        return self.day / float(calendar.monthrange(year, month)[1])

    @property
    def days_in_month(self) -> int:
        import calendar

        try:
            return calendar.monthrange(int(self.month[:4]), int(self.month[5:7]))[1]
        except ValueError:
            return 0

    @property
    def usable(self) -> bool:
        return bool(self.groups or self.unplaced)

    @property
    def lines(self) -> List["Line"]:
        return [line for group in self.groups for line in group.lines] + self.unplaced

    @property
    def readable(self) -> int:
        return sum(1 for line in self.lines if line.readable)


def targets_from_budget(budget, period: str) -> Dict[str, Optional[float]]:
    """L'objectif sell-out du mois par marché, tel que le plan l'écrit.

    Sell-out seulement, pour la même raison que la requête : le sell-in n'a pas
    d'avancement. Un marché sans ligne n'est pas à zéro, il est absent du dictionnaire.
    """
    found: Dict[str, float] = {}
    for line in getattr(budget, "lines", ()) or ():
        if line.period != period or not is_sell_out(line.segment):
            continue
        if line.budget is None:
            continue
        found[line.market] = found.get(line.market, 0.0) + float(line.budget)
    return found


def place_markets(markets: Sequence[str], org=None, directory=None):
    """Marché → périmètre, et périmètre → MD. L'annuaire d'abord, l'organigramme ensuite."""
    from . import perimeter as perimeter_module

    placed: Dict[str, str] = {}
    leads: Dict[str, str] = {}
    if directory is not None and len(directory):
        for market in markets:
            entry = directory.entry_for(market)
            if entry is not None and entry.bu:
                placed[market] = entry.bu
                leads.setdefault(entry.bu, entry.name)
    if org is not None and getattr(org, "usable", False):
        for market, name in perimeter_module.place(
                org, [market for market in markets if market not in placed]).items():
            placed[market] = name
        for name, person in org.leads().items():
            leads.setdefault(name, person.name)
    return placed, leads


def build(rows: Sequence[dict], targets: Dict[str, Optional[float]],
          phasing: Optional["pace_module.Phasing"], org=None,
          directory=None) -> "Review":
    """Joindre le réalisé du mois, le plan et la forme des mois, et ranger par périmètre.

    `rows` est le contrat de `MONTH_TO_DATE` : `market · iso2 · sales_to_date ·
    read_through`. `targets` est indexé par le nom de marché normalisé du plan.

    **L'annuaire place d'abord, l'organigramme ensuite.** L'annuaire nomme chaque pays
    avec sa BU et son MD, un par ligne ; l'organigramme nomme des zones — « Nordics »,
    « Europe du Sud » — que le code refuse d'ouvrir. La première version ne lisait que
    le second, et dix-neuf marchés se retrouvaient « sans périmètre » alors que le
    lecteur avait déjà donné la réponse, pays par pays, dans le premier.
    """
    absent: List[str] = []
    days = [_day(row.get("read_through")) for row in rows]
    days = [day for day in days if day is not None]
    if not days:
        return Review("", 0, "", [], [], ["aucune vente lue sur le mois en cours"])
    through = max(days)
    month = "%04d-%02d" % (through.year, through.month)
    week = week_of(through.day)
    within = within_week(through)

    if phasing is None or not phasing.usable:
        absent.append("forme des mois non déposée : aucun taux d'avancement du mois")
    if not targets:
        absent.append("aucun objectif sell-out au plan pour %s" % month)

    lines: List[Line] = []
    for row in rows:
        raw = str(row.get("market") or "").strip()
        if not raw:
            continue
        market = normalise_market(raw)
        actual = _number(row.get("sales_to_date")) or 0.0
        target = targets.get(market)
        progress = pace_module.progress(raw, month, week, actual, target, phasing,
                                        within=within)
        lines.append(Line(market, progress, first_day=_number(row.get("first_day_sales"))))

    placed, leads = place_markets([line.market for line in lines], org, directory)
    if not placed:
        absent.append("ni annuaire ni organigramme : les marchés ne sont pas rangés "
                      "par périmètre")

    by_perimeter: Dict[str, List[Line]] = {}
    unplaced: List[Line] = []
    for line in lines:
        name = placed.get(line.market)
        if name:
            line.perimeter = name
            by_perimeter.setdefault(name, []).append(line)
        else:
            unplaced.append(line)

    def order(items: List[Line]) -> List[Line]:
        # Le plus gros plan d'abord, les marchés sans plan à la fin : ce que le lecteur
        # cherche en premier est ce qui pèse, pas ce qui manque.
        return sorted(items, key=lambda line: -(line.progress.target or 0.0))

    groups = [Group(name, leads.get(name, ""), order(items))
              for name, items in by_perimeter.items()]
    groups.sort(key=lambda group: -sum(line.progress.target or 0.0
                                       for line in group.lines))
    return Review(month, week, through.isoformat(), groups, order(unplaced), absent,
                  day=through.day, loose=Group("Sans périmètre", "", unplaced)
                  if unplaced else None)
