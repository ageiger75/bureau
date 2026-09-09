"""L'indice de remplissage : le sell-in qui court devant ce qu'on sait de la vente.

Le sell-in facture des partenaires — travel retail, e-retailers, distributeurs, chaînes —
et le sell-out que le cockpit lit est celui de nos boutiques et de notre site. Les deux ne
se confrontent pas. Ce qu'il faudrait est le sell-through, le sell-out des partenaires sur
ce qu'on leur a facturé, et l'entrepôt n'en tient aucun : l'inventaire de l'agent entrepôt
du 9 septembre 2026 n'a trouvé ni table ni vue de sell-through, seulement les points de
vente partenaires que la maison opère elle-même, déjà dans le sell-out.

Alors le seul signal de stock en réseau est le rythme du sell-in lui-même. Un canal facturé
bien au-dessus de son rythme des douze derniers mois et bien au-dessus des mêmes mois l'an
dernier remplit des entrepôts avant de vendre — ou prépare un temps fort, ou rattrape une
rupture. C'est un indice, pas une mesure, et ce module le dit ainsi : il nomme les canaux
où la lecture est un indice faute de sell-through, et ceux où un sell-through partiel
existe dans le sell-out parce que nous y opérons des points de vente.

Lu dans ce que le cockpit a déjà : le sell-in de l'exercice à date, mois par mois avec
l'an dernier en face, et l'exercice clos, mois par mois. Jamais une requête.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .analytics import format_eur, format_pct
from .budget import channel_of, normalise_market
from .mapping import CHANNEL_NAMES

#: Les trois derniers mois clos, contre le rythme des douze derniers et les mêmes trois mois
#: l'an dernier. Trois mois, parce qu'un mois de sell-in dit le rythme de commande d'un
#: partenaire autant que la demande.
RECENT = 3
TRAILING = 12

#: Au-delà, sur les deux comparaisons à la fois, le canal se remplit plus vite qu'il ne vend
#: — sauf temps fort ou rattrapage, que le bloc ne sait pas voir et le dit.
FILLING = 0.25

#: Ce que l'entrepôt tient en face de chaque canal de sell-in, d'après l'inventaire de
#: l'agent entrepôt du 9 septembre 2026 : un sell-through partiel là où la maison opère
#: elle-même des points de vente chez le partenaire (corners, places de marché), rien
#: ailleurs. À réviser quand un objet apparaîtra dans l'entrepôt.
SELL_THROUGH = {
    "webp": "partiel — les places de marché que nous opérons sont dans le sell-out",
    "dpt": "partiel — les corners que nous opérons sont dans le sell-out",
}
NO_SELL_THROUGH = "aucun sell-through dans l'entrepôt : l'indice est tout ce qu'on a"


def _number(value) -> Optional[float]:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _shift(period: str, months: int) -> str:
    year, month = int(period[:4]), int(period[5:7])
    index = year * 12 + (month - 1) + months
    return "%04d-%02d" % (index // 12, index % 12 + 1)


def _growth(now: float, before: Optional[float]) -> Optional[float]:
    if before is None or before <= 0:
        return None
    return now / before - 1.0


class Channel:
    """Un canal de sell-in : ses trois derniers mois, son rythme, l'an dernier, le verdict."""

    __slots__ = ("code", "recent", "recent_months", "trailing_monthly", "last_year", "known")

    def __init__(self, code: str, recent: float, recent_months: Sequence[str],
                 trailing_monthly: Optional[float], last_year: Optional[float]) -> None:
        self.code = code
        self.recent = recent
        self.recent_months = list(recent_months)
        self.trailing_monthly = trailing_monthly
        self.last_year = last_year
        self.known = SELL_THROUGH.get(code, NO_SELL_THROUGH)

    @property
    def label(self) -> str:
        return CHANNEL_NAMES.get(self.code, self.code)

    @property
    def recent_monthly(self) -> float:
        return self.recent / len(self.recent_months) if self.recent_months else 0.0

    @property
    def vs_trailing(self) -> Optional[float]:
        return _growth(self.recent_monthly, self.trailing_monthly)

    @property
    def vs_last_year(self) -> Optional[float]:
        return _growth(self.recent, self.last_year)

    @property
    def filling(self) -> bool:
        return (self.vs_trailing is not None and self.vs_trailing >= FILLING
                and self.vs_last_year is not None and self.vs_last_year >= FILLING)

    @property
    def word(self) -> str:
        if self.filling:
            return "se remplit"
        if self.vs_trailing is not None and self.vs_trailing <= -FILLING and \
                self.vs_last_year is not None and self.vs_last_year <= -FILLING:
            return "se vide"
        return "au rythme"

    recent_label = property(lambda self: format_eur(self.recent))
    trailing_label = property(lambda self: "—" if self.trailing_monthly is None else format_eur(self.trailing_monthly))
    vs_trailing_label = property(lambda self: format_pct(self.vs_trailing))
    vs_last_year_label = property(lambda self: format_pct(self.vs_last_year))


