"""Le calendrier des dates mobiles, et le rapprochement avec la forme des mois.

Le module précédent (`pace`) mesure **qu'**un mois bouge, sans jamais dire pourquoi : c'est
sa force, il n'a besoin d'aucun calendrier pour désigner les marchés et les mois traversés
par quelque chose. Celui-ci fait l'étape d'après et prend le risque inverse — il nomme des
causes possibles — donc il doit se tenir à une discipline stricte, sans quoi il produira des
explications plausibles, ce qui est exactement ce dont personne n'a besoin.

**Une explication ne vaut que si elle pouvait être fausse.** Le test est le suivant. Un
événement occupe, chaque exercice, un bloc de sept jours du mois. La mobilité d'un mois est
mesurée à une semaine précise : celle où les cumuls s'écartent le plus. Si l'événement
explique cet écart, alors les exercices où il tombe **avant** cette semaine ont fait plus de
chiffre à cette semaine-là que les exercices où il tombe après — tous, sans exception. Il
suffit d'un exercice à contre-sens pour que l'explication tombe.

Trois refus valent mieux qu'une réponse molle, et le module les prononce :

**Un événement dont le bloc ne bouge pas ne peut rien expliquer.** C'est la remarque de
l'analyste sur Pâques en Europe centrale, tenue ici par le code plutôt que par l'œil. Une
date fixe qui coïncide avec un mois instable est une coïncidence, pas une cause.

**Un événement qui bouge sans jamais traverser la semaine mesurée ne peut rien expliquer
non plus.** Il se déplace de la première à la deuxième semaine alors que l'écart se joue à
la quatrième : les deux faits sont vrais et sans rapport.

**Une date qui ne varie jamais dans un fichier de dates mobiles est probablement une
convention, pas une observation.** Une fin de soldes écrite au 31 janvier huit années de
suite décrit le choix de celui qui a rempli la colonne. Le module la signale au lieu de la
consommer : un remplissage en forme de valeur n'est pas une valeur.

Une dernière chose que ce module ne fait pas, exprès. Il ne conclut pas. Il rend, pour
chaque couple qui bouge, la liste des candidats et ce que chacun devient à l'épreuve — dont,
très souvent, « aucun ». Un mois sans explication reste un mois qui bouge, et c'est une
information ; lui coller le premier événement du calendrier n'en serait pas une.
"""

from __future__ import annotations

import calendar as calendar_module
import csv
import datetime
import io
import os
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

#: La règle qui transforme un jour en bloc. Elle doit être **la même** que celle qui a
#: produit le fichier des formes de mois, sans quoi le rapprochement compare deux
#: découpages différents et rend un résultat parfaitement lisible et faux. Elle est écrite
#: ici pour être citée à l'écran, pas seulement appliquée.
BLOC_RULE = "bloc = arrondi supérieur du jour divisé par sept ; blocs 1 à 4 de sept jours, bloc 5 de zéro à trois"

#: Les colonnes minimales. Deux écritures de l'intitulé sont admises parce que deux
#: fichiers existent déjà et qu'aucun des deux n'a tort.
NAME_COLUMNS = ("event_name", "event")
REQUIRED = ("country", "family", "year", "start_date")

#: Avant le mois, et après lui. Un événement qui a quitté le mois n'est pas « en première
#: semaine » du mois suivant : il est passé, ou il n'est pas encore là, et c'est cela qui
#: ordonne les exercices. Confondre les deux ferait de la fête de la mi-automne d'octobre
#: un événement précoce de septembre, c'est-à-dire l'inverse exact de ce qu'elle est.
BEFORE = 0
AFTER = 6

AGREES = "accordé"
CONTRADICTS = "contredit"
IMMOBILE = "immobile"
OUTSIDE = "hors semaine"
THIN = "trop peu d'exercices"


def normal(text: str) -> str:
    """Un nom de pays réduit à ce qui se compare : sans accent, sans casse, sans espaces."""
    stripped = unicodedata.normalize("NFD", (text or "").strip().lower())
    return "".join(letter for letter in stripped
                   if unicodedata.category(letter) != "Mn").replace("-", " ").strip()


def bloc(iso: str) -> Optional[int]:
    """Le bloc de sept jours où tombe une date. `None` quand la date est absente."""
    text = (iso or "").strip()
    if len(text) < 10:
        return None
    try:
        day = int(text[8:10])
    except ValueError:
        return None
    if day < 1 or day > 31:
        return None
    return (day + 6) // 7


