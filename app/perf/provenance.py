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
        label="Levels cannot be reconciled; growth can",
        maturity=BETA,
        note="The two sides use different kinds of rate, not merely different rates. The "
        "sell-out converts at the group's budget rate — one figure per currency, the same "
        "on every quarter of every year, and two pegged currencies come out at their peg "
        "exactly. The consolidation uses a third set, belonging to planning: neither the "
        "budget rates nor the real accounting ones, and not respecting the peg. That set "
        "is not in the tables, and the consolidation carries no amount in original "
        "currency. So the levels are not reconcilable, and no amount of care makes them "
        "so.\n\n"
        "Growth is, exactly. This year and last year inside one consolidation year are "
        "stated at the same rates, and the sell-out's rate is invariant across years, so "
        "comparing a growth rate to a growth rate assumes no rate at all. Done that way "
        "most markets agree inside a point and several agree exactly — and the handful "
        "that do not are findings rather than artefacts.\n\n"
        "That is the instrument to publish, and it is better than the fallback of "
        "printing both rates and letting the reader judge: it gives an answer that can be "
        "checked everywhere instead of a caveat that can be checked nowhere. Two findings "
        "were manufactured by comparing levels today and both were withdrawn.",
        to_confirm="Reading the consolidation's own year-on-year alongside the sell-out's, "
        "market by market, so the reconciliation compares growth instead of levels.",
    ),
    "third_party_counters": Measure(
        key="third_party_counters",
        label="Counters the sell-out referential does not carry",
        maturity=BETA,
        note="A population of department-store counters sells outside the modelled store "
        "dimension. Why is structural rather than suspicious: the store grade is joined "
        "onto the operated-network reference, no counter of this kind carries a grade "
        "anywhere in the group, and the classification therefore stops exactly at the "
        "boundary of what the Maison runs itself. Not our staff and not our till — the "
        "business ships to a partner, and the referential agrees. Their absence follows "
        "from what they are.\n\n"
        "The transaction count on them was suspected of having been renumbered and now is "
        "shown to have been, by the shape of the change rather than by its size. The whole "
        "movement sits inside one fortnight: the month before rises, the month after is "
        "identical across both years, and inside that fortnight every single shop moves "
        "the same way — transactions collapsing, lines per transaction rising, several "
        "landing on exactly the same round ratio. A change in how people shop does not "
        "arrive on every shop at once and leave the following month untouched.\n\n"
        "So the per-transaction averages on this perimeter are unusable for that "
        "fortnight and the two flanking months are fine, and the money and quantities "
        "were never in doubt. None of it reaches this screen: the governed store "
        "dimension excludes these counters, so no query here reads the corrupted rows — "
        "and by the same token no query here can see that they exist.",
        to_confirm="Nothing on the artefact itself. Whether the same renumbering touched "
        "any perimeter this screen does read, which the operated network's own ratio "
        "answers for the market checked and for no other.",
    ),
    "semantic_descriptions": Measure(
        key="semantic_descriptions",
        label="Where the semantic layer's own descriptions are wrong",
        maturity=BETA,
        note="The governed view carries a written description per field, and three of them "
        "are wrong rather than merely terse. Two dimensions describe a couple of their "
        "values and omit the rest, including in one case the exact value a reader would "
        "come looking for — so an agent that reads the description concludes the thing it "
        "needs does not exist. The third is worse: a field named for transactions counts "
        "sales lines, several for every transaction, and the description asserts "
        "otherwise. A ratio built on it is wrong by that factor, and wrong in the "
        "direction that looks plausible.\n\n"
        "This queries' own comments already carry that trap and the queries already "
        "divide by distinct transactions, so the screen is not affected. It is recorded "
        "because the risk is not to this code: it is to anyone — a person or an agent — "
        "who reads the governed layer's description and trusts it. A wrong description on "
        "a certified path is more dangerous than a missing one, because it answers.",
        to_confirm="Whether the descriptions can be corrected at the source, and whether "
        "any other field on the path this screen uses describes itself wrongly.",
    ),
    "door_grades": Measure(
        key="door_grades",
        label="The network's own grading of its shops",
        maturity=BETA,
        note="The store dimension carries a grade per shop — a flagship tier, a top tier, "
        "an ordinary tier, outlets — and it is already inside the certified path, so the "
        "screen can read it without leaving the governed door. Nothing here reads it "
        "today, which is a missing view rather than a missing number.\n\n"
        "Two properties shape what it can be asked. The high grades exist for the main "
        "Maison only, while the ordinary tier is carried across every brand: a grouped "
        "reading of the top of the network is therefore one Maison's by construction, and "
        "saying so is part of showing it. And a large share of shops carry no grade at "
        "all, structurally, because the grading is joined onto the operated network — so "
        "the ungraded population is not a data hole to be filled but a different kind of "
        "point of sale.\n\n"
        "The reading worth building from it is a ratio rather than a total: what a top "
        "door turns over against what an ordinary one does, market by market. That is a "
        "question about where the upside sits, and it is the sort of thing a plan is "
        "argued with.",
        to_confirm="Whether the grade is exposed on the semantic sell-out view itself or "
        "only on the dimension, and whether a shop's grade is stable across years — a "
        "grade that is restated each year would make any trend on it a reclassification.",
    ),
    "certified_path_exclusions": Measure(
        key="certified_path_exclusions",
        label="What the governed store dimension leaves out, by construction",
        maturity=BETA,
        note="The dimension every sell-out query passes through carries three filters, "
        "and only one of them was known here. Reading them changes what a group figure on "
        "this screen can be said to mean.\n\n"
        "The first excludes the third-party counters, deliberately and by omission from a "
        "whitelist. The second excludes an activity zone that is inert today — the shops "
        "under it exist and sold nothing this quarter — which costs nothing now and "
        "becomes a silent hole the day one of them opens. The third is the one with reach "
        "beyond this cockpit: the dimension is filtered to a single brand, so every "
        "sell-out reading here is one Maison's and not the group's, however group-shaped "
        "the label above it looks.\n\n"
        "That third filter is correct for this screen and dangerous for the next question "
        "asked of it. A brand-level dimension answering what reads as a group question "
        "gives a right number to a wrong reader, and nothing in the number says which it "
        "is. A dormant set of several hundred shops under a second brand label was briefly "
        "taken for a missing perimeter on the strength of that filter and was not one — "
        "the shops record no sales in either year.",
        to_confirm="Whether any query on this screen is labelled at group level while "
        "reading a single brand, and what the inert activity zone is reserved for.",
    ),
    "absent_markets": Measure(
        key="absent_markets",
        label="Markets whose shops are not in the referential at all",
        maturity=BETA,
        note="One market has no point of sale in the sell-out referential under any "
        "label. What the cockpit shows for it is what the Maison invoices to third "
        "parties, to the euro, and its own retail — the majority of the country — is "
        "missing whole rather than partly.\n\n"
        "This fails in the most convincing way available: the market has a figure, the "
        "figure is exact, and it answers a different question from the one on the screen "
        "next to it. A market short by two-thirds looks identical whether a channel is "
        "unread, a share differs, or the shops are simply not there, and only counting "
        "the shops separates them. A ratio landing near a known ownership share was "
        "taken for the cause here and was a coincidence of size.",
        to_confirm="Whether other markets have no shop in the referential, by counting "
        "points of sale per market rather than by reading the size of a gap.",
    ),
    "rate_band": Measure(
        key="rate_band",
        label="Which gaps the exchange rate can honestly carry",
        maturity=BETA,
        note="The reconciliation warns that every line carries a currency move, and that "
        "is true. It is also the sentence under which a sales channel nobody reads can sit "
        "unexamined for a month, because a gap filed under change is a gap nobody looks "
        "for.\n\n"
        "Two properties separate the populations from outside. A market sharing the euro "
        "with the consolidation has no rate between the two sides at all, so anything left "
        "there is perimeter or fault by construction — one such market is short by "
        "most of itself while every other euro market lands inside a point. And a "
        "rate moves a market by a few points, not by a third: the budget rates are set "
        "months ahead, the widest genuine drift here sits comfortably inside the band, and "
        "the two markets shown by independent means to be perimeter rather than rate both "
        "fall outside it.\n\n"
        "The band is a convention and it is doing a modest job: it sorts what deserves a "
        "question from what deserves a shrug. It does not measure anything, and it is not "
        "a substitute for comparing growth to growth, which is the instrument that needs "
        "no rate at all.",
        to_confirm="Whether Treasury's own tolerance between budget and realised rates is "
        "near ten points, and what the flagged markets sell through that the sell-out and "
        "the sell-in both miss.",
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
        "the market, so a franchisee's till never reaches any figure here. France is the "
        "only market with this arrangement.\n\n"
        "Where the money does appear is the sell-in, as what the Maison invoices to the "
        "franchisee, under profit centres explicitly marked as franchised. Those can be "
        "read, and they say something the retail figures cannot: the franchised business "
        "is falling hard, and the fall is concentrated rather than general — one customer "
        "leaving accounts for about half of it while a good third of the others grew.\n\n"
        "A badge saying `PARTLY FRANCHISED` sat on the French retail figure for an hour, "
        "on the premise that a franchised till reaches the sell-out. It does not. The "
        "statement was true of the business and false of the number it was printed on.",
        to_confirm="The schedule of closures, so a step down is expected rather than "
        "discovered. The warehouse sees an exit the month it happens; it cannot see one "
        "coming, and a planned closure that surprises the screen costs the same as an "
        "unplanned one.",
    ),
    "franchise_exit": Measure(
        key="franchise_exit",
        label="Leaving the concession channel",
        maturity=BETA,
        note="The decline the reconciliation found in France is not an anomaly. It is the "
        "plan. The channel is budgeted to zero this year — a stated number of concessions "
        "closing, plus the end of two partnerships — after a year that had already taken "
        "it down by a fifth. What the warehouse showed as a franchise line collapsing is "
        "the Maison doing what it decided to do.\n\n"
        "So the question changes shape entirely. It is not whether to note the fall, nor "
        "which kind of exit it is: it is whether the plan this cockpit reads carries the "
        "closure at the same grain the actual does. If it does, the gap against plan is "
        "already near zero and nothing here needs saying — the screen is right without "
        "help. If the workbook books the closure elsewhere, or later, or in one line "
        "rather than a channel, then the screen shows a market failing at something it "
        "was told to do.\n\n"
        "The check is done and the plan carries it. Two channels move: the wholesale "
        "chains channel is planned to nothing at all, and the distributor channel is "
        "planned down by roughly a fifth. Together their decline matches, to within a "
        "rounding, the impact the budget deck states for the closures. The plan and the "
        "presentation are the same decision written twice.\n\n"
        "So there is nothing to note. The fall the reconciliation found is not a market "
        "failing; it is a market doing what was planned, and the screen judges against "
        "the plan rather than against last year — which is exactly why it needs no help "
        "here. The alarm came from comparing to last year, and last year is not the "
        "yardstick.\n\n"
        "One thing does not quite line up and is left standing rather than smoothed: over "
        "the months measured, the franchised profit centre alone invoices more than the "
        "whole distributor channel is planned to. Either that channel's plan is tight, or "
        "the profit centre spans more than one channel. It does not change the conclusion "
        "and it is not established.",
        to_confirm="Whether the franchised profit centre sits entirely inside the "
        "distributor channel. The aggregate agrees with the budget deck either way; the "
        "monthly detail does not, and only one of the two can be right.",
    ),
    "closed_store_customers": Measure(
        key="closed_store_customers",
        label="Where a closed store's customers go",
        maturity=ABSENT,
        note="Closing a point of sale is done to fund the ones that work, and the customer "
        "file follows — that is the intent, and it is what makes the closure worth doing. "
        "It also sets a trap for this screen.\n\n"
        "A customer who bought from a closed concession and later buys in an owned store "
        "arrives in the sell-out as growth. It is real revenue and it is not new demand: "
        "the same shopper moved. A market closing points of sale would therefore show its "
        "remaining network accelerating, and nothing here would distinguish that from "
        "winning customers — which is the one comparison the whole closure programme will "
        "be judged on.\n\n"
        "Nothing measures it today. The recruitment figure counts customers new to the "
        "brand, so a transferred one is not counted as recruited; that helps, and it does "
        "not separate transferred revenue from won revenue inside a store's takings.",
        to_confirm="Whether a transferred customer can be identified as such — the closed "
        "store's customer file matched against the receiving store's sales. Without it, "
        "the programme's own success measure is not readable.",
    ),
    "plan_rate": Measure(
        key="plan_rate",
        label="The plan and the actual are on one rate set",
        maturity=VALIDATED,
        note="The largest unexamined assumption under the main number, and it holds.\n\n"
        "The planning workbook is stated in euros and nobody here knew at which rates. "
        "The group's own budget-rate table answers it: the rates it fixes for the year "
        "are, currency by currency, the same ones the sell-out converts at — checked on "
        "every currency where the sell-out's implicit rate had been measured "
        "independently, and matching each time.\n\n"
        "Two consequences, and both are reassuring. Plan versus actual on this screen is "
        "already a local-currency comparison, so a market misses its plan for trading and "
        "never for its currency. And because that rate set does not move between years, "
        "every trend the sell-out produces is a local-currency trend too — the screen was "
        "rate-clean without anyone arranging it.\n\n"
        "The odd one out is the consolidation, whose set is neither the budget rates nor "
        "market rates. So the rate problem is confined exactly where it was found: the "
        "reconciliation against Finance, and nowhere else on this screen.",
    ),
    "brazil_tax": Measure(
        key="brazil_tax",
        label="Money per unit, when the yardstick moved",
        maturity=BETA,
        note="Brazil's own network sold more units for less money over the closed "
        "quarter, in local currency: volume up, revenue down, money per unit down by "
        "around ten points. The reconciliation reached that on its own, and read it as "
        "either a mix moving cheaper or a discount turning structural.\n\n"
        "It is neither, and the answer was already written into this repository. Tax rose "
        "in the market, overnight and after the plan was committed — the first wave "
        "landing on one state at the start of the fiscal year, with other states "
        "following at rates of their own. Net sales are gross "
        "less tax, so a larger tax slice moves net sales without moving gross sales or "
        "the basket a shopper fills — which is exactly the shape observed: units "
        "untouched, money per unit down. The decomposition is arithmetically exact and "
        "says the movement comes from price. True, and useless as a management signal.\n\n"
        "This is the case the note mechanism was built for and it is named in its opening "
        "lines. Everything needed is present: the shape is predicted, the note kind "
        "exists, the screen knows how to withhold a commercial question and ask another. "
        "The only missing piece is that nobody has recorded the note on the market, so "
        "the cockpit will keep offering a country manager a question about a government "
        "decision.\n\n"
        "Gross sales would settle it beyond argument and cannot be read: the discount and "
        "tax columns exist in the raw fact and the governed layer does not expose them. "
        "That was checked and refused earlier rather than worked around.\n\n"
        "One thing about it is unusual and the note has to carry it: this is not a step "
        "but a rolling change. Each state that follows widens the effect, so a gap that "
        "is explained this quarter is explained by more next quarter, and a note written "
        "as though it were a single event will look wrong within two quarters.",
        to_confirm="Nothing about the cause. What is outstanding is an action: record the "
        "note against the market, dated to the month the first wave landed, and revisit "
        "it as further states follow rather than filing it as settled.",
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
