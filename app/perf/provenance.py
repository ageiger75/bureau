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
        "carries a positive figure; every definition the warehouse can compute for the same "
        "year is negative — the finance rule, a constant perimeter of stores selling in "
        "both years, and the unfiltered sell-out total. Currency was tested and explains "
        "none of it; so was the channel perimeter. Several points, and the sign changes."
        "\n\n"
        "The gap between the two warehouse definitions is understood, and it is not "
        "refurbishment. The finance rule drops a couple of hundred stores that sold in "
        "both years and fell sharply, which lifts the headline by a couple of points on "
        "its own. Refurbishment turned out to work the other way: the refurbished stores "
        "grew while the rest fell, so taking them out of the comparison would make the "
        "figure worse, not better. That is worth knowing on its own — refurbished stores "
        "outperform the rest by several points.\n\n"
        "The rule is decided anyway — a store leaves the comparable base from the day its "
        "doors close — and it cannot be applied: refurbishment dates cover about half the "
        "estate, absence is not interpretable (coverage varies widely by country with no "
        "country at zero or a hundred), and the opening and closing dates that would "
        "settle it are empty on every store. The known contamination is a handful of "
        "stores with works inside the year, about a point of the comparable base; that is "
        "a floor with no ceiling. Nothing is shown until the two sources are reconciled: "
        "a same-store "
        "figure whose sign depends on which system you ask is not a figure.",
        to_confirm="Which perimeter the reported figure is computed on — what its "
        "'ex-cleaning' removes, and whether it composes monthly rates rather than "
        "dividing two yearly totals.",
    ),
    "store_concept": Measure(
        key="store_concept",
        label="Store concept",
        maturity=ABSENT,
        note="Eleven concepts exist in the warehouse and about a third of the turnover "
        "carries none. The business has answered why: the field is not maintained, and it "
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
        "their own and sit inside the same net sales as the creams. "
        "One café was closed this year for losing money, and that one is what Finance "
        "takes out: the cleaning is about unprofitable revenue being removed from the "
        "comparison, not about cafés being outside the business.\n\n"
        "The split, once built, was read as an anomaly and probably is not one. It "
        "counted the stores recording a sale in the café product segments — dozens, falling "
        "to one over twelve months while the revenue held flat — and read the collapse as "
        "a flow moving out of sight. But the Maison operates a handful of cafés, not "
        "dozens. So the count is measuring something else: any store that "
        "sold a box of chocolates once falls inside those segments, and a long tail of tiny "
        "amounts disappearing is not the same event as a business closing.\n\n"
        "What the money does is consistent with the plain story: the café that was closed "
        "shut in May or June, and the revenue stops after April. A store count is the "
        "wrong instrument here — the question is how the money is concentrated, not how "
        "many tills touched it.",
        to_confirm="How café revenue is distributed across those stores. If a handful "
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
        "total, and between them they carry a large share of the Maison's retail. They were "
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
        "up to the euro. The third does not: the travel-retail entity carries more than the "
        "line the file calls Hong Kong travel retail, and the file carries a line called "
        "`Other`, filed under European distributors, worth exactly that difference. The "
        "same money, named twice, and read for a week as two separate anomalies — one "
        "market unexplainedly over, one line unexplainedly missing. It is folded before "
        "the comparison now, and Hong Kong lands within a rounding of the file.\n\n"
        "China is settled in the same reading and separately: the file's cross-border "
        "line and the consolidation's cross-border entity are the same figure to the euro. "
        "Mainland China was then short, and that shortfall has since been named to within "
        "a few euros: retail the store referential does not carry, plus B2B and corporate "
        "gifts that no query reads at all.",
        to_confirm="Which travel-retail customer `Other` is. The business reads it as one "
        "large enough to be shown on its own line, which fits both the arithmetic and the "
        "place the file puts it — beside the distributors, because it is a customer and "
        "not a geography. Naming it would close this for good; nobody at Finance has yet.",
    ),
    "distributor_perimeter": Measure(
        key="distributor_perimeter",
        label="The distributor business",
        maturity=BETA,
        note="Read for a week as two organisations cutting one business differently, and "
        "it is not that. The consolidation's export entity holds 45 distributor customers, "
        "all of them filed under two commercial zones — Europe, and the Americas and "
        "Caribbean — and none under Asia or the Middle East. Those live in three other "
        "entities. So it is the business Europe and the Americas manage, not the Maison's "
        "distributor business, and the file's line is the same perimeter under Finance's "
        "name for it. Folded.\n\n"
        "An argument about a whole perimeter became a difference of a few per cent, and "
        "then nothing at all. What was missing was not a second export office nor a "
        "rebate account: the entity carries two channels and only one was being read. "
        "Both together reconcile with Finance's line to a few hundred euros.\n\n"
        "Worth keeping as a habit rather than as a fact. An entity is not a figure — it "
        "can hold several channels, and a query that reads one of them looks complete.\n\n"
        "One trap to carry: the zone called Europe in that commercial hierarchy is a "
        "management perimeter and not a continent. It contains Kazakhstan, Mongolia, "
        "Uzbekistan, Georgia, Nigeria, Mauritius, Martinique and New Caledonia. Anyone "
        "filtering on Europe expecting Europe is wrong by twenty countries — the same kind "
        "of label this screen exists to decode, one level further down.",
        to_confirm="That it still reconciles on the next closed quarter. One quarter "
        "agreeing is a good sign; the plan earned its standing over a year and a pack the "
        "organisation publishes, and this has not.",
    ),
    "commercial_zones": Measure(
        key="commercial_zones",
        label="Commercial zone names",
        maturity=ABSENT,
        note="The warehouse's commercial hierarchy is a split of who manages an account, "
        "and its labels are not geography however geographical they sound. `Europe` holds "
        "Mongolia, Kazakhstan, Nigeria, Morocco, Martinique and New Caledonia. `Americas "
        "and Caribbean` holds South Africa. `Continental Western Europe` holds the United "
        "States and the Emirates. `Middle East` holds five countries of which one is in "
        "the Middle East. `Americas` holds Switzerland and the United Kingdom. `Greater "
        "China` holds Singapore, `South-East Asia and Pacific` holds Hong Kong.\n\n"
        "Country names in that hierarchy are worse, because they look unambiguous: "
        "`Department Store Spain` holds France, `Wholesale Switzerland` holds Germany, and "
        "one German wholesale zone holds no German customer at all. A country name there "
        "is the team that manages the account, never the country of the customer.\n\n"
        "The rule, and it is the only safe one: nothing in that field may be read as a "
        "place. The customer's country field is the only answer to a question about "
        "geography. Recorded here rather than in a query comment because the next person "
        "to write a query is the one who needs it, and the label will look correct to "
        "them.",
        to_confirm="Nothing. This is a fact about the referential, and the cockpit's job "
        "is to never read those labels as places.",
    ),
    "rate_effect": Measure(
        key="rate_effect",
        label="The difference the exchange rate accounts for",
        maturity=BETA,
        note="Most of the market-by-market differences in the reconciliation are the "
        "currency, and that is now demonstrated rather than assumed. Two readings were "
        "wrong along the way and both were mine to relay: that the long tail was a missing "
        "perimeter, and then that it was the consolidation front-loading its first "
        "quarter.\n\n"
        "What settled it is a method worth keeping. The consolidation restates last year "
        "at this year's rates in a column of its own, so comparing that column against the "
        "same quarter of sell-out removes the rate entirely and leaves whatever else there "
        "is. Done that way most markets land inside a point, and the few that do not are "
        "the real findings.\n\n"
        "The tell was in the shape all along: a difference that holds at the same "
        "percentage across four quarters and then vanishes is a multiplier, and only a "
        "rate behaves like that. A calendar effect does not.",
        to_confirm="The full year at constant rates, which needs the March snapshot. Until "
        "then the quarter is the only window where both sides can be put on one rate.",
    ),
    "china_quarter_timing": Measure(
        key="china_quarter_timing",
        label="How the consolidation spreads China's quarter",
        maturity=BETA,
        note="China's retail was still short after the third-party counters were taken "
        "out, and the cause is not a missing perimeter. Every Chinese store that sells is "
        "in the referential, the monthly series has no hole, and the stores that closed "
        "carry a small fraction of what is missing.\n\n"
        "At constant rates the consolidation exceeds the sell-out on the first quarter of "
        "both years, by a similar margin each time. Stable, not fading — an earlier "
        "reading that had it shrinking was comparing two rate bases and said nothing. "
        "China is alone in this: every other market of any size lands inside a point once "
        "the rate is taken out. So it is one market's accounting question, not a property "
        "of the instrument, and the quarterly reconciliation stands.",
        to_confirm="How the retail figure of the Chinese entity is spread between "
        "quarters. That belongs to whoever produces the Chinese consolidation.",
    ),
    "franchised_network": Measure(
        key="franchised_network",
        label="The franchised network",
        maturity=ABSENT,
        note="France has franchised stores, and they are absent from this screen. Not "
        "understated — absent. The sell-out flow carries the owned network and the "
        "third-party counters and nothing else, measured to a fraction of a per cent of "
        "the market, so a franchisee's till never reaches any figure here.\n\n"
        "Where the money does appear is the sell-in, as what the Maison invoices to the "
        "franchisee — and mixed there with export and independent wholesale in one "
        "channel, so it cannot be read apart. Separating it needs the list of franchised "
        "customers, which is a business fact and not a query.\n\n"
        "A badge saying `PARTLY FRANCHISED` sat on the French figure for an hour, on the "
        "premise that a franchised till reaches the sell-out. It does not. The statement "
        "was true of the business and false of the number it was printed on, which would "
        "have had a reader discount a figure that needed no discounting.",
        to_confirm="The list of franchised customers, so their business can be read on "
        "its own wholesale revenue and contribution instead of inside the export channel.",
    ),
    "franchise_buyback": Measure(
        key="franchise_buyback",
        label="Stores coming back into the network",
        maturity=ABSENT,
        note="The Maison intends to exit franchising gradually. Each store bought back "
        "moves its revenue from one side of the invoice to the other: what was wholesale "
        "to a franchisee becomes a till of the Maison's own, so the sold figure of that "
        "market steps up and its shipped figure steps down, and neither movement is "
        "trading.\n\n"
        "Nothing here would say so. The screen would show a French retail line jumping and "
        "a distributor line falling, both real in the accounts and both meaningless as "
        "performance — the exact shape the cockpit already refuses to hand anyone as a "
        "question, and the exact reason the note mechanism exists. It only works if "
        "somebody writes the note when a store converts.",
        to_confirm="Who will say when a store converts, and when. A conversion recorded "
        "the month it happens costs one line; discovered afterwards it costs a quarter of "
        "wrong conversations.",
    ),
    "hospitality": Measure(
        key="hospitality",
        label="Hospitality, B2B and corporate gifts",
        maturity=ABSENT,
        note="Around 3% of the plan, read by no source connected here. Unlike the "
        "differences of base, this one is a hole: nothing in the cockpit counts it, so it "
        "cannot be added back by changing a filter. It has a size now, on one market: China "
        "carries both B2B and corporate gifts as channels of their own over the closed "
        "quarter, and neither reaches the screen.",
        to_confirm="Which system records hospitality, B2B and corporate gift revenue.",
    ),
    "third_party_stores": Measure(
        key="third_party_stores",
        label="Points of sale operated by a third party",
        maturity=ABSENT,
        note="The governed store referential the cockpit joins on does not carry the "
        "points of sale a partner operates. Their sales exist in the sell-out fact; the "
        "stores do not exist in the view, so the join drops them — no error, no orphan "
        "row, just revenue that never arrives.\n\n"
        "What that money is, is settled: department-store counters. China's own deck "
        "carries them as a channel of their own, and the figure to anchor on is the one "
        "column in it that is neither a budget nor an estimate — the closed year, grown "
        "forward at the rate the deck's own series shows. Done that way the two agree "
        "within a few per cent, against a year that is finished.\n\n"
        "Deliberately not against the deck's figure for the year in progress: that is a "
        "last estimate, the landing can sit well away from it, and a reconciliation that "
        "leans on a projection congratulates itself on a precision it does not have. Same "
        "reason the reconciliation reads only the quarter Finance has closed.\n\n"
        "The deck separates these counters from the Maison's own, and the warehouse does "
        "the same thing in its own vocabulary: the point of sale belongs to the department "
        "store, so it is not in a referential of the Maison's stores. Two systems agreeing "
        "on a boundary, and the cockpit falling through it.\n\n"
        "Measured, and smaller than it looked. Five markets carry such points of sale, not "
        "thirty, and between them a low single-digit percentage of the quarter's "
        "sell-out. No other channel type is excluded.\n\n"
        "So this does not explain the long tail of small shortfalls across thirty markets, "
        "which is what it was reached for: twenty-nine of those markets have no such store "
        "at all. Widening the join corrects 2.2% in five markets and nothing anywhere "
        "else — worth doing, and not the answer to the other question.\n\n"
        "Two of the five match a budgeted department-store channel and are a plain "
        "correction; three do not. France carries several times more external counters than "
        "its budget shows for department stores and independent wholesale together, and "
        "Brazil and Hong Kong have no such channel budgeted at all. Either those points "
        "of sale are budgeted somewhere else, or they are not budgeted.",
        to_confirm="Where France's, Brazil's and Hong Kong's third-party points of sale "
        "sit in their budgets, if they sit anywhere. And whether the quarterly figures "
        "annualise — a quarter multiplied by four assumes a flat year.",
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
