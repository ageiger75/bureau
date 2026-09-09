"""Ce que l'entrepôt voit de la supply, à côté de ce que le mail dit.

Le rapport mensuel de la supply chain (`supply.py`) arrive par mail. Trois de ses quatre
lignes ont une matière dans l'entrepôt, et le cockpit la lit lui-même, chaque mois, sans
rien demander à personne :

- **le service en boutique** — la valeur de la demande en rupture sur la valeur de la
  demande, par unité ; définition de l'entrepôt, hors en-transit, toutes marques ;
- **le biais de prévision** — la prévision à M-3 contre le réel, par marché de prévision,
  en valeur ; négatif, les ventes sont au-dessus de la prévision, comme dans le rapport ;
- **le sell-in livré sur commandé** — en valeur, par canal, toutes marques, lignes rejetées
  exclues.

Aucune des trois n'est *la* mesure de la supply : la première en est à quelques dixièmes,
la deuxième trouve parfois le signe inverse, la troisième est dix points plus bas. Ce sont
les mesures du cockpit, nommées comme telles, posées à côté du mail — jamais à sa place,
jamais fondues avec lui. Un écart entre les deux est une question à poser, pas une erreur
à corriger.

Chaque taux est un rapport de deux sommes, jamais une moyenne de taux : l'unité du groupe
est le groupe, pas la moyenne de ses unités.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .products import month_fr
from .supply import BIAS_NOTICED, IN_FULL_TARGET, OSA_TARGET

#: Les lignes nommées dans chaque table ; le reste se replie.
MOST = 8

#: Les mois de la série du groupe.
SERIES = 12

#: Le livré sur commandé se lit un mois en arrière : une commande à livrer en août est
#: encore en cours le 9 septembre, et le dernier mois lit à vingt-cinq points sous le
#: précédent tant qu'il n'a pas fini de se livrer. Un mois de règlement, dit à l'écran.
FILL_SETTLING_MONTHS = 1

#: Ce que la vue écrit quand une ligne de commande n'a pas de canal.
NO_CHANNEL = ("N/A", "", "(SANS CANAL)")


def _number(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: Optional[float], signed: bool = False) -> str:
    if value is None:
        return "—"
    return ("%+.1f %%" if signed else "%.1f %%") % (value * 100)


class Ratio:
    """Un numérateur et un dénominateur, nommés : le taux se calcule au dernier moment."""

    __slots__ = ("name", "num", "den", "extra")

    def __init__(self, name: str) -> None:
        self.name = name
        self.num = 0.0
        self.den = 0.0
        self.extra = 0.0

    def add(self, num: float, den: float, extra: float = 0.0) -> None:
        self.num += num
        self.den += den
        self.extra += extra

    @property
    def rate(self) -> Optional[float]:
        return self.num / self.den if self.den > 0 else None


class Service(Ratio):
    """Une unité : demande en rupture sur demande."""

    @property
    def unit_label(self) -> str:
        """L'entrepôt écrit les unités en capitales ; l'écran les écrit comme partout."""
        from .budget import normalise_market

        return normalise_market(self.name)

    @property
    def osa(self) -> Optional[float]:
        return None if self.rate is None else 1.0 - self.rate

    @property
    def below(self) -> bool:
        return self.osa is not None and self.osa < OSA_TARGET

    @property
    def label(self) -> str:
        return _pct(self.osa)


class Bias(Ratio):
    """Un marché : prévision (num) et réel (den)."""

    @property
    def bias(self) -> Optional[float]:
        return None if self.rate is None else self.rate - 1.0

    @property
    def accuracy(self) -> Optional[float]:
        return None if self.bias is None else 1.0 - abs(self.bias)

    @property
    def over(self) -> bool:
        """Les ventes au-dessus de la prévision."""
        return self.bias is not None and self.bias <= -BIAS_NOTICED

    @property
    def under(self) -> bool:
        return self.bias is not None and self.bias >= BIAS_NOTICED

    @property
    def label(self) -> str:
        return _pct(self.bias, signed=True)

    @property
    def word(self) -> str:
        if self.over:
            return "vend au-dessus de la prévision"
        if self.under:
            return "vend en dessous"
        return "dans la prévision"


class Fill(Ratio):
    """Un canal : livré (num) sur commandé (den), et la valeur livrée en entier (extra)."""

    @property
    def fill(self) -> Optional[float]:
        return self.rate

    @property
    def complete(self) -> Optional[float]:
        return self.extra / self.den if self.den > 0 else None

    @property
    def below(self) -> bool:
        return self.fill is not None and self.fill < IN_FULL_TARGET

    @property
    def label(self) -> str:
        return _pct(self.fill)

    @property
    def channel_label(self) -> str:
        from .mapping import CHANNEL_NAMES

        if self.name.strip().upper() in NO_CHANNEL:
            return "sans canal"
        return CHANNEL_NAMES.get(self.name.lower(), self.name)


class Block:
    """Une des trois lectures : le mois, le groupe, les lignes, la série du groupe."""

    def __init__(self, kind: str, month: str, group, lines: Sequence, series: Sequence[Tuple[str, Optional[float]]],
                 note: str = "") -> None:
        self.kind = kind
        self.month = month
        self.group = group
        self.lines = list(lines)
        self.series = list(series)
        self.note = note

    @property
    def usable(self) -> bool:
        return self.group is not None and self.group.rate is not None

    @property
    def month_label(self) -> str:
        return month_fr(self.month) if self.month else ""

    @property
    def of_month(self) -> str:
        """« de juillet 2026 », « d'août 2026 »."""
        label = self.month_label
        return ("d'%s" if label[:1].lower() in "aeiouy" else "de %s") % label

    @property
    def shown(self) -> List:
        return self.lines[:MOST]

    @property
    def rest(self) -> int:
        return max(0, len(self.lines) - MOST)


