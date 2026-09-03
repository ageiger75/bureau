"""Who owns which market.

This does not live in the warehouse, and should not: it is organisational knowledge, not a
measurement. It changes when people change roles, which no data pipeline will tell you.

Knowing it buys the difference between "Japan E-commerce is below plan" and "ask the
Japan GM about it this week" — which is most of the point of the screen.

**Names are read from a local file, never stored here.** The directory is a real list of
real people and their remit; the repository is not the place for it, exactly as the
planning workbook is not. `var/` is ignored by git, and this module holds the mechanism
while the file holds the names.

Resolution runs in two tiers, and the order matters. **It was the other way round, and
that was wrong.**

1. the MD of the perimeter — the person who answers to the reader of this screen;
2. otherwise the country GM, when no MD is placed above that market.

The first version put the country GM first, on the reasoning that the question goes to
whoever answers for the number rather than to whoever is most senior. That reasoning is
sound for a market review and false here. This screen has one reader, and the people who
answer to him are his MDs — six of them. A card naming a country GM installs its reader
one level below his own organisation: it proposes a conversation he does not hold, over
the head of the person who does. The house maintains that line; a cockpit that quietly
crosses it at every reading damages something real, politely, with nothing to signal it.

The country GM is not lost, and is not merely decorative: named as `local_lead`, so the
question reaches the MD and the detail stays with the person on the ground.

What is still refused is inventing a person for a market in no BU, or expanding a named
grouping ("Nordics", "Central Europe") into countries the file never lists. Putting a
real person in front of a question they do not own is worse than leaving the line blank.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .model import Owner

#: Directory country names to the form the rest of the cockpit uses. Taxonomy, not data:
#: the file is written in French and the warehouse answers in English.
COUNTRY_ALIASES = {
    "japon": "Japan",
    "chine": "China",
    "hong kong": "Hong Kong",
    "brésil": "Brazil",
    "bresil": "Brazil",
    "france": "France",
    "allemagne": "Germany",
    "royaume-uni": "United Kingdom",
    "uk": "United Kingdom",
    "irlande": "Ireland",
    "corée": "South Korea",
    "coree": "South Korea",
    "corée du sud": "South Korea",
    "taiwan": "Taiwan",
    "australie": "Australia",
    "vietnam": "Vietnam",
    "inde": "India",
    "mexique": "Mexico",
    "usa": "United States",
    "états-unis": "United States",
    "etats-unis": "United States",
    "canada": "Canada",
    "thaïlande": "Thailand",
    "thailande": "Thailand",
    "espagne": "Spain",
    "italie": "Italy",
    "portugal": "Portugal",
    "suisse": "Switzerland",
    "belgique": "Belgium",
    "pays-bas": "Netherlands",
    "autriche": "Austria",
    "royaume-uni": "United Kingdom",
    "luxembourg": "Luxembourg",
    "pologne": "Poland",
    "république tchèque": "Czechia",
    "republique tcheque": "Czechia",
    "hongrie": "Hungary",
    "slovaquie": "Slovakia",
    "norvège": "Norway",
    "norvege": "Norway",
    "suède": "Sweden",
    "suede": "Sweden",
    "danemark": "Denmark",
    "finlande": "Finland",
    "émirats arabes unis": "United Arab Emirates",
    "emirats arabes unis": "United Arab Emirates",
    "arabie saoudite": "Saudi Arabia",
    "corée du sud": "South Korea",
    "taïwan": "Taiwan",
    "malaisie": "Malaysia",
    "singapour": "Singapore",
    "états-unis": "United States",
}

#: Warehouse region names to the business unit that owns them. The regions come from the
#: planning file; the BU names come from the directory's own first column.
REGION_TO_BU = {
    "JAPAN": "japon",
    "CHINA": "greater china",
    "BRAZIL": "brésil",
    "N.AMERICA": "north america",
    "APAC": "apac",
    "GE COUNTRIES": "emea",
    "GE DISTRIBUTORS": "emea",
    # Travel Retail is a business unit, not a geography: it runs a channel worldwide. Its
    # BU head therefore owns every market in it, and its regional GMs cover continents
    # rather than countries — which is why no country row ever routes to one of them.
    "WW TR": "travel retail",
}

#: Rows whose remit is a named grouping rather than a list of countries. They are kept in
#: the directory — the person is real and their remit is real — but they are never matched
#: to an individual market, because the file does not say which markets they contain.
#: Expanding "Southern Europe" from a guess is exactly the failure this module refuses.
GROUPING_MARKERS = ("multi-pays", "export", "nordics", "europe", "sea", "tr ")

BU_HEAD = "bu"
COUNTRY_GM = "country"


def _key(name: str) -> str:
    return (name or "").strip().lower()


def _normalise(name: str) -> str:
    cleaned = _key(name)
    if cleaned in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[cleaned]
    return (name or "").strip()


def _split_zone(zone: str) -> List[str]:
    """`Chine + Hong Kong` -> two countries. `Nordics` -> nothing.

    Only zones that enumerate their members are expanded. A grouping that names itself
    without naming its countries stays unexpanded, and the BU head covers those markets.
    """
    raw = (zone or "").strip()
    if not raw:
        return []
    lowered = raw.lower()
    if any(marker in lowered for marker in GROUPING_MARKERS) and not (
        "+" in raw or "&" in raw or ";" in raw
    ):
        return []
    parts = [
        p.strip() for p in raw.replace("&", ";").replace("+", ";").split(";")
    ]
    found = []
    for part in parts:
        if not part:
            continue
        if _key(part) not in COUNTRY_ALIASES:
            # A member this module cannot name is a member it will not claim.
            continue
        found.append(_normalise(part))
    return found


class Entry:
    __slots__ = (
        "name", "role", "bu", "zone", "level", "markets", "escalates_to", "local_lead",
    )

    def __init__(
        self, name, role, bu, zone, level, markets, escalates_to="", local_lead=""
    ) -> None:
        self.name = name
        self.role = role
        self.bu = bu
        self.zone = zone
        self.level = level
        self.markets = markets
        self.escalates_to = escalates_to
        self.local_lead = local_lead


class Directory:
    """The list, and the two-tier resolution over it."""

    def __init__(self, entries: Optional[Sequence[Entry]] = None) -> None:
        self.entries: List[Entry] = list(entries or [])
        self._by_market: Dict[str, Entry] = {}
        self._by_bu: Dict[str, Entry] = {}
        for entry in self.entries:
            if entry.level == BU_HEAD:
                self._by_bu.setdefault(_key(entry.bu), entry)
            for market in entry.markets:
                # A country GM wins over a BU head reaching the same market.
                existing = self._by_market.get(market)
                if existing is None or (
                    existing.level == BU_HEAD and entry.level == COUNTRY_GM
                ):
                    self._by_market[market] = entry

    def __len__(self) -> int:
        return len(self.entries)

    def entry_for(self, market: str, region: str = "") -> Optional[Entry]:
        found = self._by_market.get((market or "").strip())
        if found is not None:
            return found
        bu = REGION_TO_BU.get((region or "").strip().upper())
        return self._by_bu.get(bu) if bu else None

    def owner_for(self, market: str, region: str = "") -> Owner:
        """The named owner of a market, or an unnamed placeholder. Never a guess."""
        found = self.entry_for(market, region)
        if found is None:
            return Owner(name="", role="", market=market)
        return Owner(
            name=found.name,
            role=found.role,
            market=market,
            escalates_to=found.escalates_to,
            local_lead=found.local_lead,
        )

    def is_named(self, owner: Optional[Owner]) -> bool:
        return bool(owner and owner.name.strip())

    def unnamed_markets(self, markets) -> List[str]:
        return sorted({m for m in markets if self.entry_for(m) is None})


EMPTY = Directory()

#: Loaded once at first use. A missing file is not an error: the cockpit runs without a
#: directory, it simply cannot say who to ask.
_loaded: Optional[Directory] = None


def _sheet_rows(book, name):
    return [
        row
        for row in book.rows(name)
        if any(cell is not None and str(cell).strip() for cell in row)
    ]


def _header(rows, *required):
    """Find the header row by its column names, and return (index, {name: position}).

    By name rather than by position, because a directory is a document people edit: a
    column inserted in front of another must not silently shift every name by one.
    """
    for index, row in enumerate(rows):
        columns = {_key(str(c)): i for i, c in enumerate(row) if c is not None}
        if all(any(r in c for c in columns) for r in required):
            return index, columns
    return None, {}


def _at(columns, *fragments):
    """Locate a column by name, exact match first.

    The order is not a nicety: `nom` is a substring of `prénom`, so a loose match on the
    first pass hands back the wrong column and every person in the directory is named
    twice by their first name.
    """
    for fragment in fragments:
        for name, position in columns.items():
            if fragment == name:
                return position
    for fragment in fragments:
        for name, position in columns.items():
            if fragment in name:
                return position
    return None


def _from_lookup(book) -> Optional["Directory"]:
    """Read the country lookup sheet, when the directory has one.

    Preferred over every other reading, because it removes this module's judgement
    entirely: one row per market, naming its BU, its BU head and its GM. Nothing has to be
    split, expanded or inferred, and a country that is not on it is a country nobody has
    claimed rather than one this code failed to place.
    """
    name = None
    for candidate in book.sheet_names:
        lowered = _key(candidate)
        if "pays" in lowered and ("recherche" in lowered or "lookup" in lowered):
            name = candidate
            break
    if name is None:
        return None

    rows = _sheet_rows(book, name)
    header_at, columns = _header(rows, "pays", "bu")
    if header_at is None:
        return None

    # The lookup names people but not their titles. Reading the titles from the leaders
    # sheet costs one pass and turns "General Manager" into "Managing Director DACH",
    # which is the difference between a label and a name the reader recognises.
    titles = _titles(book)

    market_at = _at(columns, "pays / entité", "pays /", "pays")
    bu_at = _at(columns, "bu")
    md_at = _at(columns, "responsable bu")
    gm_at = _at(columns, "responsable pays", "cluster")
    local_at = _at(columns, "local")

    entries: List[Entry] = []
    for row in rows[header_at + 1 :]:
        def cell(position):
            if position is None or position >= len(row) or row[position] is None:
                return ""
            return str(row[position]).strip()

        market = _normalise(cell(market_at))
        if not market:
            continue
        head = cell(md_at)
        gm = cell(gm_at)
        # The accountable owner is the MD of the perimeter, and the country GM only where
        # no MD is placed. See the module docstring: this screen has one reader, and the
        # people who answer to him are his MDs. Naming the country GM here proposed a
        # conversation he does not hold, over the head of the person who does.
        name_of = head or gm
        if not name_of:
            continue
        entries.append(
            Entry(
                name=name_of,
                role=titles.get(
                    _key(name_of), "Managing Director" if head else "General Manager"
                ),
                bu=cell(bu_at),
                zone=market,
                level=BU_HEAD if head else COUNTRY_GM,
                markets=[market],
                # Rien au-dessus d'un MD sinon le lecteur lui-même : l'escalade n'a plus
                # d'objet, et le GM pays devient le visage local plutôt que le destinataire.
                escalates_to="",
                local_lead=(gm if head and gm and gm != head else "") or cell(local_at),
            )
        )
    if not entries:
        return None
    # The lookup covers countries. A business unit that owns no country — Travel Retail
    # runs a channel worldwide — has its head only on the leaders sheet, so both are read:
    # the lookup places markets, the leaders sheet places business units.
    entries.extend(_bu_heads(book))
    return Directory(entries)


def _leaders_rows(book):
    """The leaders sheet, if the workbook has one: (rows, header index, columns)."""
    for candidate in book.sheet_names:
        lowered = _key(candidate)
        if "responsable" in lowered or "leader" in lowered:
            rows = _sheet_rows(book, candidate)
            header_at, columns = _header(rows, "bu", "nom")
            if header_at is None:
                return None, None, {}
            return rows, header_at, columns
    return None, None, {}


def _titles(book) -> Dict[str, str]:
    """Person to job title, read from the leaders sheet."""
    rows, header_at, columns = _leaders_rows(book)
    if rows is None:
        return {}
    first_at = _at(columns, "prénom", "prenom")
    last_at = _at(columns, "nom")
    role_at = _at(columns, "poste")
    found: Dict[str, str] = {}
    for row in rows[header_at + 1 :]:
        def cell(position):
            if position is None or position >= len(row) or row[position] is None:
                return ""
            return str(row[position]).strip()

        name = ("%s %s" % (cell(first_at), cell(last_at))).strip()
        role = cell(role_at)
        if name and role:
            found[_key(name)] = role
    return found


def _bu_heads(book) -> List["Entry"]:
    """BU heads from the leaders sheet, so every business unit has someone above it."""
    rows, header_at, columns = _leaders_rows(book)
    if rows is None:
        return []

    first_at = _at(columns, "prénom", "prenom")
    last_at = _at(columns, "nom")
    role_at = _at(columns, "poste")
    level_at = _at(columns, "niveau", "type")
    bu_at = _at(columns, "bu")

    found: List[Entry] = []
    for row in rows[header_at + 1 :]:
        def cell(position):
            if position is None or position >= len(row) or row[position] is None:
                return ""
            return str(row[position]).strip()

        if _key(cell(level_at)) not in ("md", "patron de bu"):
            continue
        name = ("%s %s" % (cell(first_at), cell(last_at))).strip()
        if not name:
            continue
        found.append(
            Entry(
                name=name,
                role=cell(role_at),
                bu=cell(bu_at),
                zone="",
                level=BU_HEAD,
                # No markets: this entry exists to answer for its business unit, never to
                # claim a country the lookup did not give it.
                markets=[],
            )
        )
    return found


def _from_leaders(book) -> "Directory":
    """Read a flat leaders sheet: one row per person, with the markets they cover."""
    sheet = book.sheet_names[0]
    rows = _sheet_rows(book, sheet)

    header_at, columns = _header(rows, "bu", "nom")
    if header_at is None:
        raise ValueError(
            "No header row found: expected columns naming a BU, a person and their markets."
        )

    first_at = _at(columns, "prénom", "prenom")
    last_at = _at(columns, "nom")
    role_at = _at(columns, "poste")
    zone_at = _at(columns, "pays couverts", "pays / zone", "pays/zone", "zone", "pays")
    level_at = _at(columns, "niveau", "type")
    bu_at = _at(columns, "bu")

    entries: List[Entry] = []
    for row in rows[header_at + 1 :]:
        def cell(position):
            if position is None or position >= len(row) or row[position] is None:
                return ""
            return str(row[position]).strip()

        first = cell(first_at)
        last = cell(last_at)
        if not (first or last):
            continue
        kind = _key(cell(level_at))
        level = BU_HEAD if kind in ("md", "") or "bu" in kind else COUNTRY_GM
        zone = cell(zone_at)
        entries.append(
            Entry(
                name=("%s %s" % (first, last)).strip(),
                role=cell(role_at),
                bu=cell(bu_at),
                zone=zone,
                level=level,
                markets=_split_zone(zone),
            )
        )
    return Directory(entries)


def load(path) -> Directory:
    """Read the directory workbook.

    Two shapes are accepted. A country lookup sheet is preferred when present — it states
    the answer outright. A flat leaders sheet is read otherwise, and then the markets a
    person covers have to be parsed out of the text, which is where guessing starts and
    where this module stops.
    """
    from .xlsx import Workbook

    book = Workbook(path)
    from_lookup = _from_lookup(book)
    if from_lookup is not None:
        return from_lookup
    return _from_leaders(book)


def current() -> Directory:
    """The active directory, loaded from the configured file on first use."""
    global _loaded
    if _loaded is None:
        from ..config import settings

        path = settings.owners_path
        try:
            _loaded = load(path) if path.exists() else EMPTY
        except Exception:  # noqa: BLE001
            # A malformed directory must not take the cockpit down. Every market simply
            # goes unnamed, which the screen already knows how to say.
            _loaded = EMPTY
    return _loaded


def reset() -> None:
    """Forget the loaded directory. For tests, and for a file edited while running."""
    global _loaded
    _loaded = None


def owner_for(market: str, region: str = "") -> Owner:
    return current().owner_for(market, region)


def is_named(owner: Optional[Owner]) -> bool:
    return bool(owner and owner.name.strip())


def unnamed_markets(markets) -> List[str]:
    return current().unnamed_markets(markets)
