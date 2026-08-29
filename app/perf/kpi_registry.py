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
from .tracker import Entry, Tracker, _plain

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
    # Ordered from most specific to least: the first alias that fits wins, so a bare
    # "traffic" may only claim a row after the qualified spellings have had their chance.
    "retail_traffic": ("trafic retail", "retail traffic", "trafic magasins", "traffic",
                       "trafic"),
    "nps_retail": ("nps retail", "nps magasin"),
    "nps_ecommerce": ("nps ecommerce", "nps e commerce", "nps web"),
    "nps_customer_service": ("nps service client", "nps customer service", "nps sav"),
    "review_rating": ("note avis", "review rating", "avis clients", "notation avis",
                      "reviews", "review"),
    # Panier moyen et articles par panier. Longtemps déclarés incalculables au mois : la
    # fonction `semantic_view()` ne rend pas un `count(distinct)` par mois, et la maison
    # n'y passe pas — ses requêtes vérifiées lisent la vue directement.
    "atv": ("panier moyen", "atv", "average transaction value", "ticket moyen",
            "valeur transaction moyenne"),
    "upt": ("upt", "articles par transaction", "units per transaction",
            "produits par transaction", "articles par panier"),
}


#: Clés que l'entrepôt rend et qu'aucune ligne du classeur n'a vocation à revendiquer.
#: Ce ne sont pas des KPI : ce sont des bases de calcul, publiées à côté d'un KPI pour
#: qu'on puisse mesurer ce qui les sépare. Les compter parmi les clés non appariées les
#: ferait lire comme « un KPI que le cockpit mesure et ne sait pas juger », ce qu'elles ne
#: sont pas, et pousserait quelqu'un à créer une ligne pour les faire taire.
NOT_A_KPI = frozenset(("net_sales_hors_bulk",))


#: Level and scope spellings that mean "the whole group". A reading returned at group
#: scope must be judged against the group's target, never a business unit's — the sheet
#: carries `Heroes WOB` twice, at 30 and at 25, and picking the wrong one silently turns a
#: KPI that holds into a KPI that misses.
GROUP_NAMES = frozenset(("loep", "groupe", "group", "monde", "total", "comex"))


#: Keys whose value is an amount of money, from the query's own contract rather than from
#: a guess about magnitudes. It matters because the tracker states some of these against a
#: *growth rate*: `Brand.com` carries a target of 10.2%, and the warehouse returns the
#: euros sold. Matched on the name they look like one measure; they are two, and scoring
#: one against the other produced "6 847 662% — on track".
AMOUNT_KEYS = frozenset(("net_sales", "same_store_sales", "brand_com_sales"))

#: Units that describe a quantity rather than a level. A reading in euros can only be
#: judged against a target in the same kind of unit.
AMOUNT_UNITS = frozenset(("m€", "k€", "€", "eur", "meur", "keur", "k clients", "clients"))


def _units_agree(key: str, entry: Entry) -> str:
    """Empty when reading and target measure the same kind of thing; else why not."""
    if key not in AMOUNT_KEYS:
        return ""
    if _plain(entry.unit) in AMOUNT_UNITS:
        return ""
    return (
        "the warehouse returns an amount here and the tracker's target is stated in %s: "
        "they are not the same measure, and one cannot be scored against the other"
        % (entry.unit or "another unit")
    )


class Join:
    """What the join produced, and what it refused to produce."""

    __slots__ = ("kpis", "unmatched_keys", "without_target", "without_reading",
                 "ambiguous")

    def __init__(self, kpis, unmatched_keys=(), without_target=(), without_reading=0,
                 ambiguous=()):
        self.kpis = list(kpis)
        #: Keys several tracker rows could have claimed. The scope decided, and the fact
        #: that it had to is worth printing: a duplicate name with two different targets
        #: is a question for whoever maintains the sheet.
        self.ambiguous = list(ambiguous)
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


def _is_group(entry: Entry) -> bool:
    return bool(GROUP_NAMES & (_words(entry.scope) | _words(entry.level)))


