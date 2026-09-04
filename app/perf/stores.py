"""La part loyer du prochain euro, boutique par boutique — la deuxième pièce de B5.

Le taux moyen d'un canal dit ce que le canal a rapporté. Le taux marginal — ce que le
prochain euro rapporterait — n'est porté par aucune source entière, mais une de ses parts
l'est : le loyer. Le référentiel immobilier de l'entrepôt écrit, bail par bail, la part de
loyer variable — le pourcentage du chiffre qu'un euro de plus vendu dans cette boutique
rend au bailleur. Là où elle vaut zéro, un euro de plus ne perd rien en loyer ; là où elle
est écrite, il perd exactement ce pourcentage ; là où elle n'est pas écrite, on ne sait pas.

Ce module joint deux fichiers par le code de boutique : les ventes par magasin telles que
la consolidation les publie, avec leur budget, et le référentiel extrait de l'entrepôt.
Il rend, par marché, ce que le loyer prend sur le prochain euro **des boutiques dont le
bail est connu**, pondéré par leurs ventes, et dit à chaque ligne quelle part des ventes
du marché ce bail connu couvre. Des états jamais confondus : une part variable écrite, un
loyer fixe confirmé — un zéro écrit à côté d'un loyer mensuel —, un zéro douteux, un bail
qui n'est pas le nôtre, et rien d'écrit. Le dernier n'est pas un zéro.

Ce que ce module refuse : étendre un taux à un pays, compléter une boutique par ses
voisines, et présenter la part loyer comme le taux marginal entier. Personnel, logistique
et marketing manquent, et l'écran continue de le dire.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional, Sequence

from . import actuals as actuals_module
from .xlsx import Workbook, read_sheet

REQUIRED = ("store_code", "market", "var_rent_percent")

#: Ce que le tableau montre au plus, du plus gros marché au plus petit ; le reste replié.
MOST = 12

#: Les états d'un bail, nommés pour ne jamais se confondre. Le référentiel écrit deux
#: choses : une part de loyer variable et un loyer mensuel. Lues ensemble, elles séparent
#: le loyer fixe confirmé — un zéro écrit à côté d'un loyer mensuel — du zéro douteux, écrit
#: sans loyer à côté, que rien ne distingue d'une case remplie par défaut. Le référentiel a
#: cinq fixes confirmés pour un douteux : la plupart des zéros sont de l'information, et le
#: cockpit ne compte que ceux-là.
VARIABLE = "part variable écrite"
FIXED = "loyer fixe confirmé"
DOUBTFUL = "zéro douteux"
NONE_WRITTEN = "zéro écrit"
UNKNOWN = "non renseigné"
#: Le travel retail opéré par un tiers : un emplacement dans le réseau d'un opérateur
#: d'aéroport, qui tient le bail avec le concessionnaire. Nous y vendons la marque, notre
#: rémunération est une marge de gros, et il n'y a pas de bail à notre nom — pas une
#: donnée manquante, une donnée sans objet. Le référentiel le marque « Not Owned », et
#: neuf de ces boutiques sur dix sont du travel retail.
THIRD_PARTY = "sans bail à notre nom"

#: Ce qu'une ligne du fichier de la CFO peut porter sans être une boutique : les ventes en
#: vrac, logées sous un pseudo-magasin. Écartées et comptées, jamais jointes.
BULK_MARK = "BUL"

#: Ce que l'écran répète, une fois écrit ici.
MARGINAL_NOTE = ("La part loyer n'est qu'une part du coût marginal. Personnel, logistique "
                 "et marketing manquent, et aucun taux ici ne se lit comme un taux marginal "
                 "entier.")

SHEET_MONTH = "Sales Data by Store MTD"
SHEET_YTD = "Sales Data by Store YTD"


def _number(raw) -> Optional[float]:
    text = str(raw if raw is not None else "").strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _rate(raw) -> Optional[float]:
    """« 12.5 » ou « 0.125 » : une part. Rien d'écrit reste rien."""
    value = _number(raw)
    if value is None:
        return None
    return value / 100.0 if value > 1.0 else value


def _code(raw) -> str:
    return " ".join(str(raw if raw is not None else "").split()).upper()


