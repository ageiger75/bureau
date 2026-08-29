"""Sales with the bulk taken out, beside sales with it in.

Bulk is real turnover and it belongs in the Maison's accounts. It answers a different
question from the one this screen asks. A shopper buying a cream in a Chinese shop and a
buyer taking a pallet at half price are both revenue, but only the first says whether the
brand is working, and the second moves in lumps that have nothing to do with the month's
retail. Read together they can hide each other: a market whose shoppers are leaving looks
flat if a bulk order landed, and a market whose shoppers are returning looks weak if last
year's bulk order did not repeat.

So the two figures are always carried as a pair, never one instead of the other. The
finding is not the level of either — it is the moment they stop telling the same story.

The exclusion is the warehouse's own: `FLAG_BULK IN (2, 3, 4, 5)`, applied in
`queries.KPI_READINGS`. What each of those four values means is still unanswered by the
view's owner, so nothing here claims that bulk is daigou. It claims only that this money
is not ordinary retail, which the prices support: 4.37 to 9.10 € a unit against 11.11 €.
"""

from typing import Dict, List, Optional, Sequence

from . import kpi_registry

SALES_KEY = "net_sales"
EX_BULK_KEY = "net_sales_hors_bulk"

#: How much bulk a market must carry before its presence changes anything the reader does.
#: Below this the two bases move together and printing both is noise; the group figure —
#: 1.9% — sits under it, which is the point: at group level bulk is a rounding difference,
#: and in Hong Kong it is a sixth of the market.
#:
#: A fraction, not points, like every other rate this application carries. The two
#: conventions in one codebase is how a growth rate reaches a screen a hundred times too
#: large, and this file has no reason to be the exception.
MATERIAL_SHARE = 0.03

#: When the two growth rates differ by more than this, the base has changed the verdict
#: rather than decorated it. Two points is roughly the width of a month of ordinary
#: noise; the divergences that matter here are ten times that.
DIVERGENCE = 0.02

#: Months compared against the same months a year earlier. Three, because one month of a
#: lumpy flow is not a trend and twelve would bury a change that started this quarter.
WINDOW_MONTHS = 3


def previous_year(period: str) -> str:
    """'2026-06' -> '2025-06'. Empty for anything that is not a month."""
    text = str(period or "").strip()
    if len(text) != 7 or text[4] != "-":
        return ""
    try:
        year = int(text[:4])
    except ValueError:
        return ""
    return "%04d-%s" % (year - 1, text[5:])


class MarketBulk:
    """One market, on both bases, over one window and the same window a year earlier."""

    __slots__ = (
        "scope",
        "periods",
        "sales",
        "ex_bulk",
        "sales_before",
        "ex_bulk_before",
        "comparable",
    )

    def __init__(self, scope: str, periods: Sequence[str], sales: float, ex_bulk: float,
                 sales_before: Optional[float] = None,
                 ex_bulk_before: Optional[float] = None,
                 comparable: bool = False) -> None:
        self.scope = scope
        #: The months summed, oldest first. Printed, because a window the reader cannot
        #: see is a window they have to trust.
        self.periods = tuple(periods)
        self.sales = float(sales)
        self.ex_bulk = float(ex_bulk)
        self.sales_before = sales_before
        self.ex_bulk_before = ex_bulk_before
        #: True when the same months exist a year earlier on both bases. False means the
        #: levels are readable and the growth is not — and saying so beats printing a
        #: growth rate computed against a hole.
        self.comparable = bool(comparable)

    @property
    def bulk(self) -> float:
        return self.sales - self.ex_bulk

    @property
    def share(self) -> Optional[float]:
        """Bulk as a fraction of the market's sales."""
        if not self.sales:
            return None
        return self.bulk / self.sales

    @property
    def is_material(self) -> bool:
        share = self.share
        return share is not None and share >= MATERIAL_SHARE

    @property
    def growth(self) -> Optional[float]:
        return _growth(self.sales, self.sales_before)

    @property
    def growth_ex_bulk(self) -> Optional[float]:
        return _growth(self.ex_bulk, self.ex_bulk_before)

    @property
    def bulk_before(self) -> Optional[float]:
        if self.sales_before is None or self.ex_bulk_before is None:
            return None
        return self.sales_before - self.ex_bulk_before

    @property
    def bulk_movement(self) -> Optional[float]:
        """Euros of bulk more, or less, than the same months last year."""
        before = self.bulk_before
        if before is None:
            return None
        return self.bulk - before

    @property
    def divergence(self) -> Optional[float]:
        """Ex-bulk growth minus total growth. Negative: the bulk is flattering."""
        whole, clean = self.growth, self.growth_ex_bulk
        if whole is None or clean is None:
            return None
        return clean - whole

    @property
    def changes_the_verdict(self) -> bool:
        """The two bases disagree enough that reading only one would mislead."""
        gap = self.divergence
        if gap is None:
            return False
        whole, clean = self.growth, self.growth_ex_bulk
        if (whole or 0.0) * (clean or 0.0) < 0:
            # Opposite signs: one base says the market grew and the other says it shrank.
            # No threshold applies to that — it is the whole finding.
            return True
        return abs(gap) >= DIVERGENCE

    def sentence(self) -> str:
        """What this market is doing once the bulk is out, in one line."""
        if not self.comparable:
            return ("%s : %.1f M€ hors bulk sur %.1f M€ ; pas de comparable il y a un an, "
                    "donc le niveau se lit et la progression non."
                    % (self.scope, self.ex_bulk / 1e6, self.sales / 1e6))
        clean = 100.0 * (self.growth_ex_bulk or 0.0)
        whole = 100.0 * (self.growth or 0.0)
        base = ("%s : hors bulk %+.1f %%, tout compris %+.1f %%"
                % (self.scope, clean, whole))
        if not self.changes_the_verdict:
            return base + " — les deux bases disent la même chose."
        movement = self.bulk_movement or 0.0
        return (base + " — l'écart vient du bulk, %+.1f M€ sur ces %d mois."
                % (movement / 1e6, len(self.periods)))


