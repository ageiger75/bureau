"""Une page par périmètre : ce qu'il faut savoir trente secondes avant un appel avec son MD.

Le même squelette pour les sept, pour que deux périmètres se comparent sans que le format
ait bougé : sommes-nous en ligne, ce mois-ci et sur l'exercice ; où atterrit l'année ; le
mois marché par marché ; le mix ; les sujets du registre qui le concernent ; et la seule
question du jour. Le MD est nommé. Rien ici n'est une donnée nouvelle : tout existe sur
l'écran du jour, découpé autrement — cette page ne fait que le filtrer sur les marchés que
l'annuaire place sous ce MD.

**L'atterrissage** répond à la question du risque : où finit l'exercice ? Deux lectures,
et aucune n'est une prévision. « Si le reste tient le plan » : les mois clos tels qu'ils
sont, plus le plan de tout ce qui reste. « À ce rythme » : les mois clos tels qu'ils sont,
plus le plan du reste au ratio réalisé sur plan des mois clos. La vérité est entre les
deux, ou en dehors, et la page ne prétend pas savoir où.
"""

from __future__ import annotations

import unicodedata
from typing import Dict, List, Optional, Sequence

from . import track as track_module

#: Le nombre de sujets et de feux portés sur la page. Au-delà, on compte.
MOST_SUBJECTS = 5
MOST_FIRES = 3


def slug(name: str) -> str:
    """« Greater China » -> « greater-china », « Japon » -> « japon »."""
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return "-".join(part for part in text.lower().replace("'", " ").split() if part)


class Landing:
    """Où finit l'exercice, selon trois hypothèses qu'aucune ne prétend prédire.

    *Si le reste tient le plan* : les mois clos plus le plan des mois restants. *À ce
    rythme* : le plan des mois restants au taux tenu sur les mois clos — le plan porte
    déjà sa saison, mais un retard de cinq pour cent pris sur des mois creux n'est pas
    un retard de cinq pour cent sur la saison des fêtes. *À la croissance tenue* : l'an
    dernier des mois restants, mois par mois, à la croissance mesurée sur les mois clos —
    les mois restants pèsent ce qu'ils ont pesé, et un plan mal phasé ne déplace plus
    l'atterrissage. Les deux dernières encadrent ; l'écart entre elles est la part du
    phasage du plan dans le chiffre, et il est dit.

    Les temps forts qui changent de mois d'un exercice à l'autre sont nommés à côté, pas
    comptés : un événement qui passe d'octobre à novembre déplace un mois, et le poids de
    l'an dernier n'en sait rien. Le lecteur, si.
    """

    __slots__ = ("closed_actual", "closed_budget", "full_plan", "closed_through",
                 "months_left", "absent", "closed_last_year", "remaining_last_year",
                 "moved_events")

    def __init__(self, closed_actual=0.0, closed_budget=0.0, full_plan=0.0,
                 closed_through="", months_left=0, absent="", closed_last_year=0.0,
                 remaining_last_year=0.0, moved_events: Sequence[str] = ()) -> None:
        self.closed_actual = closed_actual
        self.closed_budget = closed_budget
        self.full_plan = full_plan
        self.closed_through = closed_through
        self.months_left = months_left
        self.absent = absent
        #: L'an dernier des mois clos, publié avec eux, et l'an dernier des mois restants,
        #: lu dans le plan mois par mois. Zéro quand l'une des deux sources ne le porte pas.
        self.closed_last_year = closed_last_year
        self.remaining_last_year = remaining_last_year
        #: Les temps forts des mois restants qui ne tombent pas dans le même mois que l'an
        #: dernier — une phrase chacun, jamais un coefficient.
        self.moved_events = list(moved_events)

    @property
    def weighted_usable(self) -> bool:
        return self.closed_last_year > 0 and self.remaining_last_year > 0

    @property
    def growth(self) -> float:
        """Réalisé sur l'an dernier des mois clos — la croissance tenue jusqu'ici."""
        return self.closed_actual / self.closed_last_year - 1.0 if self.closed_last_year else 0.0

    @property
    def at_growth(self) -> float:
        return self.closed_actual + self.remaining_last_year * (1.0 + self.growth)

    @property
    def gap_at_growth(self) -> float:
        return self.at_growth - self.full_plan

    @property
    def growth_label(self) -> str:
        return "%+.1f %%" % (self.growth * 100)

    @property
    def low(self) -> float:
        return min(self.at_pace, self.at_growth) if self.weighted_usable else self.at_pace

    @property
    def high(self) -> float:
        return max(self.at_pace, self.at_growth) if self.weighted_usable else self.at_pace

    @property
    def phasing_gap(self) -> float:
        """Ce que le phasage du plan met entre les deux hypothèses."""
        return self.at_growth - self.at_pace if self.weighted_usable else 0.0

    @property
    def usable(self) -> bool:
        return not self.absent and self.full_plan > 0 and self.closed_budget > 0

    @property
    def remaining_plan(self) -> float:
        return self.full_plan - self.closed_budget

    @property
    def pace(self) -> float:
        """Réalisé sur plan des mois clos — le rythme tenu jusqu'ici."""
        return self.closed_actual / self.closed_budget if self.closed_budget else 0.0

    @property
    def at_plan(self) -> float:
        return self.closed_actual + self.remaining_plan

    @property
    def at_pace(self) -> float:
        return self.closed_actual + self.remaining_plan * self.pace

    @property
    def gap_at_plan(self) -> float:
        return self.at_plan - self.full_plan

    @property
    def gap_at_pace(self) -> float:
        return self.at_pace - self.full_plan

    @property
    def pct_at_pace(self) -> float:
        return self.gap_at_pace / self.full_plan if self.full_plan else 0.0

    @property
    def pace_label(self) -> str:
        return "%+.1f %%" % ((self.pace - 1.0) * 100)


