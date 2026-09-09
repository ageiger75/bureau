"""Trois conversations préparées, pas huit fiches.

L'écran « Qu'est-ce que je décide cette semaine » portait huit sujets qui disaient tous la
même chose : « montant en jeu · dure depuis plusieurs lectures ». C'est vrai, et cela ne
prépare rien. Ce qu'un lecteur emporte dans un appel tient en quatre lignes : **l'écart**
(combien, depuis quand, sur quel canal), **la tendance** (se creuse ou se referme, et ce
que la semaine et le mois en cours disent), **la dernière lecture** (ce que le cockpit
avait conclu, et ce qui est déjà engagé), **la question** (une seule, tirée des chiffres).

Ce module ne classe rien et ne décide de rien : la sélection reste au moteur, avec ses
plafonds. Il prend les trois sujets que le moteur a portés et va chercher, dans ce que
l'écran a déjà lu, de quoi en faire une conversation. Une source absente laisse sa ligne
vide plutôt que d'inventer — une conversation préparée sur des chiffres devinés est pire
qu'une fiche muette.

Les facteurs du moteur (§C6) restent visibles, en une ligne discrète à la fin : ils
disent pourquoi ce sujet est là, pas de quoi parler.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Sequence

from ..domain.issues import ALIGN, CHALLENGE, DECIDE, DELEGATE, MONITOR
from .analytics import format_eur
from .weekly import MONTHS_FR

#: Le sens de l'écart sur les derniers mois, en un mot.
WIDENING = "se creuse"
CLOSING = "se referme"
STEADY = "ne bouge pas"

#: Au-delà de cette part du premier écart, le dernier est dit autre. En dessous, c'est le
#: bruit d'un mois, et « stable » est plus juste que « se referme de deux pour cent ».
TREND_TOLERANCE = 0.05

#: Les mois comparés pour dire le sens.
TREND_MONTHS = 3

#: Le rôle du sujet, tel qu'on le lit à voix haute. Les codes restent ceux du domaine.
ROLE_WORDS: Dict[str, str] = {
    CHALLENGE: "Challenger",
    DECIDE: "Décider",
    ALIGN: "Aligner",
    DELEGATE: "Déléguer",
    MONITOR: "Surveiller",
}

#: Les statuts d'engagement, dits en français. Les codes viennent de Decision Room.
COMMITMENT_WORDS: Dict[str, str] = {
    "open": "ouvert",
    "in_progress": "en cours",
    "blocked": "bloqué",
    "done": "fait",
    "cancelled": "abandonné",
}

#: Un engagement encore vivant : tout sauf soldé ou abandonné.
LIVE_COMMITMENTS = ("open", "in_progress", "blocked")

#: Les statuts de KPI qui méritent d'être portés dans une conversation.
KPI_WORDS: Dict[str, str] = {"alert": "en alerte", "watch": "à surveiller"}


def date_fr(text: str) -> str:
    """« 2026-11-30 » → « 30 novembre 2026 ». Un texte qui n'est pas une date reste tel quel."""
    try:
        day = datetime.date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return str(text or "")
    return "%d %s %d" % (day.day, MONTHS_FR[day.month - 1], day.year)


def month_fr(period: str) -> str:
    """« 2026-08 » → « août 2026 »."""
    try:
        year, month = int(str(period)[:4]), int(str(period)[5:7])
        return "%s %d" % (MONTHS_FR[month - 1], year)
    except (TypeError, ValueError, IndexError):
        return str(period or "")


def _direction(series: Sequence[float]) -> str:
    if len(series) < 2:
        return ""
    first, last = series[0], series[-1]
    tolerance = abs(first) * TREND_TOLERANCE
    # Les écarts sont négatifs : plus bas, c'est plus loin du plan.
    if last < first - tolerance:
        return WIDENING
    if last > first + tolerance:
        return CLOSING
    return STEADY


