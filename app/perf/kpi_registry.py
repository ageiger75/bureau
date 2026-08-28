"""Joining warehouse readings to the tracker that says what they should be.

The warehouse returns `scope · kpi_key · period · value`. The tracker holds a KPI's
definition, its target, which way it is supposed to move, and who owns it. Neither is
usable alone, and the join between them is the one place where a wrong guess is invisible:
a reading matched to the wrong row is scored against somebody else's target and reads as a
finding.

So the match is made in three passes of decreasing confidence, and never by resemblance:

1. **The tracker's own id equals the key.** A claim, and the only one that is unambiguous.
2. **An alias, all of whose words appear in the label.** Every word, not any — `nps` alone
   fits four different KPIs, and a screen that picks one of them is worse than a screen
   that admits it cannot tell.
3. **Nothing.** The key is reported unmatched rather than attached to a near-miss.

What did not match is not an error to be swallowed. It is the list of what somebody has to
name, and the terminal prints it.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

from . import kpi as rules
from .tracker import Entry, Tracker

#: The whole-group scope, as the warehouse writes it. Readings at market scope exist too;
#: the panel reads the group and the market rows feed the per-market signals.
GROUP_SCOPE = "LOEP"


def _words(text) -> frozenset:
    """The distinct words of a name, unaccented and unpunctuated.

    "E-commerce", "e commerce" and "ECOMMERCE" have to be the same word, or an alias will
    match on one spelling of a sheet and silently stop matching when somebody re-types it.
    """
    if text is None:
        return frozenset()
    raw = "".join(
        char for char in unicodedata.normalize("NFKD", str(text))
        if not unicodedata.combining(char)
    ).lower()
    return frozenset(part for part in re.split(r"[^a-z0-9]+", raw) if part)


#: Warehouse key -> candidate names. Each candidate matches only when *all* of its words
#: appear in a tracker label. Several per key because the sheet is written by people: the
#: point is not to cover every phrasing, it is that an uncovered one is reported by name
#: instead of being attached to whichever row looked closest.
ALIASES: Dict[str, Tuple[str, ...]] = {
    "net_sales": ("ventes nettes", "chiffre affaires net", "net sales", "ca net"),
    "same_store_sales": ("same store", "magasins comparables", "comparable"),
    "brand_com_sales": ("brand com", "ventes brand com", "site propre", "ecommerce propre"),
    "heroes_wob": ("heroes", "hero", "produits heros"),
    "refills_wob": ("recharges", "refills", "refill"),
    "new_clients": ("nouveaux clients", "new clients", "recrutement clients"),
    "retail_traffic": ("trafic retail", "retail traffic", "trafic magasins"),
    "nps_retail": ("nps retail", "nps magasin"),
    "nps_ecommerce": ("nps ecommerce", "nps e commerce", "nps web"),
    "nps_customer_service": ("nps service client", "nps customer service", "nps sav"),
    "review_rating": ("note avis", "review rating", "avis clients", "notation avis"),
}


class Join:
    """What the join produced, and what it refused to produce."""

    __slots__ = ("kpis", "unmatched_keys", "without_target", "without_reading")

    def __init__(self, kpis, unmatched_keys=(), without_target=(), without_reading=0):
        self.kpis = list(kpis)
        #: Keys the warehouse returned that no tracker row claims. Each is a KPI the
        #: cockpit is measuring and cannot judge, which is a question for a person.
        self.unmatched_keys = list(unmatched_keys)
        #: Matched, but the tracker states no target this reader can stand behind. Shown
        #: as a count, never scored: a KPI judged against a target of nothing reads as
        #: catastrophically off, every month, forever.
        self.without_target = list(without_target)
        #: Tracker rows nothing feeds. Counted, not listed — two hundred unwired rows
        #: reported one by one is how a panel teaches its reader to skip it.
        self.without_reading = without_reading


def match(registry: Tracker, keys: Sequence[str]) -> Tuple[Dict[str, Entry], List[str]]:
    """`(key -> entry, unmatched keys)`. Ids first, then aliases, never resemblance."""
    taken, found, unmatched = set(), {}, []

    # Two passes over all the keys rather than one pass deciding per key: an id is a claim
    # and a label is a coincidence, so every id must have its chance before any alias is
    # allowed to take a row. The same rule the plan mapping needs, for the same reason.
    remaining = []
    for key in keys:
        entry = next(
            (e for e in registry.entries if _words(e.id) and _words(e.id) == _words(key)),
            None,
        )
        if entry is not None and id(entry) not in taken:
            taken.add(id(entry))
            found[key] = entry
        else:
            remaining.append(key)

    for key in remaining:
        candidates = ALIASES.get(key, ())
        chosen = None
        for alias in candidates:
            wanted = _words(alias)
            for entry in registry.entries:
                if id(entry) in taken:
                    continue
                if wanted and wanted <= _words(entry.label):
                    chosen = entry
                    break
            if chosen is not None:
                break
        if chosen is None:
            unmatched.append(key)
        else:
            taken.add(id(chosen))
            found[key] = chosen
    return found, unmatched


def readings_by_key(rows: Sequence[Sequence], scope: str = GROUP_SCOPE
                    ) -> Dict[str, List[rules.Reading]]:
    """`kpi_key -> readings, oldest first`, for one scope.

    Rows are `(scope, kpi_key, period, value)` in that order — the contract stated in
    `queries.py`. A row missing a value is dropped rather than read as zero: a KPI that
    was not measured this month and a KPI that measured nothing are different facts, and
    only one of them is a finding.
    """
    found: Dict[str, List[rules.Reading]] = {}
    for row in rows:
        if len(row) < 4:
            continue
        row_scope, key, period, value = row[0], row[1], row[2], row[3]
        if str(row_scope or "").strip().upper() != scope.upper():
            continue
        if value is None or not str(key or "").strip():
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        found.setdefault(str(key).strip(), []).append(
            rules.Reading(str(period or "").strip(), number)
        )
    for readings in found.values():
        readings.sort(key=lambda reading: reading.period)
    return found


def join(registry: Tracker, rows: Sequence[Sequence],
         scope: str = GROUP_SCOPE) -> List[rules.Kpi]:
    """The KPIs the cockpit can actually judge. See `join_report` for what it could not."""
    return join_report(registry, rows, scope).kpis


def join_report(registry: Tracker, rows: Sequence[Sequence],
                scope: str = GROUP_SCOPE) -> Join:
    readings = readings_by_key(rows, scope=scope)
    matched, unmatched = match(registry, sorted(readings))

    kpis, no_target = [], []
    for key, entry in sorted(matched.items()):
        if not entry.has_target:
            # Kept out of the list rather than scored against nothing. It is still a fact
            # worth one line: the business measures this and has not said what good is.
            no_target.append(entry.label or key)
            continue
        kpis.append(entry.to_kpi(readings.get(key, ())))
    return Join(
        kpis,
        unmatched_keys=unmatched,
        without_target=no_target,
        without_reading=max(len(registry.entries) - len(matched), 0),
    )
