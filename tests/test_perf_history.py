"""Twenty-four months behind the month on the screen.

Two things are being defended here. The first is that a series must not be invented where
one side is missing: a month with a plan and no sales, or sales and no plan, is a finding,
and filling either with a zero would turn it into an ordinary row. The second is the year
to date, which on the real warehouse is where a naive sum goes badly wrong — 86 M€ of
actual arrives with no plan against it, and adding that into a total compared against a
plan that never covered it flatters the year by more than half.

Written in English, like the rest of the cockpit — see AGENTS.md.
"""

from __future__ import annotations

from app.perf import analytics, history, mapping
from app.perf.budget import Budget, BudgetLine
from app.perf.model import ECOMMERCE, BusinessUnit, Drivers, Owner

OWNER = Owner("Test Owner", "Managing Director", "Testland")


def row(market="Japan", channel="E-COMMERCE", period="2026-04", actual=None, budget=None):
    return {
        "market": market,
        "channel": channel,
        "period": period,
        "sales_actual": actual,
        "sales_budget": budget,
    }


def months(count, start=(2025, 4), actual=None, budget=None, market="Japan",
           channel="E-COMMERCE"):
    """`count` consecutive months, oldest first, from `start`."""
    made = []
    year, month = start
    for index in range(count):
        made.append(
            row(
                market=market,
                channel=channel,
                period="%04d-%02d" % (year, month),
                actual=actual(index) if callable(actual) else actual,
                budget=budget(index) if callable(budget) else budget,
            )
        )
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return made


# ------------------------------------------------------------------ reading a series


def test_a_missing_side_is_skipped_rather_than_zeroed():
    """A month with no plan is not a month whose gap closed.

    Filling it with zero would put a €0 gap into the trend, and the acceleration factor
    reads the last two gaps — so one missing plan would report a gap as closing on a
    market that had simply not been budgeted.
    """
    built = history.from_rows([
        row(period="2026-04", actual=900.0, budget=1000.0),
        row(period="2026-05", actual=900.0, budget=None),
        row(period="2026-06", actual=800.0, budget=1000.0),
    ])
    track = built.track_for("Japan", ECOMMERCE)

    assert track.gap_history == (-100.0, -200.0)


def test_the_run_below_plan_stops_at_the_first_month_that_met_it():
    built = history.from_rows([
        row(period="2026-01", actual=900.0, budget=1000.0),
        row(period="2026-02", actual=1100.0, budget=1000.0),
        row(period="2026-03", actual=900.0, budget=1000.0),
        row(period="2026-04", actual=950.0, budget=1000.0),
    ])
    track = built.track_for("Japan", ECOMMERCE)

    assert track.months_below_budget == 2


def test_store_formats_fold_into_one_track():
    """The same fold the current month uses, or the history would be keyed differently
    from the units it describes and every store line would find no track at all."""
    built = history.from_rows([
        row(channel="MALL STORE", period="2026-04", actual=600.0, budget=1000.0),
        row(channel="STREET STORE", period="2026-04", actual=300.0, budget=1000.0),
    ])

    track = built.track_for("Japan", "retail")
    assert track is not None
    assert track.months[0].actual == 900.0
    # Summed on both sides, and correctly: the goals fact is at the same grain as the
    # sales fact, so each format carries its own target rather than repeating the
    # channel's. Folding one side and not the other is what would break it.
    assert track.months[0].budget == 2000.0


# ------------------------------------------------------------------ a mis-set plan


def test_a_year_of_the_same_steady_shortfall_is_a_mis_set_plan():
    built = history.from_rows(
        months(14, actual=lambda i: 940.0 - (i % 3) * 5, budget=1000.0)
    )
    chronic = built.track_for("Japan", ECOMMERCE).chronic

    assert chronic is not None
    assert chronic.months == 14
    assert "plan" in chronic.sentence
    assert "%.0f%%" % chronic.shortfall_pct in chronic.sentence


def test_a_widening_gap_is_not_a_mis_set_plan():
    """It is a deterioration, and calling it a planning error would excuse it."""
    built = history.from_rows(
        months(14, actual=lambda i: 990.0 - i * 20, budget=1000.0)
    )

    assert built.track_for("Japan", ECOMMERCE).chronic is None


def test_a_deep_shortfall_is_not_a_mis_set_plan_however_steady():
    built = history.from_rows(months(14, actual=500.0, budget=1000.0))

    assert built.track_for("Japan", ECOMMERCE).chronic is None


def test_a_run_shorter_than_a_year_is_not_yet_chronic():
    """Below the seasonal cycle it cannot be told apart from a plan that is wrong for
    winter and right for summer, which is a different problem."""
    built = history.from_rows(months(11, actual=940.0, budget=1000.0))

    assert built.track_for("Japan", ECOMMERCE).chronic is None


def test_the_verdict_is_withheld_when_the_two_plans_disagree():
    """The history compares against the warehouse's goals; the screen compares against
    the planning workbook. Where they diverge, a "steady shortfall" may be nothing but the
    distance between two spreadsheets — and "your plan is 6% high" said on that basis
    sends someone to renegotiate a plan that is not the one being missed."""
    built = history.from_rows(
        months(14, actual=940.0, budget=1000.0) + [
            row(period="2026-06", actual=940.0, budget=1000.0)
        ]
    )
    agreeing = mapping._history_for(built, "Japan", ECOMMERCE, "2026-06", 1000.0)
    diverging = mapping._history_for(built, "Japan", ECOMMERCE, "2026-06", 1400.0)

    assert agreeing[2]
    assert not diverging[2]
    # Only the verdict is withheld. The run and the gaps are arithmetic on the goals fact
    # alone and stay true whatever the workbook says.
    assert diverging[0] == agreeing[0] > 0