def month_of(iso: str) -> str:
    text = (iso or "").strip()
    return text[5:7] if len(text) >= 7 else ""


class Event:
    """Une occurrence : un événement, un pays, un exercice."""

    __slots__ = ("country", "name", "family", "year", "start", "end", "weekday",
                 "status", "source", "rule", "region", "event_id")

    def __init__(self, country: str, name: str, family: str, year: str, start: str,
                 end: str = "", weekday: str = "", status: str = "", source: str = "",
                 rule: str = "", region: str = "", event_id: str = "") -> None:
        self.country = country
        self.name = name
        self.family = family
        self.year = year
        self.start = start
        self.end = end
        self.weekday = weekday
        #: Ce que la source dit d'elle-même : observée, calculée, prévue, à annoncer.
        self.status = status
        self.source = source
        self.rule = rule
        self.region = region
        self.event_id = event_id or "%s·%s" % (normal(country), normal(name))

    @property
    def dated(self) -> bool:
        return bloc(self.start) is not None

    @property
    def bloc(self) -> Optional[int]:
        return bloc(self.start)

    @property
    def month(self) -> str:
        return month_of(self.start)


class Series:
    """Un événement suivi d'un exercice à l'autre. C'est ici que « mobile » se vérifie."""

    __slots__ = ("event_id", "country", "name", "family", "by_year")

    def __init__(self, event_id: str, country: str, name: str, family: str,
                 by_year: Optional[Dict[str, "Event"]] = None) -> None:
        self.event_id = event_id
        self.country = country
        self.name = name
        self.family = family
        self.by_year: Dict[str, "Event"] = dict(by_year or {})

    @property
    def dated(self) -> Dict[str, "Event"]:
        return {year: event for year, event in self.by_year.items() if event.dated}

    @property
    def absent(self) -> List[str]:
        """Les exercices sans date. Nommés, jamais comblés : le fichier dit lui-même
        « à annoncer », et une date inventée serait la seule chose pire qu'un trou."""
        return sorted(year for year, event in self.by_year.items() if not event.dated)

    def places(self, years: Sequence[str], month: str,
               lead: int = 0) -> Dict[str, int]:
        """Où tombe l'événement dans ce mois, exercice par exercice.

        `lead` recule la date d'autant de jours. Beaucoup d'événements ne se vendent pas le
        jour où ils tombent — une fête se prépare, et la mi-automne fait son chiffre dans
        les deux semaines qui la précèdent. Faire cette hypothèse est légitime ; la faire en
        silence ne l'est pas. Le décalage est donc un paramètre déclaré, que le lecteur voit
        et peut faire varier, plutôt qu'une correction cachée dans le calcul.
        """
        found: Dict[str, int] = {}
        for year in years:
            event = self.by_year.get(year)
            if event is None or not event.dated:
                continue
            place = _place(event.start, year, month, lead)
            if place is not None:
                found[year] = place
        return found

    @property
    def conventional_end(self) -> bool:
        """Une fin qui ne bouge jamais pendant que le début bouge est une convention.

        Le cas est réel et il est piégeux : une fenêtre de soldes écrite « jusqu'au 31
        janvier » huit années de suite ne décrit pas la fin des soldes, elle décrit le choix
        de celui qui a rempli la colonne. Consommée telle quelle, elle ferait conclure à une
        stabilité qui n'a jamais été observée.
        """
        ends = {event.end[5:] for event in self.dated.values() if event.end}
        starts = {event.start[5:] for event in self.dated.values()}
        return len(ends) == 1 and len(starts) > 1


class Verdict:
    """Ce qu'un candidat devient à l'épreuve d'un mois qui bouge."""

    __slots__ = ("series", "label", "why", "inside", "outside")

    def __init__(self, series: "Series", label: str, why: str,
                 inside: Sequence[str] = (), outside: Sequence[str] = ()) -> None:
        self.series = series
        self.label = label
        self.why = why
        #: Les exercices où l'événement tombe dans les semaines déjà écoulées.
        self.inside = list(inside)
        self.outside = list(outside)

    @property
    def holds(self) -> bool:
        return self.label == AGREES


