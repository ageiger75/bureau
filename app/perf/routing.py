"""What kind of problem this is, before any question of how big it is.

The cockpit used to rank everything material together: a market trading badly, a plan that
was never reachable, a feed that stopped, and a revenue line filed on the wrong side of an
accounting boundary all competed for the same five slots, sorted by euros. Sorting them
together is the mistake. They are answered by different people, in different rooms, on
different weeks — and three of the four are not questions for a commercial lead at all.

So the class is decided first, and it decides the surface:

* **business** — what deserves the CEO's attention this week: trading, and the risks that
  lead it. This is the only surface where a market's own leader is the person addressed.
* **plan** — plans that ask for growth the record has never delivered. A Finance and region
  review, measured in the year's embedded gap rather than in this month's miss.
* **data** — broken feeds, accounting boundaries and unsettled definitions. Real work,
  owned by people who are not the market, and never worth a slot of CEO attention.

The rule the whole module exists to enforce: evidence never changes the class, and it never
demotes a material problem. A €2.3m gap nobody can explain stays exactly where its money
puts it — what changes is the move, from "challenge the market" to "find out why".
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

from . import context
from .model import BusinessUnit, Dataset

# --------------------------------------------------------------------------- classes

PERFORMANCE = "performance"
PLAN = "plan"
EXECUTION = "execution"
RISK = "risk"
OPPORTUNITY = "opportunity"
DATA = "data"
ACCOUNTING = "accounting"
DEFINITION = "definition"

#: Which surface each class is answered on. Three, not eight: the reader has three kinds
#: of week — their own, Finance's, and the data team's — and a class that cannot be placed
#: on one of them is a class that has not been thought through.
SURFACES = {
    PERFORMANCE: "business",
    RISK: "business",
    OPPORTUNITY: "business",
    EXECUTION: "business",
    PLAN: "plan",
    DATA: "data",
    ACCOUNTING: "data",
    DEFINITION: "data",
}

#: Shown on screen, so in the screen's language — which is English until the whole surface
#: is turned over at once. A panel translated on its own leaves the reader on a page in two
#: languages, which is the defect this cockpit keeps finding elsewhere.
CLASS_LABELS = {
    PERFORMANCE: "Performance",
    PLAN: "Plan",
    EXECUTION: "Exécution",
    RISK: "Risque",
    OPPORTUNITY: "Opportunité",
    DATA: "Donnée",
    ACCOUNTING: "Comptabilité",
    DEFINITION: "Définition",
}

# ----------------------------------------------------------------------------- moves

CHALLENGE = "challenge"
INVESTIGATE = "investigate"
REQUEST_DATA = "request_data"
REQUEST_PLAN = "request_plan"
NO_CEO_ACTION = "no_ceo_action"

MOVE_LABELS = {
    CHALLENGE: "Challenger",
    INVESTIGATE: "Enquêter",
    REQUEST_DATA: "Demander la donnée",
    REQUEST_PLAN: "Demander un plan",
    NO_CEO_ACTION: "Aucune action du CEO",
}


#: Two words, and only where the fact changes what the reader does. The full sentence
#: behind each lives once, in the methodology note at the foot of the screen.
#:
#: The rule that decides between a badge and a paragraph: a fact that changes the action
#: is a badge, a fact that explains how the number was made is a footnote. "Shipped, not
#: sold" changes the action — it is why a partner's ordering rhythm is a candidate
#: explanation. The three sentences saying what shipping means do not, and they were
#: printed eight times on one screen.
SELL_IN_BADGE = "SELL-IN"
UNMEASURED_BADGE = "CAUSE NON MESURÉE"
STALE_BADGE = "LECTURE PÉRIMÉE"
OPEN_DEFINITION_BADGE = "DÉFINITION OUVERTE"
NO_COMMITMENT_BADGE = "SANS ENGAGEMENT"
#: There was a `PARTLY FRANCHISED` badge here for an hour, on the premise that a
#: franchised store's till reaches the sell-out. It does not: the franchised network is
#: absent from that flow entirely, measured to within a fraction of a per cent of the
#: market. The badge said something true about the business and false about the figure it
#: sat on, which is the worst combination — a reader would have discounted a number that
#: needed no discounting. What is true is recorded in the register instead, where an
#: absent measure belongs.


def badges_for(unit: BusinessUnit, has_breakdown: bool = False) -> List[str]:
    """The badges this figure earns, in reading order."""
    found = []
    if unit.basis == "shipped":
        found.append(SELL_IN_BADGE)
    if not has_breakdown:
        found.append(UNMEASURED_BADGE)
    return found


class Routed:
    """One item, placed: its class, where it is answered, and by whom."""

    __slots__ = ("klass", "move", "destination", "reason")

    def __init__(self, klass: str, move: str, destination: str = "",
                 reason: str = "") -> None:
        self.klass = klass
        self.move = move
        #: Who answers. Empty means the market's own owner, which is the only case where
        #: naming a person beside a number is fair.
        self.destination = destination
        #: Why this class and not another, in one clause. Printed, because a routing
        #: decision the reader cannot check is a routing decision they have to trust.
        self.reason = reason

    @property
    def surface(self) -> str:
        return SURFACES.get(self.klass, "business")

    @property
    def is_business(self) -> bool:
        return self.surface == "business"

    @property
    def class_label(self) -> str:
        return CLASS_LABELS.get(self.klass, self.klass)

    @property
    def move_label(self) -> str:
        return MOVE_LABELS.get(self.move, self.move)


def _note_of(unit: BusinessUnit, kind: str):
    return next((n for n in unit.context_notes if n.kind == kind), None)


def classify(unit: BusinessUnit, is_suspect: bool = False) -> Routed:
    """The class of one business unit's gap.

    Order matters, and it runs from "this is not a result" to "this is a result". A broken
    feed that also carries a reclassification note is a broken feed first: nothing can be
    said about the boundary until the numbers arrive.
    """
    if is_suspect:
        return Routed(
            DATA, NO_CEO_ACTION, "Équipe data",
            "une rupture du flux, pas un fait de commerce",
        )

    reclassified = _note_of(unit, context.RECLASSIFIED)
    if reclassified is not None:
        return Routed(
            ACCOUNTING, NO_CEO_ACTION,
            reclassified.action_owner or "Consolidation",
            "le plan et les comptes rangent ce chiffre sous des segments différents : une "
            "frontière, pas un résultat",
        )

    basis_change = _note_of(unit, context.BASIS_CHANGE)
    if basis_change is not None:
        return Routed(
            DEFINITION, NO_CEO_ACTION,
            basis_change.action_owner or "Finance",
            "le plan et le réalisé ne se mesurent plus de la même façon ici",
        )

    on_hold = _note_of(unit, context.ON_HOLD)
    if on_hold is not None:
        return Routed(
            RISK, NO_CEO_ACTION, on_hold.action_owner,
            "commerce arrêté exprès ; le chiffre manque et la raison est connue",
        )

    # A result, then. What separates the moves is not how large it is — that decides the
    # rank — but whether anything here can say why.
    if unit.has_driver_breakdown:
        return Routed(
            PERFORMANCE, CHALLENGE, "",
            "les leviers derrière cet écart sont mesurés",
        )
    if unit.basis == "shipped":
        return Routed(
            PERFORMANCE, INVESTIGATE, "",
            "pas d'entonnoir derrière une expédition, et un mois d'expéditions dit le rythme "
            "de commande d'un partenaire autant que la demande",
        )
    return Routed(
        PERFORMANCE, REQUEST_DATA, "",
        "rien de connecté ici ne mesure la cause",
    )


#: Beyond this, a growth rate is a statement about the base and not about the business.
#: A line that ran at +15962% did not grow by fifteen thousand percent; it started from
#: nearly nothing — a new listing, a first shipment, a boundary already noted. Left in, it
#: opens the list, and the first item of a Finance review has to survive Finance.
BASE_EFFECT_GROWTH = 3.0


class PlanReview:
    """A plan the record does not support, in one of the two directions.

    A separate item from the month's miss, and separately measured: the month's gap is
    what was lost in July, this is what the rest of the year still embeds. Finance and the
    region answer it; the market's lead cannot fix a number they did not set.

    Two directions, and they are two different conversations. A plan *above* everything
    the business has delivered is a credibility risk: it will be missed every month and
    the misses are not news. A plan *below* what the business is already doing is a
    forecast to redo — apparent sandbagging or deliberate caution, either way a question
    for Finance. Mixed into one list they cancel each other out: the reader sees fourteen
    lines and cannot tell which half is which.
    """

    __slots__ = ("unit", "sentence", "amount", "above", "base_effect")

    def __init__(self, unit: BusinessUnit, sentence: str, amount: float,
                 above: bool, base_effect: bool = False) -> None:
        self.unit = unit
        self.sentence = sentence
        #: The year's embedded gap, not the month's.
        self.amount = amount
        #: True when the plan asks for more than the record has ever shown.
        self.above = above
        #: True when the record it is measured against is a base effect rather than a
        #: performance. Kept and annotated rather than dropped: the plan may still be
        #: wrong, but nobody can tell from this comparison.
        self.base_effect = base_effect


def plan_reviews(dataset: Dataset, above: Optional[bool] = None) -> List[PlanReview]:
    """Plans the record does not support, largest first.

    `above=True` returns the credibility list, `above=False` the re-forecast list, and
    `None` both. Base effects sort last within their list rather than being hidden: the
    figure is real, what it cannot do is carry a comparison.
    """
    found = []
    for unit in dataset.units:
        if unit.is_aggregate:
            continue
        sentence = unit.plan_vs_record or unit.chronic_plan
        if not sentence:
            continue
        item = PlanReview(
            unit, sentence, _embedded_amount(unit),
            above="au-dessus de chaque lecture" in sentence,
            base_effect=_is_base_effect(unit, sentence),
        )
        if above is None or item.above == above:
            found.append(item)
    return sorted(found, key=lambda item: (item.base_effect, -item.amount))


def _is_base_effect(unit: BusinessUnit, sentence: str) -> bool:
    """Is the record this plan is measured against a base effect rather than a result?

    Three ways it can be, and any one of them makes the percentage meaningless: the growth
    itself is beyond what a business does, last year was nearly nothing, or the market
    already carries a note saying its figures are filed on the wrong side of a boundary.
    """
    if unit.context_notes:
        return True
    for match in re.finditer(r"([+-]?\d[\d ]*)%", sentence):
        try:
            if abs(float(match.group(1).replace(" ", ""))) / 100.0 > BASE_EFFECT_GROWTH:
                return True
        except ValueError:
            continue
    return False


def _embedded_amount(unit: BusinessUnit) -> float:
    """The year's money named in the plan sentence, when it names one.

    Read from the sentence rather than recomputed, so the figure on the plan surface and
    the figure in the sentence can never disagree — two numbers for the same fact is how
    a screen loses its reader.
    """
    import re

    match = re.search(r"([\d.,]+)\s*(M|k)€", unit.plan_vs_record or unit.chronic_plan or "")
    if not match:
        return 0.0
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return 0.0
    return value * (1_000_000.0 if match.group(2) == "M" else 1_000.0)
