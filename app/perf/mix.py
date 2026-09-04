"""L'euro gagné est-il le bon euro — la première pièce de B5.

Deux questions se cachent sous « le mix », et les confondre inverse la réponse. La première :
le mois a-t-il vendu dans les canaux où le plan le voulait ? Elle se lit sur les ventes et le
plan seuls — un canal qui pèse trente pour cent du plan et vingt-cinq du réalisé a cédé cinq
points, quel que soit ce qu'il rapporte. La seconde : que valent ces points ? Elle demande un
taux par canal, et le seul qui soit connu est le taux **moyen** de contribution — ce qu'un
canal a rapporté sur ce qu'il a vendu.

Ce module rend la première question entière et la seconde comme un **calcul, coefficients
affichés** : l'écart de ventes de chaque canal, multiplié par son taux moyen, sommé — puis
séparé en ce qui vient du volume et ce qui vient du mix. Jamais un résultat, jamais un
EBITDA : un taux moyen appliqué à un écart ne mesure pas ce que la maison a gagné ou perdu,
il mesure ce que l'écart pèserait si chaque euro valait l'euro moyen de son canal. Et il ne
le vaut pas — c'est justement la seconde chose que ce module refuse de faire.

**Aucun classement « où pousser » ne se fait ici**, et les lignes sont rangées par poids au
plan, jamais par taux. Le taux moyen classe le wholesale devant le retail parce que la
remise consentie est un coût qui suit chaque euro, quand une boutique ouverte ne coûte
guère que le produit sur l'euro suivant. Le taux **marginal** — celui du prochain euro —
peut inverser l'ordre, et aucune source lue ici ne le porte. Il est déclaré absent, par son
nom, au lieu d'être remplacé par le taux moyen.

Le fichier est celui de la maison, dans `var/`, jamais versionné : un nom, un genre, un
taux, une date, une source. Un canal vendu que le fichier ne nomme pas est ABSENT — nommé
avec son poids, jamais pris à zéro ni à la moyenne des autres. Une ligne de partenaire y
est lue et gardée, mais ne sert pas au niveau canal : le cockpit ne connaît les ventes que
par canal, et un taux d'enseigne appliqué à un canal entier dirait plus qu'il ne sait.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional, Sequence, Tuple

from .mapping import CHANNEL_NAMES

#: Les deux genres de ligne que le fichier porte.
CHANNEL = "channel"
PARTNER = "partner"
KINDS = (CHANNEL, PARTNER)

REQUIRED = ("name", "kind")

#: Les noms sous lesquels un taux peut être écrit ; le premier trouvé est lu.
RATE_COLUMNS = ("average_rate", "contribution_rate", "rate")

#: Ce que l'écran dit du taux marginal à la place d'un chiffre. Écrit une fois, ici.
MARGINAL_ABSENT = (
    "Taux marginal : absent. Personnel, logistique et marketing demandent une part fixe et "
    "une part variable qu'aucune source lue ici ne porte. Le taux moyen ne le remplace pas."
)

#: Pourquoi aucune ligne ne dit où pousser. Écrit une fois, pour l'écran et le terminal.
NO_RANKING = (
    "Aucun canal n'est classé sur son taux moyen : ce taux dit ce qu'un canal a rapporté, "
    "pas ce que son prochain euro rapporterait — et la structure de coûts peut inverser "
    "l'ordre."
)

#: Sous cette couverture des ventes par des taux, le calcul est rendu mais dit sa part.
THIN_COVERAGE = 0.50

#: Ce qu'un nom du fichier désigne, en codes de canal du cockpit. Un nom peut couvrir
#: plusieurs canaux — « Distributors + Travel Retail » est un taux sur deux lignes du plan.
#: Explicite et éditable, jamais deviné par ressemblance : un nom que cette table ne
#: connaît pas est une ligne qui ne sert à rien, et l'écran le dit.
ALIASES: Dict[str, Tuple[str, ...]] = {
    "retail": ("retail",),
    "retail (own)": ("retail",),
    "own retail": ("retail",),
    "boutiques": ("retail",),
    "stores": ("retail",),
    "brand.com": ("ecommerce",),
    "e-commerce": ("ecommerce",),
    "ecommerce": ("ecommerce",),
    "e commerce": ("ecommerce",),
    "own site": ("ecommerce",),
    "marketplace": ("marketplace",),
    "marketplaces": ("marketplace",),
    "tmall": ("marketplace",),
    "e-retailers": ("webp",),
    "e-retailer": ("webp",),
    "web partners": ("webp",),
    "webp": ("webp",),
    "travel retail": ("tra",),
    "tra": ("tra",),
    "distributors": ("dis",),
    "distributor": ("dis",),
    "dis": ("dis",),
    "distributors + travel retail": ("dis", "tra"),
    "travel retail + distributors": ("tra", "dis"),
    "department stores": ("dpt",),
    "dpt": ("dpt",),
    "chain wholesale": ("whoch",),
    "whoch": ("whoch",),
    "independent wholesale": ("whoin",),
    "whoin": ("whoin",),
    "spa wholesale": ("whosp",),
    "whosp": ("whosp",),
    "tv channels": ("tvc",),
    "tvc": ("tvc",),
    "hospitality + b2b": ("b2b",),
    "b2b": ("b2b",),
    "corporate gifts": ("copg",),
    "copg": ("copg",),
    "direct selling": ("direct selling",),
    "dds": ("direct selling",),
    "spa": ("spa",),
    "cafe": ("cafe",),
    "café": ("cafe",),
}


def _norm(name: str) -> str:
    """« Distributors & Travel Retail » -> « distributors + travel retail »."""
    text = " ".join((name or "").strip().lower().split())
    for joiner in (" & ", " and ", " et ", " / ", "/"):
        text = text.replace(joiner, " + ")
    return " ".join(text.split())


def channels_of(name: str) -> Tuple[str, ...]:
    """Les codes de canal qu'un nom du fichier désigne ; vide quand il n'en désigne aucun."""
    key = _norm(name)
    if key in ALIASES:
        return ALIASES[key]
    for code, label in CHANNEL_NAMES.items():
        if _norm(label) == key:
            return (code,)
    return ()


def _number(raw: str) -> Optional[float]:
    text = (raw or "").strip().replace("%", "")
    if not text:
        return None
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return None
    # « 42 » pour quarante-deux pour cent : les deux écritures sont légitimes.
    return value / 100.0 if abs(value) > 1.0 else value


def _points(share: float) -> str:
    """« +4 », « -8 », « 0 » — jamais « -0 »."""
    points = int(round(share * 100))
    return "0" if points == 0 else "%+d" % points


def _share(value: float) -> str:
    return "%.0f %%" % (value * 100)


class Rate:
    """Une ligne du fichier : un nom, un genre, un taux, et ce qu'elle couvre."""

    __slots__ = ("name", "kind", "rate", "as_of", "source", "channels", "line")

    def __init__(self, name: str, kind: str, rate: float, as_of: str = "",
                 source: str = "", channels: Tuple[str, ...] = (), line: int = 0) -> None:
        self.name = name
        self.kind = kind
        self.rate = rate
        self.as_of = as_of
        self.source = source
        self.channels = tuple(channels)
        self.line = line

    @property
    def is_channel(self) -> bool:
        return self.kind == CHANNEL

    @property
    def label(self) -> str:
        return _share(self.rate)


