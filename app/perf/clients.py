"""La conversation sur les clients : le pont, et le flux de la base.

Le lecteur l'a demandé avec un tableau de bord sous les yeux : clients × panier = ventes,
pour les clients enregistrés et pour les visites sans compte ; puis d'où viennent les
clients de l'exercice — retenus de l'an dernier, réactivés, nouveaux — et ce que chaque
segment vaut. Sa lecture tient en une phrase : « l'érosion de valeur est chez les fidèles,
pas dans le recrutement ». Ce module la calcule au lieu de la répéter.

Deux tableaux, une phrase, une question :

1. **Le pont.** Sur l'exercice à date, contre le même exercice à date un an plus tôt :
   les clients enregistrés actifs, leur panier moyen, leurs ventes ; les visites sans
   compte, leur panier, leurs ventes ; la part des ventes en propre que portent les
   enregistrés.
2. **Le flux.** La base de l'an dernier, ce qu'elle a perdu, ce qu'elle a gardé ; les
   réactivés ; les nouveaux et le taux de recrutement ; la variation nette. Chaque
   segment avec ses clients, son panier, ses ventes.

Rien ici n'est un objectif ; c'est de quoi parler avec le marketing global et avec une
région de ses clients, et non seulement de son chiffre. Lu dans la lecture clients de
l'entrepôt, jamais dans une requête à l'ouverture de la page.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from .analytics import format_eur, format_pct
from .products import _key, month_fr, months_label
from .weekly import MONTHS_FR

GROUP = "LOEP"

#: L'exercice ouvre en avril.
FISCAL_OPENS = 4

SEGMENT_WORDS = {
    "arc": "clients enregistrés",
    "walkin": "visites sans compte",
    "retained": "retenus",
    "reactivated": "réactivés",
    "new": "nouveaux",
    "unknown": "sans date de première transaction connue",
    "lost": "perdus",
}
FLOW = ("retained", "reactivated", "new", "unknown")

#: Sous cette part des actifs, un segment se compte dans une note et ne prend pas une
#: ligne du tableau : quelques milliers de clients sans date, à panier négatif, font une
#: ligne qui trouble plus qu'elle ne dit.
LEAST_SHARE = 0.005

#: En deçà, la part perdue est celle de l'an dernier : la saison, pas une dégradation.
LOST_NOTICED = 2.0

#: Au-delà, le flux ne fait plus le pont — retenus, réactivés, nouveaux et sans date
#: contre les enregistrés actifs — et la lecture le dit.
FLOW_AGREES = 0.005

#: Sous cet écart de panier, les fidèles ne s'érodent pas : c'est du bruit de mix.
ATV_NOTICED = 0.02


def _number(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _growth(now: float, before: Optional[float]) -> Optional[float]:
    if before is None or before <= 0:
        return None
    return now / before - 1.0


class Segment:
    """Un segment : ses clients, ses tickets, ses ventes ; le panier en découle."""

    __slots__ = ("name", "clients", "transactions", "sales")

    def __init__(self, name: str, clients: float = 0.0, transactions: float = 0.0,
                 sales: float = 0.0) -> None:
        self.name = name
        self.clients = clients
        self.transactions = transactions
        self.sales = sales

    @property
    def word(self) -> str:
        return SEGMENT_WORDS.get(self.name, self.name)

    @property
    def atv(self) -> Optional[float]:
        return self.sales / self.transactions if self.transactions > 0 else None

    @property
    def per_client(self) -> Optional[float]:
        return self.sales / self.clients if self.clients > 0 else None

    @property
    def usable(self) -> bool:
        return self.clients > 0 or self.sales > 0

    def add(self, other: "Segment") -> None:
        self.clients += other.clients
        self.transactions += other.transactions
        self.sales += other.sales


def _count(value: float) -> str:
    if value >= 1_000_000:
        return "%.2f M" % (value / 1_000_000)
    if value >= 1_000:
        return "%.0f k" % (value / 1_000)
    return "%.0f" % value


def _atv(value: Optional[float]) -> str:
    return "—" if value is None or value <= 0 else "%.0f €" % value


class Pair:
    """Un segment de l'exercice à date et le même l'an dernier, avec ses trois croissances."""

    __slots__ = ("now", "before")

    def __init__(self, now: Segment, before: Optional[Segment]) -> None:
        self.now = now
        self.before = before

    @property
    def name(self) -> str:
        return self.now.name

    @property
    def word(self) -> str:
        return self.now.word

    @property
    def clients_growth(self) -> Optional[float]:
        return _growth(self.now.clients, self.before.clients if self.before else None)

    @property
    def atv_growth(self) -> Optional[float]:
        if self.before is None or self.before.atv is None or self.now.atv is None:
            return None
        return self.now.atv / self.before.atv - 1.0

    @property
    def sales_growth(self) -> Optional[float]:
        return _growth(self.now.sales, self.before.sales if self.before else None)

    clients_label = property(lambda self: _count(self.now.clients))
    atv_label = property(lambda self: _atv(self.now.atv))
    sales_label = property(lambda self: format_eur(self.now.sales))
    clients_growth_label = property(lambda self: format_pct(self.clients_growth))
    atv_growth_label = property(lambda self: format_pct(self.atv_growth))
    sales_growth_label = property(lambda self: format_pct(self.sales_growth))


class Flow:
    """Un segment du flux : sa part de la base ou de l'exercice, son panier contre celui de
    la base de l'an dernier — et la même part l'an dernier au même mois, quand la lecture
    la porte."""

    __slots__ = ("segment", "base", "of", "base_atv", "before")

    def __init__(self, segment: Segment, base: float, of: str, base_atv: Optional[float],
                 before: Optional["Flow"] = None) -> None:
        self.segment = segment
        self.base = base
        self.of = of
        self.base_atv = base_atv
        self.before = before

    @property
    def before_share_label(self) -> str:
        if self.before is None or self.before.share is None:
            return "—"
        return "%.0f %%" % (self.before.share * 100)

    @property
    def share_change(self) -> Optional[float]:
        """En points, contre l'an dernier au même mois."""
        if self.before is None or self.before.share is None or self.share is None:
            return None
        return (self.share - self.before.share) * 100

    @property
    def share_change_label(self) -> str:
        change = self.share_change
        return "—" if change is None else "%+.0f pt%s" % (change, "s" if abs(change) >= 2 else "")

    name = property(lambda self: self.segment.name)
    word = property(lambda self: self.segment.word)
    clients_label = property(lambda self: _count(self.segment.clients))
    atv_label = property(lambda self: _atv(self.segment.atv))
    sales_label = property(lambda self: format_eur(self.segment.sales))

    @property
    def share(self) -> Optional[float]:
        return self.segment.clients / self.base if self.base > 0 else None

    @property
    def share_label(self) -> str:
        return "—" if self.share is None else "%.0f %% %s" % (self.share * 100, self.of)

    @property
    def atv_vs_base(self) -> Optional[float]:
        if self.base_atv is None or self.segment.atv is None or self.segment.atv <= 0:
            return None
        return self.segment.atv / self.base_atv - 1.0

    atv_vs_base_label = property(lambda self: format_pct(self.atv_vs_base))


