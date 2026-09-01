"""Les partenaires du digital non détenu, et la base sur laquelle chacun se lit.

Ce fichier existe parce qu'une idée simple s'est révélée fausse à 93 %. On a d'abord cru
pouvoir lire le nom d'un partenaire dans le code de son centre de profit : le motif tenait
sur quatre codes et sur quatre seulement, les cinquante-six autres suivaient deux autres
conventions ou aucune. Un affichage qui parse un code aurait donc nommé juste quatre fois
et faux le reste du temps, sans jamais le signaler.

Le nom n'était pas absent, il était à une jointure. L'entrepôt porte l'identité du client
et celle du magasin ; ce qu'il ne porte pas, c'est la **marque commerciale** sous laquelle
on veut afficher le flux — qu'une raison sociale japonaise soit une enseigne connue ne se
déduit d'aucune colonne. Cette correspondance est donc écrite à la main, ligne par ligne,
et arrive ici dans le fichier avec le reste.

Trois règles gouvernent ce lecteur, et les trois viennent de fautes rencontrées.

**Les deux bases ne s'additionnent jamais.** Le sell-in est ce que la Maison facture à un
partenaire, le sell-out ce qu'un client final achète. Un même nom vit des deux côtés — la
plateforme qui nous achète et la boutique qu'on exploite chez elle — et les additionner
mélange de l'expédié et du vendu sur une ligne. Ce module refuse structurellement : il n'y
a aucun total tous partenaires confondus, et `total()` exige sa base en argument.

**Un partenaire sans nom garde sa place et son montant.** Une poignée de lignes n'ont pas
de marque commerciale attribuable, et deux d'entre elles pèsent plus lourd que la moitié
des partenaires nommés réunis. Les cacher rendrait un total faux ; leur inventer un nom
rendrait un total juste et une conversation fausse. Elles s'affichent donc nommées « sans
nom », avec la raison, et `unnamed()` les rend.

**Le classement change de tête selon la base, et le titre doit le dire.** C'est la
conséquence directe de la première règle, et elle est visible dans les chiffres réels : le
premier partenaire de la Maison n'est pas le même selon qu'on regarde ce qu'elle expédie
ou ce qu'elle vend. Une vue « top partenaires » sans base affichée donne deux réponses
justes à une question mal posée.

Comme le plan, l'annuaire et les mesures de divergence, la source vit hors du dépôt.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional, Sequence

#: Les deux bases, écrites comme le fichier les écrit.
SELL_IN = "sell_in"
SELL_OUT = "sell_out"
BASES = (SELL_IN, SELL_OUT)

#: Ce que dit la colonne pays. La distinction n'est pas cosmétique : côté sell-in, la
#: dimension donne le pays d'immatriculation du client, et Amazon y est luxembourgeois.
#: Un écran qui traiterait cette colonne comme un marché rangerait des flux mondiaux sous
#: le pays d'une entité de facturation.
BILLING = "facturation"
MARKET = "marche"
COUNTRY_KINDS = (BILLING, MARKET)

#: Les colonnes sans lesquelles le fichier ne dit rien d'utilisable.
REQUIRED = ("base", "profit_centre", "partner", "revenue_12m")

#: Celles qu'on lit si elles sont là. Le brut et le net ne sont pas partout : une vue les
#: porte, l'autre non, et un marché a sa colonne brute vide en permanence.
OPTIONAL = ("customer_id", "legal_name", "country_field", "country_is", "months_seen",
            "gross_12m", "net_12m", "note")


class Line:
    """Un couple (base, centre de profit, client), tel que la source l'écrit."""

    __slots__ = ("base", "profit_centre", "customer_id", "partner", "legal_name",
                 "country_field", "country_is", "months_seen", "revenue", "gross",
                 "net", "note", "rate_withheld")

    def __init__(self, base, profit_centre, customer_id, partner, legal_name,
                 country_field, country_is, months_seen, revenue, gross, net,
                 note, rate_withheld: str = "") -> None:
        self.base = base
        self.profit_centre = profit_centre
        self.customer_id = customer_id
        #: La marque commerciale, ou vide. Vide est une information, jamais un défaut.
        self.partner = partner
        self.legal_name = legal_name
        self.country_field = country_field
        self.country_is = country_is
        self.months_seen = months_seen
        self.revenue = revenue
        self.gross = gross
        self.net = net
        self.note = note
        #: Pourquoi le taux n'est pas rendu, quand il ne l'est pas. Vide sinon.
        self.rate_withheld = rate_withheld

    @property
    def is_named(self) -> bool:
        return bool(self.partner)

    @property
    def label(self) -> str:
        """Ce qu'on affiche. Une raison sociale vaut mieux qu'un code, un code vaut mieux
        que rien, et aucun des deux ne prétend être une marque."""
        if self.partner:
            return self.partner
        return self.legal_name or self.profit_centre

    @property
    def deduction(self) -> Optional[float]:
        """La part du brut qui n'arrive pas jusqu'au net, en fraction.

        `None` quand le brut manque ou vaut zéro — et zéro arrive vraiment, sur un marché
        dont la colonne brute est vide en permanence. Rendre 100 % dans ce cas ferait d'une
        colonne absente le pire partenaire du portefeuille.

        Jamais comparable d'une base à l'autre : côté sell-in c'est ce qu'on consent à un
        acheteur sur un prix de cession, côté sell-out ce qui sépare un prix affiché d'un
        prix payé. Deux notions, un mot, et le rapprochement des deux serait un faux.
        """
        if self.rate_withheld or self.gross is None or self.net is None:
            return None
        if self.gross == 0:
            return None
        return (self.gross - self.net) / self.gross