def _series(units: Sequence) -> List[float]:
    """La somme des écarts mensuels des canaux budgétés du marché, du plus ancien au
    plus récent, sur les derniers mois. Alignée par la fin : un canal dont l'historique
    est plus court compte sur les mois qu'il a, jamais pour zéro sur les autres."""
    histories = [tuple(getattr(unit, "gap_history", ()) or ()) for unit in units]
    histories = [history for history in histories if history]
    if not histories:
        return []
    depth = min(TREND_MONTHS, max(len(history) for history in histories))
    series = []
    for back in range(depth, 0, -1):
        series.append(sum(history[-back] for history in histories if len(history) >= back))
    return series


def _months_below(units: Sequence) -> int:
    """Le même compte que la détection : le marché, somme de ses canaux, mois par mois."""
    from .detection import _months_below as count

    return count(list(units)) if units else 0


def _year_gap(units: Sequence) -> Optional[float]:
    values = [getattr(unit, "gap_year_to_date", None) for unit in units]
    values = [value for value in values if value is not None]
    return sum(values) if values else None


def _listed(parts: Sequence[str]) -> str:
    parts = [part for part in parts if part]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " et " + parts[-1]


#: Combien de gammes se nomment dans chaque sens sur la ligne « sur quoi ».
RANGES_NAMED = 3