class Review:
    def __init__(self, service: Optional[Block], bias: Optional[Block], fill: Optional[Block],
                 notes: Sequence[str] = ()) -> None:
        self.service = service
        self.bias = bias
        self.fill = fill
        self.notes = list(notes)

    @property
    def usable(self) -> bool:
        return any(block is not None and block.usable for block in (self.service, self.bias, self.fill))

    @property
    def service_sentence(self) -> str:
        block = self.service
        if block is None or not block.usable:
            return ""
        text = "service en boutique %s, lu par l'entrepôt : %s" % (block.of_month, block.group.label)
        below = [line for line in block.lines if line.below]
        if below:
            text += " ; sous la cible : %s" % ", ".join("%s %s" % (line.unit_label, line.label) for line in below)
        else:
            text += " ; toutes les unités au-dessus de la cible"
        return text

    @property
    def bias_sentence(self) -> str:
        block = self.bias
        if block is None or not block.usable:
            return ""
        group = block.group
        text = ("biais de prévision %s, mesure du cockpit : %s (précision %s)"
                % (block.of_month, group.label, _pct(group.accuracy)))
        over = [line for line in block.lines if line.over]
        under = [line for line in block.lines if line.under]
        if over:
            text += " ; vendent au-dessus de leur prévision : %s" % ", ".join(
                "%s %s" % (line.name, line.label) for line in over[:4])
        if under:
            text += " ; en dessous : %s" % ", ".join("%s %s" % (line.name, line.label) for line in under[:4])
        return text

    @property
    def fill_sentence(self) -> str:
        block = self.fill
        if block is None or not block.usable:
            return ""
        text = ("sell-in livré sur commandé %s (un mois de règlement), en valeur, toutes marques : "
                "%s, dont %s livré en entier"
                % (block.of_month, block.group.label, _pct(block.group.complete)))
        low = sorted((line for line in block.lines if line.fill is not None), key=lambda line: line.fill or 0.0)
        if low:
            text += " ; le plus bas : %s %s" % (low[0].channel_label, low[0].label)
        return text

    def against(self, report) -> List[str]:
        """Le mail et l'entrepôt sur le même mois, en points d'écart — une phrase par ligne
        où les deux existent, jamais une correction."""
        found = []
        group = getattr(report, "group", None)
        month = getattr(report, "month", "")
        if group is None or not month:
            return found
        pairs = (
            ("service en boutique", self.service, getattr(group, "osa", None), "osa"),
            ("biais de prévision", self.bias, getattr(group, "bias", None), "bias"),
            ("livré en entier", self.fill, getattr(group, "in_full", None), "fill"),
        )
        for label, block, reported, attribute in pairs:
            if block is None or not block.usable or reported is None or block.month != month:
                continue
            ours = getattr(block.group, attribute, None)
            if ours is None:
                continue
            gap = (ours - reported) * 100
            found.append("%s %s : le mail dit %s, l'entrepôt voit %s (%+.1f pt)"
                         % (label, block.of_month, _pct(reported, attribute == "bias"),
                            _pct(ours, attribute == "bias"), gap))
        return found


