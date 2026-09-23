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

from typing import Dict, List, Optional, Sequence, Tuple

from .analytics import format_eur, format_pct
from .grey import (FEEDERS, FLAG_NOT_VALIDATED, NEIGHBOURS, Mention, _growth, _line_for_market,
                   flag_validated)

MOST_STORE_MOVES = 5
#: Par niveau produit et par sens, les lignes que le terminal montre.
MOST_PRODUCT_LINES = 5
MOST_PARTNERS = 6
MOST_ISSUES = 8
#: Les mots de la feuille de la CFO qui disent qu'une boutique est fermée. La feuille ne
#: parle pas comme le référentiel : quand aucun mot ne s'y retrouve, le dossier montre le
#: statut tel quel et ne conclut pas.
CLOSED_WORDS = ("clos", "ferm", "close")
#: Au-delà de cette part de gros tickets non marqués, la première question est celle-là.
UNMARKED_WORTH_ASKING = 0.2
#: Le gris côté sell-in n'a pas de drapeau : les factures aux partenaires n'en portent pas.
#: Ce qui se lit, c'est le ciseau — un sell-in qui pousse de dix points de plus que le
#: sell-out du même marché, quand le sell-in pèse assez pour compter.
SCISSORS_POINTS = 0.10
LEAST_SELL_IN_SHARE = 0.15
#: Un partenaire de duty free facturé depuis le pays qui bondit d'autant sur trois mois, ou
#: sans an dernier, vaut une question.
DUTY_FREE_JUMP = 0.25


class Channel:
    __slots__ = ("label", "channel_label", "sales", "gap", "last_year", "is_sell_in",
                 "reason", "question", "budget_known")

    def __init__(self, unit) -> None:
        from .mapping import _channel_label

        self.label = unit.label
        self.channel_label = _channel_label(getattr(unit, "channel", ""))
        self.sales = float(unit.sales_actual or 0.0)
        #: Sans plan connu, pas d'écart : un écart égal aux ventes dirait que le plan est
        #: zéro, ce qui n'est jamais ce qu'un plan absent veut dire.
        self.budget_known = bool(getattr(unit, "budget_known", True))
        self.gap = float(unit.gap_vs_budget or 0.0) if self.budget_known else 0.0
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
        return format_eur(self.gap) if self.budget_known else "plan non lu"

    @property
    def growth_label(self) -> str:
        return "n/d" if self.growth is None else format_pct(self.growth)


class StoreMove:
    __slots__ = ("code", "name", "actual", "last_year", "status", "closed_codes")

    def __init__(self, code: str, name: str, actual: float, last_year: float,
                 status: str = "", closed_codes: Sequence[str] = ()) -> None:
        self.code = code
        self.name = name
        self.actual = actual
        self.last_year = last_year
        #: Le statut de la feuille de la CFO : une boutique fermée n'est pas une boutique
        #: muette, et la seconde vaut une question.
        self.status = status
        #: Les codes que la configuration déclare fermés (`CEOOS_STORE_CLOSED_STATUSES`) :
        #: la feuille parle en chiffres, et le dossier ne devine pas ce qu'ils veulent dire.
        self.closed_codes = tuple(str(code).strip() for code in closed_codes)

    @property
    def closed(self) -> bool:
        status = (self.status or "").strip()
        if status and status in self.closed_codes:
            return True
        return any(word in status.lower() for word in CLOSED_WORDS)

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
    __slots__ = ("label", "sales", "gap", "last_year", "budget_known")

    def __init__(self, label: str, sales: float, gap: float, last_year,
                 budget_known: bool = True) -> None:
        self.label = label
        self.sales = sales
        self.gap = gap if budget_known else 0.0
        self.last_year = last_year
        self.budget_known = budget_known

    @property
    def sentence(self) -> str:
        growth = _growth(self.sales, self.last_year)
        return "%s : %s ce mois, %s, %s contre l'an dernier" % (
            self.label, format_eur(self.sales),
            ("%s contre le plan" % format_eur(self.gap)) if self.budget_known else "plan non lu",
            "n/d" if growth is None else format_pct(growth))


