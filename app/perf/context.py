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

KINDS = (BASIS_CHANGE, ONE_OFF)

#: What each kind means for the reader, and — more usefully — what it means for the ask.
KIND_MEANING = {
    BASIS_CHANGE: (
        "The plan and the actual are not measured on the same basis here, so the gap "
        "between them is not a measure of trading."
    ),
    ONE_OFF: (
        "A one-off event sits inside this figure, so the gap is not the run rate."
    ),
}

KIND_QUESTION = {
    BASIS_CHANGE: "Should the plan be rebased, and what is the trend on a like-for-like basis?",
    ONE_OFF: "What does the gap look like with this event set aside?",
}


class Note:
    """One piece of context, scoped to a market, a channel and a starting month."""

    __slots__ = ("market", "channel", "since", "kind", "text", "source")

    def __init__(self, market, channel, since, kind, text, source="") -> None:
        self.market = market
        self.channel = channel
        #: The first period the note applies to. Everything before it is unaffected, which
        #: matters: a tax change in June does not explain a gap in April.
        self.since = since
        self.kind = kind
        self.text = text
        #: Who said so. A note nobody owns is a rumour with a date on it.
        self.source = source

    @property
    def meaning(self) -> str:
        return KIND_MEANING.get(self.kind, "")

    @property
    def question(self) -> str:
        return KIND_QUESTION.get(self.kind, "")

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


def load(path) -> Context:
    """Read the context file: market, channel, since, kind, note, source.

    A row whose kind is unknown is dropped rather than guessed at. Inventing a meaning for
    a word someone typed would attach a confident sentence to a note nobody wrote.
    """
    import csv

    from .budget import normalise_market
    from .mapping import normalise_channel

    notes: List[Note] = []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle):
            kind = str(record.get("kind") or "").strip().lower()
            text = str(record.get("note") or "").strip()
            if kind not in KINDS or not text:
                continue
            raw_channel = str(record.get("channel") or "").strip()
            notes.append(
                Note(
                    market=normalise_market(str(record.get("market") or "")),
                    channel=normalise_channel(raw_channel) if raw_channel else "",
                    since=str(record.get("since") or "").strip(),
                    kind=kind,
                    text=text,
                    source=str(record.get("source") or "").strip(),
                )
            )
    return Context(notes)


def current() -> Context:
    global _loaded
    if _loaded is None:
        from ..config import settings

        path = settings.context_path
        try:
            _loaded = load(path) if path.exists() else EMPTY
        except Exception:  # noqa: BLE001
            # A malformed context file must not take the cockpit down. The screen simply
            # loses its explanations, which it already knows how to do without.
            _loaded = EMPTY
    return _loaded


def reset() -> None:
    global _loaded
    _loaded = None


def notes_for(market: str, channel: str, period: str) -> List[Note]:
    return current().notes_for(market, channel, period)