class Conversation:
    """Un sujet porté, et de quoi en parler : les faits en quatre lignes, une question."""

    __slots__ = ("row", "units", "series", "months", "week", "month", "fire", "commitment",
                 "signals", "coming", "ranges")

    def __init__(self, row, units: Sequence = (), series: Sequence[float] = (),
                 months: int = 0, week=None, month=None, fire=None, commitment=None,
                 signals: Sequence = (), coming: Sequence = (), ranges=None) -> None:
        self.row = row
        #: Les canaux budgétés du marché, tels que l'écran les lit ce mois-ci.
        self.units = list(units)
        self.series = list(series)
        self.months = months
        self.week = week
        self.month = month
        #: La carte de feu la plus lourde du marché, quand l'écran en porte une.
        self.fire = fire
        self.commitment = commitment
        self.signals = list(signals)
        self.coming = list(coming)
        #: La lecture produit de ce marché — ses gammes — quand elle existe.
        self.ranges = ranges

    @property
    def issue(self):
        return self.row.issue

    @property
    def market(self) -> str:
        return self.issue.scopes[0] if self.issue.scopes else ""

    @property
    def who(self) -> str:
        return self.issue.accountable or ""

    @property
    def role(self) -> str:
        return ROLE_WORDS.get(self.row.role, self.row.role)

    @property
    def gap(self) -> Optional[float]:
        """L'écart du mois au plan, tous canaux budgétés du marché. `None` sans lecture."""
        if self.units:
            return sum(getattr(unit, "gap_vs_budget", 0.0) or 0.0 for unit in self.units)
        for item in reversed(self.issue.evidence):
            if item.amount is not None:
                return item.amount
        return None

    # ------------------------------------------------------------------ les lignes

    @property
    def year_gap(self) -> Optional[float]:
        """L'écart de l'exercice à date, tous canaux budgétés du marché. None sans historique."""
        return _year_gap(self.units)

    @property
    def stake(self) -> str:
        """L'exercice d'abord, le mois ensuite, depuis combien de mois, et quels canaux le
        portent — dans l'ordre où le lecteur lit la table juste au-dessus."""
        gap = self.gap
        if gap is None:
            return self.issue.evidence[-1].statement if self.issue.evidence else ""
        if not self.units:
            statement = self.issue.evidence[-1].statement if self.issue.evidence else ""
            return "%s%s" % (format_eur(gap), " · " + statement if statement else "")
        year = self.year_gap
        text = ""
        if year is not None:
            text = "%s %s le plan sur l'exercice à date, " % (
                format_eur(abs(year)), "sous" if year < 0 else "au-dessus du")
        text += "%s %s le plan ce mois" % (format_eur(abs(gap)), "sous" if gap < 0 else "au-dessus du")
        if self.months:
            text += ", %d mois consécutifs" % self.months if self.months > 1 else ", premier mois"
        behind = sorted(
            (unit for unit in self.units if (getattr(unit, "gap_vs_budget", 0.0) or 0.0) < 0),
            key=lambda unit: unit.gap_vs_budget,
        )
        if len(self.units) > 1 and behind:
            text += " · " + ", ".join(
                "%s %s" % (getattr(unit, "channel_label", ""), format_eur(unit.gap_vs_budget))
                for unit in behind
            )
        return text

    @property
    def direction(self) -> str:
        return _direction(self.series)

    @property
    def on_ranges(self) -> str:
        """« Sur quoi » : les gammes de ce marché qui reculent le plus sur le dernier mois
        lu, en euros, et celles qui poussent, pour que l'appel parte du produit et non du
        seul total. Vide sans lecture produit."""
        level = self.ranges.level("range") if self.ranges is not None else None
        if level is None:
            return ""
        lines = [line for line in level.lines if line.month_last_year > 0 or line.month_sales > 0]
        falling = sorted([line for line in lines if line.month_delta < 0],
                         key=lambda line: line.month_delta)[:RANGES_NAMED]
        growing = sorted([line for line in lines if line.month_delta > 0],
                         key=lambda line: -line.month_delta)[:RANGES_NAMED]
        parts = []
        if falling:
            parts.append("reculent en %s : %s" % (month_fr(self.ranges.period), ", ".join(
                "%s %s (%s)" % (line.name, line.month_label, format_eur(line.month_delta))
                for line in falling)))
        if growing:
            parts.append("poussent : %s" % ", ".join(
                "%s %s (+%s)" % (line.name, line.month_label, format_eur(line.month_delta))
                for line in growing))
        return " ; ".join(parts)

    @property
    def trend(self) -> str:
        """Le sens sur les derniers mois, puis ce que la semaine et le mois en cours disent."""
        parts = []
        direction = self.direction
        if direction:
            parts.append("l'écart %s : %s sur les %d derniers mois" % (
                direction, " puis ".join(format_eur(value) for value in self.series),
                len(self.series)))
        if self.week is not None:
            week = "la semaine passée %s, %s sur la précédente" % (
                format_eur(self.week.week), self.week.wow_label)
            if self.week.last_year is not None:
                week += ", %s sur l'an dernier" % self.week.yoy_label
            parts.append(week)
        if self.month is not None and getattr(self.month, "readable", False):
            month = "le mois en cours à %s du plan, attendu %s" % (self.month.done, self.month.expected)
            if self.month.gap:
                month += " (%s)" % self.month.gap
            parts.append(month)
        return " ; ".join(parts)

    @property
    def last_reading(self) -> str:
        if not self.issue.readings:
            return ""
        reading = self.issue.readings[-1]
        return "%s (%s)" % (reading.conclusion, date_fr(reading.at))

    @property
    def diagnosis(self) -> str:
        return getattr(self.fire, "diagnosis", "") if self.fire is not None else ""

    @property
    def engaged(self) -> str:
        """Ce qui est déjà en cours sur ce marché : l'engagement, et les KPI qui bougent."""
        parts = []
        item = self.commitment
        if item is not None:
            text = "« %s »" % item.action
            if getattr(item, "owner_name", ""):
                text += ", %s" % item.owner_name
            if getattr(item, "due_date", None):
                text += ", échéance le %s" % date_fr(item.due_date)
            days = getattr(item, "days_left", None)
            if days is not None and days < 0:
                text += " — en retard de %d jour%s" % (-days, "" if days == -1 else "s")
            else:
                text += " — %s" % COMMITMENT_WORDS.get(item.status, item.status)
            parts.append(text)
        if self.signals:
            parts.append("côté clients, %s" % _listed([
                "%s %s" % (kpi.label, KPI_WORDS.get(kpi.status, kpi.status))
                for kpi in self.signals]))
        return " ; ".join(parts)

    @property
    def ahead(self) -> str:
        """Ce qui arrive sur ce marché dans les six semaines, pesé l'an dernier."""
        return " ; ".join("%s %s : %s" % (event.name, event.when, event.weight)
                          for event in self.coming)

    @property
    def question(self) -> str:
        """Une seule question, dans cet ordre : un engagement en retard ou bloqué avant
        tout — c'est la promesse déjà faite ; sinon la question que les leviers posent ;
        sinon la question qu'un écart qui dure pose à celui qui en répond."""
        item = self.commitment
        if item is not None:
            days = getattr(item, "days_left", None)
            if item.status == "blocked":
                return ("L'engagement « %s » est bloqué : sur quoi, et qui le débloque ?"
                        % item.action)
            if days is not None and days < 0:
                return ("L'engagement « %s » était dû le %s : où en est-il, et qu'a-t-il "
                        "changé sur l'écart ?" % (item.action, date_fr(item.due_date)))
        asked = getattr(self.fire, "question", "") if self.fire is not None else ""
        if asked:
            return asked
        gap = self.gap
        if self.months and gap is not None:
            return ("%d mois sous le plan, %s ce mois : qu'est-ce qui a changé sur ce marché, "
                    "et qu'est-ce qui est engagé pour le refermer ?"
                    % (self.months, format_eur(abs(gap))))
        if self.issue.evidence and self.issue.evidence[-1].statement:
            return "%s : qui tranche, et sur quoi ?" % self.issue.evidence[-1].statement
        return "Qu'est-ce qui a changé, et qu'est-ce qui est engagé ?"

    @property
    def arbitrate_hint(self) -> str:
        """Quand la cause est connue et voulue, l'appel n'est pas le bon geste : le sujet se
        tranche par un arbitrage, avec une date de réexamen, et libère son créneau. La
        machine le dit ; le lecteur décide."""
        from . import routing

        routed = getattr(self.fire, "routed", None) if self.fire is not None else None
        if routed is None or getattr(routed, "move", "") != routing.NO_CEO_ACTION:
            return ""
        return ("À arbitrer plutôt qu'à challenger : la cause est connue et voulue. Accepter "
                "l'écart avec une date de réexamen libère ce créneau pour un sujet ouvert.")

    @property
    def retained_for(self) -> str:
        """Les facteurs du moteur, tels quels — pourquoi ce sujet est là (§C6)."""
        return self.row.why


