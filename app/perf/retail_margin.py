"""L'euro suivant en boutique, pays par pays — mesuré, avec sa précision et son côté.

Le retail est le seul canal dont l'unité naturelle est la boutique, et il en existe des
milliers : l'agent entrepôt régresse la variation de contribution sur la variation de
ventes des boutiques comparables, quatre exercices empilés, la dernière année des
boutiques fermées écartée, et écrit une ligne par pays dans
`var/incremental_margin_retail.csv`. Ce module la lit.

Trois nombres par pays, et le cockpit les tient à leur rang. **La pente** est la mesure :
ce qu'un euro de plus dans une boutique existante rapporte de contribution, avec un R² qui
dit sa précision et qu'on ne cache pas. **La dérive** est ce qu'une boutique comparable perd
chaque année à ventes constantes — le coût de l'immobilité, qui a remplacé sur l'écran une
« part loyer » que personne ne lisait. **Le côté** vient de la décomposition par le bail :
elle explique sans mieux prédire, et l'écran la garde comme explication — d'où récupérer
l'euro suivant, du bailleur ou de l'exploitation — jamais comme chiffre.

Un pays sous le plancher d'observations n'a pas de pente et le dit. Le fichier absent
laisse la ligne vide : rien ici n'est déduit d'un taux moyen.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional, Sequence

from .analytics import format_eur
from .budget import normalise_market

#: Les colonnes sans lesquelles le fichier ne se lit pas. Le reste est optionnel et vide
#: quand l'agent ne l'a pas mesuré.
REQUIRED = ("market", "slope_pct", "r2", "method")

#: La ligne du fichier qui porte le monde entier, telle que l'agent l'écrit.
WORLD = "Monde"

#: Les noms du fichier qui ne sont pas ceux du cockpit. Le reste passe par l'alias du plan.
ALIASES: Dict[str, str] = {
    "MONDE": WORLD,
    "WORLD": WORLD,
    "HK LOCAL": "Hong Kong",
    "HK": "Hong Kong",
}

#: La précision d'une pente, en un mot, sur son R². Les seuils sont ceux que la mesure
#: elle-même a montrés : au-dessus d'un demi la pente tient à trois boutiques près, en
#: dessous d'un cinquième elle donne un signe et un ordre de grandeur, pas un chiffre.
HIGH = 0.5
MEDIUM = 0.2
PRECISION_WORDS = ((HIGH, "haute"), (MEDIUM, "moyenne"), (0.0, "faible"))

#: Le côté d'où récupérer l'euro suivant. Le bailleur quand il prend au moins ce seuil de
#: l'euro et que l'exploitation en garde la moitié avant lui ; l'exploitation quand elle
#: garde moins qu'un cinquième avant même que le bailleur prenne quoi que ce soit.
LEASE_SIDE = 0.2
OPERATIONS_FLOOR = 0.2
LANDLORD = "bailleur"
OPERATIONS = "exploitation"

#: En dessous, le bail ne suit pas les ventes : un loyer fixe, et on le dit ainsi plutôt
#: que « le bailleur prend zéro centime ».
FIXED_LEASE = 0.005


def _pct(raw) -> Optional[float]:
    text = str(raw or "").strip().replace("%", "")
    if not text or text.upper() in ("NULL", "N/A", "NA"):
        return None
    try:
        return float(text.replace(",", ".")) / 100.0
    except ValueError:
        return None


def _number(raw) -> Optional[float]:
    text = str(raw or "").strip()
    if not text or text.upper() in ("NULL", "N/A", "NA"):
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _count(raw) -> int:
    value = _number(raw)
    return int(value) if value is not None else 0


def normalise(name: str) -> str:
    raw = (name or "").strip()
    if raw.upper() in ALIASES:
        return ALIASES[raw.upper()]
    return normalise_market(raw)


def precision_word(r2: Optional[float]) -> str:
    if r2 is None:
        return ""
    for floor, word in PRECISION_WORDS:
        if r2 >= floor:
            return word
    return "faible"


def _cents(rate: float) -> str:
    return "%d centime%s" % (round(rate * 100), "" if round(rate * 100) == 1 else "s")


class Line:
    """Un pays : sa pente et sa précision, sa dérive, ce que chaque coût prend, le bail."""

    __slots__ = ("market", "stores", "observations", "slope", "r2", "slope_up", "r2_up",
                 "n_up", "slope_down", "r2_down", "n_down", "drift_keur", "products", "staff",
                 "rent", "average", "years", "method", "excluded", "rule", "residual", "lease",
                 "lease_coverage", "line")

    def __init__(self, market: str, stores: int = 0, observations: int = 0,
                 slope: Optional[float] = None, r2: Optional[float] = None,
                 slope_up: Optional[float] = None, r2_up: Optional[float] = None, n_up: int = 0,
                 slope_down: Optional[float] = None, r2_down: Optional[float] = None,
                 n_down: int = 0, drift_keur: Optional[float] = None,
                 products: Optional[float] = None, staff: Optional[float] = None,
                 rent: Optional[float] = None, average: Optional[float] = None,
                 years: str = "", method: str = "", excluded: int = 0, rule: str = "",
                 residual: Optional[float] = None, lease: Optional[float] = None,
                 lease_coverage: Optional[float] = None, line: int = 0) -> None:
        self.market = market
        self.stores = stores
        self.observations = observations
        self.slope = slope
        self.r2 = r2
        self.slope_up = slope_up
        self.r2_up = r2_up
        self.n_up = n_up
        self.slope_down = slope_down
        self.r2_down = r2_down
        self.n_down = n_down
        #: En milliers d'euros par boutique et par exercice, à ventes constantes.
        self.drift_keur = drift_keur
        self.products = products
        self.staff = staff
        self.rent = rent
        self.average = average
        self.years = years
        self.method = method
        self.excluded = excluded
        self.rule = rule
        #: Ce que l'exploitation garde de l'euro suivant avant la part du bailleur.
        self.residual = residual
        #: Ce que le bail prend de l'euro suivant, tel que le référentiel l'écrit.
        self.lease = lease
        self.lease_coverage = lease_coverage
        self.line = line

    @property
    def measured(self) -> bool:
        return self.slope is not None

    @property
    def precision(self) -> str:
        return precision_word(self.r2)

    @property
    def precision_up(self) -> str:
        return precision_word(self.r2_up)

    @property
    def drift(self) -> Optional[float]:
        """La dérive en euros, pour l'écran."""
        return None if self.drift_keur is None else self.drift_keur * 1000.0

    @property
    def side(self) -> str:
        """D'où récupérer l'euro suivant : le bailleur, l'exploitation, ou rien à dire."""
        if self.residual is None or self.lease is None:
            return ""
        if self.residual < OPERATIONS_FLOOR:
            return OPERATIONS
        if self.lease >= LEASE_SIDE and self.residual >= 0.5:
            return LANDLORD
        return ""

    @property
    def side_sentence(self) -> str:
        if self.residual is None or self.lease is None:
            return ""
        if self.residual < 0:
            return ("l'exploitation perd sur l'euro suivant avant même la part du bailleur "
                    "(%s) : croître n'y paie pas, et le bail n'y est pour rien"
                    % _cents(self.lease))
        if self.lease < FIXED_LEASE:
            return ("le bail est fixe, le bailleur ne prend rien sur l'euro suivant ; "
                    "l'exploitation en garde %s" % _cents(self.residual))
        text = "le bailleur prend %s, l'exploitation en garde %s avant lui" % (
            _cents(self.lease), _cents(self.residual))
        if self.side == LANDLORD:
            text += " : c'est le bail qui pèse"
        elif self.side == OPERATIONS:
            text += " : c'est l'exploitation qui pèse"
        return text

    @property
    def sentence(self) -> str:
        """Une phrase par pays, la mesure d'abord, la précision toujours."""
        if not self.measured:
            return "non mesuré%s" % (" : " + self.method if self.method else "")
        text = "un euro de plus en boutique en rapporte %s (%d observations, précision %s)" % (
            _cents(self.slope), self.observations, self.precision)
        if self.slope_up is not None:
            text += ", %s quand la boutique croît (précision %s)" % (
                _cents(self.slope_up), self.precision_up)
        if self.drift is not None:
            verb = "perd" if self.drift < 0 else "gagne"
            text += " ; à ventes constantes, une boutique %s %s par an" % (
                verb, format_eur(abs(self.drift)))
        side = self.side_sentence
        if side:
            text += " ; " + side
        return text


