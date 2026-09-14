"""Le gris sans drapeau : ce que les tickets disent, quel que soit le marquage.

Le vrac « marqué » dépend d'un drapeau que l'entrepôt ne pose pas pareil partout : presque
tout à Hong Kong, presque rien en Chine, pour le même flux. Comparer les deux marchés sur ce
drapeau comparait des pratiques de saisie. Ce module lit deux comportements sur le fait,
que `SHADOW_BULK` rend par mois, marché et point de vente :

**Les gros tickets** — plus de cinquante unités sur un ticket. C'est le compte de gros, qu'il
soit marqué ou non ; la part marquée dit si le marché pose le drapeau, et un marché qui ne
le pose pas a un vrac « marqué » qui est un plancher.

**Les prix hors norme** — une ligne vendue sous soixante pour cent du prix unitaire moyen de
la référence dans le pays ce mois-là, hors drapeau. Ce critère ramasse surtout les magasins
d'usine ; il ne désigne pas la même population que le premier, et les deux ne se fondent
jamais.

Rien ici n'est du vrac au sens de l'entrepôt : ce sont des lectures du cockpit, nommées
comme telles, posées à côté du vrac marqué et jamais à sa place.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .accounts import _months_between, _shift, fiscal_start
from .analytics import format_eur, format_pct
from .grey import NOTICED, RECENT, _growth, _word

KINDS = ("quantity", "price")
KIND_LABELS = {"quantity": "gros tickets", "price": "prix hors norme"}
KIND_MEANING = {
    "quantity": "tickets de plus de cinquante unités, marqués ou non",
    "price": "lignes vendues sous soixante pour cent du prix de la référence, hors drapeau",
}
#: En deçà, un marché « ne pose pas le drapeau » sur ses gros tickets.
LOW_MARKING = 0.5
MOST_STORES = 6


class Store:
    __slots__ = ("code", "market", "sub_channel", "kind", "months", "flagged", "ytd",
                 "ytd_ly", "recent", "recent_ly", "flagged_ytd", "total")

    def __init__(self, code: str, market: str, sub_channel: str, kind: str) -> None:
        self.code = code
        self.market = market
        self.sub_channel = sub_channel
        self.kind = kind
        self.months: Dict[str, float] = {}
        self.flagged: Dict[str, float] = {}
        self.ytd = 0.0
        self.ytd_ly: Optional[float] = None
        self.recent = 0.0
        self.recent_ly: Optional[float] = None
        self.flagged_ytd = 0.0
        self.total = 0.0

    @property
    def label(self) -> str:
        return "%s · %s · %s" % (self.market, self.code, self.sub_channel)

    @property
    def growth(self) -> Optional[float]:
        return _growth(self.ytd, self.ytd_ly)

    @property
    def growth_recent(self) -> Optional[float]:
        return _growth(self.recent, self.recent_ly)

    @property
    def word(self) -> str:
        return _word(self.growth, self.growth_recent)

    @property
    def marking(self) -> Optional[float]:
        return self.flagged_ytd / self.ytd if self.ytd > 0 else None

    @property
    def share(self) -> Optional[float]:
        return self.ytd / self.total if self.total > 0 else None

    @property
    def unmarked(self) -> float:
        """Les euros de gros tickets que le drapeau ne couvre pas."""
        return max(self.ytd - self.flagged_ytd, 0.0) if self.kind == "quantity" else 0.0

    @property
    def unmarked_label(self) -> str:
        return format_eur(self.unmarked)

    @property
    def ytd_label(self) -> str:
        return format_eur(self.ytd)

    @property
    def growth_label(self) -> str:
        return "n/d" if self.growth is None else format_pct(self.growth)

    @property
    def growth_recent_label(self) -> str:
        return "n/d" if self.growth_recent is None else format_pct(self.growth_recent)

    @property
    def marking_label(self) -> str:
        marking = self.marking
        return "—" if marking is None else "%d %%" % round(marking * 100)

    @property
    def share_label(self) -> str:
        share = self.share
        return "—" if share is None else "%d %%" % round(share * 100)


class Slice:
    """Une population d'un marché : gros tickets, ou prix hors norme."""

    def __init__(self, kind: str, stores: Sequence[Store] = ()) -> None:
        self.kind = kind
        self.stores = sorted(stores, key=lambda item: -item.ytd)

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)

    @property
    def usable(self) -> bool:
        return self.ytd > 0

    @property
    def ytd(self) -> float:
        return sum(item.ytd for item in self.stores)

    @property
    def ytd_ly(self) -> Optional[float]:
        known = [item.ytd_ly for item in self.stores if item.ytd_ly is not None]
        return sum(known) if known else None

    @property
    def recent(self) -> float:
        return sum(item.recent for item in self.stores)

    @property
    def recent_ly(self) -> Optional[float]:
        known = [item.recent_ly for item in self.stores if item.recent_ly is not None]
        return sum(known) if known else None

    @property
    def flagged_ytd(self) -> float:
        return sum(item.flagged_ytd for item in self.stores)

    @property
    def growth(self) -> Optional[float]:
        return _growth(self.ytd, self.ytd_ly)

    @property
    def growth_recent(self) -> Optional[float]:
        return _growth(self.recent, self.recent_ly)

    @property
    def word(self) -> str:
        return _word(self.growth, self.growth_recent)

    @property
    def marking(self) -> Optional[float]:
        """La part marquée comme vrac — pour les gros tickets seulement : les prix hors norme
        sont lus hors drapeau par construction, et un zéro y serait une affirmation."""
        if self.kind != "quantity":
            return None
        return self.flagged_ytd / self.ytd if self.ytd > 0 else None

    @property
    def marks_its_bulk(self) -> Optional[bool]:
        marking = self.marking
        return None if marking is None else marking >= LOW_MARKING

    @property
    def shown(self) -> List[Store]:
        return self.stores[:MOST_STORES]

    @property
    def unmarked(self) -> float:
        """Les euros de gros tickets que le drapeau ne couvre pas : le vrac qui n'est pas
        dans le vrac marqué. C'est la mesure qui manquait — un marché qui marque ses six
        premiers comptes et pas le reste a un vrac marqué qui est un plancher."""
        return sum(item.unmarked for item in self.stores)

    @property
    def unmarked_share(self) -> Optional[float]:
        return self.unmarked / self.ytd if self.ytd > 0 else None

    @property
    def unmarked_stores(self) -> List[Store]:
        """Les points de vente qui portent les gros tickets non marqués, les plus lourds en tête."""
        carrying = [item for item in self.stores if item.unmarked > 0]
        return sorted(carrying, key=lambda item: -item.unmarked)[:MOST_STORES]

    @property
    def unmarked_label(self) -> str:
        return format_eur(self.unmarked)

    @property
    def ytd_label(self) -> str:
        return format_eur(self.ytd)

    @property
    def growth_label(self) -> str:
        return "n/d" if self.growth is None else format_pct(self.growth)

    @property
    def growth_recent_label(self) -> str:
        return "n/d" if self.growth_recent is None else format_pct(self.growth_recent)

    @property
    def marking_label(self) -> str:
        marking = self.marking
        return "—" if marking is None else "%d %%" % round(marking * 100)

    @property
    def sentence(self) -> str:
        if not self.usable:
            return "%s : rien de lisible" % self.label
        text = "%s : %s à date, %s sur l'an dernier, %s sur trois mois — %s" % (
            self.label, self.ytd_label, self.growth_label, self.growth_recent_label, self.word)
        if self.kind == "quantity" and self.marking is not None:
            text += " ; marqués comme vrac à %s en valeur, soit %s non marqués" % (
                self.marking_label, self.unmarked_label)
            if not self.marks_its_bulk:
                text += " : ce marché ne pose pas le drapeau, son vrac marqué est un plancher"
            carriers = self.unmarked_stores
            if carriers and self.unmarked > 0:
                text += " ; les non marqués sont portés par %s" % ", ".join(
                    "%s (%s)" % (item.code, item.unmarked_label) for item in carriers[:3])
        if self.stores:
            top = self.stores[0]
            text += " ; le premier point de vente, %s, en porte %s" % (top.code, top.share_label)
        return text


