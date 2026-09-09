"""Les partenaires de sell-in par leur nom — pas « e-retailers ».

« E-retailers » est un canal ; un e-retailer, une enseigne, un opérateur de voyage sont des
interlocuteurs. La
conversation se tient avec un nom, et le nom n'est pas dans l'entrepôt : il vit dans
`var/partners.csv`, écrit à la main sous le code du centre de profit. Ce que le fichier
ne nomme pas garde le libellé du centre de profit, jamais un nom deviné — deux lignes sans
nom pèsent plus lourd que la moitié des partenaires nommés réunis, et les cacher rendrait
un total faux.

Trois règles, toutes venues de la lecture réelle.

**Le plan n'a pas de ligne par partenaire.** Il planifie un marché et un canal, et un
partenaire s'étale sur plusieurs marchés. La question « tel partenaire est-il en ligne avec le
plan ? » n'a donc pas de réponse directe, et ce module ne l'invente pas : un partenaire se
lit contre l'an dernier — exercice à date, puis trois derniers mois — et contre le plan de
**son canal**, qui lui existe. Le bloc le dit en toutes lettres.

**Un mois de sell-in dit le rythme de commande autant que la demande.** Une commande qui
glisse d'un mois fait un mois à moins vingt et le suivant à plus vingt. D'où les deux
fenêtres : l'exercice à date lisse, les trois derniers mois alertent, et le mot ne se
prononce que sur les deux à la fois.

**Le pays est le pays de facturation.** Un e-retailer mondial est facturé d'un seul petit
pays d'Europe, une enseigne d'un hub d'Asie ; ce n'est pas un marché et il ne s'affiche
pas comme tel.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Sequence

from .analytics import format_eur, format_pct
from .mapping import CHANNEL_NAMES
from .products import _mended

GROUP = "LOEP"

#: Les partenaires nommés dans la table ; le reste se replie sur une ligne.
MOST = 8

#: Trois derniers mois : la fenêtre qui alerte, à côté de l'exercice qui lisse.
RECENT = 3

#: En deçà, un partenaire est « en ligne » avec son an dernier ; au-delà, il avance ou
#: recule. Cinq pour cent : un mois de commande glissé sur douze en fait déjà huit.
NOTICED = 0.05

#: Le mois qui ouvre l'exercice.
FISCAL_START = 4


def _growth(now: float, before: Optional[float]) -> Optional[float]:
    if before is None or before <= 0:
        return None
    return now / before - 1.0


def _shift(period: str, months: int) -> str:
    year, month = int(period[:4]), int(period[5:7])
    index = year * 12 + month - 1 + months
    return "%04d-%02d" % (index // 12, index % 12 + 1)


def _months_between(start: str, through: str) -> List[str]:
    """'2026-04', '2026-08' -> avril à août inclus."""
    found = []
    current = start
    while current <= through:
        found.append(current)
        current = _shift(current, 1)
    return found


def fiscal_start(period: str) -> str:
    """'2026-08' -> '2026-04' ; '2027-02' -> '2026-04'."""
    year, month = int(period[:4]), int(period[5:7])
    return "%04d-%02d" % (year if month >= FISCAL_START else year - 1, FISCAL_START)


class Partner:
    """Un partenaire : ses mois, ses deux fenêtres, sa part de canal."""

    __slots__ = ("code", "name", "named", "channel", "months", "ytd", "ytd_ly", "recent",
                 "recent_ly", "ytd_months", "recent_months", "channel_ytd", "channel_gap")

    def __init__(self, code: str, name: str, named: bool, channel: str) -> None:
        self.code = code
        self.name = name
        self.named = named
        self.channel = channel
        self.months: Dict[str, float] = {}
        self.ytd = 0.0
        self.ytd_ly: Optional[float] = None
        self.recent = 0.0
        self.recent_ly: Optional[float] = None
        self.ytd_months: List[str] = []
        self.recent_months: List[str] = []
        self.channel_ytd = 0.0
        self.channel_gap: Optional[float] = None

    @property
    def channel_label(self) -> str:
        return CHANNEL_NAMES.get(self.channel, self.channel.upper() or "—")

    @property
    def growth_ytd(self) -> Optional[float]:
        return _growth(self.ytd, self.ytd_ly)

    @property
    def growth_recent(self) -> Optional[float]:
        return _growth(self.recent, self.recent_ly)

    @property
    def share_of_channel(self) -> Optional[float]:
        return self.ytd / self.channel_ytd if self.channel_ytd > 0 else None

    @property
    def word(self) -> str:
        """« avance », « recule », « en ligne » sur les deux fenêtres ; sinon ce que dit
        l'exercice, ou « sans an dernier »."""
        year, recent = self.growth_ytd, self.growth_recent
        if year is None:
            return "sans an dernier"
        if recent is not None and year >= NOTICED and recent >= NOTICED:
            return "avance"
        if recent is not None and year <= -NOTICED and recent <= -NOTICED:
            return "recule"
        if recent is not None and abs(year) < NOTICED and recent <= -NOTICED:
            return "fléchit depuis peu"
        if recent is not None and abs(year) < NOTICED and recent >= NOTICED:
            return "accélère depuis peu"
        if recent is not None and year >= NOTICED and recent <= -NOTICED:
            return "avance mais fléchit"
        if recent is not None and year <= -NOTICED and recent >= NOTICED:
            return "recule mais reprend"
        return "en ligne avec l'an dernier"

    @property
    def ytd_label(self) -> str:
        return format_eur(self.ytd)

    @property
    def growth_ytd_label(self) -> str:
        return "n/d" if self.growth_ytd is None else format_pct(self.growth_ytd)

    @property
    def growth_recent_label(self) -> str:
        return "n/d" if self.growth_recent is None else format_pct(self.growth_recent)

    @property
    def share_label(self) -> str:
        share = self.share_of_channel
        return "—" if share is None else "%d %%" % round(share * 100)

    @property
    def channel_plan_label(self) -> str:
        if self.channel_gap is None:
            return "plan du canal non lu"
        if abs(self.channel_gap) < 1.0:
            return "canal au plan"
        return "canal %s du plan à date" % (
            ("%s au-dessus" if self.channel_gap > 0 else "%s en dessous")
            % format_eur(abs(self.channel_gap)))


