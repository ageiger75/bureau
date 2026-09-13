"""Le dossier de visite : un marché en une page, avant d'aller le voir.

Une page de groupe répond à « où pousser » ; elle ne répond pas à « qu'est-ce que je dois
savoir avant de m'asseoir en face du directeur de ce marché ». Le dossier le fait, dans un
ordre fixe : les trois questions à poser, ses canaux contre le plan, ses boutiques qui
décrochent le plus, son gris sous ses deux définitions — marqué par l'entrepôt, et lu sans
drapeau —, ce qui l'alimente sans passer par lui, les partenaires facturés depuis le pays,
et ce que le registre et les notes en disent déjà. Rien n'est relu à l'entrepôt : tout
vient des lectures que le cockpit tient.

Les questions sont générées, et elles le disent : elles partent de ce que les chiffres
montrent de plus net, pas de ce qu'on sait du marché. Le lecteur les remplace.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .analytics import format_eur, format_pct
from .grey import FEEDERS, NEIGHBOURS, Mention, _growth, _line_for_market

MOST_STORE_MOVES = 5
MOST_PARTNERS = 6
MOST_ISSUES = 8


class Channel:
    __slots__ = ("label", "channel_label", "sales", "gap", "last_year", "is_sell_in",
                 "reason", "question")

    def __init__(self, unit) -> None:
        from .mapping import _channel_label

        self.label = unit.label
        self.channel_label = _channel_label(getattr(unit, "channel", ""))
        self.sales = float(unit.sales_actual or 0.0)
        self.gap = float(unit.gap_vs_budget or 0.0)
        self.last_year = getattr(unit, "sales_last_year", None)
        self.is_sell_in = bool(getattr(unit, "is_sell_in", False))
        self.reason = getattr(unit, "no_breakdown_reason", "") or ""
        self.question = ""

    @property
    def growth(self) -> Optional[float]:
        return _growth(self.sales, self.last_year)

    @property
    def sales_label(self) -> str:
        return format_eur(self.sales)

    @property
    def gap_label(self) -> str:
        return format_eur(self.gap)

    @property
    def growth_label(self) -> str:
        return "n/d" if self.growth is None else format_pct(self.growth)


class StoreMove:
    __slots__ = ("code", "name", "actual", "last_year")

    def __init__(self, code: str, name: str, actual: float, last_year: float) -> None:
        self.code = code
        self.name = name
        self.actual = actual
        self.last_year = last_year

    @property
    def delta(self) -> float:
        return self.actual - self.last_year

    @property
    def growth(self) -> Optional[float]:
        return _growth(self.actual, self.last_year)

    @property
    def actual_label(self) -> str:
        return format_eur(self.actual)

    @property
    def delta_label(self) -> str:
        return format_eur(self.delta)

    @property
    def growth_label(self) -> str:
        return "n/d" if self.growth is None else format_pct(self.growth)


class Feed:
    __slots__ = ("label", "sales", "gap", "last_year")

    def __init__(self, label: str, sales: float, gap: float, last_year) -> None:
        self.label = label
        self.sales = sales
        self.gap = gap
        self.last_year = last_year

    @property
    def sentence(self) -> str:
        growth = _growth(self.sales, self.last_year)
        return "%s : %s ce mois, %s contre le plan, %s contre l'an dernier" % (
            self.label, format_eur(self.sales), format_eur(self.gap),
            "n/d" if growth is None else format_pct(growth))


class Dossier:
    def __init__(self, name: str, owner: str = "", period_label: str = "") -> None:
        self.name = name
        self.owner = owner
        self.period_label = period_label
        self.channels: List[Channel] = []
        self.declines: List[StoreMove] = []
        self.gains: List[StoreMove] = []
        self.stores_note = ""
        #: Le vrac marqué de ce marché (`grey.Market`), ou rien.
        self.marked = None
        self.budget_lines: List = []
        self.expected_to_date: Optional[float] = None
        self.months_elapsed = 0
        self.accounts: List = []
        self.ranges: List = []
        #: Le gris sans drapeau de ce marché (`shadow.Market`), ou rien.
        self.shadow = None
        self.shadow_note = ""
        self.neighbours: List[str] = []
        self.feeds: List[Feed] = []
        self.partners: List = []
        self.iso2 = ""
        self.issues: List[Mention] = []
        self.notes: List = []

    @property
    def slug(self) -> str:
        from .page import slug

        return slug(self.name)

    @property
    def month_gap(self) -> float:
        return sum(item.gap for item in self.channels)

    @property
    def month_sales(self) -> float:
        return sum(item.sales for item in self.channels)

    @property
    def budget_total(self) -> float:
        return sum(float(getattr(line, "sales", 0.0) or 0.0) for line in self.budget_lines)

    @property
    def budget_sentence(self) -> str:
        if not self.budget_lines or not self.months_elapsed:
            return "le budget ne nomme aucune ligne de flux à nettoyer pour %s" % self.name
        expected = self.expected_to_date or 0.0
        text = "le budget nomme %s de flux à nettoyer sur l'exercice (%s), soit %s à date au prorata de %d mois" % (
            format_eur(self.budget_total), ", ".join(str(line.name) for line in self.budget_lines),
            format_eur(expected), self.months_elapsed)
        if self.marked is not None and expected > 0:
            ratio = self.marked.bulk / expected
            text += (" — le vrac marqué est au-dessus" if ratio > 1.15 else
                     " — le vrac marqué est en dessous, et le budget compte aussi ce que l'entrepôt ne marque pas"
                     if ratio < 0.85 else " — le vrac marqué est dans l'ordre de grandeur")
        return text

    @property
    def marked_sentence(self) -> str:
        if self.marked is None:
            return "aucun vrac marqué sur %s dans les relevés" % self.name
        m = self.marked
        return ("vrac marqué : %s à date, %s des ventes du marché, %s sur l'an dernier, %s sur "
                "trois mois — %s" % (m.bulk_label, m.share_label, m.growth_label,
                                     m.growth_recent_label, m.word))

    @property
    def questions(self) -> List[str]:
        """Trois questions, générées de ce que les chiffres montrent de plus net."""
        found: List[str] = []
        shadow = self.shadow
        if shadow is not None and shadow.quantity.usable and shadow.quantity.stores:
            top = shadow.quantity.stores[0]
            if shadow.quantity.marks_its_bulk is False:
                found.append("Chez %s (%s), qui achète plus de cinquante unités par ticket, et "
                             "pourquoi ces tickets ne sont pas marqués comme du vrac quand d'autres "
                             "marchés les marquent ? Le flux est-il assumé, ou caché ?"
                             % (top.code, top.sub_channel))
            else:
                found.append("Chez %s (%s), %s de gros tickets à date, %s sur l'an dernier : "
                             "qui est le client final ?" % (top.code, top.sub_channel,
                                                           top.ytd_label, top.growth_label))
        elif self.accounts:
            top = self.accounts[0]
            found.append("%s : %s de vrac à date, %s sur l'an dernier. Qui est ce compte, et "
                         "qu'est-ce qu'on lui vend ?" % (top.label, top.ytd_label, top.growth_label))
        if self.declines:
            worst = self.declines[0]
            found.append("%s : %s sur le mois contre l'an dernier (%s). Qu'est-ce qui s'est "
                         "arrêté, une décision ou un acheteur, et où le volume est-il parti ?"
                         % (worst.name or worst.code, worst.delta_label, worst.growth_label))
        if self.marked is not None and (self.marked.share_of_market or 0.0) >= 0.05:
            found.append("La croissance de %s, c'est hors vrac ou vrac compris ? Laquelle est "
                         "dans le plan, laquelle est dans le bonus ?" % self.name)
        if len(found) < 3 and self.channels:
            worst = min(self.channels, key=lambda item: item.gap)
            if worst.gap < 0:
                found.append("%s : %s contre le plan ce mois. Qu'est-ce qui est engagé pour le "
                             "refermer, et d'ici quand ?" % (worst.label, worst.gap_label))
        if len(found) < 3 and self.feeds:
            found.append("%s. Ce que le duty free absorbe se retrouve quelque part : où ?"
                         % self.feeds[0].sentence)
        return found[:3]

    def lines(self) -> List[str]:
        """Le dossier en texte, pour la commande."""
        out = ["%s · %s · %s" % (self.name, self.owner or "sans MD", self.period_label)]
        out.append("LES TROIS QUESTIONS")
        for index, question in enumerate(self.questions, start=1):
            out.append("  %d. %s" % (index, question))
        out.append("CANAUX — le mois contre le plan et l'an dernier")
        for item in self.channels:
            out.append("  %-34s %10s  %10s vs plan  %8s vs l'an dernier%s" % (
                item.label[:34], item.sales_label, item.gap_label, item.growth_label,
                "  (sell-in)" if item.is_sell_in else ""))
        out.append("BOUTIQUES — celles qui décrochent le plus sur le mois")
        if self.stores_note:
            out.append("  " + self.stores_note)
        for move in self.declines:
            out.append("  %-40s %10s  %10s  %s" % ((move.name or move.code)[:40], move.actual_label,
                                                   move.delta_label, move.growth_label))
        if self.gains:
            out.append("  et celles qui poussent : " + ", ".join(
                "%s %s" % (move.name or move.code, move.delta_label) for move in self.gains))
        out.append("GRIS — marqué par l'entrepôt, et lu sans drapeau")
        out.append("  " + self.marked_sentence)
        out.append("  " + self.budget_sentence)
        for line in self.accounts:
            out.append("  %-40s %10s  part %5s  %8s  3 mois %8s  %s" % (
                line.label[:40], line.ytd_label, line.share_label, line.growth_label,
                line.growth_recent_label, line.word))
        if self.shadow is not None and self.shadow.usable:
            for piece in self.shadow.slices:
                out.append("  " + piece.sentence)
                for store in piece.shown:
                    out.append("    %-34s %10s  part %5s  %8s  marqué %5s" % (
                        ("%s · %s" % (store.code, store.sub_channel))[:34], store.ytd_label,
                        store.share_label, store.growth_label, store.marking_label))
        else:
            out.append("  " + (self.shadow_note or "le gris sans drapeau n'est pas lu"))
        out.append("CE QUI L'ALIMENTE SANS PASSER PAR LUI")
        for sentence in self.neighbours:
            out.append("  " + sentence)
        for feed in self.feeds:
            out.append("  " + feed.sentence)
        if not self.neighbours and not self.feeds:
            out.append("  rien de connu")
        out.append("PARTENAIRES FACTURÉS DEPUIS %s" % (self.iso2 or "le pays"))
        for partner, line in self.partners:
            out.append("  %-30s %-18s %10s  %8s  3 mois %8s  %s" % (
                partner.name[:30], partner.channel_label[:18], line.ytd_label,
                line.growth_ytd_label, line.growth_recent_label, line.word))
        if not self.partners:
            out.append("  aucun, ou pays de facturation inconnu")
        out.append("REGISTRE ET NOTES")
        for item in self.issues:
            out.append("  %s · %s · %s%s" % (item.issue_id, item.title[:100], item.status_word,
                                             (" — " + item.conclusion) if item.conclusion else ""))
        for note in self.notes:
            out.append("  note %s%s depuis %s : %s" % (
                note.kind, (" · " + note.channel) if note.channel else "", note.since or "—",
                note.text[:120]))
        if not self.issues and not self.notes:
            out.append("  rien d'écrit")
        return out


def build(market: str, dataset=None, grey_review=None, shadow_review=None, plan=None,
          accounts=None, register=None, notes: Sequence = (), store_sales=None,
          iso2_by_market: Optional[Dict[str, str]] = None, owner: str = "") -> Dossier:
    from ..domain import issues as domain
    from .budget import normalise_market

    name = normalise_market(market)
    dossier = Dossier(name, owner, str(getattr(dataset, "period_label", "") or ""))

    units = list(getattr(dataset, "units", []) or [])
    dossier.channels = sorted(
        (Channel(unit) for unit in units
         if getattr(unit, "market", "") == name and not getattr(unit, "is_aggregate", False)),
        key=lambda item: -item.sales)

    if store_sales is not None and getattr(store_sales, "usable", False):
        moves = []
        for store in store_sales.stores:
            if getattr(store, "is_bulk", False):
                continue
            if normalise_market(str(getattr(store, "market", "") or "")) != name:
                continue
            actual = float(getattr(store, "actual", 0.0) or 0.0)
            last_year = getattr(store, "last_year", None)
            if last_year is None or float(last_year) <= 0:
                continue
            moves.append(StoreMove(str(store.code), str(getattr(store, "name", "") or ""),
                                   actual, float(last_year)))
        moves.sort(key=lambda move: move.delta)
        dossier.declines = [move for move in moves if move.delta < 0][:MOST_STORE_MOVES]
        dossier.gains = [move for move in reversed(moves) if move.delta > 0][:3]
        if not moves:
            dossier.stores_note = "aucune boutique de %s avec un an dernier dans le fichier" % name
    else:
        dossier.stores_note = "le fichier par boutique n'est pas déposé"

    if grey_review is not None:
        dossier.marked = next((m for m in grey_review.markets if m.scope == name), None)
        dossier.months_elapsed = getattr(grey_review, "months_elapsed", 0) or 0
        dossier.budget_lines = _line_for_market(plan, name)
        if dossier.budget_lines and dossier.months_elapsed:
            dossier.expected_to_date = dossier.budget_total * dossier.months_elapsed / 12.0
        detail = getattr(grey_review, "detail", None)
        if detail is not None and detail.usable:
            dossier.accounts = [line for line in detail.accounts if line.market == name]
            dossier.ranges = list(detail.ranges)
        for neighbour in NEIGHBOURS.get(name, ()):
            other = next((m for m in grey_review.markets if m.scope == neighbour), None)
            if other is not None and dossier.marked is not None:
                dossier.neighbours.append(
                    "%s : vrac marqué %s sur trois mois, %s ; %s : %s sur trois mois, %s — un flux "
                    "qui change de porte se lit sur les deux"
                    % (name, dossier.marked.growth_recent_label, dossier.marked.word, neighbour,
                       other.growth_recent_label, other.word))

    if shadow_review is not None:
        dossier.shadow = shadow_review.for_market(name)
        dossier.shadow_note = getattr(shadow_review, "note", "") or ""

    for feeder in FEEDERS.get(name, ()):
        for unit in units:
            if getattr(unit, "market", "") == feeder and getattr(unit, "is_sell_in", False):
                dossier.feeds.append(Feed(unit.label, float(unit.sales_actual or 0.0),
                                          float(unit.gap_vs_budget or 0.0),
                                          getattr(unit, "sales_last_year", None)))

    dossier.iso2 = (iso2_by_market or {}).get(name, "")
    if dossier.iso2 and accounts is not None:
        billed = []
        for partner in getattr(accounts, "partners", []) or []:
            for line in getattr(partner, "countries", []) or []:
                if line.country == dossier.iso2 and line.ytd > 0:
                    billed.append((line.ytd, partner, line))
        billed.sort(key=lambda item: -item[0])
        dossier.partners = [(partner, line) for _ytd, partner, line in billed[:MOST_PARTNERS]]

    found = []
    for issue in getattr(register, "issues", []) or []:
        scopes = getattr(issue, "scopes", []) or []
        if name in scopes or name.lower() in (issue.title or "").lower():
            found.append(issue)
    found.sort(key=lambda issue: issue.status == domain.CLOSED)
    dossier.issues = [Mention(issue) for issue in found[:MOST_ISSUES]]
    dossier.notes = [note for note in notes if getattr(note, "market", "") == name]
    return dossier