class Contribution:
    """Le fichier lu : les taux par canal, les lignes de partenaire, et les défauts."""

    def __init__(self, rates: Sequence[Rate], faults: Sequence[str], path: str = "") -> None:
        self.rates = list(rates)
        self.faults = list(faults)
        self.path = path
        self.by_channel: Dict[str, Rate] = {}
        for rate in self.rates:
            if not rate.is_channel:
                continue
            for code in rate.channels:
                if code in self.by_channel:
                    # Deux taux pour un même canal : le premier tient, le second est nommé.
                    self.faults.append(
                        "ligne %d : « %s » couvre %s, déjà porté par « %s »"
                        % (rate.line, rate.name, CHANNEL_NAMES.get(code, code),
                           self.by_channel[code].name))
                    continue
                self.by_channel[code] = rate

    @property
    def is_empty(self) -> bool:
        return not self.rates

    @property
    def partners(self) -> List[Rate]:
        return [rate for rate in self.rates if rate.kind == PARTNER]

    @property
    def unmapped(self) -> List[Rate]:
        """Les lignes canal dont le nom ne désigne aucun canal du cockpit."""
        return [rate for rate in self.rates if rate.is_channel and not rate.channels]

    def of(self, channel: str) -> Optional[Rate]:
        return self.by_channel.get(channel)

    @property
    def as_of(self) -> str:
        return max((rate.as_of for rate in self.rates if rate.as_of), default="")

    @property
    def sources(self) -> List[str]:
        seen: List[str] = []
        for rate in self.rates:
            if rate.source and rate.source not in seen:
                seen.append(rate.source)
        return seen