class Review:
    """La lecture, telle que la page et la commande la rendent."""

    def __init__(self, partners: Sequence[Partner], through: str = "", start: str = "",
                 note: str = "", unnamed_note: str = "") -> None:
        self.partners = list(partners)
        self.through = through
        self.start = start
        self.note = note
        self.unnamed_note = unnamed_note

    @property
    def usable(self) -> bool:
        return bool(self.partners)

    @property
    def shown(self) -> List[Partner]:
        return self.partners[:MOST]

    @property
    def rest(self) -> List[Partner]:
        return self.partners[MOST:]

    @property
    def rest_total(self) -> float:
        return sum(item.ytd for item in self.rest)

    @property
    def total(self) -> float:
        return sum(item.ytd for item in self.partners)

    @property
    def window_label(self) -> str:
        if not self.start or not self.through:
            return ""
        return "exercice à date, %s" % _span(self.start, self.through)

    @property
    def plan_note(self) -> str:
        return ("le plan n'a pas de ligne par partenaire : chacun se lit contre l'an "
                "dernier, et contre le plan de son canal")

    @property
    def headline(self) -> str:
        if not self.usable:
            return ""
        named = [item for item in self.partners if item.named]
        ahead = [item for item in self.shown if item.word == "avance"]
        behind = [item for item in self.shown if item.word == "recule"]
        parts = ["%d partenaires facturés sur l'exercice à date, %s"
                 % (len(self.partners), format_eur(self.total))]
        if named:
            parts[0] += ", %d nommé%s" % (len(named), "s" if len(named) > 1 else "")
        if ahead:
            parts.append("avancent : %s" % ", ".join(item.name for item in ahead))
        if behind:
            parts.append("reculent : %s" % ", ".join(item.name for item in behind))
        if not ahead and not behind:
            parts.append("aucun des premiers ne s'écarte de son an dernier")
        return " ; ".join(parts)

    @property
    def question(self) -> str:
        movers = [item for item in self.shown if item.growth_recent is not None
                  and abs(item.growth_recent) >= NOTICED]
        if not movers:
            return ""
        top = max(movers, key=lambda item: abs(item.growth_recent or 0.0) * item.ytd)
        direction = "recule" if (top.growth_recent or 0.0) < 0 else "avance"
        return ("%s %s de %s sur trois mois, %s : commande qui glisse ou demande "
                "qui change ?" % (top.name, direction,
                                  format_pct(abs(top.growth_recent or 0.0)).lstrip("+"),
                                  top.channel_plan_label))


