"""Le carnet de commandes ouvert, vers l'avant : ce qui est commandé et pas encore facturé.

La facture est un rythme, jamais une avance sur le mois ; le carnet, lui, regarde devant.
Trois paquets exclusifs sur la date de promesse au client : en retard — promis avant
aujourd'hui et toujours ouvert, du sell-in qui manque au mois, pas un stock qui attend —,
promis d'aujourd'hui à la fin du mois, et au-delà. Au niveau du groupe et par canal
seulement : la vue des commandes ne porte pas de pays de destination, et le pays de son
point de vente est celui de l'entité qui facture — un axe marché bâti dessus attribuerait
la Chine à Hong Kong. Le carnet bouge chaque jour : rien ici ne se publie sans sa date de
lecture. Seule la colonne d'encours de la vue est lue ; ses « facturé » et « livré » sont
des proxys faux, et ses drapeaux des constantes.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

from .analytics import format_eur

BUCKETS = ("late", "month", "beyond")
#: Les canaux portés en clair avant de replier le reste.
MOST = 6


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

    @property
    def late_exceeds_month(self) -> bool:
        return self.late > 0 and self.late > self.month

    @property
    def channel_label(self) -> str:
        from .mapping import CHANNEL_NAMES

        if self.name.strip().lower() in ("(vide)", "", "n/a"):
            return "sans canal"
        return CHANNEL_NAMES.get(self.name.strip().lower(), self.name)

    late_label = property(lambda self: format_eur(self.late))
    month_label = property(lambda self: format_eur(self.month))
    beyond_label = property(lambda self: format_eur(self.beyond))
    due_label = property(lambda self: format_eur(self.due))
    blocked_label = property(lambda self: format_eur(self.blocked))


class Review:
    """Le carnet du groupe, par canal, avec sa date de lecture."""

    def __init__(self, channels: Dict[str, Book], read_at: str = "", note: str = "") -> None:
        self.channels = channels
        self.read_at = read_at
        self.note = note

    @property
    def usable(self) -> bool:
        return any(book.usable for book in self.channels.values())

    @property
    def group(self) -> Book:
        book = Book("Groupe")
        for item in self.channels.values():
            book.late += item.late
            book.month += item.month
            book.beyond += item.beyond
            book.blocked += item.blocked
            book.lines += item.lines
        return book

    @property
    def shown(self) -> List[Book]:
        """Les canaux par dû décroissant — ce qui doit tomber dans le mois —, ceux qui en ont."""
        return sorted((b for b in self.channels.values() if b.usable),
                      key=lambda b: (-b.due, -b.total))[:MOST]

    @property
    def read_label(self) -> str:
        return ("carnet lu le %s" % self.read_at) if self.read_at else "date de lecture inconnue"

    @property
    def sentence(self) -> str:
        """Le carnet du groupe en une phrase : promis, retard, et qui porte le retard."""
        if not self.usable:
            return self.note or "aucune commande ouverte"
        group = self.group
        text = ("carnet ouvert : promis d'ici la fin du mois %s hors retard, en retard %s"
                % (group.month_label, group.late_label))
        late = sorted((b for b in self.channels.values() if b.late > 0), key=lambda b: -b.late)
        if late and group.late > 0:
            text += " dont %s %s (%d %%)" % (late[0].channel_label, late[0].late_label,
                                             round(100 * late[0].late / group.late))
        if group.late_exceeds_month:
            text += " — le retard dépasse le promis du mois : du sell-in qui manque, pas un stock qui attend"
        if group.blocked > 0:
            text += " ; bloqué à la livraison %s" % group.blocked_label
        text += " ; au-delà du mois %s · %s" % (group.beyond_label, self.read_label)
        return text


def build(rows: Sequence[dict], read_at: str = "", note: str = "") -> Review:
    """La lecture, sur les lignes de `ORDER_BOOK`."""
    channels: Dict[str, Book] = {}
    periods: List[str] = []
    for row in rows or ():
        bucket = str(row.get("bucket") or "").strip().lower()
        if bucket not in BUCKETS:
            continue
        channel = str(row.get("channel") or "(vide)").strip() or "(vide)"
        book = channels.setdefault(channel, Book(channel))
        book.add(bucket, float(row.get("open_eur") or 0.0), float(row.get("blocked_eur") or 0.0),
                 int(row.get("lines") or 0))
        period = str(row.get("period") or "")[:10]
        if period and period not in periods:
            periods.append(period)
    stamp = read_at or (max(periods) if periods else "")
    if not channels:
        return Review({}, stamp, note or "le carnet de commandes n'est pas lu")
    return Review(channels, stamp, note)