class Market:
    def __init__(self, scope: str, quantity: Slice, price: Slice) -> None:
        self.scope = scope
        self.quantity = quantity
        self.price = price

    @property
    def usable(self) -> bool:
        return self.quantity.usable or self.price.usable

    @property
    def slices(self) -> List[Slice]:
        return [item for item in (self.quantity, self.price) if item.usable]


class Review:
    def __init__(self, markets: Sequence[Market], start: str = "", through: str = "",
                 note: str = "") -> None:
        self.markets = list(markets)
        self.start = start
        self.through = through
        self.note = note

    @property
    def usable(self) -> bool:
        return bool(self.markets)

    def for_market(self, scope: str) -> Optional[Market]:
        return next((item for item in self.markets if item.scope == scope), None)

    @property
    def window_label(self) -> str:
        if not self.start or not self.through:
            return ""
        from .accounts import _span

        return "exercice à date, %s" % _span(self.start, self.through)

    @property
    def shown(self) -> List[Market]:
        """Les marchés par gros tickets décroissants, ceux qui en ont."""
        return sorted((m for m in self.markets if m.usable),
                      key=lambda m: -(m.quantity.ytd + m.price.ytd))

    @property
    def unmarked(self) -> List[Market]:
        """Les marchés qui ne posent pas le drapeau sur leurs gros tickets."""
        return [m for m in self.shown if m.quantity.usable and m.quantity.marks_its_bulk is False]

    @property
    def headline(self) -> str:
        if not self.usable:
            return ""
        total = Slice("quantity", [s for m in self.markets for s in m.quantity.stores])
        text = "gros tickets, tous marchés : %s à date, %s sur l'an dernier, marqués comme vrac à %s" % (
            total.ytd_label, total.growth_label, total.marking_label)
        if self.unmarked:
            text += " ; ne posent pas le drapeau : %s" % ", ".join(
                "%s (%s)" % (m.scope, m.quantity.marking_label) for m in self.unmarked[:4])
        return text


