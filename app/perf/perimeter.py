"""Les sept périmètres de responsabilité, et qui répond au téléphone.

Ce module existe parce que l'écran s'est trompé d'organigramme. Il proposait comme
interlocutrice directe du CEO une General Manager pays, et rangeait les responsables sous
des zones — « North Europe », « North America » — qui ne sont aucun des périmètres qu'il
pilote. L'annuaire avait reçu la carte des marchés au lieu de la ligne hiérarchique.

Ce n'est pas un défaut d'affichage. Un cockpit qui installe son lecteur au-dessus de ses
propres MD abîme une ligne que la maison tient, et il le fait à chaque lecture,
poliment, sans que rien ne signale l'erreur.

Deux règles gouvernent tout ce fichier.

**Le rôle décide, jamais le titre.** Le MD du Japon porte le titre de *General
Manager* et rend compte directement au CEO ; un *Managing Director UK & Ireland* rend
compte à un MD. Filtrer sur l'intitulé du poste aurait promu la seconde et
rétrogradé le premier — la faute exacte que ce module doit rendre impossible. La colonne
qui fait foi est celle du type, et le lien de rattachement la confirme.

**Un marché non placé se déclare.** La source nomme des zones — « Europe du Sud »,
« Nordics », « SEA & Inde » — quand l'écran nomme des pays. Le rapprochement est donc
partiel par nature, et ce module rend la liste de ce qu'il n'a pas su placer plutôt que de
rattacher un marché au périmètre le plus ressemblant. Un marché rattaché par ressemblance
enverrait une conversation à la mauvaise personne, ce qui coûte plus cher qu'un blanc.

Comme le plan et l'annuaire, la source est un classeur local que git ignore : elle porte
des noms, des adresses et une ligne hiérarchique.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .budget import normalise_market
from .xlsx import Workbook

#: Ce que la source appelle un rattachement. Le premier est celui qui répond au CEO.
#:
#: La maison dit « MD » — parfois « regional leader » — et ne dit plus « BU ». Ce module
#: employait l'ancien mot parce que la source l'employait, et un cockpit qui parle une
#: langue que la maison a quittée fait douter de tout le reste : le lecteur se demande de
#: quand datent les chiffres avant de se demander s'ils sont justes.
MD = "MD"
COUNTRY_GM = "GM pays"
TRAVEL_GM = "GM Travel Retail"

#: Les colonnes de la source, dans l'ordre où elle les écrit.
PERIMETER_AT, FIRST_AT, LAST_AT, ROLE_AT, ZONE_AT, KIND_AT, MANAGER_AT = 0, 1, 2, 3, 4, 5, 6

#: Un rattachement que la source ne renseigne pas. Elle le marque par un tiret plutôt que
#: par un nom ; un tiret n'est pas un nom, et ce lecteur le rend comme une absence.
NO_MANAGER = ("—", "-", "")


class Person:
    """Une personne, son rôle réel, et à qui elle rend compte."""

    __slots__ = ("first", "last", "role", "perimeter", "zone", "kind", "manager")

    def __init__(self, first, last, role, perimeter, zone, kind, manager) -> None:
        self.first = first
        self.last = last
        #: L'intitulé du poste, affichable et jamais interprété.
        self.role = role
        self.perimeter = perimeter
        self.zone = zone
        #: Le rattachement réel. C'est lui qui décide, pas `role`.
        self.kind = kind
        self.manager = manager

    @property
    def name(self) -> str:
        return ("%s %s" % (self.first, self.last)).strip()

    @property
    def answers_to_ceo(self) -> bool:
        """Le seul test qui autorise à proposer cette personne comme interlocutrice.

        Il porte sur le type et non sur l'intitulé : un MD peut être titré *General
        Manager*, et un *Managing Director* peut être un responsable pays.

        Le travel retail a longtemps répondu vrai ici pour ses responsables régionaux,
        parce que la source ne nommait personne au-dessus d'eux et que le périmètre
        serait resté sans interlocuteur. Elle en nomme une maintenant, et les deux
        régionaux lui rendent compte comme un GM pays rend compte à son MD. Continuer à
        les proposer au CEO court-circuiterait une ligne que la maison tient — la faute
        exacte que ce module existe pour rendre impossible, dans l'autre sens.
        """
        return self.kind == MD


class Org:
    """L'organisation telle que la source la décrit, et ce qu'elle ne dit pas."""

    __slots__ = ("people", "faults", "path")

    def __init__(self, people, faults, path: str = "") -> None:
        self.people = list(people)
        self.faults = list(faults)
        self.path = path

    @property
    def usable(self) -> bool:
        return bool(self.people) and not self.faults

    def perimeters(self) -> List[str]:
        return sorted({p.perimeter for p in self.people if p.perimeter})

    def leads(self) -> Dict[str, "Person"]:
        """Périmètre → la personne qui répond au CEO pour lui.

        Un périmètre sans MD identifié est absent de ce dictionnaire plutôt que
        rempli par son responsable pays le plus proche : c'est précisément la substitution
        que ce module existe pour empêcher.
        """
        found: Dict[str, Person] = {}
        for person in self.people:
            if person.kind == MD and person.perimeter not in found:
                found[person.perimeter] = person
        return found

    def team_of(self, perimeter: str) -> List["Person"]:
        """Les responsables pays d'un périmètre — affichables en détail, jamais comme
        destinataires d'une conversation du CEO."""
        return [p for p in self.people
                if p.perimeter == perimeter and p.kind != MD]

    def lead_for(self, perimeter: str) -> Optional["Person"]:
        return self.leads().get(perimeter)

    def without_lead(self) -> List[str]:
        """Les périmètres que la source décrit sans nommer leur MD."""
        leads = self.leads()
        return [name for name in self.perimeters() if name not in leads]


