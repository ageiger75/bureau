"""Le rapport supply mensuel, lu comme une source : le service, la prévision, le biais.

Chaque mois, la supply chain commerciale publie ses indicateurs : le service en boutique
(OSA), le service du sell-in (livré en entier), la précision de la prévision et son biais,
par marché, et la prévision de demande de l'exercice. Ils arrivent dans un mail et un
deck. Le cockpit les lit dans un fichier de quelques lignes que le lecteur dépose, un par
mois, avec le mois en première colonne ; le dernier mois lu est celui qui compte.

Ce que ces lignes disent au cockpit, et où :

- **la prévision de demande** de l'exercice, que l'écran du jour disait absente ;
- **le biais par marché**, à côté de l'indice de remplissage : un marché qui vend
  au-dessus de sa prévision sur le wholesale a des partenaires qui commandent plus
  qu'attendu — la prévision dit ce qu'on attendait, la facture ce qui est parti, et
  l'écart entre les deux est le stock qu'on ne voit pas ;
- **le service** sous la cible, qui explique une partie des écarts de facturation.

Le biais suit la convention du rapport : négatif, les ventes sont au-dessus de la
prévision ; positif, en dessous. Aucun envoi, aucune relecture : un fichier.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional, Sequence

from .products import _key, month_fr
from . import memo

REQUIRED = ("month", "scope")
COLUMNS = ("month", "scope", "osa", "in_full", "forecast_accuracy", "bias", "forecast_growth", "note")
GROUP = "LOEP"

#: Les cibles telles que le rapport les nomme : le service en boutique à 98 %, le sell-in
#: livré en entier à 97 %. À ajuster si le rapport change les siennes.
OSA_TARGET = 0.98
IN_FULL_TARGET = 0.97

#: Au-delà, en valeur absolue, le biais est une nouvelle : les ventes s'écartent de la
#: prévision assez pour que le stock en réseau ou les ruptures en découlent.
BIAS_NOTICED = 0.05


def _pct(text) -> Optional[float]:
    """« 97 », « 97 % », « -2 » → une fraction ; vide → None."""
    raw = str(text or "").strip().replace("%", "").replace(",", ".").replace("−", "-").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    # Le fichier écrit des pour cent, comme le rapport : 97, -2, 3.
    return value / 100.0


class Line:
    __slots__ = ("month", "scope", "osa", "in_full", "accuracy", "bias", "growth", "note", "row")

    def __init__(self, month: str, scope: str, osa=None, in_full=None, accuracy=None, bias=None,
                 growth=None, note: str = "", row: int = 0) -> None:
        self.month = month
        self.scope = scope
        self.osa = osa
        self.in_full = in_full
        self.accuracy = accuracy
        self.bias = bias
        self.growth = growth
        self.note = note
        self.row = row

    @property
    def is_group(self) -> bool:
        return _key(self.scope) == _key(GROUP)

    @property
    def below_service(self) -> List[str]:
        found = []
        if self.in_full is not None and self.in_full < IN_FULL_TARGET:
            found.append("sell-in livré en entier %.1f %%" % (self.in_full * 100))
        if self.osa is not None and self.osa < OSA_TARGET:
            found.append("service en boutique %.1f %%" % (self.osa * 100))
        return found

    @property
    def over_forecast(self) -> bool:
        return self.bias is not None and self.bias <= -BIAS_NOTICED

    @property
    def under_forecast(self) -> bool:
        return self.bias is not None and self.bias >= BIAS_NOTICED

    @property
    def bias_label(self) -> str:
        if self.bias is None:
            return "—"
        return "%+.1f %% (%s)" % (self.bias * 100, "vend au-dessus de la prévision" if self.bias < 0
                                  else "vend en dessous" if self.bias > 0 else "juste")

    @staticmethod
    def _p(value) -> str:
        return "—" if value is None else "%.1f %%" % (value * 100)

    osa_label = property(lambda self: self._p(self.osa))
    in_full_label = property(lambda self: self._p(self.in_full))
    accuracy_label = property(lambda self: self._p(self.accuracy))
    growth_label = property(lambda self: "—" if self.growth is None else "%+.1f %%" % (self.growth * 100))


class Review:
    def __init__(self, lines: Sequence[Line] = (), month: str = "", faults: Sequence[str] = (),
                 path: str = "") -> None:
        self.lines = list(lines)
        self.month = month
        self.faults = list(faults)
        self.path = path

    @property
    def usable(self) -> bool:
        return bool(self.lines)

    @property
    def group(self) -> Optional[Line]:
        return next((line for line in self.lines if line.is_group), None)

    @property
    def markets(self) -> List[Line]:
        return [line for line in self.lines if not line.is_group]

    def for_scope(self, scope: str) -> Optional[Line]:
        wanted = _key(scope)
        return next((line for line in self.lines if _key(line.scope) == wanted), None)

    @property
    def month_label(self) -> str:
        return month_fr(self.month) if self.month else ""

    @property
    def forecast_sentence(self) -> str:
        """« Prévision supply de juillet 2026 : l'exercice à +3 % sur le précédent »."""
        group = self.group
        if group is None or group.growth is None:
            return ""
        text = "prévision supply de %s : l'exercice à %s sur le précédent" % (
            self.month_label, group.growth_label)
        if group.note:
            text += " (%s)" % group.note
        return text

    @property
    def forecast_short(self) -> str:
        """La même prévision sans sa note, pour l'écran du jour."""
        group = self.group
        if group is None or group.growth is None:
            return ""
        return "prévision supply : l'exercice à %s sur le précédent" % group.growth_label

    @property
    def service_sentence(self) -> str:
        group = self.group
        parts = []
        if group is not None:
            if group.osa is not None:
                parts.append("service en boutique %s" % group.osa_label)
            if group.in_full is not None:
                parts.append("sell-in livré en entier %s" % group.in_full_label)
            if group.accuracy is not None:
                parts.append("précision de prévision %s" % group.accuracy_label)
        below = [line for line in self.markets if line.below_service]
        if below:
            parts.append("sous la cible : " + ", ".join(
                "%s (%s)" % (line.scope, " ; ".join(line.below_service)) for line in below))
        return " · ".join(parts)

    @property
    def bias_sentence(self) -> str:
        over = [line for line in self.markets if line.over_forecast]
        under = [line for line in self.markets if line.under_forecast]
        parts = []
        if over:
            parts.append("vendent au-dessus de leur prévision : " + ", ".join(
                "%s %+.0f %%" % (line.scope, line.bias * 100) for line in over))
        if under:
            parts.append("en dessous : " + ", ".join(
                "%s %+.0f %%" % (line.scope, line.bias * 100) for line in under))
        return " · ".join(parts)


@memo.by_file
def load(path: str) -> Review:
    """Lire le fichier. Absent : une lecture vide, pas une erreur. Le dernier mois compte."""
    if not path or not os.path.exists(path):
        return Review(path=path)
    lines: List[Line] = []
    faults: List[str] = []
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            return Review(faults=["colonnes manquantes : %s" % ", ".join(missing)], path=path)
        for number, record in enumerate(reader, start=2):
            month = (record.get("month") or "").strip()[:7]
            scope = (record.get("scope") or "").strip()
            if len(month) != 7 or not scope:
                faults.append("ligne %d : mois ou périmètre absent" % number)
                continue
            lines.append(Line(month, scope, _pct(record.get("osa")), _pct(record.get("in_full")),
                              _pct(record.get("forecast_accuracy")), _pct(record.get("bias")),
                              _pct(record.get("forecast_growth")), (record.get("note") or "").strip(),
                              number))
    if not lines:
        return Review(faults=faults, path=path)
    latest = max(line.month for line in lines)
    return Review([line for line in lines if line.month == latest], latest, faults, path)


def current(path: Optional[str] = None) -> Review:
    from ..config import settings

    return load(path or str(settings.supply_path))
