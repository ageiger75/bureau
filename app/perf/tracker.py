"""The KPI tracker read as a registry: what each KPI is, and what would count as good.

The warehouse supplies values. Values alone cannot be judged — 25.1% is neither good nor
bad until something says what was asked for — so the cockpit refuses to show a KPI it has
only half of. This module supplies the other half from the tracker the business actually
maintains, and is deliberately unforgiving about the difference between *reading* a target
and *inferring* one.

Three refusals, each the same rule in a different place:

1. **No target, no judgement.** A row whose target cannot be read off the sheet is kept and
   counted, never scored. Guessing one would put a verdict on screen that nobody agreed.
2. **No reading, not late.** A tracker row the warehouse does not feed is not a missing
   figure, it is an unwired one. Two hundred rows reported "awaiting" every month is how a
   panel teaches its reader to skip it.
3. **An open point suspends the challenge.** A KPI named in the tracker's own open-points
   sheet is marked provisional: the variance shows, the question does not. The screen does
   not send anyone to argue about a number the business is still defining.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import kpi as rules
from .xlsx import Workbook, WorkbookError

#: The sheet holding one row per KPI, and the sheet holding what is still being argued.
REGISTRY_SHEET = "KPI FY27"
OPEN_POINTS_SHEET = "POINTS OUVERTS"


def _words_of(text) -> frozenset:
    """The distinct unaccented words of a name."""
    return frozenset(part for part in re.split(r"[^a-z0-9]+", _plain(text)) if part)


def _plain(text) -> str:
    """Lower-case, unaccented, single-spaced — for matching headers and names only.

    Never for display. A column called "Périmètre" and one called "PERIMETRE" are the same
    column, and a reader that says otherwise fails on the first file somebody re-saves.
    """
    if text is None:
        return ""
    raw = str(text).strip()
    stripped = "".join(
        char for char in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", stripped).lower()


#: Header name (normalised) -> field. Several spellings per field, because the sheet is
#: maintained by people rather than by a schema, and a renamed column must degrade to a
#: named absence rather than to a silently empty registry.
COLUMNS = {
    "id": "id",
    "niveau": "level",
    "proprietaire": "owner",
    "responsable": "owner",
    "perimetre": "scope",
    "pilier": "pillar",
    "kpi": "label",
    "indicateur": "label",
    "definition": "definition",
    "definition base": "definition",
    "def base": "definition",
    "reel fy26": "last_year",
    "realise fy26": "last_year",
    "fy26": "last_year",
    "cible": "target_text",
    "cible fy27": "target_text",
    "objectif": "target_text",
    "objectif fy27": "target_text",
    # A column the sheet has already reduced to a number. Preferred over the prose one
    # beside it: "1 259 (+4%)" is a sentence about a target, and reading a commitment out
    # of a sentence is the guessing this module exists to avoid.
    "cible num": "target_number",
    "cible numerique": "target_number",
    "unite": "unit_text",
    "unit": "unit_text",
    "def": "status_text",
    "definition status": "status_text",
    "statut definition": "status_text",
    "frequence": "frequency_text",
    "cadence": "frequency_text",
    "priorite": "priority_text",
    "source": "source",
    "sens": "direction_text",
    "direction": "direction_text",
    "polarite": "direction_text",
}

#: Words that name a quantity a business wants *down*. A target written as a bare number
#: carries no operator, and this reader defaults to "higher is better" — which is right for
#: most of the sheet and catastrophically wrong for a discount rate or an attrition rate:
#: read as a floor, a ceiling turns every overshoot into good news.
#:
#: So these do not flip the direction — inferring a business rule from a word would be the
#: same overconfidence in the other direction. They mark the row as unsettled, and the
#: screen shows the figure while withholding the verdict. Wrong loudly rather than quietly,
#: and a list somebody can correct.
CEILING_WORDS = frozenset((
    "discount", "remise", "remises", "turnover", "attrition", "cout", "couts", "delai",
    "delais", "retours", "reclamations", "ruptures", "rupture", "absenteisme",
    "demarque", "casse", "churn",
))

#: Level, as the tracker writes it, to the cockpit's priority. Board-level KPIs outrank
#: functional ones when several are equally far from target.
LEVELS = {
    "groupe": rules.P1,
    "group": rules.P1,
    "maison": rules.P1,
    "comex": rules.P1,
    "board": rules.P1,
    "bu": rules.P2,
    "marche": rules.P2,
    "market": rules.P2,
    "fonction": rules.P3,
    "function": rules.P3,
    "equipe": rules.P3,
}

#: How the sheet writes a direction. Arrows first, because that is what it actually uses —
#: and an arrow this reader does not understand is worse than no column at all: it looks
#: answered, so nothing falls back to the caution that protects an unmarked row.
DIRECTIONS = {
    "\u2191": rules.UP, "\u2193": rules.DOWN,
    "\u2b06": rules.UP, "\u2b07": rules.DOWN,
    "+": rules.UP, "-": rules.DOWN,
    "hausse": rules.UP, "baisse": rules.DOWN,
    "up": rules.UP, "down": rules.DOWN,
    "plus": rules.UP, "moins": rules.DOWN,
    "higher": rules.UP, "lower": rules.DOWN,
    "croissant": rules.UP, "decroissant": rules.DOWN,
    "max": rules.UP, "min": rules.DOWN,
}

#: The tracker states this itself, in a column of its own. Read rather than inferred: the
#: business knows which of its definitions are settled, and this cockpit's whole rule about
#: provisional KPIs was written waiting for exactly this column.
LOCKED_WORDS = frozenset(("verrouille", "verrouillee", "locked", "arrete", "arretee",
                          "valide", "validee", "ok"))

#: Month headers as the sheet writes them: `avr-26`, `juil-26`, `janv-27`.
MONTHS = {
    "janv": 1, "jan": 1, "fevr": 2, "fev": 2, "mars": 3, "mar": 3, "avr": 4, "avril": 4,
    "mai": 5, "juin": 6, "jun": 6, "juil": 7, "jul": 7, "aout": 8, "sept": 9, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}


def read_month_header(text) -> str:
    """`avr-26` -> `2026-04`. Empty when the header is not a month.

    The tracker keeps twelve columns of its own actuals beside the target. For the KPIs
    the warehouse cannot compute — a discount level, an engagement score, a B-Corp
    milestone — they are the only readings that exist, and a panel that ignored them would
    say nothing about two thirds of what the business tracks.
    """
    plain = _plain(text).replace(".", "")
    match = re.fullmatch(r"([a-z]+)[\s\-/]*(\d{2}|\d{4})", plain)
    if not match:
        return ""
    month = MONTHS.get(match.group(1))
    if month is None:
        return ""
    year = int(match.group(2))
    return "%d-%02d" % (year + 2000 if year < 100 else year, month)


FREQUENCIES = {
    "mensuel": rules.MONTHLY,
    "mensuelle": rules.MONTHLY,
    "monthly": rules.MONTHLY,
    "trimestriel": rules.QUARTERLY,
    "trimestrielle": rules.QUARTERLY,
    "quarterly": rules.QUARTERLY,
    "semestriel": rules.HALF_YEARLY,
    "semestrielle": rules.HALF_YEARLY,
    "annuel": rules.ANNUAL,
    "annuelle": rules.ANNUAL,
    "annual": rules.ANNUAL,
    "jalon": rules.MILESTONE,
    "milestone": rules.MILESTONE,
}

#: A target written as a comparison: "≥ 3", "> 4,6", "≤ 2%", "< 15 j". The operator is the
#: half that matters most — it says which way the KPI is supposed to move, and a ceiling
#: read as a floor inverts every verdict drawn from it.
_COMPARISON = re.compile(
    r"(?P<op>>=|<=|≥|≤|>|<)\s*(?P<value>-?\d[\d\s  ]*(?:[.,]\d+)?)\s*(?P<unit>%|pts?|j|jours?|€|k€|m€|k|M€)?",
    re.IGNORECASE,
)
#: A bare target: "28,9 %". Only trusted in a column that is *called* a target — a number
#: sitting in a definition is as likely to be last year's, a threshold, or a footnote.
_BARE = re.compile(
    r"(?P<value>-?\d[\d\s  ]*(?:[.,]\d+)?)\s*(?P<unit>%|pts?|€|k€|m€|k|M€)?"
)


def _number(text: str) -> Optional[float]:
    cleaned = re.sub(r"[\s  ]", "", str(text)).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _unit_of(raw: Optional[str]) -> str:
    token = (raw or "").strip().lower()
    if token == "%":
        return "%"
    if token in ("€",):
        return "€"
    if token in ("k€", "k"):
        return "k€"
    if token in ("m€",):
        return "M€"
    if token in ("j", "jour", "jours"):
        return "days"
    if token.startswith("pt"):
        return "pts"
    return ""


def read_target(text) -> Tuple[Optional[float], str, str]:
    """`(value, direction, unit)` from a target written by a human.

    Returns `(None, UP, "")` when nothing in the text is a target this can stand behind.
    The caller must treat that as "not judgeable", never as zero: a KPI silently scored
    against a target of nothing would read as catastrophically off every month.
    """
    raw = "" if text is None else str(text).strip()
    if not raw:
        return None, rules.UP, ""
    match = _COMPARISON.search(raw)
    if match:
        value = _number(match.group("value"))
        if value is None:
            return None, rules.UP, ""
        down = match.group("op") in ("<", "<=", "≤")
        return value, rules.DOWN if down else rules.UP, _unit_of(match.group("unit"))
    return None, rules.UP, ""


def read_plain_target(text) -> Tuple[Optional[float], str, str]:
    """As `read_target`, but a bare number counts too.

    Used only for a column the sheet itself labels a target. Everywhere else a loose
    number is not a commitment, and reading it as one is the whole failure this module is
    written to avoid.
    """
    value, direction, unit = read_target(text)
    if value is not None:
        return value, direction, unit
    raw = "" if text is None else str(text).strip()
    match = _BARE.fullmatch(raw)
    if not match:
        return None, rules.UP, ""
    number = _number(match.group("value"))
    if number is None:
        return None, rules.UP, ""
    return number, rules.UP, _unit_of(match.group("unit"))


class Entry:
    """One tracker row: what a KPI is, who owns it, and what was asked of it."""

    __slots__ = ("id", "label", "definition", "scope", "owner", "pillar", "level",
                 "target", "direction", "unit", "frequency", "priority", "last_year",
                 "open_question", "source", "direction_assumed", "readings", "locked")

    def __init__(self, id="", label="", definition="", scope="", owner="", pillar="",
                 level="", target=None, direction=rules.UP, unit="",
                 frequency=rules.MONTHLY, priority=rules.P2, last_year=None,
                 open_question="", source="", direction_assumed=False, readings=(),
                 locked=True) -> None:
        self.id = id
        self.label = label
        self.definition = definition
        self.scope = scope
        self.owner = owner
        self.pillar = pillar
        self.level = level
        self.target = target
        self.direction = direction
        self.unit = unit
        self.frequency = frequency
        self.priority = priority
        self.last_year = last_year
        self.open_question = open_question
        self.source = source
        #: True when nothing in the sheet said which way this KPI should move and the
        #: reader fell back to "higher is better". Harmless on most rows; on a ceiling it
        #: inverts the verdict, so it is stated rather than assumed away.
        self.direction_assumed = direction_assumed
        #: The tracker's own twelve months, where somebody has filled them in. Oldest
        #: first. Used only where the warehouse supplies nothing — never merged with it,
        #: because a figure typed into a sheet and a figure measured by a query are two
        #: different claims and the panel names which one it is showing.
        self.readings = list(readings)
        #: What the sheet's own definition-status column says.
        self.locked = locked

    @property
    def reads_as_ceiling(self) -> bool:
        """Does this KPI's own name say it should fall, against an assumed floor?

        Only where there is a target to be wrong about: a row with none is already kept
        out of the scoring, and a second reason to withhold a verdict nobody was going to
        reach is a sentence that would only ever confuse.
        """
        return (
            self.has_target
            and self.direction_assumed
            and bool(CEILING_WORDS & _words_of(self.label))
        )

    @property
    def has_target(self) -> bool:
        return self.target is not None

    @property
    def unsettled_reason(self) -> str:
        if self.open_question:
            return self.open_question
        if not self.locked:
            return "the tracker does not mark this definition as settled"
        if self.reads_as_ceiling:
            return (
                "the sheet gives \u201c%g\u201d with no sign, and this name reads as a "
                "quantity to keep down \u2014 read as a floor it would score every "
                "overshoot as good news" % self.target
            )
        return ""

    def to_kpi(self, readings: Sequence["rules.Reading"] = ()) -> "rules.Kpi":
        """The KPI as the cockpit judges it.

        `readings` are the warehouse's, and they win: measured beats typed. Where there
        are none, the tracker's own columns are used and the source says so, because a
        figure somebody typed into a sheet and one a query measured are different claims
        and a reader who cannot tell them apart cannot weigh either.
        """
        unsettled = self.unsettled_reason
        measured = list(readings)
        source = self.source or "KPI tracker"
        if not measured and self.readings:
            measured = self.readings
            source = "KPI tracker (reported, not measured)"
        return rules.Kpi(
            key=self.id or _plain(self.label),
            label=self.label,
            definition=self.definition,
            scope=self.scope,
            owner=self.owner,
            pillar=self.pillar,
            unit=self.unit,
            target=self.target,
            direction=self.direction,
            frequency=self.frequency,
            source=source,
            definition_status=rules.PROVISIONAL if unsettled else rules.LOCKED,
            priority=self.priority,
            last_year=self.last_year,
            readings=measured,
            open_question=unsettled,
        )


class Tracker:
    """Every readable row of the tracker, plus an account of what it could not read."""

    __slots__ = ("entries", "refused", "columns_missing", "open_points")

    def __init__(self, entries: Sequence[Entry], refused: Sequence[str] = (),
                 columns_missing: Sequence[str] = (),
                 open_points: Optional[Dict[str, str]] = None) -> None:
        self.entries = list(entries)
        #: One line per row the reader would not turn into a KPI, and why. Printed by the
        #: CLI rather than swallowed: a registry that silently drops half a sheet is worse
        #: than one that refuses to load.
        self.refused = list(refused)
        self.columns_missing = list(columns_missing)
        self.open_points = dict(open_points or {})

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def with_target(self) -> List[Entry]:
        return [entry for entry in self.entries if entry.has_target]

    @property
    def without_target(self) -> List[Entry]:
        return [entry for entry in self.entries if not entry.has_target]

    def find(self, name: str) -> Optional[Entry]:
        """By id first, then by name. Exact before loose, and never by resemblance.

        Two passes rather than one, for the reason the plan mapping needs two: an id is a
        claim and a label is a coincidence, so every id must have its chance before any
        label is allowed to match.
        """
        wanted = _plain(name)
        if not wanted:
            return None
        for entry in self.entries:
            if _plain(entry.id) == wanted:
                return entry
        for entry in self.entries:
            if _plain(entry.label) == wanted:
                return entry
        return None


def _header_key(text) -> str:
    """A header reduced to its words: `Cible (num)` -> `cible num`, `Déf.` -> `def`.

    `_plain` keeps punctuation, which is right for a market name and wrong here: a column
    matched on its exact punctuation stops matching the day somebody drops a full stop,
    and the failure is silent — the field goes empty, and an empty field looks like a
    workbook that says nothing.
    """
    return " ".join(part for part in re.split(r"[^a-z0-9]+", _plain(text)) if part)


def _header_map(row: Sequence[object]) -> Dict[str, int]:
    found = {}
    for index, cell in enumerate(row):
        field = COLUMNS.get(_header_key(cell))
        if field and field not in found:
            found[field] = index
    return found


def _cell(row: Sequence[object], index: Optional[int]):
    if index is None or index >= len(row):
        return None
    return row[index]


def _text(row: Sequence[object], index: Optional[int]) -> str:
    value = _cell(row, index)
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def tracker_from_rows(rows: Iterable[Sequence[object]],
                      open_points: Optional[Dict[str, str]] = None) -> Tracker:
    """Build the registry from a sheet already read into rows.

    Separate from the file reading so the rules can be tested without a workbook, which is
    also what lets the target parsing be exercised on the shapes people actually write.
    """
    rows = [list(row) for row in rows]
    header_at, columns = None, {}
    for index, row in enumerate(rows):
        found = _header_map(row)
        if "label" in found:
            header_at, columns = index, found
            break
    if header_at is None:
        return Tracker([], refused=[
            "No header row found: no column named KPI or Indicateur on this sheet."
        ], columns_missing=["kpi"])

    missing = [name for name in ("label",) if name not in columns]
    # The sheet's own twelve months of actuals. For every KPI the warehouse cannot compute
    # — a discount level, an engagement score, a milestone — these are the only readings
    # there are, and they carry the tracker's name as their source so nobody confuses a
    # figure somebody typed with one the warehouse measured.
    month_columns = {}
    for index, cell in enumerate(rows[header_at]):
        period = read_month_header(cell)
        if period and index not in columns.values():
            month_columns[index] = period
    points = dict(open_points or {})
    entries, refused = [], []

    for row in rows[header_at + 1:]:
        label = _text(row, columns.get("label"))
        if not label:
            continue
        identifier = _text(row, columns.get("id"))
        # A number the sheet has already reduced, before any prose beside it. "1 259
        # (+4%)" is a sentence about a target; a column called `Cible (num)` is the target.
        target, direction, unit = None, rules.UP, ""
        if "target_number" in columns:
            target = _number(_text(row, columns["target_number"]))
        if target is None and "target_text" in columns:
            target, direction, unit = read_plain_target(_cell(row, columns["target_text"]))
        if target is None and "target_text" not in columns:
            target, direction, unit = read_target(_cell(row, columns.get("definition")))

        stated = _text(row, columns.get("direction_text")).strip()
        from_column = DIRECTIONS.get(stated) or DIRECTIONS.get(_plain(stated))
        if from_column is not None:
            direction = from_column
        # A written operator settles it too; an unreadable arrow settles nothing, and must
        # fall back to the caution that protects an unmarked row rather than pass for an
        # answer because the cell was not empty.
        written = _COMPARISON.search(
            "%s %s" % (_text(row, columns.get("target_text")),
                       _text(row, columns.get("definition")))
        )
        if written and from_column is None:
            _value, direction, _unit = read_target(written.group(0))
        assumed = from_column is None and written is None

        if "unit_text" in columns:
            unit = _text(row, columns["unit_text"]) or unit
        if target is None:
            refused.append(
                "%s: no target this reader can stand behind, so it is counted and not "
                "scored." % label
            )
        last_year = _number(_text(row, columns.get("last_year")))
        entries.append(Entry(
            id=identifier,
            label=label,
            definition=_text(row, columns.get("definition")),
            scope=_text(row, columns.get("scope")),
            owner=_text(row, columns.get("owner")),
            pillar=_text(row, columns.get("pillar")),
            level=_text(row, columns.get("level")),
            target=target,
            direction=direction,
            unit=unit,
            frequency=FREQUENCIES.get(
                _plain(_text(row, columns.get("frequency_text"))), rules.MONTHLY),
            priority=LEVELS.get(_plain(_text(row, columns.get("level"))), rules.P2),
            last_year=last_year,
            readings=[
                rules.Reading(period, value)
                for period, value in sorted(
                    (period, _number(_text(row, at)))
                    for at, period in month_columns.items()
                )
                if value is not None
            ],
            open_question=points.get(_plain(label), "") or points.get(_plain(identifier), ""),
            source=_text(row, columns.get("source")),
            direction_assumed=assumed,
            # The tracker says which of its definitions are settled. Read rather than
            # inferred: the rule about withholding a challenge on a provisional KPI was
            # written waiting for a column exactly like this one.
            locked=(not columns.get("status_text")
                    or _plain(_text(row, columns["status_text"])) in LOCKED_WORDS),
        ))
    return Tracker(entries, refused=refused, columns_missing=missing, open_points=points)


def read_open_points(rows: Iterable[Sequence[object]]) -> Dict[str, str]:
    """KPI name -> what is still open about it.

    The sheet is prose, not a schema: the first cell that names a KPI and the first that
    reads as a sentence. Anything it cannot pair is dropped rather than guessed — a
    question attached to the wrong KPI is worse than no question.
    """
    found = {}
    for row in rows:
        cells = [str(cell).strip() for cell in row if cell not in (None, "")]
        if len(cells) < 2:
            continue
        name, rest = cells[0], " ".join(cells[1:])
        if len(name) > 80 or len(rest) < 10:
            continue
        if _plain(name) in ("kpi", "indicateur", "id", "point", "sujet"):
            continue
        found[_plain(name)] = rest
    return found


def read_tracker(path) -> Tracker:
    """Read the tracker workbook, refusing rather than improvising when a sheet is absent."""
    with Workbook(path) as workbook:
        names = workbook.sheet_names
        registry = REGISTRY_SHEET if REGISTRY_SHEET in names else None
        if registry is None:
            # Not by position: a sheet added in front would silently redirect the whole
            # registry to the wrong table.
            for name in names:
                if _plain(name).startswith("kpi"):
                    registry = name
                    break
        if registry is None:
            raise WorkbookError(
                "No KPI sheet in this workbook. Sheets present: %s" % ", ".join(names)
            )
        points = {}
        for name in names:
            if _plain(name).startswith("points ouverts") or _plain(name) == "open points":
                points = read_open_points(workbook.rows(name))
                break
        return tracker_from_rows(workbook.rows(registry), open_points=points)
