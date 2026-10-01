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

Par périmètre, à une condition dite : le pays de l'entité qui facture. Exact là où chaque
filiale facture chez elle — l'Amérique du Nord —, approximatif là où une entité facture
vingt pays — la Hongrie pour l'EMEA. Le travel retail va à la BU qui le porte, comme les
factures. Par partenaire, sur le centre de profit, nommé par `var/partners.csv` : « NA a
tant de retard sur tel e-retailer », c'est la question qu'un MD peut rendre.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .analytics import format_eur

#: Les partenaires portés en clair dans le carnet d'un périmètre.
PARTNERS_SHOWN = 8
#: Ce que dit le carnet d'un périmètre tant que la lecture ne porte pas de pays.
NO_COUNTRY_NOTE = ("le carnet n'est pas encore lu par pays ni par partenaire : la requête "
                   "attend sa validation, puis manage.py refresh --supply la relit")

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

    def __init__(self, channels: Dict[str, Book], read_at: str = "", note: str = "",
                 holds: Optional[Sequence] = None) -> None:
        self.channels = channels
        self.read_at = read_at
        self.note = note
        #: Les notes « on_hold » du fichier de contexte qui portent un canal : un retard
        #: tenu exprès — des livraisons qu'on a choisi de ne pas faire — n'est pas du
        #: sell-in qui manque, et la question n'est plus « pourquoi le retard ».
        self.holds = list(holds or [])
        #: Pour un périmètre : son nom, ses partenaires par retard décroissant, et la
        #: condition de lecture (le pays de l'entité facturante).
        self.scope = ""
        self.partners: List[Book] = []
        self.scope_note = ""

    def hold_for(self, book: Book):
        """La note qui tient ce canal, ou None."""
        code = book.name.strip().lower()
        label = book.channel_label.strip().lower()
        for note in self.holds:
            channel = str(getattr(note, "channel", "") or "").strip().lower()
            if channel and channel in (code, label):
                return note
        return None

    @property
    def held_late(self) -> float:
        return sum(b.late for b in self.channels.values() if self.hold_for(b) is not None)

    @property
    def free_late(self) -> float:
        """Le retard que personne n'a choisi."""
        return self.group.late - self.held_late

    @property
    def late_matters(self) -> bool:
        """Le retard non tenu dépasse le promis du mois : du sell-in qui manque."""
        return self.free_late > 0 and self.free_late > self.group.month

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
            hold = self.hold_for(late[0])
            if hold is not None:
                text += ", retard tenu exprès : %s" % str(getattr(hold, "text", "") or "").strip().rstrip(".")
                since = str(getattr(hold, "since", "") or "")
                if since:
                    text += " (depuis %s)" % since
        if self.late_matters:
            text += " — le retard %sdépasse le promis du mois : du sell-in qui manque, pas un stock qui attend" % (
                "non tenu " if self.held_late > 0 else "")
        elif self.held_late > 0 and group.late_exceeds_month:
            text += " — hors le retard tenu, %s de retard sous le promis du mois" % format_eur(self.free_late)
        if group.blocked > 0:
            text += " ; bloqué à la livraison %s" % group.blocked_label
        text += " ; au-delà du mois %s · %s" % (group.beyond_label, self.read_label)
        return text


def for_perimeter(rows: Sequence[dict], name: str, iso2s: Sequence[str], travel_bu: str = "",
                  names: Optional[Dict[str, str]] = None, read_at: str = "", note: str = "",
                  holds: Optional[Sequence] = None) -> Review:
    """Le carnet d'un périmètre : les lignes dont le pays de l'entité facturante est rangé
    chez lui, plus le travel retail s'il le porte ; par canal, et par partenaire."""
    from .accounts import _name_of
    from .invoiced import TRAVEL_RETAIL_CODE

    rows = list(rows or ())
    if rows and not any("iso2" in row for row in rows):
        review = Review({}, read_at, NO_COUNTRY_NOTE, holds=holds)
        review.scope = name
        return review
    wanted = {str(i).strip().upper() for i in iso2s}
    mine = []
    for row in rows:
        code = str(row.get("channel") or "").strip().lower()
        iso2 = str(row.get("iso2") or "").strip().upper()
        if code == TRAVEL_RETAIL_CODE:
            if travel_bu and travel_bu == name:
                mine.append(row)
            continue
        if iso2 in wanted:
            mine.append(row)
    review = build(mine, read_at=read_at, note=note, holds=holds)
    review.scope = name
    review.scope_note = ("sur le pays de l'entité qui facture, rangé comme les factures : exact "
                         "quand chaque filiale facture chez elle, approximatif quand une entité "
                         "facture plusieurs pays" + (" ; le travel retail est à %s" % travel_bu
                                                     if travel_bu else ""))
    partners: Dict[str, Book] = {}
    labels: Dict[str, str] = {}
    for row in mine:
        bucket = str(row.get("bucket") or "").strip().lower()
        if bucket not in BUCKETS:
            continue
        code = str(row.get("code") or "").strip().upper()
        if not code:
            continue
        labels.setdefault(code, str(row.get("label") or ""))
        book = partners.setdefault(code, Book(code))
        book.add(bucket, float(row.get("open_eur") or 0.0), float(row.get("blocked_eur") or 0.0),
                 int(row.get("lines") or 0))
    shown = []
    for code, book in sorted(partners.items(), key=lambda item: (-item[1].late, -item[1].due)):
        label, _named = _name_of(code, labels.get(code, ""), names or {})
        book.name = label
        shown.append(book)
    review.partners = shown[:PARTNERS_SHOWN]
    return review


def build(rows: Sequence[dict], read_at: str = "", note: str = "",
          holds: Optional[Sequence] = None) -> Review:
    """La lecture, sur les lignes de `ORDER_BOOK` ; `holds`, les notes « on_hold » à canal."""
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
    return Review(channels, stamp, note, holds=holds)
