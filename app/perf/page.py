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
    """Où finit l'exercice, selon deux hypothèses qu'aucune ne prétend prédire."""

    __slots__ = ("closed_actual", "closed_budget", "full_plan", "closed_through",
                 "months_left", "absent")

    def __init__(self, closed_actual=0.0, closed_budget=0.0, full_plan=0.0,
                 closed_through="", months_left=0, absent="") -> None:
        self.closed_actual = closed_actual
        self.closed_budget = closed_budget
        self.full_plan = full_plan
        self.closed_through = closed_through
        self.months_left = months_left
        self.absent = absent

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
            closed_through: str) -> Landing:
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
    closed_actual, closed_budget = track_module._closed_for(published, markets)
    left = len([p for p in periods if p > closed_through])
    if not full_plan:
        return Landing(absent="aucun plan sur l'exercice pour ces marchés")
    return Landing(closed_actual, closed_budget, full_plan, closed_through, left)


class Page:
    """Tout ce que la page rend, déjà filtré."""

    def __init__(self, name: str, lead: str, markets: Sequence[str], scope,
                 land: Landing, month_group, mix, subjects: Sequence, watched: Sequence,
                 fires: Sequence, absent: Sequence[str], ebitda=None, pnl=None) -> None:
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
          budget=None, ebitda=None, incremental=None, pnl=None) -> Page:
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
    built = Page(name, lead, sorted(markets), scope, land, group, mix,
                 subjects[:MOST_SUBJECTS], watched[:MOST_SUBJECTS], mine[:MOST_FIRES],
                 absent, ebitda=plan, pnl=done)
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