def _growth(now: float, before: Optional[float]) -> Optional[float]:
    if before is None or not before:
        return None
    return (now - before) / abs(before)


def _sums(readings, periods) -> Optional[float]:
    """Total over exactly these periods, or None if one of them is missing.

    Missing is not zero. A month the warehouse never returned and a month that sold
    nothing are different facts, and summing them the same way turns the first into a
    collapse that never happened.
    """
    by_period = {reading.period: reading.value for reading in readings}
    total = 0.0
    for period in periods:
        if period not in by_period:
            return None
        total += by_period[period]
    return total


def market_bulk(rows: Sequence, scope: str,
                months: int = WINDOW_MONTHS) -> Optional[MarketBulk]:
    """Both bases for one market, or None when the pair is not there.

    None means the question cannot be answered for this market, which is a different
    answer from zero bulk and has to stay distinguishable from it.
    """
    readings = kpi_registry.readings_by_key(rows, scope=scope)
    sales = readings.get(SALES_KEY) or []
    ex_bulk = readings.get(EX_BULK_KEY) or []
    if not sales or not ex_bulk:
        return None
    shared = sorted(set(r.period for r in sales) & set(r.period for r in ex_bulk))
    if not shared:
        return None
    window = shared[-months:]
    now_sales = _sums(sales, window)
    now_clean = _sums(ex_bulk, window)
    if now_sales is None or now_clean is None:
        return None
    earlier = [previous_year(period) for period in window]
    before_sales = _sums(sales, earlier) if all(earlier) else None
    before_clean = _sums(ex_bulk, earlier) if all(earlier) else None
    comparable = before_sales is not None and before_clean is not None
    return MarketBulk(scope, window, now_sales, now_clean,
                      before_sales if comparable else None,
                      before_clean if comparable else None,
                      comparable)


def scopes(rows: Sequence) -> List[str]:
    """Every scope the readings carry, in reading order."""
    found = []
    seen = set()
    for row in rows:
        if isinstance(row, dict):
            lowered = {str(name).lower(): value for name, value in row.items()}
            scope = lowered.get("scope")
        elif len(row) >= 1:
            scope = row[0]
        else:
            continue
        text = str(scope or "").strip()
        if text and text not in seen:
            seen.add(text)
            found.append(text)
    return found


def material(rows: Sequence, months: int = WINDOW_MONTHS) -> List[MarketBulk]:
    """The markets where bulk is big enough to change what the reader concludes.

    Ordered by euros of bulk, not by share: a sixth of a small market and a twentieth of a
    large one are not the same conversation, and the money decides which comes first.
    """
    found = []
    for scope in scopes(rows):
        if scope.upper() == kpi_registry.GROUP_SCOPE.upper():
            continue
        reading = market_bulk(rows, scope, months=months)
        if reading is not None and reading.is_material:
            found.append(reading)
    found.sort(key=lambda item: item.bulk, reverse=True)
    return found
