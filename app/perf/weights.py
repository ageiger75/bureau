"""The one place the reader's own judgement enters the ranking.

The order of subjects on this screen is `€ gap × persistence × acceleration × weight`.
Three of those four are measurements: they come out of the data and nobody argues with
them. The fourth is a judgement, it sat at 1.0 everywhere, and a ranking with no judgement
in it ranks by size alone — which is not what a plan is for.

Two properties make this file worth having rather than hard-coding the same numbers:

* **It is edited by hand, and often.** A strategy is re-read a few times a year, not daily.
  So the format is a spreadsheet anyone can open, every row carries its own evidence, and
  the file lives outside the repository with the other real figures.
* **It fails loudly.** A weight is a multiplier on money; a typo moves a subject up or down
  the list the CEO reads on a Monday. Every rule the file was written under is checked on
  load, and a row that breaks one is refused and named — never clamped, never rounded into
  range, never silently dropped. A file that half-loads is worse than one that does not.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional, Tuple

#: The band the weights were written in. Deliberately narrow: the weight multiplies euros,
#: and at this ratio a judgement can move a one-million gap above a two-million one without
#: ever moving it above five. Wider, and the judgement would drown the measurement it is
#: meant to nuance.
FLOOR = 0.70
CEILING = 1.50

#: Neutral, and the only value an unevidenced row may carry. The rule comes from the brief
#: the file was written to: silence in the strategy is answered with 1.0, never with a
#: guess from general knowledge — a weight invented in good faith moves the reader's
#: attention without anyone, including them, knowing why.
NEUTRAL = 1.0

FIRM = "FIRM"
INFERRED = "INFERRED"
ABSENT = "ABSENT"
CONFIDENCES = (FIRM, INFERRED, ABSENT)

REQUIRED = ("market", "channel", "weight", "confidence", "evidence", "reasoning")


class Weight:
    """One judgement, with what it rests on."""

    __slots__ = ("market", "channel", "weight", "confidence", "evidence", "reasoning")

    def __init__(self, market: str, channel: str, weight: float, confidence: str,
                 evidence: str, reasoning: str) -> None:
        self.market = market
        self.channel = channel
        self.weight = weight
        self.confidence = confidence
        self.evidence = evidence
        self.reasoning = reasoning

    @property
    def scope(self) -> str:
        return "%s/%s" % (self.market, self.channel) if self.channel else self.market

    @property
    def is_neutral(self) -> bool:
        return abs(self.weight - NEUTRAL) < 1e-9


class Weights:
    """Every judgement in the file, and everything the file got wrong.

    Faults are carried rather than raised: a reader who has just edited a spreadsheet needs
    to see all of its problems at once, not the first one. What they must never see is a
    ranking computed from a file that half-parsed, so `usable` is false whenever anything
    was refused.
    """

    __slots__ = ("rows", "faults", "path")

    def __init__(self, rows, faults, path: str = "") -> None:
        self.rows = list(rows)
        self.faults = list(faults)
        self.path = path

    @property
    def usable(self) -> bool:
        return not self.faults

    @property
    def markets(self) -> List[str]:
        return sorted({row.market for row in self.rows})

    def weight_for(self, market: str, channel: str = "") -> float:
        """The judgement for this unit, channel first.

        A market-level row covers all of its channels; a channel row overrides it for that
        one. Nothing found is 1.0 — a market the file does not mention is a market the
        strategy did not mention, which is the answer and not a hole.
        """
        if not self.usable:
            return NEUTRAL
        by_scope = {row.scope: row.weight for row in self.rows}
        if channel and "%s/%s" % (market, channel) in by_scope:
            return by_scope["%s/%s" % (market, channel)]
        return by_scope.get(market, NEUTRAL)

    def unknown_scopes(self, known: Tuple[Tuple[str, str], ...]) -> List[str]:
        """Rows naming business the plan does not carry.

        Not a fault — a market may be renamed or a channel dropped between two readings of
        the strategy — but a weight on a scope that does not exist is a judgement that will
        never apply, and saying so is cheaper than wondering why nothing moved.
        """
        markets = {market for market, _channel in known}
        pairs = {"%s/%s" % pair for pair in known}
        return sorted(
            row.scope for row in self.rows
            if (row.scope not in pairs) and (row.market not in markets)
        )


def load(path: str) -> Weights:
    """Read the file, checking every rule it was written under."""
    if not os.path.exists(path):
        return Weights([], ["Fichier absent : %s" % path], path)

    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            return Weights([], ["Colonnes manquantes : %s" % ", ".join(missing)], path)
        raw = list(reader)

    rows: List[Weight] = []
    faults: List[str] = []
    seen: Dict[str, int] = {}

    for number, record in enumerate(raw, start=2):
        market = (record.get("market") or "").strip()
        if not market:
            continue
        channel = (record.get("channel") or "").strip()
        scope = "%s/%s" % (market, channel) if channel else market

        text = (record.get("weight") or "").strip().replace(",", ".")
        try:
            weight = float(text)
        except ValueError:
            faults.append("ligne %d, %s : poids illisible (%r)" % (number, scope, text))
            continue

        if not (FLOOR - 1e-9 <= weight <= CEILING + 1e-9):
            # Refused rather than clamped. A weight outside the band is a decision nobody
            # made — clamping it would enact a different one and say nothing.
            faults.append("ligne %d, %s : poids %.2f hors des bornes %.2f–%.2f"
                          % (number, scope, weight, FLOOR, CEILING))
            continue

        confidence = (record.get("confidence") or "").strip().upper()
        if confidence not in CONFIDENCES:
            faults.append("ligne %d, %s : confiance %r inconnue (%s)"
                          % (number, scope, confidence, ", ".join(CONFIDENCES)))
            continue

        evidence = (record.get("evidence") or "").strip()
        if confidence == ABSENT and abs(weight - NEUTRAL) > 1e-9:
            faults.append("ligne %d, %s : ABSENT impose 1.00, pas %.2f — sans preuve, "
                          "un poids est une invention" % (number, scope, weight))
            continue
        if confidence != ABSENT and not evidence:
            faults.append("ligne %d, %s : %s sans preuve citée"
                          % (number, scope, confidence))
            continue

        if scope in seen:
            faults.append("ligne %d, %s : déjà défini ligne %d — deux jugements sur le "
                          "même périmètre, et rien ne dit lequel gagne"
                          % (number, scope, seen[scope]))
            continue
        seen[scope] = number

        rows.append(Weight(market, channel, weight, confidence, evidence,
                           (record.get("reasoning") or "").strip()))

    return Weights(rows, faults, path)


def current() -> Weights:
    """The weights as the reader's file has them right now.

    Read on every build rather than cached: the file is edited by hand between two looks at
    the screen, and a judgement that needs a restart to take effect is a judgement nobody
    will bother to make.
    """
    from ..config import settings

    return load(str(settings.weights_path))
