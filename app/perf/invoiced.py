"""Le sell-in du mois : ce que la Maison a facturé à ses partenaires depuis le 1er, contre
la même chose l'an dernier — à jours facturés égaux.

Le sell-out se lit à la vente ; le sell-in à la facture, et une facture tombe un jour ouvré.
Comparer le 1er au 5 septembre de cette année, un mardi à samedi, au 1er au 5 septembre de
l'an dernier, un lundi à vendredi, compare quatre jours ouvrés à cinq et fabrique trente
points d'écart. Ce module compare donc **les N premiers jours facturés** de chaque mois, N
étant le nombre de jours facturés depuis le 1er cette année — et rend à côté la fenêtre à
dates égales, pour que l'écart entre les deux alignements reste visible.

Ce que ce module refuse. Rien n'est comparé au plan : les factures au jour ne se
réconcilient pas canal par canal avec la consolidation — l'axe canal des factures et celui
de la consolidation ne rangent pas le même chiffre au même endroit — et le plan est écrit
sur l'axe de la consolidation. Factures contre factures, à base constante, c'est tout ce
que la table autorise, et c'est déjà la réponse à « le mois démarre-t-il comme l'an
dernier ». Le canal vient du centre de profit, jamais de la colonne de canal de la facture,
vide quatre fois sur cinq ; le montant est au taux fixe, jamais au taux de la facture.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Sequence

from .mapping import CHANNEL_NAMES

MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre")

CURRENT = "current"
LAST_YEAR = "last_year"

#: Les codes de canal des centres de profit, en minuscules comme le cockpit les tient.
CODES = {"tra": "tra", "webp": "webp", "dis": "dis", "whoch": "whoch", "whoin": "whoin",
         "dpt": "dpt", "b2b": "b2b", "tvc": "tvc", "copg": "copg", "whosp": "whosp"}

#: Le nombre de canaux et de périmètres portés avant de replier le reste.
MOST = 6

#: Ce que l'écran appelle les factures dont le centre de profit n'est pas un canal
#: commercial — HOLD, RET, ALLOCATE, PROD, un code vide. Tenues à part et nommées, hors du
#: total du groupe : elles ne disent rien du démarrage du mois chez les partenaires.
OTHER = "hors canaux commerciaux"


def _day(text) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(str(text or "")[:10])
    except ValueError:
        return None


def _number(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(now: float, before: Optional[float]) -> Optional[float]:
    if before is None or before <= 0:
        return None
    return now / before - 1.0


def _pct_label(value: Optional[float]) -> str:
    return "—" if value is None else "%+.0f %%" % (value * 100)


class Line:
    """Un canal, un périmètre ou le groupe : facturé à date, et l'an dernier à jours
    facturés égaux et à dates égales."""

    __slots__ = ("name", "current", "aligned", "same_dates")

    def __init__(self, name: str) -> None:
        self.name = name
        self.current = 0.0
        self.aligned = 0.0
        self.same_dates = 0.0

    @property
    def growth(self) -> Optional[float]:
        return _pct(self.current, self.aligned)

    @property
    def growth_same_dates(self) -> Optional[float]:
        return _pct(self.current, self.same_dates)

    @property
    def growth_label(self) -> str:
        return _pct_label(self.growth)

    @property
    def same_dates_label(self) -> str:
        return _pct_label(self.growth_same_dates)


class Review:
    """Le mois facturé vu par l'écran : le groupe, les canaux, les périmètres, ce qui manque."""

    def __init__(self, month: Optional[datetime.date], through: Optional[datetime.date],
                 days: int, group: Optional[Line], channels: Sequence[Line],
                 perimeters: Sequence[Line], absent: Sequence[str],
                 loose: Optional[Line] = None, other: Optional[Line] = None,
                 other_codes: Sequence[str] = ()) -> None:
        self.month = month
        self.through = through
        #: Les jours facturés depuis le 1er, cette année — le N de l'alignement.
        self.days = days
        self.group = group
        self.channels = list(channels)
        self.perimeters = list(perimeters)
        self.absent = list(absent)
        self.loose = loose
        #: Les factures hors canaux commerciaux, à part, avec les codes qu'elles portent.
        self.other = other
        self.other_codes = list(other_codes)

    @property
    def other_note(self) -> str:
        from .analytics import format_eur

        if self.other is None or not self.other.current:
            return ""
        return ("%s facturés hors canaux commerciaux (%s), tenus hors du total"
                % (format_eur(self.other.current), ", ".join(self.other_codes)))

    @property
    def usable(self) -> bool:
        return self.group is not None and self.group.current > 0 and self.days > 0

    @property
    def title(self) -> str:
        if self.month is None or self.through is None:
            return "Le sell-in du mois"
        return "Sell-in facturé du 1er au %d %s" % (self.through.day, MONTHS_FR[self.month.month - 1])

    @property
    def sentence(self) -> str:
        from .analytics import format_eur

        if not self.usable:
            return ""
        text = "%s sur %d jour%s facturé%s, %s sur les %d premiers jours facturés de %s %d" % (
            format_eur(self.group.current), self.days, "s" if self.days > 1 else "",
            "s" if self.days > 1 else "", self.group.growth_label, self.days,
            MONTHS_FR[self.month.month - 1], self.month.year - 1)
        if self.group.growth_same_dates is not None:
            text += " (%s à dates égales)" % self.group.same_dates_label
        return text

    @property
    def note(self) -> str:
        return ("Factures contre factures, à base constante, jamais contre le plan : les "
                "factures au jour ne se réconcilient pas canal par canal avec la "
                "consolidation, sur laquelle le plan est écrit.")

    def for_name(self, name: str) -> Optional[Line]:
        return next((line for line in self.perimeters if line.name == name), None)

    @property
    def shown_channels(self) -> List[Line]:
        return sorted(self.channels, key=lambda line: -line.current)[:MOST]

    @property
    def rest_channels(self) -> List[Line]:
        return sorted(self.channels, key=lambda line: -line.current)[MOST:]