def _span(start: str, through: str) -> str:
    from .invoiced import MONTHS_FR

    first = MONTHS_FR[int(start[5:7]) - 1]
    last = MONTHS_FR[int(through[5:7]) - 1]
    return "%s à %s" % (first, last) if start != through else last


def _name_of(code: str, label: str, names: Dict[str, str]) -> (str, bool):
    known = names.get(code) or names.get(code.strip().upper()) or ""
    if known:
        return known, True
    clean = _mended(label or "").strip()
    return (clean.title() if clean.isupper() else clean) or code, False


def build(rows: Sequence[dict], names: Optional[Dict[str, str]] = None,
          channel_gaps: Optional[Dict[str, float]] = None, note: str = "",
          today: Optional[datetime.date] = None) -> Review:
    """Les partenaires, sur les lignes de `PARTNER_SELL_IN` et les noms du fichier.

    `channel_gaps` : le code de canal (minuscule) → l'écart au plan de l'exercice à date,
    tel que la lecture principale le tient ; absent, le bloc dit que le plan du canal n'est
    pas lu plutôt que de se taire.

    Le mois en cours est écarté : la lecture court jusqu'à hier, et un mois à moitié
    facturé posé contre le même mois entier l'an dernier a fait lire trois partenaires à
    moins quarante pour cent qui ne reculaient pas.
    """
    names = {str(k).strip().upper(): v for k, v in (names or {}).items()}
    channel_gaps = {str(k).strip().lower(): v for k, v in (channel_gaps or {}).items()}
    current_month = (today or datetime.date.today()).strftime("%Y-%m")
    by_code: Dict[str, Partner] = {}
    periods = set()
    for row in rows:
        period = str(row.get("period") or "").strip()[:7]
        code = str(row.get("code") or "").strip()
        if not period or not code or period >= current_month:
            continue
        value = _number(row.get("net_eur"))
        if value is None:
            continue
        partner = by_code.get(code)
        if partner is None:
            name, named = _name_of(code, str(row.get("label") or ""), names)
            partner = Partner(code, name, named, str(row.get("channel") or "").strip().lower())
            by_code[code] = partner
        partner.months[period] = partner.months.get(period, 0.0) + value
        periods.add(period)
    if not by_code:
        return Review([], note=note or "aucune facture de partenaire dans la lecture")

    through = max(periods)
    start = fiscal_start(through)
    ytd_months = [m for m in _months_between(start, through) if m in periods]
    recent_months = ytd_months[-RECENT:]
    channel_ytd: Dict[str, float] = {}
    for partner in by_code.values():
        partner.ytd_months = ytd_months
        partner.recent_months = recent_months
        partner.ytd = sum(partner.months.get(m, 0.0) for m in ytd_months)
        partner.recent = sum(partner.months.get(m, 0.0) for m in recent_months)
        ly_months = [_shift(m, -12) for m in ytd_months]
        if all(m in periods for m in ly_months):
            partner.ytd_ly = sum(partner.months.get(m, 0.0) for m in ly_months)
        recent_ly = [_shift(m, -12) for m in recent_months]
        if all(m in periods for m in recent_ly):
            partner.recent_ly = sum(partner.months.get(m, 0.0) for m in recent_ly)
        channel_ytd[partner.channel] = channel_ytd.get(partner.channel, 0.0) + partner.ytd
    for partner in by_code.values():
        partner.channel_ytd = channel_ytd.get(partner.channel, 0.0)
        partner.channel_gap = channel_gaps.get(partner.channel)

    partners = sorted(by_code.values(), key=lambda item: -item.ytd)
    unnamed = [item for item in partners[:MOST] if not item.named]
    unnamed_note = ""
    if unnamed:
        unnamed_note = ("%d des premiers partenaires n'ont pas de nom dans var/partners.csv "
                        "et gardent le libellé de leur centre de profit : %s"
                        % (len(unnamed), ", ".join(item.name for item in unnamed)))
    return Review(partners, through, start, note, unnamed_note)


def _number(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def names_from(partners) -> Dict[str, str]:
    """`code du centre de profit → nom commercial`, sur la base sell-in du fichier."""
    from . import partners as partners_module

    found: Dict[str, str] = {}
    for line in getattr(partners, "lines", []) or []:
        if getattr(line, "base", "") != partners_module.SELL_IN:
            continue
        if getattr(line, "partner", "") and getattr(line, "profit_centre", ""):
            found[str(line.profit_centre).strip().upper()] = line.partner
    return found