def load(path: str) -> Contribution:
    """Lire le fichier. Absent : une lecture vide, pas une erreur."""
    if not path or not os.path.exists(path):
        return Contribution([], [], path)
    rates: List[Rate] = []
    faults: List[str] = []
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        missing = [name for name in REQUIRED if name not in header]
        rate_column = next((name for name in RATE_COLUMNS if name in header), "")
        if not rate_column:
            missing.append("average_rate")
        if missing:
            return Contribution([], ["colonnes manquantes : %s" % ", ".join(missing)], path)
        for number, record in enumerate(reader, start=2):
            name = (record.get("name") or "").strip()
            kind = (record.get("kind") or "").strip().lower()
            if not name:
                faults.append("ligne %d : nom absent" % number)
                continue
            if kind not in KINDS:
                faults.append("ligne %d : genre « %s » inconnu (channel ou partner)"
                              % (number, kind))
                continue
            rate = _number(record.get(rate_column) or "")
            if rate is None:
                faults.append("ligne %d : taux illisible pour « %s »" % (number, name))
                continue
            channels = channels_of(name) if kind == CHANNEL else ()
            if kind == CHANNEL and not channels:
                faults.append("ligne %d : « %s » ne désigne aucun canal du cockpit"
                              % (number, name))
            rates.append(Rate(name, kind, rate, (record.get("as_of") or "").strip(),
                              (record.get("source") or "").strip(), channels, number))
    return Contribution(rates, faults, path)


def current(path: Optional[str] = None) -> Contribution:
    from ..config import settings

    return load(path or str(settings.contribution_path))


# ------------------------------------------------------------------------- le mois


class Slice:
    """Un canal du mois : sa part au plan, sa part réalisée, et le coefficient qui le pèse."""

    __slots__ = ("channel", "actual", "budget", "rate", "total_actual", "total_budget")

    def __init__(self, channel: str, actual: float, budget: float, rate: Optional[Rate],
                 total_actual: float, total_budget: float) -> None:
        self.channel = channel
        self.actual = actual
        self.budget = budget
        self.rate = rate
        self.total_actual = total_actual
        self.total_budget = total_budget

    @property
    def label(self) -> str:
        return CHANNEL_NAMES.get(self.channel, self.channel.title())

    @property
    def plan_share(self) -> float:
        return self.budget / self.total_budget if self.total_budget else 0.0

    @property
    def actual_share(self) -> float:
        return self.actual / self.total_actual if self.total_actual else 0.0

    @property
    def mix_gap(self) -> float:
        """Points de mix gagnés ou cédés contre le plan. Positif : plus lourd que prévu."""
        return self.actual_share - self.plan_share

    @property
    def sales_gap(self) -> float:
        return self.actual - self.budget

    @property
    def covered(self) -> bool:
        return self.rate is not None

    @property
    def weighted(self) -> Optional[float]:
        """L'écart de ventes au taux moyen du canal — un terme du calcul, pas un résultat."""
        if self.rate is None:
            return None
        return self.rate.rate * self.sales_gap

    # Ce que l'écran écrit.
    @property
    def plan_share_label(self) -> str:
        return _share(self.plan_share)

    @property
    def actual_share_label(self) -> str:
        return _share(self.actual_share)

    @property
    def mix_gap_label(self) -> str:
        return _points(self.mix_gap)

    @property
    def rate_label(self) -> str:
        return self.rate.label if self.rate else "absent"


