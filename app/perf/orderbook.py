"""Le carnet de commandes ouvert, vers l'avant : ce qui est commandé et pas encore facturé.

La facture est un rythme, jamais une avance sur le mois ; le carnet, lui, regarde devant.
Trois paquets sur la date de promesse au client : en retard — promis avant aujourd'hui et
toujours ouvert, du sell-in qui manque au mois, pas un stock qui attend —, promis d'ici la
fin du mois, et au-delà. Le carnet bouge chaque jour : rien ici ne se publie sans sa date
de lecture. Seule la colonne d'encours de la vue est lue ; ses « facturé » et « livré »
sont des proxys faux, et ses drapeaux des constantes.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .analytics import format_eur

BUCKETS = ("late", "month", "beyond")


class Book:
    """Un carnet : les trois paquets, et ce qui est bloqué à la livraison."""

    __slots__ = ("name", "late", "month", "beyond", "blocked", "lines")

    def __init__(self, name: str) -> None:
        self.name = name
        self.late = 0.0
        self.month = 0.0
        self.beyond = 0.0
        self.blocked = 0.0
        self.lines = 0

    def add(self, bucket: str, open_eur: float, blocked: float, lines: int) -> None:
        if bucket == "late":
            self.late += open_eur
        elif bucket == "month":
            self.month += open_eur
        else:
            self.beyond += open_eur
        self.blocked += blocked
        self.lines += lines

    @property
    def due(self) -> float:
        """Ce qui doit tomber dans le mois : le promis d'ici la fin, et le retard."""
        return self.month + self.late

    @property
    def total(self) -> float:
        return self.late + self.month + self.beyond

    @property
    def usable(self) -> bool:
        return self.total > 0

    late_label = property(lambda self: format_eur(self.late))
    month_label = property(lambda self: format_eur(self.month))
    beyond_label = property(lambda self: format_eur(self.beyond))
    due_label = property(lambda self: format_eur(self.due))
    blocked_label = property(lambda self: format_eur(self.blocked))

    @property
    def sentence(self) -> str:
        if not self.usable:
            return "aucune commande ouverte"
        text = "carnet ouvert : promis d'ici la fin du mois %s, en retard %s" % (
            self.month_label, self.late_label)
        if self.late > 0 and self.late > self.month:
            text += " — le retard dépasse le promis du mois"
        if self.blocked > 0:
            text += " ; bloqué à la livraison %s" % self.blocked_label
        text += " ; au-delà du mois %s" % self.beyond_label
        return text


class Review:
    """Le carnet par marché, avec sa date de lecture."""

    def __init__(self, markets: Dict[str, Book], read_at: str = "", note: str = "") -> None:
        self.markets = markets
        self.read_at = read_at
        self.note = note

    @property
    def usable(self) -> bool:
        return any(book.usable for book in self.markets.values())

    def for_markets(self, markets: Sequence[str], name: str = "") -> Optional[Book]:
        wanted = set(markets)
        book = Book(name or ", ".join(markets))
        for market, item in self.markets.items():
            if market in wanted:
                book.late += item.late
                book.month += item.month
                book.beyond += item.beyond
                book.blocked += item.blocked
                book.lines += item.lines
        return book if book.usable else None

    @property
    def group(self) -> Book:
        return self.for_markets(list(self.markets), "Groupe") or Book("Groupe")

    @property
    def read_label(self) -> str:
        return ("lu le %s" % self.read_at) if self.read_at else "date de lecture inconnue"


def build(rows: Sequence[dict], read_at: str = "", note: str = "") -> Review:
    """La lecture, sur les lignes de `ORDER_BOOK`."""
    from .budget import normalise_market

    markets: Dict[str, Book] = {}
    periods: List[str] = []
    for row in rows or ():
        bucket = str(row.get("bucket") or "").strip().lower()
        if bucket not in BUCKETS:
            continue
        market = normalise_market(str(row.get("market") or "(sans pays)"))
        book = markets.setdefault(market, Book(market))
        book.add(bucket, float(row.get("open_eur") or 0.0), float(row.get("blocked_eur") or 0.0),
                 int(row.get("lines") or 0))
        period = str(row.get("period") or "")[:10]
        if period and period not in periods:
            periods.append(period)
    stamp = read_at or (max(periods) if periods else "")
    if not markets:
        return Review({}, stamp, note or "le carnet de commandes n'est pas lu")
    return Review(markets, stamp, note)