def load(path: str) -> "Org":
    """Lire la source, en tenant le rôle pour vrai et l'intitulé pour un libellé."""
    # La feuille est prise telle qu'elle vient plutôt que nommée : cette source est un
    # export d'annuaire à une seule feuille, et exiger un nom exact ferait échouer la
    # lecture le jour où quelqu'un renomme l'onglet — pour rien.
    try:
        with Workbook(path) as workbook:
            names = workbook.sheet_names
            first = names[0] if names else ""
            rows = list(workbook.rows(first))
    except Exception as exc:  # noqa: BLE001 — le message vaut mieux que le type
        return Org([], ["%s" % exc], path)

    people: List[Person] = []
    faults: List[str] = []
    unknown = set()

    for row in rows:
        if len(row) <= MANAGER_AT:
            continue
        kind = str(row[KIND_AT] or "").strip()
        if not kind or kind.lower() == "type":
            continue
        if kind not in (MD, COUNTRY_GM, TRAVEL_GM):
            unknown.add(kind)
            continue
        manager = str(row[MANAGER_AT] or "").strip()
        people.append(Person(
            first=str(row[FIRST_AT] or "").strip(),
            last=str(row[LAST_AT] or "").strip(),
            role=str(row[ROLE_AT] or "").strip(),
            perimeter=str(row[PERIMETER_AT] or "").strip(),
            zone=str(row[ZONE_AT] or "").strip(),
            kind=kind,
            manager="" if manager in NO_MANAGER else manager,
        ))

    if unknown:
        # Refusé plutôt qu'assimilé : un rattachement que ce lecteur ne connaît pas est
        # peut-être un troisième niveau, et le ranger d'office parmi les MD
        # mettrait quelqu'un devant le CEO sans que personne l'ait décidé.
        faults.append("rattachements inconnus, lignes ignorées : %s"
                      % ", ".join(sorted(unknown)))
    if not people:
        faults.append("aucune personne lue dans %s" % path)
    return Org(people, faults, path)


