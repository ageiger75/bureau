"""At what speed the screen may run, market by market.

The cockpit has said for weeks that it runs at two speeds and says which one it is on:
before the close, the warehouse, directional; after the close, the consolidation, and that
is the figure to quote. True, and stated globally, which made it almost useless — it told
a reader to distrust the warehouse everywhere because it cannot be trusted somewhere.

It is now measured. Twelve published months set against the warehouse, market by market,
growth against growth so no exchange rate enters, gives each market a distance and a
steadiness. Three shapes come out and they ask for three different things:

* **Aligned** — the two systems agree, month after month. Here the warehouse is not a
  degraded stand-in for the accounts: it says the same thing three weeks earlier. This is
  the majority of the estate and it is the finding that pays for the whole exercise.
* **Offset** — a constant displacement, steady enough to state as a number. A rule can be
  written for it, which is exactly the mechanical class: deterministic, repeating, and
  closable without anyone's judgement.
* **Unstable** — the distance moves month to month. No rule reaches this, because what
  moves it is decided at the close rather than computed. Here the screen waits.

Two properties of the grading matter more than the thresholds.

A market the file does not carry is **not graded**, and not graded is not aligned. The
failure this guards against is the one this repository keeps meeting: an absence that
looks like a pass. A market with too few months is in the same state, and says so.

And the sign is carried separately from the size. A distance that never changes sign over
twelve months is not a closing decision that lands differently each time — it is a
perimeter that one side counts and the other does not, and it grows as that perimeter
grows. That reads as instability in a standard deviation and is a different thing entirely.

Two readings of an average are refused here, and both were met in the real data.

An average near zero is not agreement. A market swinging six points either way averages to
nothing and agrees with nobody; the movement is the finding and the mean hides it. So a
grade never rests on the mean alone — a distance has to be both small *and* steady to be
called aligned.

And a displacement larger than the movement around it is its own state. A market can be
unstable and, underneath that, systematically apart by more than it moves: the close
explains what changes month to month, and something else explains the part that never
goes away. One market is in exactly that position, and it needs both questions asked of
two different people.

Like the weights and the plan, the measurements live outside the repository: they are
readings of the house's own business.
"""

from __future__ import annotations

import csv
import io
import os
from typing import Dict, List, Optional

from .budget import normalise_market

#: Grades, from the reader's point of view rather than the statistician's: each one names
#: what the screen is allowed to do, not how wide a distribution is.
ALIGNED = "ALIGNED"
OFFSET = "OFFSET"
UNSTABLE = "UNSTABLE"
NOT_GRADED = "NOT_GRADED"

#: Where aligned stops. Half a point of average distance and a point of movement around it:
#: at that size a market's direction, its rank against its neighbours and its answer to
#: "am I ahead or behind" are all unchanged, which is the only test that matters here.
ALIGNED_MEAN = 0.005
ALIGNED_SIGMA = 0.010

#: Where a displacement stops being statable as one number. Beyond this the distance is not
#: a constant with noise on it, it is a different distance each month.
OFFSET_SIGMA = 0.015

#: Below this, nothing is graded. A grade computed on a handful of months describes those
#: months. Set so that a market missing a third of the year cannot earn a pass.
MINIMUM_MONTHS = 10

REQUIRED = ("market", "months", "mean", "sigma", "low", "high", "evidence")

#: What the screen may do with each grade, in the words the screen uses.
SPEED = {
    ALIGNED: "l'entrepôt suffit pour piloter avant la clôture",
    OFFSET: "l'entrepôt, corrigé d'un décalage constant",
    UNSTABLE: "attendre la clôture sur ce marché",
    NOT_GRADED: "pas mesuré : ni l'un ni l'autre n'est autorisé à trancher",
}


class Market:
    """One market's distance between the two systems, and what it permits."""

    __slots__ = ("market", "months", "mean", "sigma", "low", "high", "evidence")

    def __init__(self, market, months, mean, sigma, low, high, evidence="") -> None:
        self.market = market
        #: How many months the distance was measured over.
        self.months = months
        #: Average signed distance, as a fraction. Positive: the consolidation grows faster.
        self.mean = mean
        #: How much that distance moves around its own average.
        self.sigma = sigma
        self.low = low
        self.high = high
        self.evidence = evidence

    @property
    def grade(self) -> str:
        if self.months < MINIMUM_MONTHS:
            return NOT_GRADED
        if abs(self.mean) <= ALIGNED_MEAN and self.sigma <= ALIGNED_SIGMA:
            return ALIGNED
        if self.sigma <= OFFSET_SIGMA:
            return OFFSET
        return UNSTABLE

    @property
    def sign_holds(self) -> bool:
        """Whether the distance never crossed zero across the whole window.

        Carried apart from the grade because it separates two causes a standard deviation
        cannot. A distance that swings either side of zero is a decision landing differently
        each close. One that stays on its side, however much it moves, is business one side
        counts and the other does not — and if the perimeter is growing, so is the distance.
        Same spread, different question, different person to ask.
        """
        return self.low * self.high > 0

    @property
    def displaced(self) -> bool:
        """Whether the systematic distance is larger than the month-to-month movement.

        Two causes can sit on one market. The close explains what moves; it does not
        explain a floor that never lifts. When the average exceeds its own spread, the
        displacement is the dominant term and it is a perimeter question — asked of
        different people, and answerable without waiting for any close.
        """
        return abs(self.mean) > self.sigma

    @property
    def speed(self) -> str:
        return SPEED[self.grade]