def build(rows: Sequence[dict], through: str = "", note: str = "") -> Review:
    """La lecture, sur les lignes de `SHADOW_BULK`."""
    from .budget import normalise_market

    rows = [row for row in rows if row.get("period") and str(row.get("kind") or "") in KINDS]
    if not rows:
        return Review([], note=note or "le gris sans drapeau n'est pas encore lu")
    periods = sorted(set(str(row["period"])[:7] for row in rows))
    last = periods[-1] if not through else min(periods[-1], through)
    start = fiscal_start(last)
    ytd_months = [m for m in _months_between(start, last) if m in periods]
    if not ytd_months:
        return Review([], note=note or "le gris sans drapeau ne couvre pas l'exercice à date")
    recent_months = ytd_months[-RECENT:]
    stores: Dict[tuple, Store] = {}
    for row in rows:
        market = normalise_market(str(row.get("market") or "(sans pays)"))
        key = (market, str(row.get("store") or "(sans code)"), str(row.get("kind")))
        store = stores.get(key)
        if store is None:
            store = stores[key] = Store(key[1], market, str(row.get("sub_channel") or "N/A"), key[2])
        period = str(row["period"])[:7]
        store.months[period] = store.months.get(period, 0.0) + float(row.get("net_eur") or 0.0)
        store.flagged[period] = store.flagged.get(period, 0.0) + float(row.get("flagged_eur") or 0.0)
    ly = [_shift(m, -12) for m in ytd_months]
    ly_recent = [_shift(m, -12) for m in recent_months]
    by_market: Dict[str, Dict[str, List[Store]]] = {}
    for store in stores.values():
        store.ytd = sum(store.months.get(m, 0.0) for m in ytd_months)
        store.recent = sum(store.months.get(m, 0.0) for m in recent_months)
        store.flagged_ytd = sum(store.flagged.get(m, 0.0) for m in ytd_months)
        if any(m in store.months for m in ly):
            store.ytd_ly = sum(store.months.get(m, 0.0) for m in ly)
        if any(m in store.months for m in ly_recent):
            store.recent_ly = sum(store.months.get(m, 0.0) for m in ly_recent)
        if store.ytd <= 0:
            continue
        by_market.setdefault(store.market, {}).setdefault(store.kind, []).append(store)
    markets = []
    for scope, kinds in by_market.items():
        for kind, items in kinds.items():
            total = sum(item.ytd for item in items)
            for item in items:
                item.total = total
        markets.append(Market(scope, Slice("quantity", kinds.get("quantity", [])),
                              Slice("price", kinds.get("price", []))))
    markets.sort(key=lambda m: -(m.quantity.ytd + m.price.ytd))
    return Review(markets, start, last, note)