def _latest(rows: Sequence[dict], back: int = 0) -> str:
    """Le dernier mois lu — ou, `back` mois en arrière, un mois qui a fini de se régler."""
    periods = sorted(set(str(row.get("period") or "")[:7] for row in rows if row.get("period")))
    if not periods:
        return ""
    return periods[max(0, len(periods) - 1 - back)]


def _group_series(rows, key, num_field, den_field, transform) -> List[Tuple[str, Optional[float]]]:
    by_period: Dict[str, Ratio] = {}
    for row in rows:
        period = str(row.get("period") or "")[:7]
        num, den = _number(row.get(num_field)), _number(row.get(den_field))
        if not period or num is None or den is None:
            continue
        by_period.setdefault(period, Ratio(period)).add(num, den)
    return [(period, transform(by_period[period].rate)) for period in sorted(by_period)[-SERIES:]]


def _block(kind, rows, key_field, num_field, den_field, cls, transform, extra_field=None,
           sort_key=None, note: str = "", back: int = 0) -> Optional[Block]:
    if not rows:
        return None
    month = _latest(rows, back)
    group = cls("LOEP")
    lines: Dict[str, Ratio] = {}
    for row in rows:
        if str(row.get("period") or "")[:7] != month:
            continue
        name = str(row.get(key_field) or "").strip() or "(sans nom)"
        num, den = _number(row.get(num_field)), _number(row.get(den_field))
        if num is None or den is None:
            continue
        extra = _number(row.get(extra_field)) if extra_field else 0.0
        lines.setdefault(name, cls(name)).add(num, den, extra or 0.0)
        group.add(num, den, extra or 0.0)
    ordered = sorted(lines.values(), key=sort_key or (lambda line: -line.den))
    return Block(kind, month, group, ordered, _group_series(rows, key_field, num_field, den_field, transform), note)


def build(osa_rows: Sequence[dict] = (), forecast_rows: Sequence[dict] = (), order_rows: Sequence[dict] = (),
          notes: Sequence[str] = ()) -> Review:
    """Les trois lectures, sur les dernières lectures en cache — jamais une requête."""
    service = _block("service", osa_rows, "unit", "rupture_eur", "demand_eur", Service,
                     lambda rate: None if rate is None else 1.0 - rate,
                     sort_key=lambda line: (line.osa if line.osa is not None else 1.0))
    forecast = [row for row in forecast_rows
                if (_number(row.get("actual_eur")) or 0.0) > 0 and (_number(row.get("forecast_eur")) or 0.0) > 0]
    bias = _block("bias", forecast, "market", "forecast_eur", "actual_eur", Bias,
                  lambda rate: None if rate is None else rate - 1.0,
                  sort_key=lambda line: -abs((line.bias or 0.0) * line.den))
    fill = _block("fill", order_rows, "channel", "delivered_eur", "ordered_eur", Fill,
                  lambda rate: rate, extra_field="complete_eur",
                  sort_key=lambda line: -line.den, back=FILL_SETTLING_MONTHS,
                  note="lu un mois en arrière : le dernier mois est encore en cours de livraison")
    return Review(service, bias, fill, [note for note in notes if note])
