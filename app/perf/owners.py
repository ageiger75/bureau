"""Who owns which market.

This does not live in the warehouse, and should not: it is organisational knowledge, not a
measurement. It changes when people change roles, which no data pipeline will tell you.

Knowing it buys the difference between "Japan E-commerce is below plan" and "ask the
Japan GM about it this week" — which is most of the point of the screen.

**Names are read from a local file, never stored here.** The directory is a real list of
real people and their remit; the repository is not the place for it, exactly as the
planning workbook is not. `var/` is ignored by git, and this module holds the mechanism
while the file holds the names.

Resolution runs in two tiers, and the order matters:

1. the country GM, when the directory names one for that market;
2. otherwise the BU head, who genuinely owns everything in their business unit.

The fallback is not a guess — a BU head does own an unlisted market in their BU. What is
refused is inventing a person for a market in no BU, or expanding a named grouping
("Nordics", "Central Europe") into countries the file never lists. Putting a real person
in front of a question they do not own is worse than leaving the line blank.
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
        "+" in raw or "&" in raw
    ):
        return []
    parts = [p.strip() for p in raw.replace("&", "+").split("+")]
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
    __slots__ = ("name", "role", "bu", "zone", "level", "markets")

    def __init__(self, name, role, bu, zone, level, markets) -> None:
        self.name = name
        self.role = role
        self.bu = bu
        self.zone = zone
        self.level = level
        self.markets = markets


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
        return Owner(name=found.name, role=found.role, market=market)

    def is_named(self, owner: Optional[Owner]) -> bool:
        return bool(owner and owner.name.strip())

    def unnamed_markets(self, markets) -> List[str]:
        return sorted({m for m in markets if self.entry_for(m) is None})


EMPTY = Directory()

#: Loaded once at first use. A missing file is not an error: the cockpit runs without a
#: directory, it simply cannot say who to ask.
_loaded: Optional[Directory] = None


def load(path) -> Directory:
    """Read the directory workbook. Columns are found by header, not by position."""
    from .xlsx import Workbook

    book = Workbook(path)
    sheet = book.sheet_names[0]
    rows = [
        row
        for row in book.rows(sheet)
        if any(cell is not None and str(cell).strip() for cell in row)
    ]

    header_at = None
    columns: Dict[str, int] = {}
    for index, row in enumerate(rows):
        cells = {_key(str(c)): i for i, c in enumerate(row) if c is not None}
        if "bu" in cells and ("prénom" in cells or "prenom" in cells):
            header_at = index
            columns = cells
            break
    if header_at is None:
        raise ValueError(
            "No header row found: expected columns BU, Prénom, Nom, Poste, Pays / Zone, Type."
        )

    def at(*names):
        for name in names:
            if name in columns:
                return columns[name]
        return None

    first_at = at("prénom", "prenom")
    last_at = at("nom")
    role_at = at("poste")
    zone_at = at("pays / zone", "pays/zone", "zone")
    type_at = at("type")
    bu_at = at("bu")

    entries: List[Entry] = []
    for row in rows[header_at + 1 :]:
        def cell(position):
            if position is None or position >= len(row) or row[position] is None:
                return ""
            return str(row[position]).strip()

        first = cell(first_at)
        if not first:
            continue
        last = cell(last_at)
        kind = _key(cell(type_at))
        level = BU_HEAD if "bu" in kind else COUNTRY_GM
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