class Partners:
    """Le fichier lu, ses défauts, et les seules agrégations qui aient un sens."""

    __slots__ = ("lines", "faults", "path")

    def __init__(self, lines, faults, path: str = "") -> None:
        self.lines = list(lines)
        self.faults = list(faults)
        self.path = path

    def __len__(self) -> int:
        return len(self.lines)

    @property
    def usable(self) -> bool:
        return bool(self.lines) and not self.faults

    def of_base(self, base: str) -> List["Line"]:
        return [line for line in self.lines if line.base == base]

    def total(self, base: str) -> float:
        """Le chiffre d'une base. L'argument n'a pas de défaut, et c'est délibéré : un
        total sans base nommée est le mélange que ce module existe pour empêcher."""
        if base not in BASES:
            raise ValueError("Base inconnue : %s. Les deux bases sont %s."
                             % (base, " et ".join(BASES)))
        return sum(line.revenue for line in self.of_base(base))

    def by_partner(self, base: str) -> List["Line"]:
        """Les lignes d'une base regroupées par marque, du plus gros au plus petit.

        Le regroupement se fait ici et pas dans la source parce qu'un même partenaire y
        occupe légitimement plusieurs lignes : plusieurs centres de profit, ou deux comptes
        clients du même groupe. Les lignes sans nom ne sont pas regroupées entre elles —
        elles n'ont rien en commun qu'une absence.
        """
        merged: Dict[str, Line] = {}
        loose: List[Line] = []
        for line in self.of_base(base):
            if not line.is_named:
                loose.append(line)
                continue
            held = merged.get(line.partner)
            if held is None:
                merged[line.partner] = Line(
                    base=line.base, profit_centre=line.profit_centre,
                    customer_id="", partner=line.partner, legal_name="",
                    country_field="", country_is=line.country_is,
                    months_seen=line.months_seen, revenue=line.revenue,
                    gross=line.gross, net=line.net, note="",
                    rate_withheld=line.rate_withheld)
                continue
            held.revenue += line.revenue
            held.gross = _add(held.gross, line.gross)
            held.net = _add(held.net, line.net)
            # Une ligne dont le taux est retenu contamine celui de son groupe. Sinon le
            # regroupement blanchirait le défaut : la somme resterait cohérente, le taux
            # sortirait plausible, et le seul endroit où l'anomalie était visible aurait
            # disparu dans l'agrégat.
            if line.rate_withheld and not held.rate_withheld:
                held.rate_withheld = line.rate_withheld
            if line.profit_centre not in held.profit_centre.split(" + "):
                held.profit_centre = "%s + %s" % (held.profit_centre, line.profit_centre)
            if line.months_seen is not None and (held.months_seen is None
                                                 or line.months_seen > held.months_seen):
                held.months_seen = line.months_seen
        rows = list(merged.values()) + loose
        rows.sort(key=lambda row: row.revenue, reverse=True)
        return rows

    def unnamed(self, base: Optional[str] = None) -> List["Line"]:
        """Les lignes sans marque commerciale, du plus gros montant au plus petit.

        Rendues, jamais cachées. Le plus gros de ces montants pèse plus que la moitié des
        partenaires nommés du fichier ; le retirer d'un écran donnerait un total faux et
        un classement crédible, ce qui est la pire combinaison.
        """
        rows = [line for line in self.lines
                if not line.is_named and (base is None or line.base == base)]
        rows.sort(key=lambda row: row.revenue, reverse=True)
        return rows

    def withheld(self) -> List["Line"]:
        """Les lignes dont le taux de déduction n'est pas rendu, et la raison.

        Rendues plutôt que tues : un taux manquant se remarque, un taux fabriqué non.
        """
        return [line for line in self.lines if line.rate_withheld
                and line.rate_withheld.startswith("net hors")]

    def unnamed_total(self, base: str) -> float:
        return sum(line.revenue for line in self.unnamed(base))

    def named_in_both_bases(self) -> List[str]:
        """Les marques présentes des deux côtés.

        Ce sont les seules pour lesquelles une addition serait tentante et fausse : la
        plateforme qui nous achète et la boutique qu'on exploite chez elle portent le même
        nom sans être le même métier.
        """
        first = {line.partner for line in self.of_base(SELL_IN) if line.is_named}
        second = {line.partner for line in self.of_base(SELL_OUT) if line.is_named}
        return sorted(first & second)


