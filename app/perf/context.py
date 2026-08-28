"""What happened that the numbers cannot say.

The cockpit knows two ways a gap can appear: the business moved, or the measurement broke.
There is a third, and it is the one most likely to send the wrong question to the wrong
person — the number is correct on both sides and they are not measured on the same basis.

Brazil is the case that revealed it. A tax change moved net sales without moving gross
sales, months after the plan was committed. The gap against plan is real in the accounts
and says nothing at all about how the market is trading. Ranking it as a commercial
failure would put a country manager in front of a question about a government decision.

These notes are not corrections. Nothing here changes a figure — a cockpit that quietly
adjusts numbers towards what someone expected is worth less than one that shows an
uncomfortable number and says why it is uncomfortable. What they change is the *question*.

Like the planning workbook and the directory, they are organisational knowledge rather
than measurement, so they live in a local file that git ignores.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

#: The plan and the actual are not measured on the same basis. A tax change, a transfer
#: pricing revision, a change of accounting standard, a currency rebasing.
BASIS_CHANGE = "basis_change"

#: Something happened once and will not repeat. A store closure, a shipment pulled into
#: the previous month, a one-off order.
ONE_OFF = "one_off"

#: The plan and the accounts draw a boundary in different places. Nothing changed and
#: nobody is wrong about a number — a customer sits on the line between two segments, and
#: each source files it on its own side. The market total is identical; only the split
#: differs.
#:
#: Left unsaid this is worse than a single wrong figure, because it produces two: one
#: segment above plan and its neighbour below it by exactly the same amount, both stated
#: with confidence, both meaningless.
RECLASSIFIED = "reclassified"

#: Trading has deliberately stopped, and will resume when a condition is met. A partner
#: on credit hold, a market awaiting a licence, a listing suspended.
#:
#: Distinct from a one-off, which is an event in the past: this is a live decision, and
#: the money really is missing while it lasts. So it is *not* among the kinds where the
#: gap stops being about trading — the euros are gone and someone owns them. What changes
#: is the question. Asking a country manager why sales collapsed, when the answer is that
#: the Maison chose to stop shipping to a customer who is not paying, wastes the meeting
#: and the credibility of the screen. The question is what unblocks it and what is owed.
ON_HOLD = "on_hold"

KINDS = (BASIS_CHANGE, ONE_OFF, RECLASSIFIED, ON_HOLD)

#: Kinds where the gap is not a statement about trading, so nobody is asked to answer for
#: it. A gap that is real in the accounts and belongs to no one's performance must never
#: reach "People to push": handing it over would be this product's most expensive kind of
#: mistake — confidently wrong, about a named human being.
NOT_TRADING = frozenset({BASIS_CHANGE, RECLASSIFIED})

#: What each kind means for the reader, and — more usefully — what it means for the ask.
KIND_MEANING = {
    BASIS_CHANGE: (
        "The plan and the actual are not measured on the same basis here, so the gap "
        "between them is not a measure of trading."
    ),
    ONE_OFF: (
        "A one-off event sits inside this figure, so the gap is not the run rate."
    ),
    ON_HOLD: (
        "Trading here is deliberately stopped until a condition is met. The revenue is "
        "genuinely missing, and the reason is known — so the gap is real and the question "
        "is not about commercial performance."
    ),
    RECLASSIFIED: (
        "The plan and the accounts file this revenue under different segments, so the gap "
        "here is a boundary rather than a result. The market total is unaffected."
    ),
}

KIND_QUESTION = {
    BASIS_CHANGE: "Should the plan be rebased, and what is the trend on a like-for-like basis?",
    ONE_OFF: "What does the gap look like with this event set aside?",
    RECLASSIFIED: (
        "Which classification is right — and is the neighbouring segment's plan wrong by "
        "the same amount?"
    ),
    ON_HOLD: (
        "What has to happen for this to resume, how much is owed, and what does the delay "
        "cost by the time it does?"
    ),
}


def resolve_channel(name: str) -> str:
    """A channel from whatever the writer had in front of them.

    They may type a channel the screen shows (`retail`), a segment label the plan uses
    (`WEBP - Web Partners`), or a bare segment code (`WEBP`). All three name the same
    thing, and asking someone to remember which vocabulary this file wants would be a good
    way to have the note written wrongly or not at all.
    """
    from .budget import channel_of, segment_code
    from .mapping import normalise_channel

    raw = (name or "").strip()
    if not raw:
        return ""
    if "-" in raw:
        return channel_of(raw)
    direct = normalise_channel(raw)
    from .mapping import CHANNEL_ALIASES

    if raw.strip().lower() in CHANNEL_ALIASES:
        return direct
    # Not a channel this cockpit names, so read it as a segment code — `WEBP`, `DIS`.
    coded = channel_of(segment_code(raw))
    return coded or direct


class Note:
    """One piece of context, scoped to a market, a channel and a starting month."""

    __slots__ = ("market", "channel", "since", "kind", "text", "source", "asked")

    def __init__(self, market, channel, since, kind, text, source="", asked="") -> None:
        self.market = market
        self.channel = channel
        #: The first period the note applies to. Everything before it is unaffected, which
        #: matters: a tax change in June does not explain a gap in April.
        self.since = since
        self.kind = kind
        self.text = text
        #: Who said so. A note nobody owns is a rumour with a date on it.
        self.source = source
        #: The question to ask instead of the kind's default. The default is a good guess
        #: at what a reader should do next; the person writing the note often knows better,
        #: and sometimes knows the default question has already been answered. Showing
        #: someone a question they have settled is a fast way to teach them to skip the
        #: panel.
        self.asked = asked

    @property
    def meaning(self) -> str:
        return KIND_MEANING.get(self.kind, "")

    @property
    def question(self) -> str:
        return self.asked or KIND_QUESTION.get(self.kind, "")

    def applies_to(self, market: str, channel: str, period: str) -> bool:
        if self.market and self.market != market:
            return False
        # An empty channel means the note covers the whole market, which is usually right:
        # a tax change does not stop at the shop door.
        if self.channel and self.channel != channel:
            return False
        if self.since and period and period < self.since:
            return False
        return True


class Context:
    def __init__(self, notes: Optional[Sequence[Note]] = None) -> None:
        self.notes: List[Note] = list(notes or [])

    def __len__(self) -> int:
        return len(self.notes)

    def notes_for(self, market: str, channel: str, period: str) -> List[Note]:
        return [n for n in self.notes if n.applies_to(market, channel, period)]

    def markets(self) -> List[str]:
        return sorted({n.market for n in self.notes if n.market})


EMPTY = Context()

_loaded: Optional[Context] = None

#: The timestamp the notes were read at, so a file that changed is noticed.
_stamp: Optional[float] = None


def load(path) -> Context:
    """Read the context file: market, channel, since, kind, note, source.

    A row whose kind is unknown is dropped rather than guessed at. Inventing a meaning for
    a word someone typed would attach a confident sentence to a note nobody wrote.
    """
    import csv

    from .budget import normalise_market

    notes: List[Note] = []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle):
            market_cell = str(record.get("market") or "").strip()
            # A line the writer commented out is documentation, not a note. Reading it as
            # one puts a market nobody named on the screen — and the example file, copied
            # verbatim, would have created exactly that.
            if market_cell.startswith("#"):
                continue
            kind = str(record.get("kind") or "").strip().lower()
            text = str(record.get("note") or "").strip()
            if kind not in KINDS or not text:
                continue
            raw_channel = str(record.get("channel") or "").strip()
            notes.append(
                Note(
                    market=normalise_market(market_cell),
                    channel=resolve_channel(raw_channel),
                    since=str(record.get("since") or "").strip(),
                    kind=kind,
                    text=text,
                    source=str(record.get("source") or "").strip(),
                    asked=str(record.get("question") or "").strip(),
                )
            )
    return Context(notes)


def _stamp_of(path) -> float:
    """When the file last changed, or 0.0 if there is no file."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def current() -> Context:
    """The notes as they are on disk right now.

    Re-read when the file changes, and not only once per process. Notes are written from a
    terminal while the server is running — that is the whole point of a command rather than
    a file to edit — so a context loaded once and kept would mean writing a note, reloading
    the screen, and seeing nothing. The natural conclusion is that notes do not work.

    The check is a `stat` per call, which costs nothing next to reading the file, and the
    file is read again only when its timestamp has actually moved.
    """
    global _loaded, _stamp
    from ..config import settings

    path = settings.context_path
    stamp = _stamp_of(path)
    if _loaded is None or stamp != _stamp:
        try:
            _loaded = load(path) if path.exists() else EMPTY
        except Exception:  # noqa: BLE001
            # A malformed context file must not take the cockpit down. The screen simply
            # loses its explanations, which it already knows how to do without.
            _loaded = EMPTY
        _stamp = stamp
    return _loaded


def generation() -> float:
    """A value that changes whenever the notes do.

    Anything holding units built with these notes baked in can compare it and know to
    rebuild. Without it the notes would be current and the screen would still be showing
    the units it assembled before they changed.
    """
    current()
    return _stamp


def install(notes: Sequence[Note]) -> None:
    """Use these notes instead of the file, until `reset()`.

    A seam for tests and nothing else, but a real one: setting `_loaded` by hand is not
    enough, because `current()` compares the file's timestamp and would reload over the
    top. Two pieces of state that must move together is exactly the kind of thing to put
    behind one function rather than leave to whoever remembers both.
    """
    global _loaded, _stamp
    from ..config import settings

    _loaded = Context(notes)
    _stamp = _stamp_of(settings.context_path)


def reset() -> None:
    global _loaded, _stamp
    _loaded = None
    _stamp = None


def notes_for(market: str, channel: str, period: str) -> List[Note]:
    return current().notes_for(market, channel, period)
