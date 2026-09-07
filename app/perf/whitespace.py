"""Les white spaces internes : là où l'on pourrait vendre et où l'on ne vend pas.

Le lecteur a nommé le besoin en une phrase : identifier les white spaces, avec ce que
l'entreprise sait déjà. Un white space **externe** — une part de marché que d'autres
prennent — demande une donnée que l'entrepôt n'a pas ; il attend l'extrait Beauté Research
pour l'Asie. Un white space **interne** se lit dans nos propres chiffres, et il en existe
trois formes que ce module mesure :

1. **Un canal absent.** Un canal que les marchés comparables — ceux du même périmètre —
   ont, et que ce marché n'a pas. L'ordre de grandeur est la part médiane du canal chez
   les pairs, appliquée aux ventes de ce marché : une hypothèse nommée, jamais un plan.
2. **Un mix sous le plan depuis plusieurs mois.** Un canal dont la part est sous celle
   que le plan lui donnait, mois après mois : le plan y voyait un relais, le réalisé ne
   le prend pas. L'enjeu est l'écart de l'exercice à date sur ce canal.
3. **Des boutiques sous la médiane de leur marché.** Dans un marché qui en compte assez,
   les boutiques qui font moins de la moitié de la boutique médiane. L'ordre de grandeur
   est ce qu'elles vendraient de plus à la médiane — pas une promesse, une taille.

Chaque chiffre porte son hypothèse. Rien ici n'est un objectif : c'est une taille de
question, pour décider laquelle vaut un appel.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .analytics import format_eur

#: Un canal est « établi chez les pairs » quand au moins deux d'entre eux le portent, la
#: moitié d'entre eux au moins, et qu'il y pèse une part médiane digne d'une conversation.
PEERS_LEAST = 2
PEERS_SHARE = 0.5
CHANNEL_SHARE = 0.05

#: Les mois consécutifs sous la part planifiée avant qu'un mix devienne un white space.
MIX_MONTHS = 3

#: Le nombre de boutiques à partir duquel une médiane veut dire quelque chose, et la
#: fraction de la médiane sous laquelle une boutique est dite en dessous.
STORES_LEAST = 6
BELOW_MEDIAN = 0.5

#: Combien de lignes par forme, à l'écran.
MOST = 5

CHANNEL_ABSENT = "canal absent"
MIX_BELOW_PLAN = "mix sous le plan"
STORES_BELOW = "boutiques sous la médiane"


class Space:
    """Un white space : sa forme, son marché, sa taille, et l'hypothèse qui la donne."""

    __slots__ = ("kind", "market", "label", "amount", "basis", "question", "details")

    def __init__(self, kind: str, market: str, label: str, amount: Optional[float],
                 basis: str, question: str, details: Sequence[str] = ()) -> None:
        self.kind = kind
        self.market = market
        self.label = label
        #: L'ordre de grandeur, en euros par mois pour les formes 1 et 3, sur l'exercice
        #: à date pour la forme 2. None quand la taille ne se calcule pas.
        self.amount = amount
        self.basis = basis
        self.question = question
        self.details = list(details)

    @property
    def amount_label(self) -> str:
        return "—" if self.amount is None else format_eur(self.amount)


class Review:
    """Les trois formes, et ce qui manque pour lire chacune."""

    def __init__(self, channels: Sequence[Space] = (), mixes: Sequence[Space] = (),
                 stores: Sequence[Space] = (), absent: Sequence[str] = ()) -> None:
        self.channels = list(channels)
        self.mixes = list(mixes)
        self.stores = list(stores)
        self.absent = list(absent)

    @property
    def usable(self) -> bool:
        return bool(self.channels or self.mixes or self.stores)

    @property
    def count(self) -> int:
        return len(self.channels) + len(self.mixes) + len(self.stores)


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _budgeted(units: Sequence) -> List:
    return [unit for unit in units
            if not getattr(unit, "is_aggregate", False) and getattr(unit, "budget_known", True)
            and getattr(unit, "market", "")]


# --------------------------------------------------------------------- forme 1


def absent_channels(units: Sequence, placed: Dict[str, str], no_site: Sequence[str] = ()
                    ) -> List[Space]:
    """Les canaux que les pairs d'un marché portent et qu'il n'a pas."""
    by_market: Dict[str, Dict[str, float]] = {}
    labels: Dict[str, str] = {}
    for unit in _budgeted(units):
        sales = max(getattr(unit, "sales_actual", 0.0) or 0.0, 0.0)
        by_market.setdefault(unit.market, {})
        if sales > 0 or (getattr(unit, "sales_budget", 0.0) or 0.0) > 0:
            by_market[unit.market][unit.channel] = by_market[unit.market].get(unit.channel, 0.0) + sales
            labels.setdefault(unit.channel, getattr(unit, "channel_label", unit.channel))
    found: List[Space] = []
    for market, channels in by_market.items():
        perimeter = placed.get(market)
        if not perimeter:
            continue
        peers = [name for name, group in placed.items()
                 if group == perimeter and name != market and name in by_market]
        if len(peers) < PEERS_LEAST:
            continue
        total = sum(channels.values())
        if total <= 0:
            continue
        candidates = {code for peer in peers for code in by_market[peer]} - set(channels)
        for code in sorted(candidates):
            if code == "ecommerce" and market in no_site:
                # Vendre en ligne par des partenaires est une façon de travailler, pas une
                # absence : ce marché n'a pas de site et le sait.
                continue
            shares = []
            for peer in peers:
                peer_total = sum(by_market[peer].values())
                if peer_total > 0 and code in by_market[peer]:
                    shares.append(by_market[peer][code] / peer_total)
            if len(shares) < PEERS_LEAST or len(shares) < PEERS_SHARE * len(peers):
                continue
            share = _median(shares)
            if share < CHANNEL_SHARE:
                continue
            label = labels.get(code, code)
            carrying = [peer for peer in peers if code in by_market[peer]]
            found.append(Space(
                CHANNEL_ABSENT, market, label, total * share,
                "part médiane de %s chez %s (%.0f %% de leurs ventes), appliquée aux %s de ce "
                "marché ce mois" % (label, ", ".join(carrying), share * 100, format_eur(total)),
                "Pourquoi %s n'a pas %s quand %s l'ont ?" % (market, label, ", ".join(carrying)),
                carrying,
            ))
    found.sort(key=lambda space: -(space.amount or 0.0))
    return found