class Dossier:
    def __init__(self, name: str, owner: str = "", period_label: str = "") -> None:
        self.name = name
        self.owner = owner
        self.period_label = period_label
        self.channels: List[Channel] = []
        self.declines: List[StoreMove] = []
        self.gains: List[StoreMove] = []
        #: Les boutiques sans vente ce mois avec un an dernier : fermées, ou muettes — pas
        #: des décrochages, et comptées à part.
        self.silent: List[StoreMove] = []
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
        #: Les centres arrêtés et nouveaux facturés depuis le pays : la relève, ou le trou.
        self.stopped: List = []
        self.newcomers: List = []
        self.iso2 = ""
        self.issues: List[Mention] = []
        self.notes: List = []
        #: Ce qui marche par produit sur ce marché — catégories et gammes, la même lecture
        #: que la page du périmètre, sur ce seul marché — ou None.
        self.products = None

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

    # ---- côté sell-in : ce que la lecture du gris ne couvre pas, et le ciseau
    @property
    def sell_in_channels(self) -> List[Channel]:
        return [item for item in self.channels if item.is_sell_in]

    @property
    def sell_out_channels(self) -> List[Channel]:
        return [item for item in self.channels if not item.is_sell_in]

    @staticmethod
    def _growth_of(channels: Sequence[Channel]) -> Optional[float]:
        known = [item for item in channels if item.last_year is not None]
        if not known:
            return None
        return _growth(sum(item.sales for item in known),
                       sum(float(item.last_year or 0.0) for item in known))

    @property
    def sell_in_sales(self) -> float:
        return sum(item.sales for item in self.sell_in_channels)

    @property
    def sell_in_share(self) -> Optional[float]:
        total = self.month_sales
        return self.sell_in_sales / total if total > 0 and self.sell_in_channels else None

    @property
    def sell_in_share_label(self) -> str:
        share = self.sell_in_share
        return "%.0f %%" % (share * 100) if share is not None else "aucun"

    sell_in_growth = property(lambda self: self._growth_of(self.sell_in_channels))
    sell_out_growth = property(lambda self: self._growth_of(self.sell_out_channels))

    @property
    def scissors(self) -> Optional[float]:
        """Le sell-in moins le sell-out, en points de croissance sur l'an dernier."""
        if self.sell_in_growth is None or self.sell_out_growth is None:
            return None
        return self.sell_in_growth - self.sell_out_growth

    @property
    def scissors_open(self) -> bool:
        share = self.sell_in_share or 0.0
        return (self.scissors is not None and self.scissors >= SCISSORS_POINTS
                and share >= LEAST_SELL_IN_SHARE)

    @property
    def sell_in_grey_sentence(self) -> str:
        """Le gris côté sell-in : ce que les factures aux partenaires pèsent dans le marché,
        hors de toute lecture à drapeau, et le ciseau quand il s'ouvre."""
        if not self.channels:
            return ""
        if not self.sell_in_channels:
            return ("aucun canal sell-in sur %s ce mois : le gris de ce marché passe par ses "
                    "tickets, que la lecture couvre" % self.name)
        text = ("le sell-in fait %s des ventes du mois de %s (%s), hors de toute lecture du "
                "gris : les factures aux partenaires ne portent pas de drapeau vrac"
                % (self.sell_in_share_label, self.name, format_eur(self.sell_in_sales)))
        if self.sell_in_growth is not None and self.sell_out_growth is not None:
            text += " ; il fait %s sur l'an dernier quand le sell-out fait %s" % (
                format_pct(self.sell_in_growth), format_pct(self.sell_out_growth))
            if self.scissors_open:
                text += (" — ce que les partenaires achètent ne se vend pas en face : du stock "
                         "chez eux, ou un flux qui ressort ailleurs")
        return text

    @property
    def marked_bulk(self) -> float:
        """L'officiel : ce que l'entrepôt marque comme vrac."""
        return float(self.marked.bulk) if self.marked is not None else 0.0

    @property
    def unmarked_bulk(self) -> float:
        """Les gros tickets que le drapeau ne couvre pas."""
        shadow = self.shadow
        if shadow is None or not shadow.quantity.usable:
            return 0.0
        return float(shadow.quantity.unmarked)

    @property
    def measured_bulk(self) -> float:
        """Ce que le cockpit mesure : le marqué, plus ce qui passe sans drapeau."""
        return self.marked_bulk + self.unmarked_bulk

    @property
    def unmarked_known(self) -> bool:
        return self.shadow is not None and self.shadow.quantity.usable

    @property
    def flag_validated(self) -> bool:
        return flag_validated(self.name)

    @property
    def marked_bulk_label(self) -> str:
        if self.marked is None and not self.flag_validated:
            return FLAG_NOT_VALIDATED
        return format_eur(self.marked_bulk)

    measured_bulk_label = property(lambda self: format_eur(self.measured_bulk))

    @property
    def unmarked_bulk_label(self) -> str:
        return format_eur(self.unmarked_bulk) if self.unmarked_known else "non lu"

    @property
    def plan_bulk_label(self) -> str:
        expected = self.expected_to_date
        return format_eur(expected) if expected else "plan sans ligne"

    @property
    def measured_vs_plan(self) -> str:
        """Le mesuré contre le plan à date, en un mot — et rien quand le plan n'a pas de
        ligne, plutôt qu'un écart contre zéro."""
        expected = self.expected_to_date or 0.0
        if expected <= 0 or self.measured_bulk <= 0:
            return ""
        ratio = self.measured_bulk / expected
        if ratio > 1.15:
            return "au-dessus du plan"
        if ratio < 0.85:
            return "en dessous du plan"
        return "dans l'ordre du plan"

    @property
    def grey_sentence(self) -> str:
        """Mesuré = marqué + sans drapeau, contre le plan : la ligne d'un périmètre."""
        if self.marked is None and not self.unmarked_known:
            return "aucun vrac lu sur %s" % self.name
        text = "%s : mesuré %s, dont marqué par l'entrepôt %s et lu sans drapeau %s ; le plan attend %s à date" % (
            self.name, self.measured_bulk_label,
            self.marked_bulk_label if self.flag_validated or self.marked is not None
            else "%s (zéro de méthode)" % FLAG_NOT_VALIDATED,
            self.unmarked_bulk_label, self.plan_bulk_label)
        word = self.measured_vs_plan
        return text + (" — %s" % word if word else "")

    @property
    def marked_sentence(self) -> str:
        if self.marked is None:
            if not self.flag_validated:
                return ("aucun vrac marqué sur %s : le drapeau n'est pas validé par la Finance sur "
                        "ce marché (Chine et Hong Kong seulement à ce jour), un zéro de méthode, "
                        "pas l'absence d'un flux" % self.name)
            return "aucun vrac marqué sur %s dans les relevés" % self.name
        m = self.marked
        return ("vrac marqué : %s à date, %s des ventes du marché, %s sur l'an dernier, %s sur "
                "trois mois — %s" % (m.bulk_label, m.share_label, m.growth_label,
                                     m.growth_recent_label, m.word))

    @property
    def relay_sentence(self) -> str:
        parts = []
        if self.stopped:
            parts.append("arrêtés cette année, %s l'an dernier sur la fenêtre : %s" % (
                format_eur(sum(p.ytd_ly or 0.0 for p in self.stopped)),
                ", ".join(p.name for p in self.stopped[:3])))
        if self.newcomers:
            parts.append("nouveaux, %s à date : %s" % (
                format_eur(sum(p.ytd for p in self.newcomers)),
                ", ".join(p.name for p in self.newcomers[:3])))
        text = " ; ".join(parts)
        if self.stopped and self.newcomers:
            gone = sum(p.ytd_ly or 0.0 for p in self.stopped)
            if gone > 0:
                text += " — la relève couvre %d %% de ce qui s'est arrêté" % round(
                    100 * sum(p.ytd for p in self.newcomers) / gone)
        return text

    @property
    def closure_vocabulary_known(self) -> bool:
        """La feuille dit-elle « fermée » avec un mot que le dossier reconnaît ? Sans quoi
        une boutique muette et une boutique fermée se ressemblent, et le dossier ne doit pas
        les distinguer à la place du lecteur."""
        return any(m.closed for m in self.silent)

    @property
    def silent_statuses(self) -> List[str]:
        seen: List[str] = []
        for m in self.silent:
            label = (m.status or "").strip() or "(vide)"
            if label not in seen:
                seen.append(label)
        return seen

    @property
    def silent_status_counts(self) -> List[Tuple[str, int]]:
        """Chaque statut des boutiques sans vente et son nombre, le plus fréquent d'abord :
        de quoi lire « 4 » ×14, « 1 » ×1 et décider ce que « 4 » veut dire."""
        counts: Dict[str, int] = {}
        for label in ((m.status or "").strip() or "(vide)" for m in self.silent):
            counts[label] = counts.get(label, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    @property
    def silent_statuses_sentence(self) -> str:
        return ", ".join("« %s » ×%d" % (label, count)
                         for label, count in self.silent_status_counts[:4])

    @property
    def mute_stores(self) -> List[StoreMove]:
        if not self.closure_vocabulary_known:
            return []
        return [m for m in self.silent if not m.closed]

    @property
    def questions(self) -> List[str]:
        """Trois questions, générées de ce que les chiffres montrent de plus net."""
        found: List[str] = []
        shadow = self.shadow
        if shadow is not None and shadow.quantity.usable and shadow.quantity.stores:
            piece = shadow.quantity
            top = piece.stores[0]
            carriers = piece.unmarked_stores
            if not piece.flag_validated and carriers:
                found.append("%s de gros tickets à date, portés d'abord par %s (%s), et le "
                             "drapeau vrac n'est pas validé ici : personne ne mesure ce flux "
                             "officiellement. Qui achète plus de cinquante unités par ticket, "
                             "et le flux est-il assumé, ou caché ?"
                             % (piece.ytd_label, carriers[0].code, carriers[0].sub_channel))
            elif (piece.unmarked_share or 0.0) >= UNMARKED_WORTH_ASKING and carriers:
                found.append("%s de gros tickets ne sont pas marqués comme du vrac à date, "
                             "portés d'abord par %s (%s) : qui achète plus de cinquante unités "
                             "par ticket, et pourquoi ces tickets ne portent pas le drapeau "
                             "quand les grands comptes le portent ? Le flux est-il assumé, ou "
                             "caché ?" % (piece.unmarked_label, carriers[0].code,
                                          carriers[0].sub_channel))
            elif piece.marks_its_bulk is False:
                found.append("Chez %s (%s), qui achète plus de cinquante unités par ticket, et "
                             "pourquoi ces tickets ne sont pas marqués comme du vrac quand d'autres "
                             "marchés les marquent ? Le flux est-il assumé, ou caché ?"
                             % (top.code, top.sub_channel))
            elif shadow.resells:
                found.append("Chez %s (%s), les gros tickets sont remisés à %s contre %s sur les "
                             "autres tickets : c'est de la revente. Qui revend, à qui, et "
                             "est-ce assumé ?" % (top.code, top.sub_channel,
                                                   shadow.quantity.discount_label,
                                                   shadow.normal.discount_label))
            else:
                found.append("Chez %s (%s), %s de gros tickets à date, %s sur l'an dernier : "
                             "qui est le client final ?" % (top.code, top.sub_channel,
                                                           top.ytd_label, top.growth_label))
        elif self.accounts:
            top = self.accounts[0]
            found.append("%s : %s de vrac à date, %s sur l'an dernier. Qui est ce compte, et "
                         "qu'est-ce qu'on lui vend ?" % (top.label, top.ytd_label, top.growth_label))
        if self.stopped and self.newcomers:
            found.append("Facturé depuis %s, %s. Qui reprend le volume des centres arrêtés, et "
                         "où va le reste ?" % (self.iso2, self.relay_sentence))
        if self.mute_stores:
            mute = self.mute_stores[0]
            found.append("%s : aucune vente ce mois, %s l'an dernier, et aucune fermeture dans la "
                         "feuille. Fermée, ou muette ?" % (mute.name or mute.code,
                                                           format_eur(mute.last_year)))
        if self.scissors_open:
            found.append("Le sell-in de %s fait %s sur l'an dernier quand le sell-out fait %s, "
                         "pour %s des ventes du mois. Qui achète, et où ça ressort ?"
                         % (self.name, format_pct(self.sell_in_growth),
                            format_pct(self.sell_out_growth), self.sell_in_share_label))
        if self.declines:
            worst = self.declines[0]
            found.append("%s : %s sur le mois contre l'an dernier (%s). Qu'est-ce qui s'est "
                         "arrêté, une décision ou un acheteur, et où le volume est-il parti ?"
                         % (worst.name or worst.code, worst.delta_label, worst.growth_label))
        duty_free = [(partner, line) for partner, line in self.partners
                     if "travel" in (partner.channel_label or "").lower()
                     and (line.growth_recent is None or line.growth_recent >= DUTY_FREE_JUMP)]
        if duty_free:
            partner, line = duty_free[0]
            found.append("Le duty free facturé depuis %s : %s à date chez %s, %s — qui commande "
                         "ce stock, et où est-il vendu ?" % (
                             self.iso2, line.ytd_label, partner.name,
                             "sans an dernier" if line.growth_ytd is None
                             else "%s sur trois mois" % line.growth_recent_label))
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
        if self.silent:
            if self.closure_vocabulary_known:
                closed = [m for m in self.silent if m.closed]
                mute = self.mute_stores
                out.append("  sans vente ce mois : %d boutiques, %s l'an dernier — %d fermées selon "
                           "la feuille%s" % (len(self.silent), format_eur(sum(-m.delta for m in self.silent)),
                                             len(closed),
                                             (", et muettes sans fermeture : %s" % ", ".join(
                                                 (m.name or m.code) for m in mute[:4])) if mute else ""))
            else:
                out.append("  sans vente ce mois : %d boutiques, %s l'an dernier — fermées ou muettes, "
                           "la feuille dit %s et le dossier ne tranche pas (CEOOS_STORE_CLOSED_STATUSES "
                           "dans .env dit quels codes sont fermés)"
                           % (len(self.silent), format_eur(sum(-m.delta for m in self.silent)),
                              self.silent_statuses_sentence))
        if self.gains:
            out.append("  et celles qui poussent : " + ", ".join(
                "%s %s" % (move.name or move.code, move.delta_label) for move in self.gains))
        out.append("GRIS — marqué par l'entrepôt, et lu sans drapeau ; le sell-in à côté")
        out.append("  " + self.grey_sentence)
        out.append("  " + self.marked_sentence)
        out.append("  " + self.budget_sentence)
        if self.sell_in_grey_sentence:
            out.append("  " + self.sell_in_grey_sentence)
        for line in self.accounts:
            out.append("  %-40s %10s  part %5s  %8s  3 mois %8s  %s" % (
                line.label[:40], line.ytd_label, line.share_label, line.growth_label,
                line.growth_recent_label, line.word))
        if self.shadow is not None and self.shadow.usable:
            for piece in self.shadow.slices:
                out.append("  " + piece.sentence)
                if self.shadow.discount_sentence:
                    out.append("  " + self.shadow.discount_sentence)
                for store in piece.shown:
                    out.append("    %-34s %10s  part %5s  %8s  marqué %5s%s" % (
                        ("%s · %s" % (store.code, store.sub_channel))[:34], store.ytd_label,
                        store.share_label, store.growth_label, store.marking_label,
                        ("  non marqué %s" % store.unmarked_label) if store.unmarked > 0 else ""))
                if piece.kind == "quantity" and piece.unmarked > 0:
                    out.append("    non marqués, portés par : " + ", ".join(
                        "%s · %s %s" % (item.code, item.sub_channel, item.unmarked_label)
                        for item in piece.unmarked_stores))
        else:
            out.append("  " + (self.shadow_note or "le gris sans drapeau n'est pas lu"))
        out.append("PRODUITS — ce qui pousse et ce qui recule, exercice à date")
        products = self.products
        if products is not None and getattr(products, "usable", False):
            out.append("  " + products.headline)
            for level in products.levels:
                out.append("  %s : %s" % (level.title, level.sentence or "%s sur l'exercice"
                                          % format_pct(level.growth)))
                for word, lines in (("pousse", level.growing), ("recule", level.falling)):
                    for line in lines[:MOST_PRODUCT_LINES]:
                        out.append("    %-8s %-30s %10s  %8s  écart %10s  part %5s  dernier mois %8s" % (
                            word, line.name[:30], format_eur(line.sales), line.growth_label,
                            line.delta_label, "%.0f %%" % (line.share * 100), line.month_label))
        else:
            out.append("  " + (getattr(products, "absent", [""])[0] if products is not None
                               and getattr(products, "absent", None) else
                               "la lecture produit n'est pas déposée"))
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
        if self.stopped or self.newcomers:
            out.append("  relève : %s" % self.relay_sentence)
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
          iso2_by_market: Optional[Dict[str, str]] = None, owner: str = "",
          closed_statuses: Optional[Sequence[str]] = None, products=None) -> Dossier:
    from ..domain import issues as domain
    from .budget import normalise_market

    if closed_statuses is None:
        from ..config import settings

        closed_statuses = tuple(getattr(settings, "store_closed_statuses", ()) or ())

    name = normalise_market(market)
    dossier = Dossier(name, owner, str(getattr(dataset, "period_label", "") or ""))
    dossier.products = products

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
                                   actual, float(last_year),
                                   str(getattr(store, "status", "") or ""), closed_statuses))
        moves.sort(key=lambda move: move.delta)
        dossier.silent = [move for move in moves if move.actual <= 0]
        dossier.declines = [move for move in moves if move.delta < 0 and move.actual > 0][:MOST_STORE_MOVES]
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
                                          getattr(unit, "sales_last_year", None),
                                          bool(getattr(unit, "budget_known", True))))

    dossier.iso2 = (iso2_by_market or {}).get(name, "")
    if dossier.iso2 and accounts is not None:
        billed = []
        for partner in getattr(accounts, "partners", []) or []:
            for line in getattr(partner, "countries", []) or []:
                if line.country == dossier.iso2 and line.ytd > 0:
                    billed.append((line.ytd, partner, line))
        billed.sort(key=lambda item: -item[0])
        dossier.partners = [(partner, line) for _ytd, partner, line in billed[:MOST_PARTNERS]]
        # La relève, vue du pays : les centres facturés depuis lui qui se sont tus, et les
        # nouveaux. Un opérateur qui s'arrête et deux qui ouvrent ne se lisent que côte à côte.
        for partner in getattr(accounts, "stopped", []) or []:
            if any(line.country == dossier.iso2 and (line.ytd_ly or 0.0) > 0
                   for line in partner.countries):
                dossier.stopped.append(partner)
        for partner in getattr(accounts, "newcomers", []) or []:
            if any(line.country == dossier.iso2 and line.ytd > 0 for line in partner.countries):
                dossier.newcomers.append(partner)

    found = []
    for issue in getattr(register, "issues", []) or []:
        scopes = getattr(issue, "scopes", []) or []
        if name in scopes or name.lower() in (issue.title or "").lower():
            found.append(issue)
    found.sort(key=lambda issue: issue.status == domain.CLOSED)
    dossier.issues = [Mention(issue) for issue in found[:MOST_ISSUES]]
    dossier.notes = [note for note in notes if getattr(note, "market", "") == name]
    return dossier