class Lease:
    """Une boutique du référentiel : son code, son bail, et ce que le bail dit."""

    __slots__ = ("store_code", "conso_code", "name", "market", "ownership",
                 "var_rent", "monthly_rent", "category", "status", "line", "rent_known")

    def __init__(self, store_code, conso_code="", name="", market="", ownership="",
                 var_rent=None, monthly_rent=None, category="", status="", line=0,
                 rent_known=False) -> None:
        self.store_code = store_code
        self.conso_code = conso_code
        self.name = name
        self.market = market
        self.ownership = ownership
        self.var_rent = var_rent
        self.monthly_rent = monthly_rent
        self.category = category
        self.status = status
        self.line = line
        #: Si le fichier porte la colonne du loyer mensuel. Sans elle, un zéro écrit ne
        #: peut être ni confirmé ni mis en doute, et se lit comme un zéro écrit.
        self.rent_known = rent_known

    @property
    def codes(self) -> List[str]:
        return [code for code in (self.conso_code, self.store_code) if code]

    @property
    def is_third_party(self) -> bool:
        return " ".join(self.ownership.lower().split()) == "not owned"

    @property
    def state(self) -> str:
        if self.var_rent is None:
            return THIRD_PARTY if self.is_third_party else UNKNOWN
        if self.var_rent > 0:
            return VARIABLE
        if not self.rent_known:
            return NONE_WRITTEN
        return FIXED if self.monthly_rent else DOUBTFUL

    @property
    def informed(self) -> bool:
        """Si le bail dit ce qu'un euro de plus perd en loyer : une part écrite, ou un zéro
        qu'un loyer mensuel confirme. Un zéro douteux ne compte pas."""
        return self.state in (VARIABLE, FIXED, NONE_WRITTEN)


class Register:
    """Le référentiel lu, et ce qu'il n'a pas pu lire."""

    def __init__(self, leases: Sequence[Lease], faults: Sequence[str], path: str = "") -> None:
        self.leases = list(leases)
        self.faults = list(faults)
        self.path = path
        self.by_code: Dict[str, Lease] = {}
        for lease in self.leases:
            for code in lease.codes:
                # Le premier bail tient pour un code ; un second est nommé, jamais mélangé.
                if code in self.by_code and self.by_code[code] is not lease:
                    self.faults.append("ligne %d : code %s déjà porté par la ligne %d"
                                       % (lease.line, code, self.by_code[code].line))
                    continue
                self.by_code[code] = lease

    @property
    def is_empty(self) -> bool:
        return not self.leases

    def of(self, code: str) -> Optional[Lease]:
        return self.by_code.get(_code(code))


def load(path: str) -> Register:
    """Lire le référentiel. Absent : une lecture vide, pas une erreur."""
    if not path or not os.path.exists(path):
        return Register([], [], path)
    leases: List[Lease] = []
    faults: List[str] = []
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            return Register([], ["colonnes manquantes : %s" % ", ".join(missing)], path)
        rent_known = "monthly_rent" in header
        for number, record in enumerate(reader, start=2):
            code = _code(record.get("store_code"))
            if not code:
                faults.append("ligne %d : code de boutique absent" % number)
                continue
            leases.append(Lease(
                store_code=code,
                conso_code=_code(record.get("conso_code")),
                name=(record.get("store_name") or "").strip(),
                market=(record.get("market") or "").strip(),
                ownership=(record.get("ownership") or "").strip(),
                var_rent=_rate(record.get("var_rent_percent")),
                monthly_rent=_number(record.get("monthly_rent")),
                category=(record.get("store_category") or "").strip(),
                status=(record.get("status") or "").strip(),
                line=number,
                rent_known=rent_known,
            ))
    return Register(leases, faults, path)


def current(path: Optional[str] = None) -> Register:
    from ..config import settings

    return load(path or str(settings.stores_path))


# ---------------------------------------------------------------- les ventes par boutique


class StoreSales:
    """Une boutique du fichier de la CFO : ses ventes, son plan, son code."""

    __slots__ = ("code", "name", "market", "status", "actual", "last_year", "budget")

    def __init__(self, code, name, market, status, actual, last_year, budget) -> None:
        self.code = code
        self.name = name
        self.market = market
        self.status = status
        self.actual = actual
        self.last_year = last_year
        self.budget = budget

    @property
    def is_bulk(self) -> bool:
        """Une ligne de vrac logée sous un pseudo-magasin — pas une boutique."""
        return BULK_MARK in self.code


class Sales:
    def __init__(self, stores: Sequence[StoreSales], faults: Sequence[str], path: str = "",
                 sheet: str = "") -> None:
        self.stores = list(stores)
        self.faults = list(faults)
        self.path = path
        self.sheet = sheet

    @property
    def usable(self) -> bool:
        return bool(self.stores)