class Review:
    """Un périmètre : le pont, le flux, la phrase, la question, et ce qui manque."""

    def __init__(self, scope: str = GROUP, through: str = "", bridge: Sequence[Pair] = (),
                 flow: Sequence[Flow] = (), lost: Optional[Flow] = None,
                 absent: Sequence[str] = (), approximate: bool = False) -> None:
        self.scope = scope
        self.through = through
        self.bridge = list(bridge)
        self.flow = list(flow)
        self.lost = lost
        self.absent = list(absent)
        #: Une somme de marchés : un client actif dans deux pays y compte deux fois.
        self.approximate = approximate

    @property
    def usable(self) -> bool:
        return bool(self.bridge)

    def pair(self, name: str) -> Optional[Pair]:
        return next((pair for pair in self.bridge if pair.name == name), None)

    def part(self, name: str) -> Optional[Flow]:
        return next((item for item in self.flow if item.name == name), None)

    @property
    def flow_shown(self) -> List[Flow]:
        """Les segments qui pèsent ; les autres se comptent dans `flow_noise`."""
        return [item for item in self.flow if item.share is None or item.share >= LEAST_SHARE]

    @property
    def flow_noise(self) -> str:
        small = [item for item in self.flow if item.share is not None and item.share < LEAST_SHARE]
        if not small:
            return ""
        return "hors tableau, sous la part de bruit : " + ", ".join(
            "%s %s (%s)" % (item.clients_label, item.word, item.sales_label) for item in small)

    @property
    def window_months(self) -> int:
        if not self.through:
            return 0
        year, month = int(self.through[:4]), int(self.through[5:7])
        return month - FISCAL_OPENS + 1 if month >= FISCAL_OPENS else month + 12 - FISCAL_OPENS + 1

    @property
    def months(self) -> str:
        if not self.through:
            return ""
        year, month = int(self.through[:4]), int(self.through[5:7])
        opens = "%04d-%02d" % (year if month >= FISCAL_OPENS else year - 1, FISCAL_OPENS)
        return months_label([opens, self.through]) if opens != self.through else month_fr(self.through)

    @property
    def basis(self) -> str:
        head = ("ventes en propre, boutiques et site, %s, exercice à date contre le même "
                "exercice à date un an plus tôt · hors vrac et hors gratuits" % self.months)
        if self.approximate:
            head += " · la somme des marchés, un client actif dans deux pays y compte deux fois"
        return head

    @property
    def registered_share(self) -> Optional[float]:
        arc, walkin = self.pair("arc"), self.pair("walkin")
        if arc is None:
            return None
        total = arc.now.sales + (walkin.now.sales if walkin else 0.0)
        return arc.now.sales / total if total > 0 else None

    @property
    def net_change(self) -> Optional[float]:
        arc = self.pair("arc")
        if arc is None or arc.before is None:
            return None
        return arc.now.clients - arc.before.clients

    @property
    def headline(self) -> str:
        """Clients × panier = ventes, en une phrase, pour les enregistrés."""
        arc = self.pair("arc")
        if arc is None:
            return ""
        text = "%s clients enregistrés (%s) × panier %s (%s) = %s (%s)" % (
            arc.clients_label, arc.clients_growth_label, arc.atv_label, arc.atv_growth_label,
            arc.sales_label, arc.sales_growth_label)
        share = self.registered_share
        if share is not None:
            text += " · %.0f %% des ventes en propre" % (share * 100)
        return text

    @property
    def read(self) -> str:
        """Où la valeur s'érode — chez les fidèles ou dans le recrutement — dit par les
        paniers contre celui de la base de l'an dernier, pas par un avis."""
        retained, new = self.part("retained"), self.part("new")
        lost = self.lost
        parts = []
        if lost is not None and lost.share is not None:
            text = "la base de l'an dernier a perdu %.0f %% de ses clients" % (lost.share * 100)
            change = lost.share_change
            if change is not None:
                text += " (%s l'an dernier au même mois, %s" % (lost.before_share_label,
                                                                lost.share_change_label)
                if abs(change) < LOST_NOTICED:
                    text += " : la saison, pas une dégradation)"
                elif change > 0:
                    text += " : une perte acquise, au-delà de la saison)"
                else:
                    text += " : la base tient mieux que l'an dernier)"
            parts.append(text)
        if retained is not None and retained.atv_vs_base is not None:
            if retained.atv_vs_base <= -ATV_NOTICED:
                parts.append("les retenus achètent moins cher qu'elle (%s de panier) : l'érosion de "
                             "valeur est dans le cœur fidèle" % retained.atv_vs_base_label)
            elif retained.atv_vs_base >= ATV_NOTICED:
                parts.append("les retenus achètent plus cher qu'elle (%s de panier)" % retained.atv_vs_base_label)
            else:
                parts.append("les retenus tiennent leur panier")
        if new is not None and new.atv_vs_base is not None and new.share is not None:
            parts.append("les nouveaux, %.0f %% des actifs, entrent à %s de panier" % (
                new.share * 100, new.atv_vs_base_label))
        change = self.net_change
        if change is not None:
            parts.append("%s%s clients nets" % ("+" if change > 0 else "", _count(abs(change)) if change >= 0 else "-" + _count(abs(change))))
        return " ; ".join(parts)

    @property
    def question(self) -> str:
        retained = self.part("retained")
        lost = self.lost
        if retained is not None and retained.atv_vs_base is not None and retained.atv_vs_base <= -ATV_NOTICED:
            return ("Les fidèles achètent moins cher : le mix, la promotion, ou la fréquence ? "
                    "Et que fait-on des clients perdus avant qu'ils ne le soient tout à fait ?")
        if lost is not None and lost.share_change is not None and lost.share_change >= LOST_NOTICED:
            return ("La base perd plus que la saison : qui part, de quel canal, et que fait-on "
                    "des clients perdus avant qu'ils ne le soient tout à fait ?")
        if lost is not None and lost.share_change is not None:
            return ("La part perdue est celle de l'an dernier ; la base recule pourtant en nombre : "
                    "le recrutement compense-t-il en valeur, pas seulement en nombre, et d'où "
                    "viennent les nouveaux ?")
        return ("Le recrutement compense-t-il la base en valeur, pas seulement en nombre ? "
                "Et que fait-on des clients perdus avant qu'ils ne le soient tout à fait ?")