#: Le pont entre deux vocabulaires. L'annuaire est tenu en français — « Japon », « Brésil »
#: — et l'écran nomme ses marchés comme le plan les nomme, en anglais. Le rapprochement
#: échouait donc partout sauf sur les pays qui s'écrivent pareil, silencieusement : la
#: fonction rendait ce qu'elle pouvait et personne ne comptait ce qui manquait.
#:
#: Écrit comme une correspondance et non comme une traduction. Chaque zone propose
#: plusieurs candidats, et seul celui qui figure réellement dans la liste des marchés est
#: retenu — la Corée s'écrit « Korea » sur certains plans et « South Korea » sur d'autres,
#: et deviner laquelle rattacherait la moitié d'un continent au mauvais MD.
SPELLINGS: Dict[str, Tuple[str, ...]] = {
    "japon": ("Japan",),
    "bresil": ("Brazil",),
    "chine": ("China",),
    "hong kong": ("Hong Kong", "HK Local"),
    "allemagne": ("Germany",),
    "coree": ("Korea", "South Korea"),
    "australie": ("Australia",),
    "nouvelle-zelande": ("New Zealand",),
    "inde": ("India",),
    "mexique": ("Mexico",),
    "usa": ("United States", "USA", "US"),
    "etats-unis": ("United States", "USA", "US"),
    "uk": ("United Kingdom", "UK"),
    "royaume-uni": ("United Kingdom", "UK"),
    "irlande": ("Ireland",),
    "espagne": ("Spain",),
    "italie": ("Italy",),
    "suisse": ("Switzerland",),
    "belgique": ("Belgium",),
    "pays-bas": ("Netherlands",),
    "autriche": ("Austria",),
    "pologne": ("Poland",),
    "tchequie": ("Czechia", "Czech Republic"),
    "suede": ("Sweden",),
    "norvege": ("Norway",),
    "danemark": ("Denmark",),
    "finlande": ("Finland",),
    "thailande": ("Thailand",),
    "malaisie": ("Malaysia",),
    "singapour": ("Singapore",),
    "indonesie": ("Indonesia",),
    "turquie": ("Turkey",),
    # Le travel retail n'est pas un pays, mais c'est un périmètre piloté : il porte
    # une responsable, un budget et des sujets. Sans cette entrée, un fait qui le
    # concerne s'écrit sous le libellé exact de l'annuaire, parenthèse comprise, ou
    # ne se rattache à personne.
    "travel retail (monde)": ("Travel Retail",),
}

#: Ce qui sépare deux pays dans une même cellule. La source écrit « Chine + Hong Kong » et
#: « UK & Irlande » — deux conventions pour une seule idée, et n'en lire qu'une laissait la
#: moitié d'un périmètre sans interlocuteur.
SEPARATORS = ("+", "&", ",", "/")


def _folded(text: str) -> str:
    """Le libellé réduit à ce qui se compare : sans accents, sans casse, sans espaces
    doubles. Les accents seuls faisaient échouer « Brésil » contre « bresil »."""
    import unicodedata

    stripped = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return "".join(ch for ch in stripped if not unicodedata.combining(ch))


def spellings_of(zone: str) -> Tuple[str, ...]:
    """Les noms sous lesquels ce morceau de zone peut apparaître sur l'écran.

    Le libellé tel quel vient d'abord : une source qui nomme déjà ses pays comme l'écran
    n'a besoin d'aucun pont, et ce cas doit continuer de marcher le jour où la table
    ci-dessus est vidée.
    """
    raw = (zone or "").strip()
    if not raw:
        return ()
    candidates = [normalise_market(raw), raw]
    candidates.extend(SPELLINGS.get(_folded(raw), ()))
    seen: List[str] = []
    for name in candidates:
        if name and name not in seen:
            seen.append(name)
    return tuple(seen)


def _parts(zone: str) -> List[str]:
    parts = [zone or ""]
    for separator in SEPARATORS:
        parts = [piece for part in parts for piece in part.split(separator)]
    return [part.strip() for part in parts if part.strip()]


def place(org: "Org", markets: Sequence[str]) -> Dict[str, str]:
    """Marché → périmètre, pour les marchés que la source place sans ambiguïté.

    Le rapprochement teste plusieurs orthographes et ne retient que celle qui figure
    réellement dans la liste des marchés fournie. C'est ce qui distingue une correspondance
    d'une traduction : rien n'est placé sous un nom que l'écran n'emploie pas.

    Une zone qui n'est pas un pays — « Europe du Sud », « Nordics » — ne place rien : elle
    couvre plusieurs marchés et la source ne dit pas lesquels. Ce qui n'est pas placé n'est
    pas deviné. Voir `unplaced`.
    """
    known = set(markets)
    found: Dict[str, str] = {}
    for person in org.people:
        for part in _parts(str(person.zone or "")):
            for candidate in spellings_of(part):
                if candidate in known and candidate not in found:
                    found[candidate] = person.perimeter
                    break
    return {market: found[market] for market in markets if market in found}


def unplaced(org: "Org", markets: Sequence[str]) -> List[str]:
    """Les marchés de l'écran qu'aucune ligne de la source ne rattache.

    Rendus comme une liste et non comblés : rattacher un marché au périmètre qui lui
    ressemble le plus enverrait une conversation à quelqu'un qui n'en est pas responsable.
    """
    placed = place(org, markets)
    return [market for market in markets if market not in placed]


def current() -> "Org":
    from ..config import settings

    return load(str(settings.org_path))