def load_sales(path: str, month: bool = True, brand: str = actuals_module.BRAND) -> Sales:
    """La feuille par boutique de l'extraction de la CFO, à taux constant, en euros."""
    wanted = SHEET_MONTH if month else SHEET_YTD
    try:
        with Workbook(path) as book:
            names = book.sheet_names
    except Exception as exc:  # noqa: BLE001 — le message compte plus que le type
        return Sales([], ["%s" % exc], path, wanted)
    sheet = next((name for name in names
                  if " ".join(name.split()).lower() == wanted.lower()), "")
    if not sheet:
        return Sales([], ["aucune feuille %r — feuilles : %s" % (wanted, ", ".join(names))],
                     path, wanted)
    rows = read_sheet(path, sheet)
    index, at = actuals_module._header_row(rows, "Brand", "Code PCC", "Desc PCC", "Status")
    if index is None:
        return Sales([], ["en-tête introuvable : Brand, Code PCC, Desc PCC, Status"], path,
                     sheet)
    measures, why = actuals_module._measures(rows, index, at)
    if why:
        return Sales([], [why], path, sheet)
    market_at = at.get("Management Unit - Lowest")
    if market_at is None:
        return Sales([], ["colonne manquante : Management Unit - Lowest"], path, sheet)
    width = max(max(at.values()), max(measures.values())) + 1
    stores: List[StoreSales] = []
    for row in rows[index + 1:]:
        if len(row) < width:
            row = list(row) + [None] * (width - len(row))
        if str(row[at["Brand"]] or "").strip() != brand:
            continue
        code = _code(row[at["Code PCC"]])
        if not code:
            continue
        actual = _number(row[measures["actual"]])
        budget = _number(row[measures["budget"]])
        last_year = _number(row[measures["last_year"]])
        if actual is None and budget is None and last_year is None:
            continue
        status = row[at["Status"]]
        stores.append(StoreSales(
            code=code,
            name=str(row[at["Desc PCC"]] or "").strip(),
            market=actuals_module._market(row[market_at]),
            status=str(int(status)) if isinstance(status, float) else str(status or ""),
            actual=(actual or 0.0) * actuals_module.THOUSANDS,
            last_year=(last_year or 0.0) * actuals_module.THOUSANDS,
            budget=(budget or 0.0) * actuals_module.THOUSANDS,
        ))
    faults = [] if stores else ["aucune boutique %s dans %r" % (brand, sheet)]
    return Sales(stores, faults, path, sheet)


def current_sales(path: Optional[str] = None, month: bool = True) -> Sales:
    from ..config import settings

    return load_sales(path or str(settings.store_sales_path), month)


# ------------------------------------------------------------------------ la jointure


class Joined:
    __slots__ = ("sale", "lease")

    def __init__(self, sale: StoreSales, lease: Optional[Lease]) -> None:
        self.sale = sale
        self.lease = lease

    @property
    def state(self) -> str:
        return self.lease.state if self.lease else UNKNOWN

    @property
    def informed(self) -> bool:
        return bool(self.lease and self.lease.informed)


class Market:
    """Un marché : ses boutiques, celles dont le bail est connu, et ce que le loyer prend."""

    def __init__(self, name: str, stores: Sequence[Joined]) -> None:
        self.name = name
        self.stores = list(stores)

    @property
    def count(self) -> int:
        return len(self.stores)

    @property
    def joined(self) -> List[Joined]:
        return [store for store in self.stores if store.lease]

    @property
    def informed(self) -> List[Joined]:
        return [store for store in self.stores if store.informed]

    def in_state(self, *states: str) -> List[Joined]:
        return [store for store in self.stores if store.state in states]

    @property
    def variable(self) -> List[Joined]:
        return self.in_state(VARIABLE)

    @property
    def fixed(self) -> List[Joined]:
        """Loyer fixe confirmé, ou un zéro écrit quand le fichier ne sait pas confirmer."""
        return self.in_state(FIXED, NONE_WRITTEN)

    @property
    def none_written(self) -> List[Joined]:
        return self.fixed

    @property
    def doubtful(self) -> List[Joined]:
        return self.in_state(DOUBTFUL)

    @property
    def third_party(self) -> List[Joined]:
        return self.in_state(THIRD_PARTY)

    @property
    def unknown(self) -> List[Joined]:
        """Ni bail connu, ni tiers : un bail à nous dont le référentiel ne dit rien, ou un
        zéro douteux. Les deux attendent l'immobilier."""
        return [store for store in self.stores
                if not store.informed and store.state != THIRD_PARTY]

    @property
    def sales(self) -> float:
        return sum(store.sale.actual for store in self.stores)

    @property
    def informed_sales(self) -> float:
        return sum(store.sale.actual for store in self.informed)

    @property
    def coverage(self) -> float:
        """La part des ventes du marché faite par des boutiques dont le bail est connu."""
        return self.informed_sales / self.sales if self.sales else 0.0

    @property
    def rent_share(self) -> Optional[float]:
        """Ce que le loyer prend sur le prochain euro, sur les boutiques au bail connu.

        Pondéré par leurs ventes et par rien d'autre ; None quand aucun bail n'est connu.
        Un marché à cinq boutiques connues sur cinquante rend le taux de ces cinq-là, et
        la couverture à côté dit qu'il ne parle que d'elles.
        """
        if not self.informed or not self.informed_sales:
            return None
        return sum(store.lease.var_rent * store.sale.actual
                   for store in self.informed) / self.informed_sales

    @property
    def rent_share_label(self) -> str:
        return "—" if self.rent_share is None else "%.1f %%" % (self.rent_share * 100)

    @property
    def coverage_label(self) -> str:
        return "%.0f %%" % (self.coverage * 100)

    @property
    def unmatched(self) -> List[str]:
        return [store.sale.code for store in self.stores if not store.lease]