def build(rows: Sequence[dict], markets_by_iso2: Optional[Dict[str, str]] = None, org=None,
          directory=None, today: Optional[datetime.date] = None) -> Review:
    """Le mois facturé, à jours facturés égaux.

    `rows` est le contrat de `SELL_IN_DAILY` : `window · invoice_date · iso2 · channel ·
    net_eur`, `window` valant `current` ou `last_year`. `markets_by_iso2` traduit le pays
    de la facture en marché du cockpit, tel que le sell-out au jour le nomme.
    """
    from .month import place_markets

    absent: List[str] = []
    current: Dict[datetime.date, List[dict]] = {}
    before: Dict[datetime.date, List[dict]] = {}
    for row in rows:
        day = _day(row.get("invoice_date"))
        amount = _number(row.get("net_eur"))
        if day is None or amount is None:
            continue
        window = str(row.get("window") or "").strip().lower()
        target = current if window == CURRENT else before if window == LAST_YEAR else None
        if target is None:
            continue
        if today is not None and window == CURRENT and day > today:
            continue
        target.setdefault(day, []).append({"iso2": str(row.get("iso2") or "").strip().upper(),
                                           "channel": str(row.get("channel") or "").strip().lower(),
                                           "amount": amount})
    if not current:
        return Review(None, None, 0, None, [], [], ["aucune facture lue sur le mois en cours : le sell-in du mois ne se lit pas"])
    through = max(current)
    month = through.replace(day=1)
    days = len(current)
    # Les N premiers jours facturés du même mois l'an dernier, dans l'ordre des dates.
    last_month_days = sorted(day for day in before if day.month == month.month)
    aligned_days = set(last_month_days[:days])
    same_dates = {day for day in before if day.month == month.month and day.day <= through.day}
    if len(last_month_days) < days:
        absent.append("l'an dernier ne porte que %d jour%s facturé%s sur ce mois : l'alignement est court"
                      % (len(last_month_days), "s" if len(last_month_days) > 1 else "",
                         "s" if len(last_month_days) > 1 else ""))

    channels: Dict[str, Line] = {}
    countries: Dict[str, Line] = {}
    group = Line("Groupe")
    other = Line(OTHER)
    other_codes: List[str] = []

    def pour(entries, attribute):
        for entry in entries:
            code = entry["channel"]
            if code not in CODES:
                # Pas un canal commercial : à part, nommé, hors du total.
                setattr(other, attribute, getattr(other, attribute) + entry["amount"])
                shown = code.upper() if code else "vide"
                if shown not in other_codes:
                    other_codes.append(shown)
                continue
            label = CHANNEL_NAMES.get(CODES[code], code.upper())
            for bucket, key in ((channels, label), (countries, entry["iso2"] or "??")):
                line = bucket.setdefault(key, Line(key))
                setattr(line, attribute, getattr(line, attribute) + entry["amount"])
            setattr(group, attribute, getattr(group, attribute) + entry["amount"])

    for day, entries in current.items():
        pour(entries, "current")
    for day, entries in before.items():
        if day in aligned_days:
            pour(entries, "aligned")
        if day in same_dates:
            pour(entries, "same_dates")

    names = markets_by_iso2 or {}
    market_lines: Dict[str, Line] = {}
    for iso2, line in countries.items():
        market = names.get(iso2, iso2)
        merged = market_lines.setdefault(market, Line(market))
        merged.current += line.current
        merged.aligned += line.aligned
        merged.same_dates += line.same_dates
    placed, _leads = place_markets(list(market_lines), org, directory)
    perimeters: Dict[str, Line] = {}
    loose = Line("Sans périmètre")
    for market, line in market_lines.items():
        target = perimeters.setdefault(placed[market], Line(placed[market])) if placed.get(market) else loose
        target.current += line.current
        target.aligned += line.aligned
        target.same_dates += line.same_dates
    ordered = sorted(perimeters.values(), key=lambda line: -line.current)
    if not placed:
        absent.append("ni annuaire ni organigramme : les pays facturés ne sont pas rangés par périmètre")
    return Review(month, through, days, group, list(channels.values()), ordered, absent,
                  loose if loose.current else None, other if other.current else None,
                  sorted(other_codes))
