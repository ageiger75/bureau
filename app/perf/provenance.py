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
        maturity=BETA,
        note="From the planning workbook, not the warehouse. It was carried here as "
        "settled, on the strength of its yearly total reconciling with the consolidated "
        "pack and its monthly totals with the quarter\'s estimate. **That is no longer "
        "enough.** Set beside a published monthly flash for the same brand and the same "
        "month, this workbook\'s plan is several points lower, and the shortfall is not "
        "spread evenly: by region it runs from a couple of points above to more than a "
        "tenth below.\n\n"
        "The spread is the finding. A different vintage of the same plan would move every "
        "region by roughly the same proportion; a range this wide, with one region above "
        "and several far below, is a perimeter that differs line by line. So the workbook "
        "is not an older version to be swapped — it is missing, or carrying, specific "
        "business. One alternative explanation has been eliminated rather than assumed: "
        "the workbook names exactly one Maison, so it is not two brands summed under one "
        "country.\n\n"
        "This matters more than a plan being slightly wrong, because a variance is a "
        "ratio of two numbers and this is the denominator. A screen whose actuals are "
        "known to be short and whose plan is short by a different amount produces a "
        "variance that is neither, and that lands near the truth or far from it by "
        "arithmetic accident rather than by measurement.",
        to_confirm="Which lines each region is missing or carrying, by comparing the "
        "workbook against the published plan region by region and then channel by "
        "channel — one region\'s discrepancy names its own cause faster than the total "
        "ever will.",
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
    "distribution_signals": Measure(
        key="distribution_signals",
        label="Distribution signals",
        maturity=BETA,
        note="Eight named signals per entity, each beside the threshold it must cross, "
        "computed against the norm of the entity's own channel within its own market. "
        "Nothing here is a verdict: the warehouse carries no authorisation field, so the "
        "measure is a distance from the retail behaviour of the same kind, never a "
        "finding.\n\n"
        "Three rankings were built on this data before one held, and each failed by "
        "applying a single criterion correctly. Counting fired signals ranked the "
        "largest doors, because signals built on a maximum or a count grow with traffic. "
        "Ranking on a free-goods ratio returned the smallest accounts, because a ratio "
        "over a few hundred units explodes. Ranking on absolute value returned one "
        "market, which carried four fifths of the total. Two conditions are therefore "
        "required and the reader enforces both: abnormal for its own kind first, "
        "material second.\n\n"
        "The totals are floors. Around a fifth of the rows carry no computable value, "
        "and every screen that shows a total must show its coverage beside it.",
        to_confirm="Whether the free-goods valuation reconciles with the per-millilitre "
        "measurement taken on the same account by another route — the two diverge by "
        "half; and whether a control group of markets known to be sound stays out of "
        "the ranking.",
    ),
    "partners": Measure(
        key="partners",
        label="Non-owned digital partners",
        maturity=BETA,
        note="Two bases, read from two different fact tables and never summed. The "
        "commercial brand is the only column with no source at all: the warehouse carries "
        "the customer's registered name and the store's label, not the banner a reader "
        "would recognise, so the mapping is written by hand and travels with the file. "
        "That is why this is BETA and not VALIDATED — every amount reconciles, and every "
        "name is a judgement.\n\n"
        "Three cautions the file itself records. The sell-in country column is the "
        "customer's country of registration, not the market it serves. A handful of lines "
        "carry no brand because the invoiced entity is a commercial operator rather than "
        "the platform its profit centre is named after — refusing to name them is the "
        "point, not a gap. And the deduction rate is computed from a different pair of "
        "columns on each side: it compares within a base and never across.",
        to_confirm="Whether the two sell-out fact tables should agree to the euro, and "
        "which is authoritative; and who the invoiced operators are behind the profit "
        "centres named for a platform.",
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
        "This register said for weeks that the rule could not be applied, because opening "
        "and closing dates were empty on every store and refurbishment covered about half "
        "the estate. **That was true of the store dimension and false of the warehouse.** "
        "A consolidation view at store grain carries all three dates filled throughout, "
        "and it carries something better: the consolidation\'s own comparable-base status, "
        "in seven named levels — same store, opened last year, opened this year, closed, "
        "refurbished last year, refurbished this year, other. It is not a rule to "
        "reinvent; it is the rule, written down.\n\n"
        "One correction to what this register said an hour ago. The dates are not filled "
        "throughout: the empty value is a sentinel date early in the last century rather "
        "than a null, so a column that reads as complete is not. They remain usable — an "
        "opening is real, a closing is real where the shop closed — provided the sentinel "
        "is treated as absent. Counted naively, every age computed from them is wrong.\n\n"
        "The view ties out: its statuses sum to the euro on the country table\'s retail "
        "line for the market checked. So the blocker is no longer whether the comparable "
        "base can be computed — it is that this view keys stores by a consolidation "
        "identifier, and the join to the sell-out turned out to need no bridge: that "
        "key is the sell-out's own store-group code. Two traps remain: the net sales "
        "account differs from the one the "
        "country table uses, and the current fiscal year carries few snapshots, one of "
        "them dated in the future.\n\n"
        "Nothing is shown until the two sources are reconciled: a same-store figure whose "
        "sign depends on which system you ask is not a figure. But what stands between "
        "here and there is now a join and a status field, not an absence.\n\n"
        "It has since been computed, on a small market where the join is complete and where "
        "the currency cannot interfere. The two readings differ by fourteen points, and the "
        "whole of that difference is one shop that opened mid-way through last year with no "
        "counterpart in the earlier period. Publishing the total there would publish an "
        "opening as if it were performance — which is exactly what a comparable base exists "
        "to prevent, demonstrated on a real market rather than argued.\n\n"
        "Two things constrain what can ever be claimed for it. The status field lives on "
        "the consolidation fact itself, beside the actuals and the forecasts, which is a "
        "serious presumption of provenance and not proof of use. And the same-store class "
        "is **not reproducible from the dates**: dozens of the shops in it carry a closing "
        "or a recent refurbishment date without being classed as closed or refurbished, so "
        "at least one further rule exists that is not visible. This perimeter can be read "
        "as given; it cannot be recomputed or checked. A screen showing it depends "
        "entirely on Finance for its correctness, and should say so.\n\n"
        "One candidate for what the published figure excludes has been eliminated: the "
        "catch-all status is nine tenths pseudo-entities — bulk and road-show lines, not "
        "shops — so a treatment that removes shops cannot be living there. The market "
        "where its size looked right was one bulk line, and the resemblance was a "
        "coincidence for the third time this week.",
        to_confirm="Whether the reported figure is computed on that status field — likely "
        "but not demonstrated, since carrying the taxonomy does not prove the published "
        "number uses it. Five candidate definitions have been computed and they separate "
        "widely, so one comparison against the published figure identifies the rule — or "
        "shows it is computed somewhere else entirely, which would make displaying this "
        "one a second competing number.",
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
        "were manufactured by comparing levels today and both were withdrawn.\n\n"
        "Searched and answered since: no view of the consolidation, in the governed schema "
        "or outside it, carries an amount in original currency. One of them is worse than "
        "the others — it states a euro amount with no rate-year at all, so not even which "
        "set converted it can be recovered. The rate-free instrument is not a preference "
        "here; it is the only exact method available.\n\n"
        "It has since been run across every market where both sides exist. Ten land on "
        "exactly zero, twelve more inside a point, and seven separate by more than that. "
        "Ten exact zeros is the demonstration: a method that agrees to the decimal on a "
        "third of the estate is measuring, not approximating, and the spreads it leaves "
        "are findings rather than noise. The levels bounded the gap; this measures it.\n\n"
        "Two things have narrowed this since. The screen's own convention is now decided "
        "rather than inferred — budget rates, fixed across the year, `fixed_rates` — so "
        "everything stated here is on one set and the unreconcilable levels are confined to "
        "figures taken from the consolidation's own views. And the headline no longer "
        "crosses the boundary at all: it is a subtraction inside a single published file. "
        "This measure stops being load-bearing for the number and stays the right "
        "instrument for the question behind it.",
        to_confirm="Reading the consolidation's own year-on-year alongside the sell-out's, "
        "market by market, and what the remaining spreads are, now that the method itself "
        "is demonstrated rather than proposed.",
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
    "consolidation_by_store": Measure(
        key="consolidation_by_store",
        label="The consolidation, readable one store at a time",
        maturity=BETA,
        note="The consolidation was read as a country total for months, and a view exists "
        "carrying it at store grain. It ties out to the euro on the country table\'s "
        "retail line, and the join to the sell-out turned out to need no bridge at all: "
        "the consolidation\'s entity key and the sell-out\'s store-group code are the same "
        "string.\n\n"
        "Joined, it decomposes the market\'s retail residue completely — every euro placed, "
        "the whole falling within single digits of the gap measured from the other "
        "direction. What it decomposes into is the finding: a bulk pseudo-entity worth "
        "most of it, a set of dormant road-show pseudo-entities, one shop opening after "
        "the quarter, six shops that closed inside it, and the unmatched counters.\n\n"
        "The near-equality of the two store counts, flagged here as a hypothesis rather "
        "than a finding, was neither a match nor a five-shop discrepancy. Both counts were "
        "right and neither counted what the other counted: eleven entities carrying no "
        "sale on one side, six live shops on the other whose closing dates fall inside the "
        "quarter and which therefore sell legitimately in both sources. **A difference of "
        "five between two counts does not mean five items differ** — the lesson is worth "
        "more than the reconciliation it settled.\n\n"
        "What is left is a genuine gap on an identical, named perimeter, traceable shop by "
        "shop where this morning it was a lump. It is stated in euros, so the two rate "
        "regimes still bound it rather than measure it: reading it properly means redoing "
        "this confrontation on growth, or in local currency against two consolidation "
        "years.",
        to_confirm="What the gap on the common perimeter becomes once it is read on "
        "growth rather than on levels, and whether the entity key holds as the join "
        "outside the one market tested.",
    ),
    "store_grain_is_not_only_stores": Measure(
        key="store_grain_is_not_only_stores",
        label="What sits in the consolidation at store grain, that is not a store",
        maturity=BETA,
        note="The consolidation\'s store grain carries entities that are not points of "
        "sale, and they are not marked as such — only their names distinguish them. A "
        "bulk pseudo-entity, a family of road-show pseudo-entities, and they sit inside "
        "the retail line under the comparable-base status meaning \"other\".\n\n"
        "Two consequences. Anyone dividing that retail line by its store count divides by "
        "a denominator holding things that have no floor and no staff. And the bulk this "
        "screen has spent weeks separating — because the sell-out mixes it with shop "
        "sales — is sitting inside the consolidation\'s retail too, at a size matching "
        "what the reforecast pulls out on its own cleaning sheet. Neither source keeps it "
        "out of retail; one of them names it, in a field nobody reads.\n\n"
        "The counters excluded from the modelled dimension carry the literal string used "
        "for \"not applicable\" as their store-group code — a deliberate filler rather "
        "than a null. They are therefore unmatchable by design and not by omission, which "
        "is a different problem with a different fix.",
        to_confirm="Whether other markets carry the same kind of pseudo-entity, and "
        "whether the bulk pseudo-entity is the same money the reforecast separates.",
    ),
    "placeholders_that_answer": Measure(
        key="placeholders_that_answer",
        label="The recurring defect is not missing data, it is fillers that reply",
        maturity=BETA,
        note="Four defects found in the warehouse this week look unrelated and are one. A "
        "field description stating the opposite of what the field counts. Two dimension "
        "descriptions listing a couple of their values and omitting the one a reader comes "
        "for. A store code whose value is the literal string meaning not-applicable. A "
        "date whose empty state is a sentinel early in the last century rather than a "
        "null.\n\n"
        "Each one answers. None declines to answer. That is the whole defect: a missing "
        "value announces itself and gets handled, while a filler shaped like a value is "
        "consumed silently and travels. All four produced a confident wrong reading before "
        "being caught — a basket at a third of its size, a market declared absent, a "
        "column of dates declared complete.\n\n"
        "The rule that follows is cheap and general: join on codes and never on labels, "
        "treat any sentinel as absent before computing, and read a field's description as "
        "a hypothesis about the field rather than a statement of it. The clearest instance "
        "was found inside a query written to avoid exactly this trap, which measures how "
        "easy it is to walk into.",
        to_confirm="Whether these fillers are historic residue or current convention — "
        "which decides whether they are corrected at the source or documented where they "
        "are.",
    ),
    "growth_spreads": Measure(
        key="growth_spreads",
        label="What the rate-free comparison leaves behind",
        maturity=BETA,
        note="Run market by market, the growth comparison closes most of the estate and "
        "isolates a short list. Two of the spreads were already suspected and are now "
        "sized; one is new and covered by nothing found so far; the rest sit just above "
        "the threshold.\n\n"
        "The most valuable reading is not on the list but about it. The largest market\'s "
        "growth agrees within about a point while its level gap is substantial. A large "
        "level gap with agreeing growth is a **stable structural difference, not a "
        "drift** — something booked systematically on one side, in the same proportion in "
        "both years. That is a far better description than residue, and it moves the "
        "question from the data to the accounts: not what is missing, but what the "
        "consolidation includes here that the till does not, every year alike.\n\n"
        "One market reverses sign between the two sources, which no reading gathered this "
        "week explains. One is where a tax change was recorded as a basis note, and the "
        "shape of its spread is the shape that change predicts — the accounts falling "
        "further than the till, by whatever the tax took. That is a hypothesis with an "
        "obvious test and not a conclusion: the spread must open at the month the tax "
        "changed and be absent before it. A spread of the right size in the wrong month "
        "would mean something else entirely.",
        to_confirm="Whether the tax-change spread opens at the month the tax changed; what "
        "the sign-reversing market sells that one source sees and the other does not; and "
        "whether the smallest markets on the list are stable or an artefact of counting "
        "growth over very few shops.",
    ),
    "why_not_rules": Measure(
        key="why_not_rules",
        label="Why a rule set cannot make the warehouse equal the consolidation",
        maturity=BETA,
        note="The obvious question, and it deserves a real answer: if the gap between the "
        "two systems has been named market by market, why not encode the rules and compute "
        "the published figure from the warehouse?\n\n"
        "Part of the gap is mechanical and rules do close it. Counters a dimension omits, "
        "pseudo-entities filed inside retail, a market absent from the referential, zone "
        "labels that are not geographies, the cleaning lines a reforecast separates — all "
        "of it is deterministic, all of it repeats, and most of it is already written "
        "down here.\n\n"
        "The rest is decided rather than derived, and no rule reaches it. The rate set the "
        "consolidation applies is in no table anyone can query, and it changes by exercise. "
        "A provision estimated through the year and trued up at close moves a quarter by "
        "over a million on one market, on a date a person chose. A customer reclassified "
        "between two channels is a decision taken once and applied from a date. Accruals "
        "and eliminations exist in one system by construction and in the other not at all. "
        "**A rule can only exist where a relationship is deterministic**, and a close is "
        "the opposite of that — it is where judgement is applied on purpose.\n\n"
        "And the argument that settles it is about timing, not accuracy. Suppose the rules "
        "were perfect on three months: there would still be no way to know they held on "
        "the fourth until the accounts published it. The rule set therefore never delivers "
        "the figure *earlier* — it delivers a figure that still has to be checked against "
        "the one it was meant to replace. What it delivers instead is the explanation of "
        "the difference, which is worth building and is worth more to the people who own "
        "both systems than to this screen.\n\n"
        "So the screen runs at two speeds, and says which one it is on. Before the close: "
        "the warehouse, directional, in its own terms, useful the next morning. After the "
        "close: the accounts, once, and that is the figure to quote. Neither is an estimate "
        "of the other.",
        to_confirm="Whether the residual left after every known rule is applied shrinks "
        "month on month — a shrinking residual is a maturing pipeline, and one that jumps "
        "is a closing decision worth asking about by name. Half of that is now measurable "
        "without the warehouse and without anyone's help: twelve published files, read as a "
        "series, say which months were changed after they were published and by how much. "
        "The provision trued up at close is confirmed as real; the series turns it from a "
        "reason a reconciliation cannot converge into a dated list.",
    ),
    "window_comparability": Measure(
        key="window_comparability",
        label="A sound instrument does not make two periods comparable",
        maturity=BETA,
        note="A fixed calendar window was compared across two years and showed a "
        "collapse in transactions large enough to eclipse everything else on the table. "
        "The reading had been screened for the fault that had just been caught elsewhere: "
        "the ratio of lines to transactions was stable, so the counter had not been "
        "renumbered, so the fall was taken as real. Widened to the whole quarter, the "
        "transactions are flat. The promotional peak had moved by two weeks, and the "
        "window had been laid across the gap.\n\n"
        "The lesson generalises past this market. Two independent questions hide inside "
        "one comparison — is the instrument trustworthy, and do the two periods hold the "
        "same event — and passing the first reads exactly like passing both. Ratio "
        "stability answers only the first. Nothing about a correctly measured period "
        "says it describes the same commercial moment as the one beside it.\n\n"
        "This screen is exposed to it by construction: it sets a calendar month against "
        "the same month last year. Wherever the commercial calendar is keyed to something "
        "other than the Gregorian month — a lunar new year that moves between two months, "
        "a festival on a moving date, a promotional peak scheduled by a partner — that "
        "comparison silently sets one event against another. The context register now "
        "carries a note for it, and a note is a reader's device rather than a fix: what "
        "would fix it is a window that follows the event.",
        to_confirm="Which markets have a commercial calendar that moves against the "
        "Gregorian month, and by how much — the answer decides whether a note per "
        "occurrence is enough or whether the comparison window itself has to move.",
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
        note="The store dimension carries a grade per shop, inside the certified path, and "
        "nothing here read it until now. Read, it produces the first finding of this whole "
        "reconciliation that is about the business rather than about the data.\n\n"
        "The top tier grows while the ordinary tier falls, seven points apart, and the "
        "sign holds in three quarters of the markets — in one it is more than forty "
        "points. A top door turns over two and a half times what an ordinary one does. On "
        "the largest market this reframes a decline that had been validated three times "
        "over: its national figure is the average of a top tier growing and an ordinary "
        "tier falling twice as fast. **That market is not declining, it is "
        "concentrating** — which is a different sentence, addressed to different people, "
        "and it argues for the closure programme rather than against it.\n\n"
        "A control question decided how this can be read, and it answered in both "
        "directions at once. The grade is not versioned: one row per shop, one grade, no "
        "history. So a reclassification cannot contaminate the trend — today\'s grade "
        "applies to both years by construction, and what is measured is genuinely "
        "performance on a constant perimeter. And a reclassification is undetectable: a "
        "shop promoted this year has last year\'s sales counted under its new grade, and "
        "nothing here can say how it was graded then.\n\n"
        "So the trend is clean and the composition is dated today. A screen showing this "
        "shows the performance of the shops that hold the top grade **now**, never of "
        "those that held it a year ago, and the difference cannot be measured from here. "
        "That belongs on the panel, not in a footnote.",
        to_confirm="Whether the grade is restated in a source that keeps history, so the "
        "composition can be dated; and how much of the ordinary tier's movement in the "
        "smallest markets is openings rather than trading — this is not a comparable base, "
        "and two markets where the ordinary tier leaps on single-digit shop counts look "
        "like openings.",
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
        "not separate transferred revenue from won revenue inside a store's takings.\n\n"
        "One half of the arithmetic has since become readable. The consolidation at store "
        "grain names its closed stores and what they took, so the revenue leaving is "
        "measurable. What leaves is not what arrives, and the transfer itself is still "
        "unmeasured.",
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
        "reconciliation against Finance, and nowhere else on this screen.\n\n"
        "That confinement has since been made a rule rather than an observation: the screen "
        "states everything at the budget rates and holds them fixed all year. See "
        "`fixed_rates` — what this measure discovered, that one settles.",
    ),
    "warehouse_before_close": Measure(
        key="warehouse_before_close",
        label="Where the warehouse can steer before the accounts close",
        maturity=BETA,
        note="The screen has said for weeks that it runs at two speeds and names the one it "
        "is on: before the close the warehouse, directional; after it the consolidation, "
        "and that is the figure to quote. The sentence was true and stated globally, which "
        "made it close to useless — it asked a reader to distrust the warehouse everywhere "
        "because it cannot be trusted somewhere.\n\n"
        "It is now measured per market, over twelve published months, growth against growth "
        "so no exchange rate enters. Three shapes come out and each asks for something "
        "different. Most of the estate is **aligned**: the two systems agree month after "
        "month, which means the warehouse is not a degraded stand-in for the accounts — it "
        "says the same thing three weeks earlier. A couple of markets sit at a **constant "
        "displacement**, steady enough to state as one number, which is a rule someone can "
        "write. The rest is **unstable**, and no rule reaches it, because what moves it is "
        "decided at the close.\n\n"
        "That the aligned group is the majority is the finding that pays for the whole "
        "reconciliation. It converts a caveat into a permission: on most markets the CEO "
        "can act on the warehouse before Finance publishes, and on the named few he waits. "
        "Nothing about the previous global statement allowed either.\n\n"
        "One rule of the grading matters more than any threshold in it: a market absent "
        "from the measurement grades as **not measured**, never as aligned. Every version "
        "of this cockpit that let an absence default to a pass produced a confident wrong "
        "answer inside a week.",
        to_confirm="Whether the grades hold on the next published month — a market moving "
        "out of the aligned group is worth more attention than any single variance, because "
        "it says an instrument changed rather than a business.",
    ),
    "closing_month": Measure(
        key="closing_month",
        label="The month the two systems agree least is the one that closes the year",
        maturity=BETA,
        note="Across twelve months and thirty-odd markets, the largest divergences between "
        "the consolidation and the warehouse do not scatter. They pile into one month, and "
        "it is the last month of the fiscal year — eight of the ten widest sit there, on "
        "markets that otherwise disagree by very little.\n\n"
        "Six markets landing in one month is not a coincidence of six markets; it is a "
        "property of the month. The close is where provisions are trued up, "
        "reclassifications applied and accruals settled — everything the year deferred is "
        "decided at once, and none of it exists in a system that records what shops sold.\n\n"
        "The consequence for the screen is narrow and worth stating: a year-end comparison "
        "between the two sources is the least informative one available, and a divergence "
        "measured there should never be read as a market's instrument being broken. It is "
        "the calendar of the close, and it repeats every March.\n\n"
        "It has since been tested by removal rather than argued, and the result is larger "
        "than expected. Regrading on the eleven months without the close moves three "
        "markets out of the unstable group entirely — one of them falls from over a point "
        "of movement to a third of a point. So a real share of what was being read as "
        "markets behaving erratically belonged to the month, and was being charged to the "
        "countries. The grading window now excludes the closing month, and the close is "
        "reported on its own terms instead of contaminating eleven other months.",
        to_confirm="Whether the same concentration appears in the prior year. One year "
        "makes the exclusion a measurement of this close; two make it a property of closes, "
        "which is what would justify writing it as a permanent rule.",
    ),
    "door_filed_twice": Measure(
        key="door_filed_twice",
        label="One door, two entities, and a market at the top of the wrong list",
        maturity=BETA,
        note="The widest divergence in the whole table, on a market nobody expected to see "
        "there, came from a single shop. The consolidation files that door on an entity of "
        "its own; the warehouse's referential codes it inside the country's main entity. "
        "Both are internally consistent. Set side by side, one system's country contains "
        "the shop and the other's does not.\n\n"
        "It stayed invisible while the door traded, because a difference of one shop inside "
        "a large country is a rounding error in a growth rate. It became the largest line "
        "in the table the month the door closed: its collapse pulls the warehouse's country "
        "down and leaves the consolidation's country untouched, so the two diverge by "
        "several tens of points on a market that agrees to within a point once the shop is "
        "removed from both sides.\n\n"
        "Two things generalise. A perimeter difference is worth what the business inside it "
        "is *doing*, not what it is worth — a large stable one hides and a small collapsing "
        "one shouts. And the arithmetic that found it is the one to keep: the country was "
        "recomputed without the door and the divergence fell to nothing, which is a "
        "demonstration rather than an explanation. Naming a plausible cause proves nothing; "
        "removing it and watching the gap close proves it.\n\n"
        "The removal has now been run on both sides across the whole window, and the market "
        "that led the divergence table by a wide margin sits in the aligned group — an "
        "average distance near zero and a spread under a point. One door, correctly filed "
        "in each system and filed differently between them, was the entire finding.\n\n"
        "The list was then asked for rather than waited for, and it has one name on it. The "
        "counterpart is identified: what the sold side holds as one shop, the consolidation "
        "splits into two entities — the retail floor and the café inside it — under a "
        "prefix the sold side does not use, and the two sides reconcile to under a fifth of "
        "a percent. Both consolidation entities are classed outside the comparable base, "
        "which is why the published figure never showed the door either.\n\n"
        "The rest of the unmatched codes are structural and legitimate: web pseudo-shops, "
        "marketplace, external counters, roadshows — things a store-grain consolidation "
        "does not carry because they are not shops. One physical shop out of a hundred and "
        "eleven codes. The worry that others would surface one closure at a time is "
        "answered, and answered by asking rather than by waiting.",
        to_confirm="Whether the two consolidation entities should be folded onto the sold "
        "side's single shop in the cockpit itself. Nothing depends on it today — the "
        "divergence file already carries that market with the door removed from both sides "
        "— so it is a question for whenever a door-level panel exists.",
    ),
    "counters_outside_the_view": Measure(
        key="counters_outside_the_view",
        label="The counters the view excludes are excluded on both sides",
        maturity=BETA,
        note="Written here first as a hypothesis with a test attached: the governed "
        "sell-out view excludes a class of counter present in exactly five markets, four "
        "of them in the unstable group, and in one of those the counters did not exist "
        "last year — a perimeter starting from nothing and growing produces a distance of "
        "constant sign and rising size, which is the shape that market shows. Plausible, "
        "concentrated, and wrong.\n\n"
        "The test was to put the counters back and watch the distance close. It opened "
        "instead, on every market and in almost every month — on the largest of them not a "
        "single month out of eleven improved. A hypothesis that predicts a direction and "
        "gets the opposite one is not weakened, it is finished.\n\n"
        "And the refutation is worth more than the hypothesis was. If adding the counters "
        "makes the two sides disagree, the consolidation is not counting them in its sold "
        "lines either — so the view's exclusion is not a hole this cockpit inherits, it is "
        "**the same boundary drawn in the same place**. That had been assumed for months "
        "and never demonstrated; it is now demonstrated, by a test designed to show the "
        "opposite. The counters are consolidated elsewhere, on the shipped side, which the "
        "orders of magnitude support.\n\n"
        "One market of the five appeared to refuse the conclusion, and the way that "
        "exception died is worth more than the exception was.\n\n"
        "Over the months where its counter estate was unchanged, excluding the counters left "
        "the consolidation growing seven points faster and including them left the warehouse "
        "growing three points faster. Both extremes overshoot, in opposite directions — and "
        "the inference drawn from that was that the consolidation must carry part of those "
        "counters and not the rest. The arithmetic was right. The conclusion was wrong, and "
        "it was wrong in a way worth naming: **toggling a bucket tests the bucket, not the "
        "label on it.**\n\n"
        "The bucket did not hold what its name said. Three of that market's marketplaces "
        "had been filed inside the external-counter class — they carried no store code, and "
        "the class was where uncoded things landed — while the consolidation counts "
        "marketplace as sold, like every other market. So the governed view was dropping "
        "three marketplaces worth around half of that country's own network, the "
        "consolidation was not, and the whole displacement was a classification error rather "
        "than a boundary drawn differently. It was repaired at source: the three were "
        "recreated under proper marketplace codes, and the distance falls from eight or ten "
        "points to two tenths of a point in that exact month. A dated repair, visible in the "
        "series, is as close to proof as this kind of question gets.\n\n"
        "So the finding is universal after all: all five markets draw the boundary in the "
        "same place, and the one that seemed not to was measuring a defect. The partition "
        "inference stands as a form and is retracted as a conclusion — before reading a sign "
        "flip as a partition, look inside the bucket being toggled.",
        to_confirm="Where Finance consolidates those counters, stated rather than inferred "
        "from magnitudes — the shipped-side line they land on, and whether every market with "
        "them does it the same way.",
    ),
    "gross_column_break": Measure(
        key="gross_column_break",
        label="A break inside one market's own series, and a claim that was mine to retract",
        maturity=BETA,
        note="This entry began as a finding and is kept because of how it failed.\n\n"
        "The raw fact was read as stating a gross figure below its own tax-inclusive net, "
        "which was called arithmetically impossible. It is not. The gross column is stated "
        "before tax and the net column beside it includes tax, so a ratio under one hundred "
        "per cent is the normal state wherever tax exceeds discount — as it is in some "
        "twenty markets. **Two different bases were compared and the difference was read as "
        "a defect.** This repository has recorded that exact failure before, on the month a "
        "budget was derived by dividing a published value at one rate set by a published "
        "percentage computed at another. Knowing a failure mode does not stop you repeating "
        "it; only checking does.\n\n"
        "What survives the correction is smaller, sharper and real. Inside one market the "
        "ratio holds its usual band, collapses to a fifth of it for thirteen consecutive "
        "days, and returns to normal the next day. Every channel moves together, the shop "
        "count is unchanged throughout, and no other market moves on those dates. A break "
        "with a start, an end and a perimeter is a feed incident, not a business event.\n\n"
        "And the method that survives is the general lesson: **compare a series to itself, "
        "not to its neighbours, unless the base is known to be homogeneous.** That ratio "
        "runs past two hundred per cent in some markets and under ninety in others, so it "
        "measures nothing across a table of countries. Within one country, across time, it "
        "found a thirteen-day window to the day.\n\n"
        "One more anomaly of the same kind sits beside it: another market's gross column is "
        "zero throughout, on every month and every channel. Empty rather than inconsistent, "
        "and invisible to any test that divides by it.\n\n"
        "Neither of them explains the divergence that prompted the search. The net figures "
        "are undisturbed across the whole window, and the net is what the reconciliation "
        "reads. That market's distance stays open.",
        to_confirm="What ran against that market's feed on those thirteen days, and why "
        "another market's gross column is empty — both asked of whoever owns the feed, as "
        "defects with dates rather than as questions about trading.",
    ),
    "model_change": Measure(
        key="model_change",
        label="A market that changed model has no last year",
        maturity=BETA,
        note="A country served through a distributor is invoiced once, at wholesale, when "
        "the goods leave. The same country run as a subsidiary is counted when a shopper "
        "pays, at retail. Nothing about the demand has to move for the recorded revenue to "
        "change by the whole distance between those two prices.\n\n"
        "So a year-on-year across the switch measures a change of accounting and presents "
        "it as growth — and it fails in the direction nobody checks. A market showing a "
        "collapse gets a question within the day; a market showing a surge gets "
        "congratulated, and this produces a surge. The screen therefore withholds the "
        "comparison instead of footnoting it: a caveat under a number invites the reader "
        "to use the number, and there is no honest number here to use.\n\n"
        "It was very nearly filed as something else. Read from the data alone the market "
        "looks like an opening — last year absent on both sides, this year present — and "
        "an opening is a different fact with the same shape in a table of two columns. "
        "Nothing measurable separates them. The distinction came from the business "
        "knowing it, which is the argument for this register existing at all.\n\n"
        "The comparison returns on its own once twelve months exist on the new model. "
        "Until then the market is read on its level and its plan, both of which are "
        "stated on today's basis and are sound.",
        to_confirm="Which other markets changed model in the last two years, and on which "
        "month each switched — a switch mid-year splits a single year across two bases and "
        "is worse than one at the year boundary, because the annual total is then on "
        "neither.",
    ),
    "ceo_interlocutor": Measure(
        key="ceo_interlocutor",
        label="Who the screen may put in front of the CEO",
        maturity=BETA,
        note="The screen was proposing a country General Manager as a direct conversation "
        "for the CEO, and filing leaders under zones — a northern-Europe grouping, a "
        "north-American one — that are none of the seven perimeters he runs. The directory "
        "had been given the map of markets instead of the reporting line.\n\n"
        "That is not a display setting. A cockpit that seats its reader above his own "
        "business-unit heads damages a line the house holds, and it does it at every "
        "reading, politely, with nothing to signal the error.\n\n"
        "The trap in the source is sharper than it looks: **the role decides and the job "
        "title never does**. One business-unit head is titled *General Manager* and "
        "reports to the CEO; one *Managing Director* reports to a business-unit head. A "
        "filter on the title would have promoted the second and demoted the first — which "
        "is exactly the mistake, arrived at by a different route.\n\n"
        "And a perimeter whose head is not in the source stays without one. It does not "
        "receive its nearest country manager: an empty interlocutor is a fact that gets "
        "corrected at the source, a substituted one is a conversation sent to the wrong "
        "person that nobody notices.",
        to_confirm="Which markets belong to which perimeter. The source names zones — "
        "southern Europe, the Nordics — where the screen names countries, so it places "
        "part of the estate and the rest is listed as unplaced rather than guessed.",
    ),
    "plan_reference": Measure(
        key="plan_reference",
        label="The plan is the budget, not the reforecast",
        maturity=VALIDATED,
        note="The screen said `no forecast reported`, which was false: the house produces "
        "successive reforecasts and the whole internal comparison rests on them. The fix "
        "was never a connection, though — it was a decision about which vintage a variance "
        "is measured against, and a variance measured against a moving reference measures "
        "nothing at all.\n\n"
        "It is decided: **the budget**. Reforecasts are read and displayed as vintages, "
        "dated, beside the figure; they are never the reference the gap is taken from.\n\n"
        "The reason is the one the plan itself rests on: a commitment that moves when the "
        "year gets hard has stopped being a commitment. A reforecast is a useful statement "
        "about where the house now thinks it lands, and a poor yardstick for whether it is "
        "holding what it promised.",
    ),
    "fixed_rates": Measure(
        key="fixed_rates",
        label="One rate set, fixed for the year, decided rather than discovered",
        maturity=VALIDATED,
        note="This register treated the exchange rate for months as something to be found "
        "out, and wrote, as though it closed the matter, that the consolidation's set sits "
        "in no table anyone can query. The sentence is true and the conclusion was wrong. "
        "A rate is a convention before it is a measurement, and a convention is settled by "
        "deciding it — which is what has now been done, at the only level where it could "
        "be.\n\n"
        "The decision: this screen states everything at the group's budget rates, the set "
        "fixed for the exercise, and holds them fixed from April to March. Nothing here "
        "converts at a rate that moves.\n\n"
        "Three things fall into line at once, and they were already in line without anyone "
        "having arranged it. The planning workbook is stated at those rates. The sell-out "
        "converts at those rates, and they do not move between years. And of the two actual "
        "columns the published file carries side by side, the one this reader takes — the "
        "choice that was made for a technical reason and cost this repository a retracted "
        "finding — is the one at the budget's rates. So every term of every comparison on "
        "this screen now sits on one set by decision, not by luck: a market misses its plan "
        "for trading and never for its currency, and every trend is a local-currency trend.\n\n"
        "What stays outside is named rather than absorbed. The published file's neighbouring "
        "column, and the sell-in views of the consolidation, carry a set of their own; they "
        "are no longer under the headline, which is a subtraction inside one file, but a "
        "figure taken from them must not be set against a figure from here.\n\n"
        "And the convention has a cost that has to be said out loud, because a fixed rate "
        "is convenient in exactly the way that misleads. It does not say what the year "
        "earned in euros. Nobody should read a figure on this screen as cash. Performance "
        "is measured at a rate that is held still on purpose; what a moving rate does to "
        "the money belongs to Treasury, and is a different question asked by different "
        "people.",
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
        "Gross sales would settle it beyond argument and cannot be read from the governed "
        "layer: the discount and tax columns exist in the raw fact and the layer does not "
        "expose them. They have since been read at the raw grain, and they answer a "
        "different question from this one — see `gross_column_break`. What they settle is that "
        "the *divergence between the two systems* on this market is not a tax-treatment "
        "difference: the warehouse's implicit rate is not frozen, it moves by more than the "
        "real tax did, and it does not track the divergence in size or in sign. A hypothesis "
        "that predicts a shape and finds none is finished. This measure, which is about the "
        "movement inside one system rather than between two, is untouched by that.\n\n"
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