class Calendar:
    """Les séries lues, et ce que le fichier a de faux."""

    __slots__ = ("series", "faults", "path")

    def __init__(self, series: Dict[str, "Series"], faults: Sequence[str],
                 path: str = "") -> None:
        self.series = dict(series)
        self.faults = list(faults)
        self.path = path

    def __len__(self) -> int:
        return len(self.series)

    @property
    def usable(self) -> bool:
        return bool(self.series)

    @property
    def countries(self) -> List[str]:
        return sorted({item.country for item in self.series.values()})

    def of_country(self, country: str) -> List["Series"]:
        wanted = normal(country)
        return [item for item in self.series.values() if normal(item.country) == wanted]

    def in_month(self, country: str, month: str) -> List["Series"]:
        """Les séries dont au moins une occurrence datée tombe dans ce mois.

        Le filtre est volontairement large — une seule occurrence suffit. Un événement qui
        entre et sort du mois selon l'exercice est précisément le suspect qu'on cherche ;
        exiger qu'il y soit toutes les années le ferait disparaître au moment où il devient
        intéressant.
        """
        month = (month or "").strip()[-2:]
        found = []
        for item in self.of_country(country):
            if any(event.month == month for event in item.dated.values()):
                found.append(item)
        return sorted(found, key=lambda item: item.name)


def _place(start: str, year: str, month: str, lead: int = 0) -> Optional[int]:
    """Le rang de l'événement par rapport à ce mois-là : avant, dans un bloc, ou après."""
    try:
        day = datetime.date(int(start[0:4]), int(start[5:7]), int(start[8:10]))
        first = datetime.date(int(year), int(str(month)[-2:]), 1)
    except (TypeError, ValueError):
        return None
    day = day - datetime.timedelta(days=int(lead or 0))
    last = datetime.date(first.year, first.month,
                         calendar_module.monthrange(first.year, first.month)[1])
    if day < first:
        return BEFORE
    if day > last:
        return AFTER
    return (day.day + 6) // 7


def weigh(cumulative: Dict[str, float], series: "Series", week: int,
          month: str, lead: int = 0) -> "Verdict":
    """L'épreuve : l'événement ordonne-t-il les exercices comme il le devrait ?

    `cumulative` porte, par exercice, la part du mois faite à la fin de la semaine mesurée.
    Si l'événement en est la cause, les exercices où il est déjà passé ont tous fait plus
    que ceux où il ne l'est pas encore. Un seul exercice à contre-sens suffit à conclure
    non, et c'est ce qui rend le test utile : il peut échouer.
    """
    places = series.places(sorted(cumulative), month, lead)
    if len(places) < 2:
        return Verdict(series, THIN,
                       "moins de deux exercices datés en commun avec la forme du mois")
    if len({value for value in places.values()}) == 1:
        only = list(places.values())[0]
        where = {BEFORE: "toujours avant le mois",
                 AFTER: "toujours après le mois"}.get(only, "toujours en semaine %d" % only)
        return Verdict(series, IMMOBILE,
                       "%s : un événement qui ne se déplace pas ne peut pas déplacer un "
                       "mois" % where)

    inside = sorted(year for year, place in places.items() if place <= week)
    outside = sorted(year for year, place in places.items() if place > week)
    if not inside or not outside:
        side = "toujours avant" if outside == [] else "toujours après"
        return Verdict(series, OUTSIDE,
                       "il bouge, mais %s la semaine %d : il ne traverse jamais la "
                       "frontière où l'écart se joue" % (side, week),
                       inside, outside)

    low = min(cumulative[year] for year in inside)
    high = max(cumulative[year] for year in outside)
    if low > high:
        return Verdict(series, AGREES,
                       "les exercices où il est déjà passé ont tous fait plus (%.3f au "
                       "minimum) que ceux où il ne l'est pas (%.3f au maximum)"
                       % (low, high), inside, outside)
    return Verdict(series, CONTRADICTS,
                   "au moins un exercice va à contre-sens : %.3f d'un côté contre %.3f "
                   "de l'autre" % (low, high), inside, outside)


def _column(header: Sequence[str], names: Sequence[str]) -> Optional[str]:
    for name in names:
        if name in header:
            return name
    return None