class Review:
    def __init__(self, channels: Sequence[Channel] = (), months: Sequence[str] = (),
                 absent: Sequence[str] = ()) -> None:
        self.channels = list(channels)
        self.months = list(months)
        self.absent = list(absent)

    @property
    def usable(self) -> bool:
        return bool(self.channels)

    @property
    def filling(self) -> List[Channel]:
        return [channel for channel in self.channels if channel.filling]

    @property
    def basis(self) -> str:
        from .products import months_label

        return ("sell-in facturé, %s, contre le rythme mensuel des %d derniers mois et contre "
                "les mêmes mois l'an dernier · un indice, pas une mesure : aucun sell-through "
                "dans l'entrepôt" % (months_label(self.months), TRAILING))

    @property
    def sentence(self) -> str:
        if not self.channels:
            return ""
        names = [channel.label for channel in self.filling]
        if not names:
            return "aucun canal ne court devant son rythme sur ces trois mois"
        return ("%s se remplit plus vite qu'il ne vendait : facturé %s au-dessus de son rythme "
                "et de l'an dernier — un temps fort devant, un rattrapage, ou du stock en réseau"
                % (", ".join(names), "d'un quart ou plus"))

    question = ("Pour chaque canal qui se remplit : le partenaire a-t-il vendu ce qu'on lui a "
                "facturé ? Sans sell-through, la seule réponse est la sienne — la demander "
                "avant les retours.")


def series(current: Iterable[dict], closed: Iterable[dict]) -> Tuple[Dict[Tuple[str, str], float],
                                                                    Dict[Tuple[str, str], float]]:
    """(canal, mois) → facturé, pour l'exercice à date et l'exercice clos ; et l'an dernier
    des mois de l'exercice à date, tels que la consolidation les publie en face."""
    sold: Dict[Tuple[str, str], float] = {}
    before: Dict[Tuple[str, str], float] = {}
    for row in current or []:
        segment = str(row.get("segment") or "").strip()
        period = str(row.get("period") or "").strip()
        if not segment or len(period) != 7:
            continue
        code = channel_of(segment)
        now, last = _number(row.get("sales_actual")), _number(row.get("sales_last_year"))
        if now is not None:
            sold[(code, period)] = sold.get((code, period), 0.0) + now
        if last is not None:
            before[(code, period)] = before.get((code, period), 0.0) + last
    for row in closed or []:
        segment = str(row.get("segment") or "").strip()
        period = str(row.get("period") or "").strip()
        value = _number(row.get("value"))
        if not segment or len(period) != 7 or value is None:
            continue
        code = channel_of(segment)
        if (code, period) not in sold:
            sold[(code, period)] = sold.get((code, period), 0.0) + value
    return sold, before


def build(current: Iterable[dict], closed: Iterable[dict], only: Sequence[str] = ()) -> Review:
    """L'indice par canal de sell-in, sur les caches que le cockpit tient déjà."""
    sold, before = series(list(current or []), list(closed or []))
    if not sold:
        return Review(absent=["le sell-in de l'exercice à date n'est pas lu : rien à comparer"])
    codes = sorted({code for code, _ in sold})
    if only:
        codes = [code for code in codes if code in only]
    anchor = max(period for _, period in sold)
    recent_months = [_shift(anchor, -offset) for offset in range(RECENT - 1, -1, -1)]
    trailing_months = [_shift(anchor, -offset) for offset in range(TRAILING - 1, -1, -1)]
    channels = []
    absent: List[str] = []
    for code in codes:
        if code in ("ecommerce", "retail", "marketplace", "spa", "cafe", "direct selling"):
            continue
        recent = sum(sold.get((code, month), 0.0) for month in recent_months)
        present = [month for month in trailing_months if (code, month) in sold]
        trailing = (sum(sold[(code, month)] for month in present) / len(present)) if present else None
        last = [before[(code, month)] for month in recent_months if (code, month) in before]
        last_year = sum(last) if len(last) == len(recent_months) else None
        channels.append(Channel(code, recent, recent_months, trailing, last_year))
        if len(present) < TRAILING:
            absent.append("%s : le rythme est lu sur %d mois, pas %d" % (
                CHANNEL_NAMES.get(code, code), len(present), TRAILING))
    channels.sort(key=lambda channel: -channel.recent)
    return Review(channels, recent_months, absent)