class Retail:
    """Le fichier lu : une ligne par pays, le monde à part, et ce qui n'a pas pu l'être."""

    def __init__(self, lines: Sequence[Line], faults: Sequence[str], path: str = "") -> None:
        self.lines = list(lines)
        self.faults = list(faults)
        self.path = path
        self.by_market: Dict[str, Line] = {}
        for line in self.lines:
            self.by_market.setdefault(line.market, line)

    @property
    def is_empty(self) -> bool:
        return not self.lines

    @property
    def world(self) -> Optional[Line]:
        return self.by_market.get(WORLD)

    @property
    def countries(self) -> List[Line]:
        return [line for line in self.lines if line.market != WORLD]

    @property
    def measured(self) -> List[Line]:
        return [line for line in self.countries if line.measured]

    def of(self, market: str) -> Optional[Line]:
        return self.by_market.get(normalise(market))

    def for_markets(self, markets: Sequence[str]) -> List[Line]:
        """Les lignes des marchés d'un périmètre, mesurées d'abord, par pente décroissante."""
        found = [line for line in (self.of(market) for market in markets) if line is not None]
        return sorted(found, key=lambda line: (not line.measured, -(line.slope or 0.0)))

    @property
    def years(self) -> str:
        return self.world.years if self.world is not None else ""