def load(path: str) -> "Calendar":
    """Lire le calendrier. Un fichier absent rend une lecture vide, pas une erreur."""
    if not path or not os.path.exists(path):
        return Calendar({}, [], path)

    faults: List[str] = []
    series: Dict[str, "Series"] = {}
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        name_column = _column(header, NAME_COLUMNS)
        missing = [name for name in REQUIRED if name not in header]
        if name_column is None:
            missing.append(" ou ".join(NAME_COLUMNS))
        if missing:
            return Calendar({}, ["colonnes manquantes : %s" % ", ".join(missing)], path)

        for number, record in enumerate(reader, start=2):
            country = (record.get("country") or "").strip()
            name = (record.get(name_column) or "").strip()
            year = (record.get("year") or "").strip()
            if not country or not name or not year:
                faults.append("ligne %d : pays, événement ou exercice absent" % number)
                continue
            event = Event(
                country=country, name=name,
                family=(record.get("family") or "").strip(),
                year=year,
                start=(record.get("start_date") or "").strip(),
                end=(record.get("end_date") or "").strip(),
                weekday=(record.get("start_weekday") or "").strip(),
                status=(record.get("date_status") or record.get("status") or "").strip(),
                source=(record.get("source") or "").strip(),
                rule=(record.get("rule") or "").strip(),
                region=(record.get("region") or "").strip(),
                event_id=(record.get("event_id") or "").strip())
            held = series.get(event.event_id)
            if held is None:
                held = Series(event.event_id, country, name, event.family)
                series[event.event_id] = held
            if year in held.by_year:
                faults.append("ligne %d : %s en double sur l'exercice %s"
                              % (number, name, year))
                continue
            held.by_year[year] = event

    return Calendar(series, faults, path)


def current(path: Optional[str] = None) -> "Calendar":
    from ..config import settings

    return load(path or str(settings.calendar_path))


#: Comment l'exercice de la forme des mois se traduit en année du calendrier. Trois
#: conventions existent et **aucune ne se devine** : un décalage d'un an passe totalement
#: inaperçu — les années se recouvrent, le rapprochement rend un tableau parfaitement
#: lisible, et il compare le mois d'un exercice aux fêtes d'un autre. La convention est donc
#: demandée, affichée, et jamais choisie en silence.
CONVENTIONS = ("calendaire", "ouverture", "cloture")


def calendar_year(exercice: str, month: str, convention: str = "calendaire") -> str:
    """L'année du calendrier où tombe ce mois de cet exercice.

    `calendaire` : l'exercice **est** l'année. `ouverture` : l'exercice porte l'année de son
    mois d'avril, donc janvier à mars appartiennent à l'année suivante. `cloture` :
    l'exercice porte l'année de son mois de mars — la convention de la maison, où l'exercice
    27 s'ouvre en avril 26.
    """
    try:
        year = int(str(exercice).strip())
    except (TypeError, ValueError):
        return str(exercice).strip()
    number = (month or "").strip()[-2:]
    try:
        index = int(number)
    except ValueError:
        return str(year)
    if convention == "ouverture":
        return str(year + 1 if index <= 3 else year)
    if convention == "cloture":
        return str(year if index <= 3 else year - 1)
    return str(year)


def load_markets(path: str) -> Tuple[Dict[str, List[str]], List[str]]:
    """Quel marché de la maison correspond à quel pays du calendrier.

    Fichier optionnel, deux colonnes `market,country`. Sans lui le rapprochement se fait sur
    le nom, ce qui marche pour « Hong Kong » et échoue pour tout marché nommé autrement que
    son pays — un marché non joint est **nommé**, jamais traité comme un marché sans
    événement, faute de quoi une absence de jointure se lirait comme une absence de cause.

    **Plusieurs lignes par marché sont admises et c'est l'usage principal.** Un calendrier
    porte des repères qui ne sont d'aucun pays — Black Friday, les campagnes d'une place de
    marché, Pâques occidentale — et savoir lesquels s'appliquent à un marché donné est un
    jugement de commerce, pas une déduction. Le fichier est l'endroit où ce jugement
    s'écrit, une ligne à la fois, plutôt que d'être supposé par le code.
    """
    if not path or not os.path.exists(path):
        return {}, []
    pairs: Dict[str, List[str]] = {}
    faults: List[str] = []
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        if "market" not in header or "country" not in header:
            return {}, ["colonnes manquantes : market, country"]
        for number, record in enumerate(reader, start=2):
            market = (record.get("market") or "").strip()
            country = (record.get("country") or "").strip()
            if not market or not country:
                faults.append("ligne %d : marché ou pays absent" % number)
                continue
            held = pairs.setdefault(normal(market), [])
            if country not in held:
                held.append(country)
    return pairs, faults