def landing(markets: Optional[Sequence[str]], published, budget, period: str,
            closed_through: str, calendar=None) -> Landing:
    """L'atterrissage d'un ensemble de marchés — tous quand `markets` est None."""
    if not closed_through:
        return Landing(absent="pas de mois clos publié jusqu'au mois précédent")
    if budget is None:
        return Landing(absent="classeur de plan absent : le plan de l'année n'est pas lu")
    start = track_module._fiscal_start(period)
    year, month = int(start[:4]), int(start[5:7])
    periods = []
    for offset in range(12):
        periods.append("%04d-%02d" % (year + (month + offset - 1) // 12,
                                      (month + offset - 1) % 12 + 1))
    wanted = set(markets) if markets is not None else None
    full_plan = sum((line.budget or 0.0) for line in budget.lines
                    if line.period in periods and (wanted is None or line.market in wanted))
    remaining = [p for p in periods if p > closed_through]
    remaining_last_year = sum((getattr(line, "last_year", None) or 0.0) for line in budget.lines
                              if line.period in remaining and (wanted is None or line.market in wanted))
    closed_actual, closed_budget, closed_last_year = _closed_three(published, markets)
    if not full_plan:
        return Landing(absent="aucun plan sur l'exercice pour ces marchés")
    return Landing(closed_actual, closed_budget, full_plan, closed_through, len(remaining),
                   closed_last_year=closed_last_year, remaining_last_year=remaining_last_year,
                   moved_events=moved_events(calendar, markets, remaining))


def _closed_three(published, markets: Optional[Sequence[str]]):
    """Actual, budget et an dernier publiés, sur tout le fichier ou sur des marchés nommés."""
    from . import actuals as actuals_module

    if markets is None:
        totals = published.totals()
        return totals["actual"], totals["budget"], totals.get("last_year", 0.0)
    wanted = set(markets)
    actual = budget = last_year = 0.0
    for line in actuals_module.by_scope(published).values():
        if line.market in wanted:
            actual += line.actual
            budget += line.budget
            last_year += getattr(line, "last_year", 0.0) or 0.0
    return actual, budget, last_year