class Divergence:
    """Every market measured, and everything the file got wrong."""

    __slots__ = ("rows", "faults", "path")

    def __init__(self, rows, faults, path: str = "") -> None:
        self.rows = list(rows)
        self.faults = list(faults)
        self.path = path

    @property
    def usable(self) -> bool:
        return bool(self.rows) and not self.faults

    def of(self, market: str) -> Optional["Market"]:
        for row in self.rows:
            if row.market == market:
                return row
        return None

    def grade_of(self, market: str) -> str:
        """The grade for a market, and `NOT_GRADED` for one the file does not carry.

        The default is the whole point. A market absent from the measurement has not passed
        it, and every version of this cockpit that defaulted an absence to a pass produced a
        confident wrong answer within the week.
        """
        if not self.usable:
            return NOT_GRADED
        found = self.of(market)
        return found.grade if found is not None else NOT_GRADED

    def by_grade(self) -> Dict[str, List["Market"]]:
        grouped: Dict[str, List[Market]] = {}
        for row in self.rows:
            grouped.setdefault(row.grade, []).append(row)
        for rows in grouped.values():
            rows.sort(key=lambda row: (-abs(row.sigma), -abs(row.mean)))
        return grouped

    def steerable(self) -> List[str]:
        """Markets the warehouse can steer before the close, aligned or offset."""
        return sorted(row.market for row in self.rows
                      if row.grade in (ALIGNED, OFFSET))


def named(market: str) -> str:
    """The market as the rest of the cockpit spells it.

    The measurements are cut the way the consolidation names countries — upper case, and
    a handful of names of its own. The screen names them the way the plan does. Left
    unmatched, every market would grade as not measured and the screen would print
    "nothing has been checked here" on all of them, which is the failure this whole file
    exists to avoid: an absence dressed as a finding.

    Two steps, both already written elsewhere: the plan's own aliasing, then the rollups
    that fold a consolidation label into the country the business belongs to.
    """
    from .reference import ROLLUP

    normalised = normalise_market(market)
    return ROLLUP.get(normalised, normalised)


def _number(text: str) -> Optional[float]:
    try:
        return float((text or "").strip().replace(",", "."))
    except ValueError:
        return None


def load(path: str) -> Divergence:
    """Read the measurements, checking every rule they were written under.

    Faults are collected rather than raised, and any fault makes the whole file unusable —
    at which point every market grades as not measured. Degrading to "nothing is proven" is
    the only safe direction: the alternative is a half-read file granting a pass to markets
    whose rows failed to parse.
    """
    if not os.path.exists(path):
        return Divergence([], ["Fichier absent : %s" % path], path)

    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing = [name for name in REQUIRED if name not in header]
        if missing:
            return Divergence([], ["Colonnes manquantes : %s" % ", ".join(missing)], path)
        raw = list(reader)

    rows: List[Market] = []
    faults: List[str] = []
    seen: Dict[str, int] = {}

    for number, record in enumerate(raw, start=2):
        market = (record.get("market") or "").strip()
        if not market:
            continue
        if market in seen:
            faults.append("ligne %d : %s figure déjà ligne %d — aucune des deux retenue"
                          % (number, market, seen[market]))
            continue
        seen[market] = number

        months = _number(record.get("months", ""))
        mean = _number(record.get("mean", ""))
        sigma = _number(record.get("sigma", ""))
        low = _number(record.get("low", ""))
        high = _number(record.get("high", ""))
        if None in (months, mean, sigma, low, high):
            faults.append("ligne %d, %s : une valeur illisible" % (number, market))
            continue
        if sigma < 0:
            faults.append("ligne %d, %s : écart-type négatif" % (number, market))
            continue
        if low > high:
            faults.append("ligne %d, %s : minimum au-dessus du maximum" % (number, market))
            continue
        if not (low - 1e-9 <= mean <= high + 1e-9):
            # A mean outside its own range is a row assembled from two different windows,
            # and it would grade as steady while describing nothing.
            faults.append("ligne %d, %s : moyenne hors de l'intervalle mesuré"
                          % (number, market))
            continue

        rows.append(Market(named(market), int(months), mean, sigma, low, high,
                           (record.get("evidence") or "").strip()))

    if not rows and not faults:
        faults.append("aucune mesure dans %s" % path)
    return Divergence(rows, faults, path)


def current() -> "Divergence":
    from ..config import settings

    return load(str(settings.divergence_path))


def swing_needed(effect: float, share: float) -> Optional[float]:
    """How much a line's own growth must move to shift a market's growth by `effect`.

    A candidate explanation has to be big enough to produce the thing it explains, and the
    arithmetic that settles it is one division. A line worth `share` of a market moves that
    market's growth rate by its share times its own change in growth — so a small line needs
    an enormous swing, and past a point the swing it would need is one no business does.

    This has been needed three times and improvised three times. Twice a plausible cause
    was proposed for a gap it was far too small to make, and once a ratio landing near a
    known ownership share was taken for the cause and turned out to be a coincidence of
    size. Named here so the next candidate meets a number rather than an opinion:

        >>> round(swing_needed(0.013, 0.003), 1)   # a small line, a wide gap
        4.3

    Four hundred per cent of growth movement, on a line trading in both years. That is not
    a lead that needs investigating; it is a lead that is already answered.

    Returns nothing when the line has no share at all — an absent line explains nothing, and
    dividing by it would produce infinity and look like certainty.
    """
    if not share:
        return None
    return effect / share