class Review:
    """Le mois vu par son mix : les canaux, les deux effets, et ce qui manque."""

    def __init__(self, period: str, slices: Sequence[Slice], absent: Sequence[str],
                 contribution: Optional[Contribution] = None) -> None:
        self.period = period
        self.slices = list(slices)
        self.absent = list(absent)
        self.contribution = contribution

    @property
    def usable(self) -> bool:
        return bool(self.slices) and self.total_budget > 0

    @property
    def total_actual(self) -> float:
        return sum(piece.actual for piece in self.slices)

    @property
    def total_budget(self) -> float:
        return sum(piece.budget for piece in self.slices)

    @property
    def sales_gap(self) -> float:
        return self.total_actual - self.total_budget

    @property
    def covered(self) -> List[Slice]:
        return [piece for piece in self.slices if piece.covered]

    @property
    def uncovered(self) -> List[Slice]:
        return [piece for piece in self.slices if not piece.covered]

    @property
    def weighs(self) -> bool:
        """Si au moins un canal porte un taux, le calcul repondéré se rend."""
        return bool(self.covered)

    @property
    def coverage(self) -> float:
        """La part des ventes du mois que les taux couvrent."""
        if not self.total_actual:
            return 0.0
        return sum(piece.actual for piece in self.covered) / self.total_actual

    @property
    def thin(self) -> bool:
        return self.weighs and self.coverage < THIN_COVERAGE

    @property
    def plan_rate(self) -> float:
        """Le taux moyen du plan sur les canaux couverts : Σ taux × part au plan."""
        return sum(piece.rate.rate * piece.plan_share for piece in self.covered)

    @property
    def weighted(self) -> float:
        """Σ taux × écart de ventes, sur les canaux couverts."""
        return sum(piece.weighted for piece in self.covered)

    @property
    def volume_effect(self) -> float:
        """Ce que l'écart total de ventes pèserait au taux moyen du plan."""
        return self.sales_gap * self.plan_rate

    @property
    def mix_effect(self) -> float:
        """Ce que les points de mix pèsent, aux ventes réalisées : ventes × Σ taux × écart de mix.

        Les deux effets somment exactement au repondéré — c'est une identité, pas une
        approximation, et le test la garde.
        """
        return self.total_actual * sum(piece.rate.rate * piece.mix_gap
                                       for piece in self.covered)

    @property
    def mix_points(self) -> float:
        """La somme des points de mix cédés — ce qui a bougé, hors de tout taux."""
        return sum(abs(piece.mix_gap) for piece in self.slices) / 2

    @property
    def coverage_label(self) -> str:
        return _share(self.coverage)

    @property
    def plan_rate_label(self) -> str:
        return _share(self.plan_rate)

    #: Les deux phrases que l'écran répète à chaque rendu, tenues ici pour n'exister
    #: qu'une fois.
    marginal = MARGINAL_ABSENT
    no_ranking = NO_RANKING

    @property
    def uncovered_note(self) -> str:
        """Les canaux vendus sans taux, chacun avec son poids. Vide quand tout est couvert."""
        if not self.uncovered or not self.weighs:
            return ""
        parts = ["%s (%s des ventes)" % (piece.label, piece.actual_share_label)
                 for piece in self.uncovered]
        return "Sans taux, donc hors du calcul : %s." % ", ".join(parts)

    @property
    def partners_note(self) -> str:
        if not self.contribution or not self.contribution.partners:
            return ""
        names = ", ".join(rate.name for rate in self.contribution.partners)
        return ("Lu mais non appliqué : %s. Un taux d'enseigne ne se pose pas sur un canal "
                "entier, et le cockpit ne connaît les ventes que par canal." % names)


def build(dataset, contribution: Optional[Contribution]) -> Review:
    """Le mois par canal, contre son plan, aux taux moyens quand il y en a.

    Sur les unités comparables — celles où les deux termes existent — et jamais sur les
    agrégats, qui recouvrent des lignes déjà comptées. Sans fichier, le mix contre le plan
    se lit quand même : il n'a besoin d'aucun taux. Seule la repondération l'attend.
    """
    absent: List[str] = []
    actual: Dict[str, float] = {}
    budget: Dict[str, float] = {}
    for unit in dataset.comparable:
        if unit.is_aggregate:
            continue
        actual[unit.channel] = actual.get(unit.channel, 0.0) + unit.sales_actual
        budget[unit.channel] = budget.get(unit.channel, 0.0) + unit.sales_budget
    total_actual = sum(actual.values())
    total_budget = sum(budget.values())
    if contribution is None:
        absent.append("Aucun fichier de contribution : le mix se lit, la repondération "
                      "attend un taux moyen par canal dans var/contribution.csv.")
    elif contribution.is_empty and not contribution.faults:
        absent.append("Le fichier de contribution est vide.")
    if contribution is not None:
        for fault in contribution.faults:
            absent.append("fichier de contribution, %s" % fault)
    slices = [Slice(channel, actual[channel], budget[channel],
                    contribution.of(channel) if contribution else None,
                    total_actual, total_budget)
              for channel in actual]
    # Par poids au plan, jamais par taux : l'ordre est déjà une opinion, et celle-là
    # dirait où pousser.
    slices.sort(key=lambda piece: (-piece.budget, piece.label))
    if not slices:
        absent.append("Aucune unité comparable : le mix demande un réalisé et un plan sur "
                      "les mêmes canaux.")
    return Review(getattr(dataset, "period_label", ""), slices, absent, contribution)
