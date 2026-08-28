"""Where each figure comes from, and whether anyone has checked it.

The cockpit is going to be read before IT has finished. That is the right call — waiting
for a complete warehouse would mean waiting a year — but it creates a specific danger: a
screen where a validated number and a guess look identical.

So every measure on the screen declares its maturity. Not as a disclaimer footer nobody
reads, but attached to the figure itself, with the question that would settle it.

Three states, and the middle one is the point:

* `VALIDATED` — reconciles against something the organisation already reports. A
  disagreement here is a bug in the cockpit, not a discussion.
* `BETA` — computed, plausible, and unconfirmed. Usable for direction, not for a board
  paper. Each one carries what IT would have to confirm to promote it.
* `ABSENT` — not measured at all. The most important of the three, because an absent
  measure is invisible by nature: nothing on a screen says "the thing you are not seeing".

What must never happen is a figure with no state. A measure added without one is a measure
whose author did not ask themselves the question.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

VALIDATED = "validated"
BETA = "beta"
ABSENT = "absent"

ORDER = {ABSENT: 0, BETA: 1, VALIDATED: 2}


class Measure:
    """One family of figures, and the state of the ground under it."""

    __slots__ = ("key", "label", "maturity", "note", "to_confirm")

    def __init__(
        self,
        key: str,
        label: str,
        maturity: str,
        note: str,
        to_confirm: str = "",
    ) -> None:
        self.key = key
        self.label = label
        self.maturity = maturity
        self.note = note
        #: The question that would move this measure up a state. Empty only when validated:
        #: a beta or absent measure with nothing to confirm is a measure nobody owns.
        self.to_confirm = to_confirm

    @property
    def is_settled(self) -> bool:
        return self.maturity == VALIDATED

    @property
    def badge(self) -> str:
        return {VALIDATED: "", BETA: "beta", ABSENT: "not measured"}[self.maturity]


#: The register. Edited by hand, deliberately: promoting a measure to VALIDATED should cost
#: someone a moment's thought, not follow automatically from a query being written.
REGISTER: Dict[str, Measure] = {
    "sales_actual": Measure(
        key="sales_actual",
        label="Net sales",
        maturity=BETA,
        note="Read from the sell-out semantic view — the one the organisation's own Sell "
        "Out Analyst already uses, so the definition is shared. What is not settled is "
        "the timing: facts on recent months are still being reprocessed, and markets "
        "have been seen to move between two runs on the same day.",
        to_confirm="From how many days after month end is a month's sell-out final?",
    ),
    "sales_budget": Measure(
        key="sales_budget",
        label="Plan",
        maturity=VALIDATED,
        note="From the planning workbook, not the warehouse. Its yearly total reconciles "
        "exactly with the Sales line of the consolidated EBITDA pack, and its monthly "
        "totals with the Q1 estimate pack.",
    ),
    "web_funnel": Measure(
        key="web_funnel",
        label="Sessions, orders, conversion, AOV",
        maturity=BETA,
        note="Moved onto the semantic layer, which changed one thing: orders now hang "
        "off the session date rather than the transaction date. The order count was "
        "identical on the month tested, so nothing moved — but the two dates could "
        "diverge at a month boundary, where it would matter most.",
        to_confirm="Do session date and transaction date diverge across month end?",
    ),
    "retail_funnel": Measure(
        key="retail_funnel",
        label="Store traffic and conversion",
        maturity=ABSENT,
        note="Not in the query. And outside the markets with footfall counters it would "
        "not be readable anyway — the cockpit refuses to build a store conversion rate "
        "where nothing counts the door.",
        to_confirm="Which markets have reliable counters, beyond Europe and the US?",
    ),
    "sell_in": Measure(
        key="sell_in",
        label="Sell-in",
        maturity=BETA,
        note="Everything invoiced to a partner who then resells: wholesale, distributors, "
        "department stores, travel retail, e-retailers. Read from the management "
        "consolidation, which is where the plan's own actuals come from — so the two "
        "reconcile by construction rather than by coincidence, and they do: across last "
        "year, the whole perimeter agrees to within a euro, and 98% of its monthly cells "
        "agree individually. What is not settled is that this is a query written here "
        "rather than a source anyone else can use, and that a few months arrive as pairs "
        "because the underlying figures are cumulative and one snapshot is missing.",
        to_confirm="A governed sell-in view, so this stops depending on one query nobody "
        "else maintains.",
    ),
    "sales_history": Measure(
        key="sales_history",
        label="Twenty-four months of history",
        maturity=BETA,
        note="What lets the screen say \"three months below plan\" and \"the gap is "
        "widening\" instead of comparing one month to one plan. The actuals are the "
        "same sell-out figures as the current month and carry the same standing. The "
        "plan they are measured against is the planning workbook and nothing else: the "
        "warehouse also publishes a goals fact, but it has no target at all for two "
        "fifths of what the group sells and the business does not stand behind it. So "
        "the trend reaches exactly as far back as the workbook does — the current "
        "fiscal year — rather than the two years the warehouse could supply. It is also "
        "sell-out only: sell-in has no history query yet, so the year to date covers the "
        "channels the warehouse measures and not the ones invoiced to partners.",
        to_confirm="A second fiscal year of the monthly workbook. Until one exists, no "
        "twelve-month judgement can be made against a plan anyone stands behind.",
    ),
    "commitments": Measure(
        key="commitments",
        label="Commitments",
        maturity=ABSENT,
        note="No source connected. The panel says so rather than showing an empty board.",
        to_confirm="Where commitments are recorded today, if anywhere.",
    ),
    "client_kpis": Measure(
        key="client_kpis",
        label="Customer KPIs",
        maturity=ABSENT,
        note="Readings would come from the warehouse; definitions, targets and cadence "
        "come from the KPI tracker. Neither is wired.",
        to_confirm="Which KPIs are already computed centrally, and to whose definition.",
    ),
    "owners": Measure(
        key="owners",
        label="Market owners",
        maturity=BETA,
        note="Read from the directory file, which lists BU heads and country GMs. A "
        "market the directory names goes to its GM; a market it does not goes to the BU "
        "head, who does own it. What is never done is expanding a named grouping — "
        "Nordics, Southern Europe, Central Europe, SEA — into countries the file does "
        "not list, so those markets are answered one level up.",
        to_confirm="Which countries sit in each named grouping, to route them precisely.",
    ),
}


def measure(key: str) -> Optional[Measure]:
    return REGISTER.get(key)


def unsettled(settled: Sequence[str] = ()) -> List[Measure]:
    """Everything not validated, worst first.

    Sorted so that what is missing outranks what is merely unconfirmed: a wrong number can
    be argued with, an absent one cannot.

    `settled` names measures the running configuration has resolved — a file that is
    present, a source that connected. The register describes the design; only the running
    instance knows what it actually has in hand.
    """
    resolved = set(settled)
    found = [m for m in REGISTER.values() if not m.is_settled and m.key not in resolved]
    found.sort(key=lambda m: (ORDER[m.maturity], m.label))
    return found


def has_beta() -> bool:
    return any(m.maturity == BETA for m in REGISTER.values())
