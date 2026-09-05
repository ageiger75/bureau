"""La marge incrémentale par canal, mesurée au compte de gestion — le taux du prochain euro.

Le panneau du mix déclarait le taux marginal absent, et c'était vrai : aucune source lue ici
ne le portait. Le compte de gestion le porte désormais, canal par canal, comme un rapport
de différences entre deux exercices — Δcontribution ÷ Δventes — calculé cellule par cellule
(pays × canal) puis agrégé sur les cellules dont la série est stable. L'agent entrepôt
l'écrit dans `var/incremental_margin_channels.csv`, avec pour chaque canal la mesure sur
deux paires d'exercices, la couverture des ventes que les cellules stables représentent, et
un **statut** qui dit si la mesure tient.

Un seul statut autorise le cockpit à poser un taux : `mesure`. Les autres sont nommés tels
que le fichier les écrit — un signe qui change quand on décale la paire d'un an, une
couverture partielle, une absence — et le canal reste ABSENT du calcul, jamais pris au taux
moyen ni à celui d'un voisin. Le retail, par exemple, sort de la liste : la thèse des coûts
fixes tient en structure, mais un rapport de différences sur une paire ne la chiffre pas.

Le fichier porte la date de l'instantané du compte de gestion sur lequel il est bâti, et
l'écran la rend : un taux vieux d'un exercice se lit comme tel.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional, Sequence, Tuple

from .mapping import CHANNEL_NAMES

#: Le seul statut qui fasse d'une ligne un taux. Le reste est nommé, jamais appliqué.
MEASURED = "mesure"

REQUIRED = ("channel", "status", "incremental_margin_pct")

#: Les libellés du compte de gestion, en codes de canal du cockpit. Ceux que `mix.ALIASES`
#: connaît déjà ne sont pas répétés ; ceux-ci sont propres à cette source.
ALIASES: Dict[str, Tuple[str, ...]] = {
    "e-business": ("ecommerce",),
    "e business": ("ecommerce",),
    "market place": ("marketplace",),
    "chains wholesale": ("whoch",),
    "wholesale indep": ("whoin",),
    "wholesales spa": ("whosp",),
    "digital direct selling": ("direct selling",),
}


def channels_of(name: str) -> Tuple[str, ...]:
    from . import mix

    key = mix._norm(name)
    if key in ALIASES:
        return ALIASES[key]
    return mix.channels_of(name)


def _pct(raw: str) -> Optional[float]:
    """« 49.7 » -> 0.497. Toujours en pour cent : le nom de la colonne le dit."""
    text = (raw or "").strip().replace("%", "")
    if not text or text.upper() in ("NULL", "N/A", "NA"):
        return None
    try:
        return float(text.replace(",", ".")) / 100.0
    except ValueError:
        return None


def _number(raw: str) -> Optional[float]:
    text = (raw or "").strip()
    if not text or text.upper() in ("NULL", "N/A", "NA"):
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


class Marginal:
    """Une ligne du fichier : un canal, sa mesure sur deux paires, son statut."""

    __slots__ = ("name", "group", "channels", "marginal", "previous", "average", "status",
                 "sales", "coverage", "snapshot", "snapshot_prev", "line")

    def __init__(self, name: str, group: str, channels: Tuple[str, ...],
                 marginal: Optional[float], previous: Optional[float],
                 average: Optional[float], status: str, sales: Optional[float],
                 coverage: Optional[float], snapshot: str, snapshot_prev: str,
                 line: int) -> None:
        self.name = name
        self.group = group
        self.channels = tuple(channels)
        self.marginal = marginal
        self.previous = previous
        self.average = average
        self.status = status
        self.sales = sales
        self.coverage = coverage
        self.snapshot = snapshot
        self.snapshot_prev = snapshot_prev
        self.line = line

    @property
    def measured(self) -> bool:
        return self.status == MEASURED and self.marginal is not None

    @property
    def label(self) -> str:
        return "—" if self.marginal is None else "%.0f %%" % (self.marginal * 100)

    @property
    def lever(self) -> Optional[float]:
        """Marginal moins moyen, sur la même base — celle du compte de gestion."""
        if self.marginal is None or self.average is None:
            return None
        return self.marginal - self.average

    @property
    def lever_label(self) -> str:
        if self.lever is None:
            return "—"
        points = int(round(self.lever * 100))
        return "0 pt" if points == 0 else "%+d pt%s" % (points, "" if abs(points) == 1 else "s")

    @property
    def screen_name(self) -> str:
        if self.channels:
            return CHANNEL_NAMES.get(self.channels[0], self.name)
        return self.name


class Incremental:
    """Le fichier lu : les taux mesurés par canal, les autres nommés, les défauts."""

    def __init__(self, rates: Sequence[Marginal], faults: Sequence[str], path: str = "") -> None:
        self.rates = list(rates)
        self.faults = list(faults)
        self.path = path
        self.by_channel: Dict[str, Marginal] = {}
        for rate in self.rates:
            if not rate.measured:
                continue
            for code in rate.channels:
                if code in self.by_channel:
                    self.faults.append("ligne %d : « %s » couvre %s, déjà porté par « %s »"
                                       % (rate.line, rate.name, CHANNEL_NAMES.get(code, code),
                                          self.by_channel[code].name))
                    continue
                self.by_channel[code] = rate

    @property
    def is_empty(self) -> bool:
        return not self.rates

    def of(self, channel: str) -> Optional[Marginal]:
        return self.by_channel.get(channel)

    @property
    def measured(self) -> List[Marginal]:
        return [rate for rate in self.rates if rate.measured]

    @property
    def unmeasured(self) -> List[Marginal]:
        return [rate for rate in self.rates if not rate.measured]

    @property
    def unmapped(self) -> List[Marginal]:
        return [rate for rate in self.rates if not rate.channels]

    @property
    def snapshot(self) -> str:
        return max((rate.snapshot for rate in self.rates if rate.snapshot), default="")


def load(path: str) -> Incremental:
    """Lire le fichier. Absent : une lecture vide, pas une erreur."""
    if not path or not os.path.exists(path):
        return Incremental([], [], path)
    rates: List[Marginal] = []
    faults: List[str] = []
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            return Incremental([], ["colonnes manquantes : %s" % ", ".join(missing)], path)
        for number, record in enumerate(reader, start=2):
            name = (record.get("channel") or "").strip()
            if not name:
                faults.append("ligne %d : canal absent" % number)
                continue
            status = " ".join((record.get("status") or "").strip().lower().split())
            marginal = _pct(record.get("incremental_margin_pct") or "")
            if status == MEASURED and marginal is None:
                faults.append("ligne %d : « %s » est mesuré sans taux lisible" % (number, name))
                status = "mesure sans taux lisible"
            channels = channels_of(name)
            if not channels:
                faults.append("ligne %d : « %s » ne désigne aucun canal du cockpit" % (number, name))
            rates.append(Marginal(
                name, (record.get("channel_group") or "").strip(), channels, marginal,
                _pct(record.get("incremental_margin_prev_pct") or ""),
                _pct(record.get("average_margin_pct") or ""), status,
                _number(record.get("sales_ty") or ""), _pct(record.get("coverage_pct") or ""),
                (record.get("snapshot_date") or "").strip(),
                (record.get("snapshot_date_prev") or "").strip(), number))
    return Incremental(rates, faults, path)


def current(path: Optional[str] = None) -> Incremental:
    from ..config import settings

    return load(path or str(settings.incremental_path))