def moved_events(calendar, markets: Optional[Sequence[str]], remaining: Sequence[str]) -> List[str]:
    """Les temps forts des mois restants qui ne tombent pas dans le même mois que l'an
    dernier, une phrase chacun. Rien sans calendrier ; rien quand tout tombe pareil."""
    if calendar is None or not getattr(calendar, "usable", False) or not remaining:
        return []
    from . import events as events_module
    from .invoiced import MONTHS_FR

    found = []
    for series in calendar.series.values():
        if markets is not None and not any(events_module.same_country(series.country, m) for m in markets):
            continue
        dated = series.dated
        for event in dated.values():
            this_month = str(event.start or "")[:7]
            if this_month not in remaining:
                continue
            before = dated.get(str(int(event.year) - 1)) if str(event.year).isdigit() else None
            if before is None:
                continue
            last_month = str(before.start or "")[:7]
            if len(last_month) < 7 or last_month[5:7] == this_month[5:7]:
                continue
            found.append("%s (%s) : en %s cette année, en %s l'an dernier"
                         % (series.name, series.country, MONTHS_FR[int(this_month[5:7]) - 1],
                            MONTHS_FR[int(last_month[5:7]) - 1]))
    return sorted(found)


class Page:
    """Tout ce que la page rend, déjà filtré."""

    def __init__(self, name: str, lead: str, markets: Sequence[str], scope,
                 land: Landing, month_group, mix, subjects: Sequence, watched: Sequence,
                 fires: Sequence, absent: Sequence[str], ebitda=None, pnl=None,
                 weekly=None, invoiced=None, gifting=None, retail: Sequence = (),
                 retail_years: str = "", talks: Sequence = (), watch_lines: Sequence = (),
                 products=None, elsewhere: Sequence = (), clients=None) -> None:
        self.name = name
        self.lead = lead
        self.markets = list(markets)
        #: Le périmètre tel que le verdict le voit — mois et exercice.
        self.scope = scope
        self.landing = land
        self.month_group = month_group
        self.mix = mix
        self.subjects = list(subjects)
        self.watched = list(watched)
        self.fires = list(fires)
        self.absent = list(absent)
        #: Le plan EBITDA de ce périmètre, tel que la Finance l'a budgété — ou None.
        self.ebitda = ebitda
        #: La contribution réalisée à date de ce périmètre, au compte de gestion — ou None.
        self.pnl = pnl
        #: Son écart au budget, poste par poste, avec le verdict de chaque poste.
        self.pnl_breakdown = ""
        #: La semaine de ce périmètre, marché par marché — ou None.
        self.weekly = weekly
        #: Le sell-in du mois facturé à date pour ce périmètre — ou None.
        self.invoiced = invoiced
        #: Ce qui arrive sur ce périmètre dans les six semaines — ou None.
        self.gifting = gifting
        #: L'euro suivant en boutique, marché par marché, mesuré — vide sans le fichier.
        self.retail = list(retail)
        self.retail_years = retail_years
        #: Les conversations préparées de ce périmètre, et ses lignes de surveillance —
        #: la même préparation que l'écran du jour, filtrée sur ses marchés.
        self.talks = list(talks)
        self.watch_lines = list(watch_lines)
        #: Ce qui marche par produit sur ce périmètre — catégories et gammes, la somme de
        #: ses marchés — ou None sans lecture produit.
        self.products = products
        #: Les clients de ce périmètre — le pont et le flux, la somme de ses marchés — ou None.
        self.clients = clients
        #: Les écarts de ce périmètre qui ne sont pas une conversation commerciale — une
        #: frontière comptable, une mesure qui a changé, des livraisons arrêtées exprès —
        #: portés ici, à côté du sell-in, parce que c'est là qu'on les cherche.
        self.elsewhere = list(elsewhere)
        #: La contribution réalisée à date de ce périmètre, au compte de gestion — ou None.
        self.pnl = pnl
        #: Son écart au budget, poste par poste, avec le verdict de chaque poste.
        self.pnl_breakdown = ""

    @property
    def slug(self) -> str:
        return slug(self.name)

    @property
    def question(self) -> str:
        """La seule question du jour : le sujet porté cette semaine, sinon le plus gros feu,
        sinon ce que le verdict du mois dit."""
        if self.subjects:
            return self.subjects[0].issue.title
        if self.fires:
            return getattr(self.fires[0], "question", "") or ""
        month = self.scope.month if self.scope else None
        if month is not None and month.usable and month.label != track_module.IN_LINE:
            return "%s ce mois-ci, %s : qu'est-ce qui l'explique ?" % (
                month.label.capitalize(), month.gap_label)
        return ""


def _in(markets: Sequence[str], scope_text: str) -> bool:
    head = (scope_text or "").split("/")[0].strip()
    return head in markets


