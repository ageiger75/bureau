"""The only module that knows where performance numbers come from.

Brief §35 Phase 6 asks for a clean seam between the data source and everything above it,
so that a warehouse can replace mock data without rewriting the application. That seam is
this file: the analytics engine, the routes and the templates never import `mock`.

When real data arrives, add a source that returns the same normalised `Dataset` and change
`current_source()`. Nothing above this line should need to move.
"""

from __future__ import annotations

from typing import List, Optional

import logging
import time

from ..config import settings
from ..util import now_iso
from . import mock
from .kpi import Kpi
from . import kpi_registry, tracker
from .model import Dataset


#: The query anchors on the last complete month, so the screen must not say "MTD" — a
#: label that promises a month in progress while showing a month that has closed.
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


#: How long a warehouse read stays good for. The screen shows a month that has closed, so
#: the figures behind it move only when the warehouse reprocesses a fact — once a day at
#: most. The query takes minutes. Re-reading it more often than this costs the reader
#: everything and buys nothing, and the screen still carries the moment of the read, so a
#: cached figure is never passed off as a fresh one.
CACHE_SECONDS = 3600

#: The same read, kept on disk. Without it every restart pays the query again, which is
#: the cost that actually bites: the server is restarted far more often than an hour goes
#: by. Only the warehouse rows are stored — primitives, no pickled objects — so a stale or
#: corrupt file can never do worse than force one more query.
CACHE_FILE = "warehouse-rows.json"

#: The twenty-four months behind the month on screen, cached apart from it and for far
#: longer. They are not the same kind of fact: this month's figures are still being
#: reprocessed, while a month that closed a year ago will not move again. Re-reading two
#: years of history on every click would buy nothing and cost the whole wait back.
HISTORY_CACHE_FILE = "warehouse-history.json"

#: The closed fiscal year of sell-in, kept beside the sell-out history and for the same
#: reason: it is a year that has finished and will not move again, while the query that
#: reads it is not cheap.
SELL_IN_HISTORY_CACHE_FILE = "warehouse-sell-in-history.json"

#: The customer readings. Cached hardest of the three: the query is a two-minute read that
#: has already hit the warehouse's own 300-second ceiling once, and a KPI moves monthly, so
#: a reading a few hours old is the same reading. What must never happen is the screen
#: waiting on it — a panel is worth a stale figure, never the whole page.
KPI_CACHE_FILE = "warehouse-kpis.json"

#: Le mois en cours, marché par marché. La plus petite lecture de ce fichier — un mois,
#: une dimension — et la seule que l'écran a le droit de payer sans cache chaud. Une
#: heure comme la lecture principale : le mois bouge chaque jour, pas chaque minute.
MONTH_CACHE_FILE = "warehouse-month.json"

#: A day. Bounded not by time but by the anchor: a cached history whose last month is not
#: the month on screen is re-read whatever its age, because that is the only staleness
#: that can actually mislead anyone.
HISTORY_CACHE_SECONDS = 24 * 3600

#: (dataset, read at, conflicts, unnamed markets, perimeter note, context generation).
#: Module level rather than on the instance: `current_source()` builds a new source per
#: request, and a cache that dies with the request is not a cache.
#:
#: The context generation is in the key because the notes are baked into the units when
#: they are built. Notes are written from a terminal against a running server, so without
#: it the file would be current, the units would not, and writing a note would appear to
#: do nothing.
_cached = None


def _cache_path(name: str = CACHE_FILE):
    return settings.budget_path.parent / name


def cache_clear() -> None:
    global _cached
    _cached = None


def cache_forget() -> None:
    """Drop the disk caches too. For `--refresh`, and for a warehouse known to have moved."""
    cache_clear()
    for name in (CACHE_FILE, HISTORY_CACHE_FILE, SELL_IN_HISTORY_CACHE_FILE,
                 KPI_CACHE_FILE, MONTH_CACHE_FILE):
        try:
            _cache_path(name).unlink()
        except OSError:
            pass


