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
        label="Sell-in — shipped, not sold",
        maturity=BETA,
        note="Everything invoiced to a partner who then resells: wholesale, distributors, "
        "department stores, travel retail, e-retailers. Read from the management "
        "consolidation, which is where the plan's own actuals come from — so the two "
        "reconcile by construction rather than by coincidence, and they do: across last "
        "year, the whole perimeter agrees to within a euro, and 98% of its monthly cells "
        "agree individually. What it counts is what was shipped, because that is when "
        "the accounts recognise revenue, and every figure on this perimeter says so. "
        "What happens after the invoice — how much of it reaches a shopper, and when — "
        "is not measured by any source connected here. That is the management question, "
        "and answering it would take partner sell-through, which is a different source "
        "with a different owner, not a query away.",
        to_confirm="Whether partner sell-through exists in a form anyone can query — "
        "and if it does, it is reported beside the shipped figure and never instead of "
        "it, or the screen stops reconciling with Finance.",
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
        "fiscal year — rather than the two years the warehouse could supply. The month by "
        "month trend is sell-out only, because the consolidation publishes a comparison "
        "and not a series; the year to date covers both, sold and shipped, as the "
        "accounts recognise them.",
        to_confirm="Partner sell-through, and a second fiscal year of the monthly workbook. Until one exists, no "
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
    "same_store": Measure(
        key="same_store",
        label="Same-store sales",
        maturity=ABSENT,
        note="Two sources disagree about the direction, not the decimal. The tracker "
        "carries +2.0%; every definition the warehouse can compute for the same year is "
        "negative — the finance rule gives -0.8%, a constant perimeter of stores selling "
        "in both years gives -2.8%, and the unfiltered sell-out total gives -2.8% as "
        "well. Currency was tested and explains none of it; so was the channel "
        "perimeter. Three to five points, and the sign changes.\n\n"
        "The gap between the two warehouse definitions is understood, and it is not "
        "refurbishment. The finance rule drops 213 stores that sold in both years and "
        "that fell 10.6%, which lifts the headline by two points on its own. "
        "Refurbishment turned out to work the other way: the 136 refurbished stores grew "
        "0.4% against -3.4% for the rest, so taking them out of the comparison would make "
        "the figure worse, not better. That is worth knowing on its own — refurbished "
        "stores outperform by nearly four points.\n\n"
        "The rule is decided anyway — a store leaves the comparable base from the day its "
        "doors close — and it cannot be applied: refurbishment dates cover 49% of the "
        "estate, absence is not interpretable (coverage runs from 30% to 81% by country "
        "with no country at zero or a hundred), and the opening and closing dates that "
        "would settle it are empty on every store. The known contamination is 14 stores "
        "with works inside the year, 1.3% of the comparable base; that is a floor with no "
        "ceiling. Nothing is shown until the two sources are reconciled: a same-store "
        "figure whose sign depends on which system you ask is not a figure.",
        to_confirm="Which perimeter the reported +2.0% is computed on — what its "
        "'ex-cleaning' removes, and whether it composes monthly rates rather than "
        "dividing two yearly totals.",
    ),
    "store_concept": Measure(
        key="store_concept",
        label="Store concept",
        maturity=ABSENT,
        note="Eleven concepts exist in the warehouse and a third of the turnover — 35% — "
        "carries none. The business has answered why: the field is not maintained, and "
        "carries no meaning today. So this is not a gap waiting to be filled by a query. "
        "Nothing is counted by concept, and the KPI that would be — the count of trendy "
        "places — has no readable source until somebody owns the coding.",
        to_confirm="Who would own coding store concepts, on the day the Maison wants to "
        "steer by them. Until then there is nothing here to chase.",
    ),
    "cafes": Measure(
        key="cafes",
        label="Cafés and food service",
        maturity=BETA,
        note="Pastry, chocolate, ice cream and drinks are sold under product segments of "
        "their own and sit inside the same net sales as the creams — roughly €5m a year. "
        "One café was closed this year for losing money, and that one is what Finance "
        "takes out: the cleaning is about unprofitable revenue being removed from the "
        "comparison, not about cafés being outside the business.\n\n"
        "The split, once built, was read as an anomaly and probably is not one. It "
        "counted the stores recording a sale in the café product segments — 51, falling "
        "to 1 over twelve months while the revenue held near €400k a month — and read the "
        "collapse as a flow moving out of sight. But the Maison operates three or four "
        "cafés, not fifty-one. So the count is measuring something else: any store that "
        "sold a box of chocolates once falls inside those segments, and fifty small tails "
        "disappearing is not the same event as a business closing.\n\n"
        "What the money does is consistent with the plain story: the café that was closed "
        "shut in May or June, and the revenue stops after April. A store count is the "
        "wrong instrument here — the question is how the money is concentrated, not how "
        "many tills touched it.",
        to_confirm="How café revenue is distributed across those stores. If three or four "
        "carry nearly all of it, there is no anomaly and the key can be read; if it is "
        "genuinely spread, the segments do not mean cafés and the key is misnamed.",
    ),
    "store_count": Measure(
        key="store_count",
        label="Points of sale opened and closed",
        maturity=ABSENT,
        note="`STORE_OPENING_DATE` and `STORE_CLOSING_DATE` are empty on every store in "
        "the referential — not sparse, empty. So the KPI that counts the network down by "
        "112 points of sale has no readable source here, and neither has any question of "
        "the form 'how old is this store'. It was briefly thought readable; it is not.",
        to_confirm="Which system records an opening and a closing, if the store "
        "referential does not.",
    ),
    "consolidation_rollups": Measure(
        key="consolidation_rollups",
        label="Store-total entities in the consolidation",
        # Not validated, and the register is right to refuse it: that state is reserved
        # for a figure checked against a pack the organisation publishes, and this is a
        # control rather than a figure. The zero-retail check that clears these entities
        # came from one reading of the warehouse, not from a published reconciliation.
        maturity=BETA,
        note="Seven entities in the consolidation carry a country's retail as a store "
        "total — 168m€ a year, the largest being the United States at 81m€. They were "
        "briefly taken for duplicates of their countries, and they are not: in every one "
        "of those countries the base entity carries zero retail, so the store total is "
        "the sole carrier, exactly as Japan and the United Kingdom carry theirs without "
        "the suffix. Adding them gives the right figure.\n\n"
        "The check that survives is narrower and it is the one that matters: a market "
        "receiving both a total and its own detail lines would be inflated without any "
        "total looking wrong. That condition is tested on the rows read, at every "
        "reconciliation, rather than on the shape of a name — the first version alarmed "
        "on the naming convention itself and would have cried wolf on every run.",
        to_confirm="Whether the base entity carrying zero retail is a rule of the "
        "consolidation or the state it happens to be in this year. One reading cleared "
        "these seven; a rule would clear the eighth before it appears.",
    ),
    "china_hong_kong_boundary": Measure(
        key="china_hong_kong_boundary",
        label="The China / Hong Kong / travel-retail boundary",
        maturity=BETA,
        note="Hong Kong is written three times in Finance's file — as an APAC country, as "
        "distributors, and as travel retail under a worldwide heading — and the "
        "consolidation carries all three under one entity family. Two of the three line "
        "up to the euro. The third does not: the travel-retail entity carries 4 826k€ "
        "more than the line the file calls Hong Kong travel retail, and the file carries "
        "a line called `Other`, filed under European distributors, worth 4 826k€. The "
        "same money, named twice, and read for a week as two separate anomalies — one "
        "market unexplainedly over, one line unexplainedly missing. It is folded before "
        "the comparison now, and Hong Kong lands within 29k€.\n\n"
        "China is settled in the same reading and separately: the file's cross-border "
        "line and the consolidation's cross-border entity are the same 6 085k€ to the "
        "euro. What remains short is mainland China alone, by 6.2m€, and that is a real "
        "question rather than a naming one.",
        to_confirm="Which travel-retail customer `Other` is. The business reads it as one "
        "large enough to be shown on its own line, which fits both the arithmetic and the "
        "place the file puts it — beside the distributors, because it is a customer and "
        "not a geography. Naming it would close this for good; nobody at Finance has yet.",
    ),
    "distributor_perimeter": Measure(
        key="distributor_perimeter",
        label="What the distributor line covers",
        maturity=ABSENT,
        note="The consolidation carries one distributor line, `Export`, worth 8 767k€ in "
        "the closed quarter. Finance carries `Loi Distributors` at 10 079k€. Whether they "
        "hold the same business is open, and the business has read it both ways within an "
        "hour: every distributor including Asia, which would make the consolidation's line "
        "the wider one; or only the distributors Europe and the Americas manage, which "
        "would make it narrower.\n\n"
        "The arithmetic favours the second reading — a superset thirteen per cent smaller "
        "than what it contains is a contradiction, not a perimeter difference — but the "
        "two sides are stated at different rates, so that is an argument and not a proof. "
        "Until it is settled the pair is printed side by side and never netted: an alias "
        "here would make a ten-million line agree by coincidence of size.",
        to_confirm="The distributor customers behind the consolidation's export entity, "
        "by region. One list settles which of the two readings is right.",
    ),
    "hospitality": Measure(
        key="hospitality",
        label="Hospitality and corporate gifts",
        maturity=ABSENT,
        note="Around 3% of the plan, read by no source connected here. Unlike the "
        "differences of base, this one is a hole: nothing in the cockpit counts it, so it "
        "cannot be added back by changing a filter.",
        to_confirm="Which system records hospitality and corporate gift revenue.",
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