def match(registry: Tracker, keys: Sequence[str], scope: str = GROUP_SCOPE
          ) -> Tuple[Dict[str, Entry], List[str], List[str]]:
    """`(key -> entry, unmatched keys, ambiguous keys)`.

    Ids first, then aliases, never resemblance — and among the rows an alias fits, the one
    whose perimeter matches the reading's. The tracker holds the same KPI at several
    levels: `Heroes WOB` appears at 30% for the group and 25% for a business unit, and a
    group reading scored against the unit's target reads as a miss that is not there.
    """
    taken, found, unmatched, ambiguous = set(), {}, [], []

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

    wants_group = scope.strip().lower() in GROUP_NAMES
    for key in remaining:
        fitting = []
        for alias in ALIASES.get(key, ()):
            wanted = _words(alias)
            if not wanted:
                continue
            fitting.extend(
                entry for entry in registry.entries
                if id(entry) not in taken and wanted <= _words(entry.label)
                and entry not in fitting
            )
        if not fitting:
            if key not in NOT_A_KPI:
                unmatched.append(key)
            continue
        # The perimeter decides, and never the sheet's order: preferring the first row
        # would make the answer depend on how somebody sorted the spreadsheet.
        if wants_group:
            scoped = [entry for entry in fitting if _is_group(entry)]
        else:
            scoped = [entry for entry in fitting if _words(entry.scope) == _words(scope)]
        if not scoped:
            # No row at the perimeter asked for. Falling back to another one is the very
            # error the perimeter was introduced to stop: `Brand.com` exists for EMEA and
            # not for the group, and a group reading scored against EMEA's target reads
            # as a verdict about the Maison drawn from one region's commitment.
            unmatched.append(key)
            continue
        if len(fitting) > 1:
            ambiguous.append(key)
        taken.add(id(scoped[0]))
        found[key] = scoped[0]
    return found, unmatched, ambiguous


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
        # The warehouse hands back dictionaries keyed by column name; the tests and the
        # disk cache hand back sequences. Read by name where there is one — a positional
        # read of a mapping does not fail loudly, it fails two minutes into a query, on
        # the one machine that has the data.
        if isinstance(row, dict):
            lowered = {str(name).lower(): value for name, value in row.items()}
            row_scope = lowered.get("scope")
            key = lowered.get("kpi_key")
            period = lowered.get("period")
            value = lowered.get("value")
        elif len(row) >= 4:
            row_scope, key, period, value = row[0], row[1], row[2], row[3]
        else:
            continue
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


def latest_by_market(rows: Sequence[Sequence], key: str,
                     skip: str = GROUP_SCOPE) -> Dict[str, float]:
    """`market -> most recent value` for one key, the group roll-up left out.

    One pass over the rows rather than one `readings_by_key` call per market: the readings
    are eight thousand rows and thirty-five markets, and the quadratic version of this was
    measurable on a page load.
    """
    latest: Dict[str, Tuple[str, float]] = {}
    for row in rows:
        if isinstance(row, dict):
            lowered = {str(name).lower(): value for name, value in row.items()}
            scope, row_key = lowered.get("scope"), lowered.get("kpi_key")
            period, value = lowered.get("period"), lowered.get("value")
        elif len(row) >= 4:
            scope, row_key, period, value = row[0], row[1], row[2], row[3]
        else:
            continue
        name = str(scope or "").strip()
        if not name or name.upper() == skip.upper():
            continue
        if str(row_key or "").strip() != key or value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        stamp = str(period or "").strip()
        held = latest.get(name)
        if held is None or stamp >= held[0]:
            latest[name] = (stamp, number)
    return {name: value for name, (_period, value) in latest.items()}


def join_report(registry: Tracker, rows: Sequence[Sequence],
                scope: str = GROUP_SCOPE) -> Join:
    readings = readings_by_key(rows, scope=scope)
    matched, unmatched, ambiguous = match(registry, sorted(readings), scope=scope)

    kpis, no_target = [], []
    for key, entry in sorted(matched.items()):
        refusal = _units_agree(key, entry) or entry.scorable
        if refusal:
            # Kept out of the list rather than scored against something it cannot be
            # compared with. Still a fact worth one line each: the business measures this
            # and either has not said what good is, or has said it for a whole year.
            no_target.append("%s (%s)" % (entry.label or key, refusal))
            continue
        kpi = entry.to_kpi(readings.get(key, ()))
        # Only where the group's own target applies to a market unchanged — a floor and a
        # ceiling do. A target stated as an amount or as a level to reach by a date does
        # not divide between markets, and holding a market to the group's euros would
        # manufacture failures out of size.
        if kpi.target is not None and key not in AMOUNT_KEYS:
            per_market = latest_by_market(rows, key)
            kpi.markets_read = len(per_market)
            kpi.behind = sorted(
                ((name, value) for name, value in per_market.items()
                 if rules.misses_target(value, kpi.target, kpi.direction)),
                key=lambda pair: pair[1] if kpi.direction == rules.UP else -pair[1],
            )
        kpis.append(kpi)
    return Join(
        kpis,
        unmatched_keys=unmatched,
        without_target=no_target,
        without_reading=max(len(registry.entries) - len(matched), 0),
        ambiguous=ambiguous,
    )