class Watch:
    """Un sujet suivi, en une ligne : l'écart, depuis quand, le sens, qui, la prochaine date."""

    __slots__ = ("row", "gap", "months", "direction", "next_on", "year_gap")

    def __init__(self, row, gap: Optional[float] = None, months: int = 0,
                 direction: str = "", next_on: str = "", year_gap: Optional[float] = None) -> None:
        self.row = row
        self.gap = gap
        self.year_gap = year_gap
        self.months = months
        self.direction = direction
        self.next_on = next_on

    @property
    def issue(self):
        return self.row.issue

    @property
    def line(self) -> str:
        parts = []
        if self.year_gap is not None:
            parts.append("%s sur l'exercice" % format_eur(self.year_gap))
        if self.gap is not None:
            parts.append("%s ce mois" % format_eur(self.gap) if self.year_gap is not None
                         else format_eur(self.gap))
        if self.months:
            parts.append("%d mois sous le plan" % self.months)
        elif self.issue.evidence and self.issue.evidence[-1].statement:
            parts.append(self.issue.evidence[-1].statement)
        if self.direction:
            parts.append(self.direction)
        parts.append(self.issue.accountable or "personne n'en répond")
        if self.next_on:
            parts.append("réexamen le %s" % date_fr(self.next_on))
        elif self.issue.last_seen:
            parts.append("vu %s" % month_fr(self.issue.last_seen[:7]))
        return " · ".join(parts)


class Prepared:
    __slots__ = ("conversations", "watch")

    def __init__(self, conversations: Sequence[Conversation], watch: Sequence[Watch]) -> None:
        self.conversations = list(conversations)
        self.watch = list(watch)


# ------------------------------------------------------------------------- lecture