def kpi_cache_forget() -> None:
    """Drop the KPI reading alone, and leave the rest of the day's work in place.

    A new key in `KPI_READINGS` makes yesterday's KPI cache incomplete without making it
    stale, and the whole-cache reset would pay for the history read again to fix it —
    minutes of warehouse time, and a screen that opens empty in the meantime.
    """
    try:
        _cache_path(KPI_CACHE_FILE).unlink()
    except OSError:
        pass


def _read_disk_cache(name: str = CACHE_FILE, max_age: Optional[float] = None):
    """The last warehouse read, if it is still young enough to use.

    Anything unreadable is treated as absent rather than raised: a cache that can break a
    screen is worse than no cache, and the only cost of ignoring it is one query.

    `max_age` is resolved here and not in the signature: a default argument would capture
    `CACHE_SECONDS` at import and go on using that value after the constant changed, which
    is exactly the kind of quietly-wrong that a cache should never be allowed.
    """
    import json

    if max_age is None:
        max_age = CACHE_SECONDS
    path = _cache_path(name)
    try:
        with path.open(encoding="utf-8") as handle:
            stored = json.load(handle)
        stamp = float(stored["stamp"])
        rows = stored["rows"]
        read_at_text = str(stored["read_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(rows, list) or not rows:
        return None
    if time.time() - stamp >= max_age:
        return None
    return rows, stamp, read_at_text


def _write_disk_cache(
    rows, stamp: float, read_at_text: str, name: str = CACHE_FILE
) -> None:
    import json

    path = _cache_path(name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            # `default=str` because a warehouse hands back dates and decimals; every
            # consumer of these rows parses numbers from text already.
            json.dump(
                {"stamp": stamp, "read_at": read_at_text, "rows": rows},
                handle,
                default=str,
            )
    except OSError as exc:  # pragma: no cover — depends on the local filesystem
        LOG.info("warehouse: cache not written (%s)", exc)


def cached_history_rows():
    """The last history read from disk, or None. `(rows, when it was read)`.

    Shared with the terminal on purpose. Two years of history is the expensive read on
    this warehouse, and a command that ignored the screen's cache would pay it again in
    full — three times over, for someone looking at the year to date, then at a market,
    then at what carries no plan.
    """
    stored = _read_disk_cache(HISTORY_CACHE_FILE, max_age=HISTORY_CACHE_SECONDS)
    if stored is None:
        return None
    rows, _stamp, read_at_text = stored
    return rows, read_at_text


def store_history_rows(rows) -> None:
    """Keep a history read where the screen will find it, whoever paid for it."""
    _write_disk_cache(rows, time.time(), read_at(), HISTORY_CACHE_FILE)


def _read_kpi_cache():
    stored = _read_disk_cache(KPI_CACHE_FILE, max_age=HISTORY_CACHE_SECONDS)
    return None if stored is None else stored[0]


def _write_kpi_cache(rows) -> None:
    _write_disk_cache(rows, time.time(), read_at(), KPI_CACHE_FILE)


def month_cache_forget() -> None:
    """Oublier la seule lecture du mois en cours — quelques secondes à repayer, contre
    des minutes pour le reste. Pour une colonne ajoutée à la requête, comme pour les KPI."""
    try:
        _cache_path(MONTH_CACHE_FILE).unlink()
    except OSError:
        pass


def _read_month_cache():
    stored = _read_disk_cache(MONTH_CACHE_FILE)
    return None if stored is None else stored[0]


def _write_month_cache(rows) -> None:
    _write_disk_cache(rows, time.time(), read_at(), MONTH_CACHE_FILE)


def _sell_in_month(rows, sold_in, period: str):
    """Every sell-out row, and the sell-in rows of the month the screen is showing.

    The two sources close their month independently, and they can disagree — the
    consolidation is cut on a snapshot date, the sell-out warehouse on a transaction date.
    Filtering blindly on the sell-out month would then drop the entire sell-in perimeter
    from the screen and leave a calm-looking page missing a third of the Maison, which is
    the one failure this module exists to prevent. So a disagreement falls back to the
    sell-in's own latest month and says so.
    """
    wanted = period
    if sold_in:
        months = {str(r.get("period") or "") for r in sold_in}
        if period not in months:
            wanted = max(months) if months else period
            LOG.info(
                "warehouse: sell-in closes on %s, sell-out on %s — showing %s",
                wanted, period, wanted,
            )
    return [
        row for row in rows
        if not row.get("segment") or str(row.get("period") or "") == wanted
    ]


def last_read() -> str:
    """When the figures now in memory were read, or empty before the first read.

    Deliberately cheap and deliberately incapable of causing one: it reports what the
    cache holds and never fetches. A freshness check that could trigger a three-minute
    query would be a worse problem than the one it solves.
    """
    if _cached is None:
        return ""
    return _cached[0].as_of


def read_at() -> str:
    """When the warehouse was read, to the minute. UTC, like every other stamp here."""
    return now_iso()[:16].replace("T", " ") + " UTC"


LOG = logging.getLogger("ceoos.warehouse")


#: How each channel is named in prose. Without an entry a channel reaches the screen as
#: its bare code — "Dis", "Whoch", "Webp" — which is the vocabulary of a planning file,
#: not of a sentence anyone reads.
CHANNEL_WORDS = {
    "ecommerce": "e-commerce",
    "retail": "store sales",
    "marketplace": "marketplace sales",
    "spa": "spa",
    "cafe": "café",
    "direct selling": "direct selling",
    "webp": "e-retailers",
    "mktp": "marketplace sales",
    "tra": "travel retail",
    "dis": "distributors",
    "dpt": "department stores",
    "whoch": "chain wholesale",
    "whoin": "independent wholesale",
    "whosp": "spa wholesale",
    "tvc": "TV channels",
    "b2b": "hospitality and B2B",
    "copg": "corporate gifts",
}

#: Above this share of the plan, listing what is covered stops informing anyone: eleven
#: channel names read as noise, and the one fact worth having — what is still missing —
#: is buried at the end. Past it, the sentence inverts and names only the gap.
COVERAGE_INVERTS_ABOVE = 0.80

#: And how the segments outside it are named, so the sentence stays specific rather than
#: retreating into "everything else".
LEFT_OUT_WORDS = (
    ("WEBP", "e-retailers"),
    ("TRA", "travel retail"),
    ("DIS", "distributors"),
    ("DPT", "department stores"),
    ("WHOCH", "wholesale"),
    ("WHOIN", "wholesale"),
    ("WHOSP", "wholesale"),
    ("TVC", "TV channels"),
    ("B2B", "hospitality"),
    ("COPG", "corporate gifts"),
    ("DDS", "direct selling"),
)


def _listed(words) -> str:
    unique = []
    for word in words:
        if word not in unique:
            unique.append(word)
    if len(unique) < 2:
        return "".join(unique)
    return "%s and %s" % (", ".join(unique[:-1]), unique[-1])


def _perimeter_note(budget, units=()) -> str:
    """What the headline figure covers, and what it leaves out.

    Both halves are read from the data rather than written down. The sentence used to name
    the covered channels from what was on screen and the excluded ones from a fixed list —
    so the day stores arrived it announced "own retail and e-commerce only" and then put
    "store sales" among the things no source measures. A caveat that contradicts itself in
    one sentence costs more trust than no caveat.

    The share is read from the plan for the same reason: the mix changes every year, and a
    number written into a caveat is a caveat that quietly stops being true.
    """
    from .budget import segment_code

    channels = {unit.channel for unit in units}
    if not channels:
        return ""

    measured = 0.0
    total = 0.0
    missing_codes = []
    for line in budget.lines if budget else []:
        amount = line.budget or 0.0
        total += amount
        if line.channel in channels:
            measured += amount
        elif amount:
            missing_codes.append(segment_code(line.segment))

    covered = _listed([
        CHANNEL_WORDS.get(channel, channel) for channel in sorted(channels)
    ])
    if total <= 0:
        return "%s only." % covered.capitalize()

    share = measured / total
    left_out = _listed([
        word for code, word in LEFT_OUT_WORDS if code in set(missing_codes)
    ])

    # Near-complete coverage: say what is missing, not what is present. Naming eleven
    # channels to explain that almost everything is there tells the reader nothing they
    # could act on, and buries the one fact that matters at the end of the list.
    if share >= COVERAGE_INVERTS_ABOVE:
        if not left_out:
            return "Every channel the plan commits to."
        return (
            "Every channel except %s — about %.0f%% of the plan. Nothing here measures "
            "the rest yet." % (left_out, 100.0 * share)
        )

    tail = (
        " The rest is %s — invoiced to partners who resell, and no source measures it "
        "here yet." % left_out
        if left_out
        else ""
    )
    return "%s only — about %.0f%% of the plan.%s" % (
        covered.capitalize(), 100.0 * share, tail
    )


def _period_label(period: str, shipped: str = "") -> str:
    """'2026-07' -> 'July 2026 sales'. Falls back to the raw value rather than guessing."""
    parts = period.split("-")
    if len(parts) != 2:
        return "Sales"
    try:
        month = int(parts[1])
    except ValueError:
        return "Sales"
    if not 1 <= month <= 12:
        return "Sales"
    # "Last complete month" is not decoration: read on the 27th, a screen headed "July"
    # looks like a month-old screen unless it says why July is the freshest month there is.
    label = "%s %s sales · last complete month" % (_MONTHS[month - 1], parts[0])
    if shipped and shipped != period:
        # Only when they differ, which is not most months. A caveat printed every time is
        # a caveat read none of the time.
        other = shipped.split("-")
        if len(other) == 2 and other[1].isdigit() and 1 <= int(other[1]) <= 12:
            label += " · partner invoices to %s" % _MONTHS[int(other[1]) - 1]
    return label


def _inputs_generation():
    """What the units in memory were built from, beyond the warehouse rows.

    The notes, and the file Finance publishes. Either changing means the units held for
    the hour describe a screen that no longer exists — and the published file is dropped
    into `var/` from a terminal while the server runs, exactly as the notes are. Without
    this, a new closing file waited an hour or a restart to reach the top of the screen,
    while every command in the terminal already read it.
    """
    from . import context as context_module

    try:
        published = settings.actuals_path.stat().st_mtime
    except OSError:
        published = 0.0
    return (context_module.generation(), published)


def _published_month():
    """The month as Finance publishes it, whole, or nothing where the file is absent."""
    from . import actuals as actuals_module

    read = actuals_module.current(month=True)
    return read.totals() if read.lines else None


def _published_year():
    """Finance's own year to date, whole, or nothing where the file is absent.

    Handed over as the reading itself rather than folded by scope. A scope-by-scope fold
    makes the year's perimeter the intersection of two sources, which is the difference
    this file was adopted to remove — so the totals are taken from it directly.

    Absent, the year falls back to the warehouse against the workbook exactly as before:
    degraded, never wrong.
    """
    from . import actuals as actuals_module

    read = actuals_module.current(month=False)
    return read if read.lines else None


class MockSource:
    """Invented data, clearly labelled as such everywhere it is shown."""

    name = "mock"
    label = "Mock data"
    #: Shown in the interface. A cockpit that looks authoritative while running on
    #: invented numbers is worse than no cockpit at all.
    caveat = (
        "Every figure on this screen is invented for demonstration. No real market, "
        "person or product appears here."
    )

    def dataset(self, refresh: bool = False,
                wait_for_warehouse: bool = True) -> Dataset:
        return mock.dataset()

    def commitments(self) -> List["mock.MockCommitment"]:
        return mock.commitments()

    def client_kpis(self) -> List[Kpi]:
        return mock.client_kpis()

    def bulk_findings(self) -> List:
        return mock.bulk_findings()

    def month_to_date(self) -> List[dict]:
        return mock.month_to_date()

    def month_targets(self, period: str) -> dict:
        return mock.month_targets(period)


class SnowflakeSource:
    """Real figures, read from the warehouse through a named CLI connection.

    Deliberately incomplete: it refuses to serve anything until the queries in
    `queries.py` are written against the real schema. Returning empty lists instead would
    render a calm-looking cockpit on a business that has problems — the most expensive
    failure available to this product.
    """

    name = "snowflake"
    label = "Snowflake"
    caveat = ""

    def __init__(self) -> None:
        #: Filled by `dataset()`. Where the planning file and the warehouse disagree, and
        #: which markets have no named owner — both worth saying out loud on the screen.
        self.conflicts = []
        self.markets_without_owner = []
        #: What the headline figure leaves out, in the plan's own proportions. Computed
        #: from the file rather than written down, so it stays true when the file changes.
        self.perimeter_note = ""
        #: How much of the tracker this panel can actually see. Set when the KPIs are
        #: read, because "two of three hold" says nothing without it: the tracker follows
        #: two hundred and fourteen, and a reader who takes three for the whole is worse
        #: off than one who was told nothing.
        self.kpi_coverage = ""
        self.kpi_judged = None
        self.kpi_tracked = 0

    def _refuse_if_unwritten(self, *names: str) -> None:
        from . import queries

        missing = [n for n in names if not queries.ALL.get(n, "").strip()]
        if missing:
            raise NotImplementedError(
                "These queries are not written yet: %s. See app/perf/queries.py — it "
                "describes exactly what each must return." % ", ".join(missing)
            )

    def _budget(self):
        """The planning workbook, or a refusal.

        Not optional. Without it almost every market arrives with no commitment to be
        measured against, so nothing is a gap, nothing is a win, and the screen renders
        calm — the failure this whole module is arranged to avoid. Better to say the file
        is missing than to show a business with no problems.
        """
        from . import budget as budget_module

        if not settings.has_budget_file:
            raise NotImplementedError(
                "The planning workbook is missing. The warehouse supplies actuals; the "
                "budget comes from the file, because the targets in Snowflake are not "
                "always filled in. Copy it to %s and restart."
                % settings.budget_path
            )
        return budget_module.load(settings.budget_path)

    def _sell_in_rows(self, mapping, queries, warehouse):
        """Invoiced-to-a-reseller revenue, or nothing at all.

        Nothing at all is a real answer here and not a failure: roughly two fifths of the
        plan is simply not measured yet, the screen already says so, and refusing to render
        the other three fifths over it would help nobody. What must not happen is the
        absence passing unnoticed — hence the note, and hence the register entry that keeps
        saying "not measured" until this returns something.
        """
        if not queries.SELL_IN.strip():
            return []
        try:
            return mapping.sell_in_rows(
                warehouse.rows(queries.SELL_IN, label="SELL_IN")
            )
        except Exception as exc:  # noqa: BLE001 — one source failing is not all of them
            LOG.info("warehouse: sell-in unavailable (%s)", exc)
            return []

    def _history(self, queries, warehouse, anchor: str):
        """Twenty-four months behind the anchor month, or nothing.

        Nothing is survivable and says so on the screen: without it the cockpit compares
        one month to one plan, which is what it did before this existed. What it must not
        do is fail the whole render — the history is context around the figures, not the
        figures.

        Cached apart from the current month and validated against the anchor rather than
        against the clock. A history whose last month is the month on screen is current by
        construction, however old the file is; one that ends earlier is stale however
        fresh, because the month everyone is reading would be missing from its own trend.
        """
        from . import history as history_module

        if not queries.SALES_HISTORY.strip():
            return None

        stored = _read_disk_cache(HISTORY_CACHE_FILE, max_age=HISTORY_CACHE_SECONDS)
        if stored is not None:
            rows, _stamp, read_at_text = stored
            built = history_module.from_rows(rows)
            if not anchor or built.latest_period == anchor:
                LOG.info(
                    "warehouse: history from cache (%d tracks, read %s)",
                    len(built),
                    read_at_text,
                )
                return built
            LOG.info(
                "warehouse: cached history ends %s, screen shows %s — re-reading",
                built.latest_period,
                anchor,
            )

        try:
            rows = warehouse.rows(queries.SALES_HISTORY, label="SALES_HISTORY")
        except Exception as exc:  # noqa: BLE001 — one source failing is not all of them
            LOG.info("warehouse: history unavailable (%s)", exc)
            return None
        if not rows:
            return None
        _write_disk_cache(rows, time.time(), read_at(), HISTORY_CACHE_FILE)
        return history_module.from_rows(rows)

    def _sell_in_record(self, queries, warehouse, sell_in_rows, budget):
        """What the sell-in plan asks, against what partners have been buying.

        Keyed by market and channel so the units can carry it. Nothing at all is a
        survivable answer and the usual one until the closed year is readable: the screen
        then shows sell-in with its month and without its trajectory, which is what it did
        before this existed.
        """
        from . import history as history_module

        if not queries.SELL_IN_HISTORY.strip() or not sell_in_rows:
            return {}

        stored = _read_disk_cache(SELL_IN_HISTORY_CACHE_FILE, max_age=HISTORY_CACHE_SECONDS)
        if stored is not None:
            closed = stored[0]
        else:
            try:
                closed = warehouse.rows(
                    queries.SELL_IN_HISTORY, label="SELL_IN_HISTORY"
                )
            except Exception as exc:  # noqa: BLE001 — one source failing is not all
                LOG.info("warehouse: sell-in history unavailable (%s)", exc)
                return {}
            if closed:
                _write_disk_cache(
                    closed, time.time(), read_at(), SELL_IN_HISTORY_CACHE_FILE
                )

        moved = history_module.sell_in_trajectories(
            closed, sell_in_rows, budget, history_module.explained_pairs()
        )
        return {
            (m.market, m.channel): m.sentence for m in moved if m.sentence
        }

    def dataset(self, refresh: bool = False, wait_for_warehouse: bool = True) -> Dataset:
        """The screen's figures.

        `wait_for_warehouse` is false wherever somebody is waiting in front of the result.
        An expired cache then serves anyway, with its age stated, instead of holding the
        page open for the minutes a full read costs — because a cockpit that occasionally
        takes three minutes to open is a cockpit nobody opens. Refreshing becomes something
        the reader asks for, not something that happens to them.

        The rule this follows is the one the whole product runs on: this screen reads what
        has been prepared. It does not go and fetch while its reader waits.
        """
        global _cached

        from . import context as context_module

        if not refresh and _cached is not None:
            dataset, stored_at, conflicts, unnamed, note, generation = _cached
            if (
                time.time() - stored_at < CACHE_SECONDS
                and generation == _inputs_generation()
            ):
                self.conflicts = conflicts
                self.markets_without_owner = unnamed
                self.perimeter_note = note
                return dataset

        self._refuse_if_unwritten("SALES_AND_DRIVERS")

        from . import mapping, queries, warehouse

        # Before the network, not after: a missing local file is not worth a round trip to
        # the warehouse, and the refusal is clearer when nothing has been read yet.
        budget = self._budget()

        stored = None if refresh else _read_disk_cache()
        if stored is None and not refresh and not wait_for_warehouse:
            # Expired is not absent. An hour-old reading answers the same questions as a
            # fresh one; a page that hangs for minutes answers none.
            stored = _read_disk_cache(max_age=float("inf"))
            if stored is not None:
                LOG.info("warehouse: serving an expired cache rather than making the "
                         "reader wait")
        if stored is not None:
            rows, stamp, read_at_text = stored
            LOG.info("warehouse: %d rows from cache, read %s", len(rows), read_at_text)
        else:
            rows = warehouse.rows(queries.SALES_AND_DRIVERS, label="SALES_AND_DRIVERS")
            sold_in = self._sell_in_rows(mapping, queries, warehouse)
            # Sell-in comes from a different source with a different cadence, so it is
            # read separately and its absence costs its own lines rather than the whole
            # screen. Read here and not after the cache branch: what gets written to
            # disk below is this concatenation, so appending again on a cache hit would
            # count every invoiced euro twice.
            rows = rows + sold_in
            stamp = time.time()
            read_at_text = read_at()

        if not rows:
            raise NotImplementedError(
                "The query ran and returned nothing. An empty cockpit and a healthy "
                "business look identical, so this refuses rather than renders."
            )

        period = str(rows[0].get("period") or "")
        # Read after the current month and keyed to it, so a history that ends on an older
        # month is caught and re-read rather than quietly ageing the trend by a month.
        history = self._history(queries, warehouse, period)

        # Sell-in rows survive the cache as part of the concatenation above, so they are
        # recovered from it rather than re-read: a screen that grew its own revenue by
        # being looked at twice is the worst failure available here.
        sold_in = [row for row in rows if row.get("segment")]
        sell_in_record = self._sell_in_record(queries, warehouse, sold_in, budget)

        # The screen is a month; the year to date is a year. Sell-in now arrives with
        # every month of the fiscal year, so the units take only the one on screen —
        # otherwise a market would appear four times, once per month, all called July.
        current = _sell_in_month(rows, sold_in, period)
        mapped = mapping.units_from_rows(
            current, budget=budget, history=history, sell_in_record=sell_in_record
        )
        # Kept on the source, not on the dataset: they describe the plumbing, not the
        # business, and the screen shows them where it shows the caveat.
        self.conflicts = mapped.conflicts
        self.markets_without_owner = mapped.markets_without_owner
        self.perimeter_note = _perimeter_note(budget, mapped.units)

        # The month on the headline is the sell-out month. When the consolidation closes
        # earlier, the figure beside it holds a different month of sell-in, and saying
        # "July 2026 sales" over a total that carries June's shipments is the kind of
        # quiet inaccuracy that costs a screen its standing the first time anyone checks
        # it against the accounts.
        shipped = {str(r.get("period") or "") for r in current if r.get("segment")}
        built = Dataset(
            period_label=_period_label(period, max(shipped) if shipped else ""),
            # The moment of the read, not the period — and to the minute, because the
            # warehouse is not yet stable within a day. Sell-out facts are still being
            # reprocessed on recent months, so the same query run hours apart returns
            # different figures for some markets. Two screens that disagree are a
            # scandal; two screens stamped an hour apart are a fact about the pipeline.
            # The moment of the *read*, which a cached screen inherits rather than
            # restamps: the whole point of saying when is that it stays said.
            as_of=read_at_text,
            units=mapped.units,
            # The year takes its terms from the published file wherever that file covers a
            # scope, exactly as the month does. Read from the year-to-date sheet of the
            # same workbook — the one that is already cumulative through its own month.
            ytd=history.ytd(period, budget=budget, sell_in=sold_in,
                            published=_published_year())
            if history is not None
            else None,
            published_month=_published_month(),
        )
        if stored is None:
            _write_disk_cache(rows, stamp, read_at_text)
        _cached = (
            built,
            stamp,
            self.conflicts,
            self.markets_without_owner,
            self.perimeter_note,
            _inputs_generation(),
        )
        return built

    def commitments(self) -> List["mock.MockCommitment"]:
        self._refuse_if_unwritten("COMMITMENTS")
        raise NotImplementedError("Commitment mapping not written yet.")

    def client_kpis(self) -> List[Kpi]:
        """Warehouse readings, judged against the tracker the business maintains.

        Both halves are required and neither substitutes for the other. Readings without a
        registry are numbers nobody can score; a registry without readings is a list of
        intentions. Missing either, this refuses — the panel then says it is not connected,
        which is true, rather than showing green on what it cannot see.
        """
        self._refuse_if_unwritten("KPI_READINGS")
        if not settings.has_kpi_file:
            raise NotImplementedError(
                "The KPI tracker is not on this machine, so no reading can be judged. "
                "Expected at %s." % settings.kpi_path
            )
        from . import queries, warehouse

        registry = tracker.read_tracker(settings.kpi_path)
        # Its own cache, and a long one. The query is a two-minute read that has hit the
        # warehouse's own timeout at least once; hanging the screen on it would trade a
        # panel for the whole page. A KPI moves monthly — a reading a day old is the same
        # reading.
        rows = _read_kpi_cache()
        if rows is None:
            rows = warehouse.rows(queries.KPI_READINGS, label="KPI_READINGS")
            _write_kpi_cache(rows)
        report = kpi_registry.join_report(registry, rows)
        self.kpi_coverage = _kpi_coverage(report, registry)
        #: The denominator alone, for the decision screen. The rest of the sentence —
        #: which keys nothing claims, which are matched and unjudgeable — is wiring, and
        #: wiring belongs on System status.
        self.kpi_judged = len(report.kpis)
        self.kpi_tracked = len(registry.entries)
        return report.kpis

    def month_to_date(self) -> List[dict]:
        """Le mois en cours, marché par marché, jusqu'au dernier jour lu.

        Son propre cache, court. La requête est bornée au mois et c'est ce qui l'autorise
        ici : une lecture de quelques secondes peut être payée à l'ouverture, une lecture
        de trois minutes jamais — voir `client_kpis` pour la règle inverse.
        """
        self._refuse_if_unwritten("MONTH_TO_DATE")
        from . import queries, warehouse

        rows = _read_month_cache()
        if rows is None:
            rows = warehouse.rows(queries.MONTH_TO_DATE, label="MONTH_TO_DATE")
            _write_month_cache(rows)
        return rows

    def month_targets(self, period: str) -> dict:
        """L'objectif sell-out du mois par marché, tel que le plan l'écrit."""
        from . import month as month_module

        return month_module.targets_from_budget(self._budget(), period)

    def bulk_findings(self) -> List:
        """The markets whose two bases disagree — and only those.

        Read from the KPI cache and never from the warehouse: this is a second reading of
        rows the screen already pays for, and a page load must not be able to start a
        two-minute query. A cold cache therefore returns nothing, which is the honest
        answer — the pair has not been read yet — and the block simply does not appear.

        Only the markets where the two bases tell different stories. A market whose bulk
        moves with the rest of it has nothing to say here, and printing it would put the
        reader back to scanning for the one line that matters.
        """
        from . import bulk

        rows = _read_kpi_cache()
        if not rows:
            return []
        return [found for found in bulk.material(rows) if found.changes_the_verdict]


def _kpi_coverage(report, registry) -> str:
    """One sentence on what this panel can see, and what it cannot.

    Deliberately a count and not a list. The panel exists to show what is off; two
    hundred rows named one by one would bury the one that is. But the denominator has to
    be said, or three KPIs read as the whole customer picture.
    """
    parts = ["%d of the tracker's %d KPIs are wired to a reading and a target"
             % (len(report.kpis), len(registry.entries))]
    if report.unmatched_keys:
        parts.append(
            "%d measured figure%s has no row claiming it"
            % (len(report.unmatched_keys), "" if len(report.unmatched_keys) == 1 else "s")
        )
    if report.without_target:
        parts.append("%d matched but cannot be judged" % len(report.without_target))
    return ". ".join(parts) + "."


def current_source():
    """The active source.

    Mock unless the environment asks otherwise, and it has to ask twice — a source name
    and a connection name. A warehouse is never reached by default.
    """
    if settings.reads_warehouse:
        return SnowflakeSource()
    return MockSource()