# --------------------------------------------------------------------- forme 2


def mixes_below_plan(units: Sequence) -> List[Space]:
    """Les canaux dont la part reste sous celle du plan depuis plusieurs mois."""
    by_market: Dict[str, List] = {}
    for unit in _budgeted(units):
        by_market.setdefault(unit.market, []).append(unit)
    found: List[Space] = []
    for market, members in by_market.items():
        actual = sum(max(getattr(unit, "sales_actual", 0.0) or 0.0, 0.0) for unit in members)
        planned = sum(max(getattr(unit, "sales_budget", 0.0) or 0.0, 0.0) for unit in members)
        if actual <= 0 or planned <= 0 or len(members) < 2:
            continue
        for unit in members:
            history = tuple(getattr(unit, "gap_history", ()) or ())
            if len(history) < MIX_MONTHS or any(value >= 0 for value in history[-MIX_MONTHS:]):
                continue
            share = (getattr(unit, "sales_actual", 0.0) or 0.0) / actual
            plan_share = (getattr(unit, "sales_budget", 0.0) or 0.0) / planned
            if share >= plan_share:
                continue
            year = getattr(unit, "gap_year_to_date", None)
            amount = -year if year is not None and year < 0 else -sum(history[-MIX_MONTHS:])
            label = getattr(unit, "channel_label", unit.channel)
            found.append(Space(
                MIX_BELOW_PLAN, market, label, amount,
                "%s fait %.0f %% du marché contre %.0f %% au plan, sous le plan depuis %d mois ; "
                "%s" % (label, share * 100, plan_share * 100, MIX_MONTHS,
                        "l'écart de l'exercice à date" if year is not None
                        else "l'écart des %d derniers mois" % MIX_MONTHS),
                "Le plan voyait %s comme un relais sur %s : qu'est-ce qui n'a pas été fait, ou "
                "le relais n'existe-t-il pas ?" % (label, market),
            ))
    found.sort(key=lambda space: -(space.amount or 0.0))
    return found


# --------------------------------------------------------------------- forme 3


def stores_below_median(sales) -> List[Space]:
    """Dans chaque marché qui en compte assez, les boutiques sous la moitié de la médiane."""
    if sales is None or not getattr(sales, "usable", False):
        return []
    by_market: Dict[str, List] = {}
    for store in sales.stores:
        if getattr(store, "is_bulk", False):
            continue
        actual = getattr(store, "actual", None)
        if actual is None or actual <= 0:
            continue
        by_market.setdefault(store.market, []).append(store)
    found: List[Space] = []
    for market, stores in by_market.items():
        if len(stores) < STORES_LEAST:
            continue
        median = _median([store.actual for store in stores])
        below = [store for store in stores if store.actual < BELOW_MEDIAN * median]
        if not below:
            continue
        amount = sum(median - store.actual for store in below)
        found.append(Space(
            STORES_BELOW, market, "%d boutique%s sur %d" % (len(below), "s" if len(below) > 1 else "", len(stores)),
            amount,
            "boutiques sous la moitié de la médiane du marché (%s par boutique ce mois) ; ce "
            "qu'elles vendraient de plus à la médiane" % format_eur(median),
            "Ces %d boutiques : à relancer, à réduire, ou à fermer ?" % len(below),
            ["%s %s %s" % (store.code, store.name, format_eur(store.actual)) for store in
             sorted(below, key=lambda store: store.actual)],
        ))
    found.sort(key=lambda space: -(space.amount or 0.0))
    return found


# ---------------------------------------------------------------------- lecture


def build(dataset, placed: Optional[Dict[str, str]] = None, sales=None) -> Review:
    """Les trois formes sur ce que la page a déjà lu. Rien n'est relu."""
    units = list(getattr(dataset, "units", []) or [])
    absent: List[str] = []
    if not units:
        absent.append("aucune unité lue : ni canal absent ni mix à comparer")
    placed = placed or {}
    if units and not placed:
        absent.append("aucun périmètre placé : les pairs d'un marché ne se nomment pas, la forme "
                      "« canal absent » ne se lit pas")
    no_site = list(getattr(dataset, "markets_without_own_site", []) or [])
    channels = absent_channels(units, placed, no_site) if placed else []
    mixes = mixes_below_plan(units)
    if sales is None:
        absent.append("ventes par boutique non lues : la forme « boutiques sous la médiane » attend "
                      "le fichier de la CFO")
    stores = stores_below_median(sales)
    absent.append("les white spaces externes — la part de marché que d'autres prennent — attendent "
                  "l'extrait Beauté Research pour l'Asie")
    return Review(channels[:MOST], mixes[:MOST], stores[:MOST], absent)