class Review:
    """Le mois par marché, et ce qui manque pour le lire entier."""

    def __init__(self, markets: Sequence[Market], absent: Sequence[str], period: str = "",
                 register_faults: Sequence[str] = ()) -> None:
        self.markets = sorted(markets, key=lambda market: -market.sales)
        self.absent = list(absent)
        self.period = period
        self.register_faults = list(register_faults)

    @property
    def usable(self) -> bool:
        return bool(self.markets)

    @property
    def shown(self) -> List[Market]:
        return self.markets[:MOST]

    @property
    def rest(self) -> List[Market]:
        return self.markets[MOST:]

    @property
    def stores(self) -> int:
        return sum(market.count for market in self.markets)

    @property
    def joined(self) -> int:
        return sum(len(market.joined) for market in self.markets)

    @property
    def informed(self) -> int:
        return sum(len(market.informed) for market in self.markets)

    @property
    def sales(self) -> float:
        return sum(market.sales for market in self.markets)

    @property
    def coverage(self) -> float:
        informed = sum(market.informed_sales for market in self.markets)
        return informed / self.sales if self.sales else 0.0

    @property
    def coverage_label(self) -> str:
        return "%.0f %%" % (self.coverage * 100)

    @property
    def third_party(self) -> int:
        return sum(len(market.third_party) for market in self.markets)

    @property
    def doubtful(self) -> int:
        return sum(len(market.doubtful) for market in self.markets)

    @property
    def join_label(self) -> str:
        label = ("%d boutiques au fichier de la CFO · %d jointes au référentiel · %d au "
                 "bail connu" % (self.stores, self.joined, self.informed))
        if self.third_party:
            label += " · %d sans bail à notre nom" % self.third_party
        if self.doubtful:
            label += " · %d zéro%s douteux" % (self.doubtful, "s" if self.doubtful > 1 else "")
        return label

    marginal = MARGINAL_NOTE


def build(sales: Optional[Sales], register: Optional[Register]) -> Review:
    """Joindre par le code, regrouper par marché, ne rien compléter."""
    absent: List[str] = []
    if sales is None or not sales.usable:
        absent.append("Aucune vente par boutique lue : la feuille par magasin de l'extraction "
                      "de la CFO attend dans var/stores-sales.xlsx.")
        if sales is not None:
            absent.extend(sales.faults)
        return Review([], absent)
    if register is None or register.is_empty:
        absent.append("Aucun référentiel immobilier : var/stores.csv attend le code, le "
                      "bail et la part de loyer variable, boutique par boutique.")
    by_market: Dict[str, List[Joined]] = {}
    bulk = 0
    for sale in sales.stores:
        if sale.is_bulk:
            bulk += 1
            continue
        lease = register.of(sale.code) if register else None
        by_market.setdefault(sale.market, []).append(Joined(sale, lease))
    if bulk:
        absent.append("%d ligne%s de vrac écartée%s : un pseudo-magasin n'est pas une "
                      "boutique, et n'a pas de bail." % (bulk, "s" if bulk > 1 else "",
                                                          "s" if bulk > 1 else ""))
    markets = [Market(name, stores) for name, stores in by_market.items()]
    return Review(markets, absent, period="",
                  register_faults=register.faults if register else [])