def _market_units(dataset, market: str) -> List:
    grouped = {}
    if dataset is not None and hasattr(dataset, "by_market"):
        try:
            grouped = dataset.by_market()
        except TypeError:  # pragma: no cover — une propriété plutôt qu'une méthode
            grouped = dataset.by_market
    return list(grouped.get(market, ()))


def _week_line(weekly, market: str):
    if weekly is None:
        return None
    lines = list(getattr(weekly, "perimeters", ()) or ())
    loose = getattr(weekly, "loose", None)
    if loose is not None:
        lines.append(loose)
    for perimeter in lines:
        for line in getattr(perimeter, "markets", ()) or ():
            if line.name == market:
                return line
    return None


def _month_line(month, market: str):
    if month is None:
        return None
    for line in getattr(month, "lines", ()) or ():
        if getattr(line, "market", "") == market:
            return line
    return None


def _fire_for(fires: Sequence, market: str):
    found = [fire for fire in fires or () if getattr(fire.unit, "market", "") == market]
    if not found:
        return None
    return max(found, key=lambda fire: abs(fire.gap))


def _commitment_for(commitments: Sequence, market: str):
    live = [item for item in commitments or ()
            if getattr(item, "market", "") == market and item.status in LIVE_COMMITMENTS]
    if not live:
        return None
    # Le plus pressant d'abord : bloqué, puis en retard, puis le plus proche de son terme.
    def urgency(item):
        days = getattr(item, "days_left", None)
        return (item.status != "blocked", days is None or days >= 0,
                days if days is not None else 10 ** 6)
    return sorted(live, key=urgency)[0]


def _signals_for(kpis: Sequence, market: str) -> List:
    return [kpi for kpi in kpis or ()
            if getattr(kpi, "scope", "") == market and getattr(kpi, "status", "") in KPI_WORDS]


def _coming_for(gifting, market: str) -> List:
    if gifting is None:
        return []
    groups = list(getattr(gifting, "groups", ()) or ())
    loose = getattr(gifting, "loose", None)
    if loose is not None:
        groups.append(loose)
    return [event for group in groups for event in getattr(group, "events", ())
            if getattr(event, "market", "") == market]


def _ranges_for(product_rows, market: str):
    """La lecture produit d'un marché, ou None sans lignes : jamais une requête."""
    if not product_rows or not market:
        return None
    from . import products as products_module

    review = products_module.build(product_rows, market)
    return review if review.usable else None


def build(week, dataset=None, fires: Sequence = (), weekly=None, month=None,
          commitments: Sequence = (), kpis: Sequence = (), gifting=None,
          product_rows: Sequence = ()) -> Prepared:
    """Préparer les sujets portés, à partir de ce que l'écran a déjà lu.

    Tout est optionnel sauf la semaine du moteur : une source absente laisse sa ligne
    vide. Rien ici ne relit l'entrepôt.
    """
    conversations = []
    for row in getattr(week, "attention", ()) or ():
        market = row.issue.scopes[0] if row.issue.scopes else ""
        units = _market_units(dataset, market)
        conversations.append(Conversation(
            row, units=units, series=_series(units),
            months=_months_below(units),
            week=_week_line(weekly, market), month=_month_line(month, market),
            fire=_fire_for(fires, market), commitment=_commitment_for(commitments, market),
            signals=_signals_for(kpis, market), coming=_coming_for(gifting, market),
            ranges=_ranges_for(product_rows, market),
        ))
    watch = []
    for row in getattr(week, "watch", ()) or ():
        market = row.issue.scopes[0] if row.issue.scopes else ""
        units = _market_units(dataset, market)
        gap = sum(getattr(unit, "gap_vs_budget", 0.0) or 0.0 for unit in units) if units else None
        if gap is None:
            for item in reversed(row.issue.evidence):
                if item.amount is not None:
                    gap = item.amount
                    break
        arbitration = row.issue.arbitration
        watch.append(Watch(
            row, gap=gap, year_gap=_year_gap(units),
            months=_months_below(units),
            direction=_direction(_series(units)),
            next_on=arbitration.review_on if arbitration is not None and arbitration.review_on else "",
        ))
    return Prepared(conversations, watch)