def _read(rows: Iterable[dict], scopes_wanted: Sequence[str]) -> Dict[tuple, Segment]:
    """(window, segment) → segment sommé sur les périmètres voulus, et le dernier mois."""
    wanted = {_key(scope) for scope in scopes_wanted}
    found: Dict[tuple, Segment] = {}
    for row in rows:
        if _key(row.get("scope")) not in wanted:
            continue
        window = str(row.get("window") or "").strip().lower()
        segment = str(row.get("segment") or "").strip().lower()
        if window not in ("ty", "ly", "ly2") or segment not in SEGMENT_WORDS:
            continue
        piece = Segment(segment, _number(row.get("clients")), _number(row.get("transactions")),
                        _number(row.get("sales")))
        found.setdefault((window, segment), Segment(segment)).add(piece)
    return found


def _through(rows: Iterable[dict], scopes_wanted: Sequence[str]) -> str:
    wanted = {_key(scope) for scope in scopes_wanted}
    return max((str(row.get("through") or "")[:7] for row in rows
                if _key(row.get("scope")) in wanted), default="")


def build(rows: Iterable[dict], scope: str = GROUP, note: str = "",
          markets: Optional[Sequence[str]] = None) -> Review:
    """La lecture d'un périmètre : le scope lui-même, ou la somme de ses marchés."""
    rows = list(rows or [])
    absent: List[str] = []
    if note:
        absent.append(note)
    scopes_wanted = list(markets) if markets else [scope]
    found = _read(rows, scopes_wanted)
    if not found:
        if not note:
            absent.append("aucune lecture clients pour %s" % scope)
        return Review(scope, absent=absent)
    bridge = []
    for name in ("arc", "walkin"):
        now = found.get(("ty", name))
        if now is not None and now.usable:
            bridge.append(Pair(now, found.get(("ly", name))))
    base = found.get(("ly", "arc"))
    base_atv = base.atv if base is not None else None
    arc_now = found.get(("ty", "arc"))

    def flows(window: str, previous: str):
        """Le flux d'une fenêtre, classé contre la précédente : ty contre ly, ly contre ly2."""
        before = found.get((previous, "arc"))
        base_clients = before.clients if before is not None else 0.0
        atv = before.atv if before is not None else None
        now = found.get((window, "arc"))
        active = now.clients if now is not None else 0.0
        items = {}
        for name in FLOW + ("lost",):
            piece = found.get((window, name))
            if piece is not None and piece.usable:
                on_base = name in ("retained", "lost")
                items[name] = Flow(piece, base_clients if on_base else active,
                                   "de la base" if on_base else "des actifs", atv)
        return items

    earlier = flows("ly", "ly2")
    current = flows("ty", "ly")
    flow = []
    for name in FLOW:
        if name in current:
            current[name].before = earlier.get(name)
            flow.append(current[name])
    lost = current.get("lost")
    if lost is not None:
        lost.before = earlier.get("lost")
    if not flow:
        absent.append("le flux — retenus, réactivés, nouveaux — n'est pas dans la lecture")
    elif arc_now is not None and arc_now.clients > 0:
        summed = sum(item.segment.clients for item in flow)
        if abs(summed - arc_now.clients) > FLOW_AGREES * arc_now.clients:
            absent.append("le flux ne fait pas le pont : %s clients dans les segments contre "
                          "%s enregistrés actifs — une lecture à vérifier avant de lire les parts"
                          % (_count(summed), _count(arc_now.clients)))
    if base is None:
        absent.append("l'an dernier n'est pas dans la lecture : le pont n'a pas de croissance")
    elif lost is not None and lost.before is None:
        absent.append("l'exercice d'avant n'est pas dans la lecture : la part perdue ne se "
                      "compare pas encore à l'an dernier au même mois")
    review = Review(scope, _through(rows, scopes_wanted), bridge, flow, lost, absent,
                    approximate=bool(markets) and len(scopes_wanted) > 1)
    if review.flow_noise:
        review.absent.append(review.flow_noise)
    if 0 < review.window_months < 12 and lost is not None:
        # Sur cinq mois, un client qui achète deux fois l'an a une chance sur deux de
        # n'être pas encore revenu : la part perdue se lit contre l'an dernier au même
        # mois, et vraiment en fin d'exercice.
        review.absent.append("les fenêtres font %d mois : la part perdue est celle qui n'est pas "
                             "encore revenue, pas une perte acquise — elle se lit contre l'an "
                             "dernier au même mois, et vraiment en fin d'exercice"
                             % review.window_months)
    return review


def for_markets(rows: Iterable[dict], markets: Sequence[str], scope: str, note: str = "") -> Review:
    return build(rows, scope, note=note, markets=markets)