def build(name: str, lead: str, markets: Sequence[str], dataset, month_review, track,
          week=None, fires: Sequence = (), contribution=None, published=None,
          budget=None, ebitda=None, incremental=None, pnl=None, weekly=None,
          invoiced=None, gifting=None, retail=None, prepared=None, products=None,
          elsewhere: Sequence = (), clients=None) -> Page:
    """Assembler la page d'un périmètre à partir de ce que l'écran du jour a déjà lu."""
    from . import mix as mix_module
    from .model import Dataset

    absent: List[str] = []
    wanted = set(markets)
    scope = next((item for item in getattr(track, "perimeters", []) if item.name == name),
                 None)
    if scope is None:
        absent.append("aucun verdict pour ce périmètre : ses marchés ne sont pas lus sur "
                      "le mois en cours")
    group = next((item for item in getattr(month_review, "groups", []) if item.name == name),
                 None)
    units = [unit for unit in getattr(dataset, "units", []) if unit.market in wanted]
    mix = None
    if units:
        subset = Dataset(getattr(dataset, "period_label", ""), getattr(dataset, "as_of", ""),
                         units, period=getattr(dataset, "period", ""))
        mix = mix_module.build(subset, contribution, incremental)
    else:
        absent.append("aucune unité de l'écran sur ces marchés : pas de mix")
    land = landing(list(markets), published, budget, getattr(track, "period", "") or "",
                   getattr(track, "closed_through", "") or "")
    subjects = [row for row in getattr(week, "attention", [])
                if any(_in(markets, scope_text) for scope_text in row.issue.scopes)]
    watched = [row for row in getattr(week, "watch", [])
               if any(_in(markets, scope_text) for scope_text in row.issue.scopes)]
    mine = [fire for fire in fires if getattr(fire.unit, "market", "") in wanted]
    plan = ebitda.for_name(name) if ebitda is not None else None
    if ebitda is not None and plan is None:
        absent.append("aucune ligne EBITDA au budget pour ce périmètre")
    done = pnl.for_name(name) if pnl is not None else None
    seven = weekly.for_name(name) if weekly is not None and weekly.usable else None
    billed = invoiced.for_name(name) if invoiced is not None and invoiced.usable else None
    ahead = gifting.for_name(name) if gifting is not None and gifting.usable else None
    stores = retail.for_markets(markets) if retail is not None and not retail.is_empty else []
    talks = [talk for talk in getattr(prepared, "conversations", ()) or () if talk.market in wanted]
    watch_lines = [item for item in getattr(prepared, "watch", ()) or ()
                   if item.issue.scopes and item.issue.scopes[0] in wanted]
    built = Page(name, lead, sorted(markets), scope, land, group, mix,
                 subjects[:MOST_SUBJECTS], watched[:MOST_SUBJECTS], mine[:MOST_FIRES],
                 absent, ebitda=plan, pnl=done, weekly=seven, invoiced=billed, gifting=ahead,
                 retail=stores, retail_years=retail.years if retail is not None else "",
                 talks=talks, watch_lines=watch_lines, products=products, clients=clients,
                 elsewhere=[fire for fire in elsewhere
                            if getattr(getattr(fire, "unit", None), "market", "") in wanted])
    if pnl is not None and done is not None:
        built.pnl_breakdown = pnl.breakdown(name)
    return built


def perimeters(directory, month_review) -> Dict[str, Dict[str, object]]:
    """Les périmètres connus, avec leur MD et leurs marchés : l'annuaire d'abord, puis ce
    que le mois a placé sans lui."""
    known: Dict[str, Dict[str, object]] = {}
    if directory is not None and len(directory):
        for bu in directory.bus():
            markets = directory.markets_of(bu)
            entry = directory.entry_for(markets[0]) if markets else None
            lead = ""
            if entry is not None:
                head = getattr(directory, "_by_bu", {}).get(bu.strip().lower())
                lead = head.name if head is not None else entry.name
            known[bu] = {"lead": lead, "markets": markets}
    for group in getattr(month_review, "groups", []):
        item = known.setdefault(group.name, {"lead": group.lead, "markets": []})
        if not item["lead"]:
            item["lead"] = group.lead
        for line in group.lines:
            if line.market not in item["markets"]:
                item["markets"].append(line.market)
    return known