def rate_fault(gross: Optional[float], net: Optional[float]) -> str:
    """Pourquoi ce couple brut/net ne donne pas un taux, ou une chaîne vide.

    Un taux de déduction vit entre zéro et cent pour cent : le net se tient entre zéro et
    le brut. Écrit avec les deux signes plutôt qu'avec `net <= gross`, parce que la source
    porte de vraies lignes négatives — un avoir a un brut et un net négatifs, et son taux
    est parfaitement lisible. La première version de cette règle les a toutes déclarées
    fautives et a rendu le fichier entier inutilisable pour deux avoirs.

    Un net au-dessus de son brut n'est pas une remise négative : c'est un rapprochement de
    deux définitions, hors taxe d'un côté et toutes taxes de l'autre — le défaut que ce
    dépôt a déjà rencontré, et qui se signale mal parce que le taux qui en sort reste un
    nombre plausible.
    """
    if gross is None or net is None:
        return "brut ou net absent"
    if gross == 0:
        return "brut à zéro"
    if gross > 0 and not (0 <= net <= gross):
        return "net hors de l'intervalle [0, brut]"
    if gross < 0 and not (gross <= net <= 0):
        return "net hors de l'intervalle [brut, 0]"
    return ""


def _add(left: Optional[float], right: Optional[float]) -> Optional[float]:
    """Somme de deux valeurs dont l'une peut manquer.

    Une absence contamine la somme au lieu de compter pour zéro : additionner un brut connu
    et un brut absent donnerait un taux de déduction calculé sur un périmètre plus petit que
    son net, donc un taux flatteur et faux.
    """
    if left is None or right is None:
        return None
    return left + right


def _number(text: str) -> Optional[float]:
    value = (text or "").strip().replace(" ", "").replace(" ", "")
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def load(path: str) -> "Partners":
    """Lire la source, en refusant tout ce qui rendrait un total silencieusement faux.

    Comme pour les mesures de divergence, un défaut rend le fichier entier inutilisable
    plutôt que partiellement lu : un fichier à moitié lu produit un total crédible et court,
    ce qui est indétectable à l'œil et coûte une demi-journée à qui tente de le rapprocher.
    """
    if not os.path.exists(path):
        return Partners([], ["Fichier absent : %s" % path], path)

    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            return Partners([], ["Colonnes manquantes : %s" % ", ".join(missing)], path)
        raw = list(reader)

    lines: List[Line] = []
    faults: List[str] = []
    seen: Dict[str, int] = {}

    for number, record in enumerate(raw, start=2):
        base = (record.get("base") or "").strip()
        if not base:
            continue
        if base not in BASES:
            # Refusé plutôt qu'assimilé : une troisième base qu'on rangerait d'office dans
            # l'une des deux ferait entrer de l'expédié dans un total de vendu.
            faults.append("ligne %d : base « %s » inconnue — les deux bases sont %s"
                          % (number, base, " et ".join(BASES)))
            continue

        centre = (record.get("profit_centre") or "").strip()
        customer = (record.get("customer_id") or "").strip()
        identity = "%s|%s|%s" % (base, centre, customer)
        if identity in seen:
            faults.append(
                "ligne %d : %s figure déjà ligne %d — aucune des deux retenue"
                % (number, centre or "(sans centre)", seen[identity]))
            continue
        seen[identity] = number

        revenue = _number(record.get("revenue_12m", ""))
        if revenue is None:
            faults.append("ligne %d, %s : montant illisible" % (number, centre))
            continue

        country_is = (record.get("country_is") or "").strip()
        if country_is and country_is not in COUNTRY_KINDS:
            faults.append("ligne %d, %s : nature de pays « %s » inconnue"
                          % (number, centre, country_is))
            continue

        gross = _number(record.get("gross_12m", ""))
        net = _number(record.get("net_12m", ""))
        # Un couple brut/net incohérent retient le taux de cette ligne, il ne condamne pas
        # le fichier. Le montant, lui, reste bon et appartient au total : refuser tout
        # aurait privé le lecteur de deux cent soixante millions pour quatre cent mille,
        # ce qui est le mauvais côté de la prudence. Ce qui compte est que le taux ne
        # s'invente pas — et qu'on sache lequel manque et pourquoi.
        withheld = rate_fault(gross, net) if (gross is not None or net is not None) else ""

        months = _number(record.get("months_seen", ""))
        lines.append(Line(
            base=base,
            profit_centre=centre,
            customer_id=customer,
            partner=(record.get("partner") or "").strip(),
            legal_name=(record.get("legal_name") or "").strip(),
            country_field=(record.get("country_field") or "").strip(),
            country_is=country_is,
            months_seen=int(months) if months is not None else None,
            revenue=revenue,
            gross=gross,
            net=net,
            note=(record.get("note") or "").strip(),
            rate_withheld=withheld,
        ))

    if not lines and not faults:
        faults.append("aucune ligne dans %s" % path)
    return Partners(lines, faults, path)


def current(path: Optional[str] = None) -> "Partners":
    from ..config import settings

    return load(path or str(settings.partners_path))