# ------------------------------------------------------------------ the year to date


def test_the_year_to_date_sums_matched_pairs_only():
    """The trap this whole module is arranged around. On the real warehouse, 86 M€ of
    actual arrives with no plan beside it; summed into the total and compared with a plan
    that never covered it, a year behind budget reads as a year ahead of it."""
    built = history.from_rows([
        row(period="2026-04", actual=1000.0, budget=1200.0),
        row(period="2026-05", actual=1000.0, budget=1200.0),
        row(market="Korea", period="2026-05", actual=5000.0, budget=None),
    ])
    ytd = built.ytd("2026-05")

    assert ytd.actual == 2000.0
    assert ytd.budget == 2400.0
    assert ytd.gap == -400.0
    # Named and counted, not absorbed. Nobody can act on a total that hides it.
    assert ytd.unbudgeted_actual == 5000.0
    assert ytd.unbudgeted_lines == 1


def test_a_plan_with_no_sales_against_it_is_counted_apart():
    built = history.from_rows([
        row(period="2026-04", actual=1000.0, budget=1000.0),
        row(market="Korea", period="2026-04", actual=None, budget=800.0),
    ])
    ytd = built.ytd("2026-04")

    assert ytd.budget == 1000.0
    assert ytd.unsold_budget == 800.0
    assert ytd.unsold_lines == 1


def test_the_year_to_date_opens_in_april():
    """The fiscal year, not the calendar one. Reading a year to date from January would
    put a quarter of the previous year's trading into this year's figure."""
    built = history.from_rows([
        row(period="2026-02", actual=9000.0, budget=9000.0),
        row(period="2026-03", actual=9000.0, budget=9000.0),
        row(period="2026-04", actual=1000.0, budget=1200.0),
        row(period="2026-05", actual=1000.0, budget=1200.0),
    ])
    ytd = built.ytd("2026-05")

    assert ytd.first_period == "2026-04"
    assert ytd.months == 2
    assert ytd.actual == 2000.0
    assert ytd.label == "FY27 to date"


def test_a_month_before_the_fiscal_year_opens_looks_back_to_the_previous_april():
    built = history.from_rows([
        row(period="2025-04", actual=100.0, budget=100.0),
        row(period="2026-02", actual=100.0, budget=100.0),
    ])
    ytd = built.ytd("2026-02")

    assert ytd.first_period == "2025-04"
    assert ytd.label == "FY26 to date"


# ------------------------------------------------------------------ reaching the screen


def _unit(**overrides):
    base = {
        "key": "japan-ecommerce",
        "label": "Japan E-commerce",
        "market": "Japan",
        "region": "Japan",
        "channel": ECOMMERCE,
        "owner": OWNER,
        "actual": Drivers.sales_only(900_000.0),
        "budget": Drivers.sales_only(1_000_000.0),
        "last_year": Drivers.sales_only(950_000.0),
        "forecast_sales": 0.0,
    }
    base.update(overrides)
    return BusinessUnit(**base)


def test_a_mis_set_plan_does_not_earn_the_persistence_multiplier():
    """Persistence says "this keeps coming back and nobody has fixed it". On a plan missed
    by the same margin every month it says the opposite of what the numbers mean, and says
    it at full strength — the factor peaks exactly where the business is most stable."""
    chronic = _unit(months_below_budget=18, chronic_plan="The plan is set high.")
    deteriorating = _unit(months_below_budget=18)

    assert analytics.priority_of(chronic).score < analytics.priority_of(deteriorating).score
    assert dict(analytics.priority_of(chronic).factors)["persistence"] == 1.0
    assert any("plan to reset" in reason for reason in analytics.priority_of(chronic).reasons)


def test_a_mis_set_plan_is_asked_about_the_plan():
    fire = analytics.Fire(_unit(chronic_plan="The plan is set high."))

    assert "plan" in fire.question.lower()
    assert "30 days" not in fire.question
    assert fire.chronic_plan == "The plan is set high."


def test_the_history_reaches_the_units():
    built = history.from_rows([
        row(period="2026-05", actual=800.0, budget=1000.0),
        row(period="2026-06", actual=700.0, budget=1000.0),
    ])
    budget = Budget([
        BudgetLine(
            market="Japan", region="Japan", segment="EBU - E-Business",
            channel=ECOMMERCE, period="2026-06", budget=1000.0, last_year=900.0,
        )
    ])
    mapped = mapping.units_from_rows(
        [{"market": "Japan", "channel": "E-COMMERCE", "period": "2026-06",
          "sales_actual": 700.0}],
        budget=budget,
        history=built,
    )

    unit = mapped.units[0]
    assert unit.months_below_budget == 2
    assert unit.gap_history == (-200.0, -300.0)


def test_no_history_costs_the_units_nothing_but_the_history():
    mapped = mapping.units_from_rows(
        [{"market": "Japan", "channel": "E-COMMERCE", "period": "2026-06",
          "sales_actual": 700.0}],
        history=None,
    )

    assert mapped.units[0].months_below_budget == 0
    assert mapped.units[0].gap_history == ()
    assert mapped.units[0].chronic_plan == ""


def test_the_year_to_date_percentage_is_a_fraction():
    """The same units as every other percentage in the cockpit. The template's filter
    multiplies by a hundred, so a figure already in percent would reach the screen a
    hundred times too large — and a headline that reads -1000% discredits the page, not
    the number."""
    built = history.from_rows([row(period="2026-04", actual=900.0, budget=1000.0)])
    ytd = built.ytd("2026-04")

    assert ytd.pct == -0.1
    assert analytics.format_pct(ytd.pct) == "-10.0%"