def load(path: str) -> Retail:
    """Lire le fichier. Absent : une lecture vide, pas une erreur."""
    if not path or not os.path.exists(path):
        return Retail([], [], path)
    lines: List[Line] = []
    faults: List[str] = []
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            return Retail([], ["colonnes manquantes : %s" % ", ".join(missing)], path)
        for number, record in enumerate(reader, start=2):
            name = (record.get("market") or "").strip()
            if not name:
                faults.append("ligne %d : marché absent" % number)
                continue
            slope = _pct(record.get("slope_pct"))
            r2 = _number(record.get("r2"))
            method = " ".join((record.get("method") or "").split())
            if slope is not None and r2 is None:
                faults.append("ligne %d : « %s » a une pente sans R²" % (number, name))
                slope = None
            lines.append(Line(
                normalise(name), _count(record.get("stores")), _count(record.get("observations")),
                slope, r2, _pct(record.get("slope_up_pct")), _number(record.get("r2_up")),
                _count(record.get("n_up")), _pct(record.get("slope_down_pct")),
                _number(record.get("r2_down")), _count(record.get("n_down")),
                _number(record.get("intercept_keur")), _pct(record.get("products_pct")),
                _pct(record.get("staff_pct")), _pct(record.get("rent_pct")),
                _pct(record.get("average_margin_pct")),
                " ".join((record.get("fiscal_years") or "").split()), method,
                _count(record.get("excluded_observations")),
                " ".join((record.get("exclusion_rule") or "").split()),
                _pct(record.get("residual_slope_pct")), _pct(record.get("lease_pct")),
                _pct(record.get("lease_coverage_pct")), number,
            ))
    return Retail(lines, faults, path)


def current(path: Optional[str] = None) -> Retail:
    from ..config import settings

    return load(path or str(settings.retail_margin_path))
