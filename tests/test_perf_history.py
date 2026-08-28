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


def row(market="Japan", channel="E-COMMERCE", period="2026-04", actual=None, goal=None):
    """A history row. `goal` is the warehouse's target — data, never the plan."""
    return {
        "market": market,
        "channel": channel,
        "period": period,
        "sales_actual": actual,
        "sales_budget": goal,
    }


def months(count, start=(2025, 4), actual=None, goal=None, market="Japan",
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
                goal=goal(index) if callable(goal) else goal,
            )
        )
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return made


def plan(*lines, **kwargs):
    """The planning workbook: the only plan anything here is measured against.

    `plan(("2026-04", 1000.0), ("2026-05", 1000.0))` for Japan e-commerce, or
    `plan(*rows, amount=1000.0)` to cover every period of a fixture at one figure.
    """
    from app.perf.budget import Budget, BudgetLine

    market = kwargs.get("market", "Japan")
    channel = kwargs.get("channel", ECOMMERCE)
    amount = kwargs.get("amount")
    if amount is not None:
        lines = tuple(
            (r["period"] if isinstance(r, dict) else r, amount) for r in lines
        )
    return Budget([
        BudgetLine(market=market, region="Test", segment="EBU - E-Business",
                   channel=channel, period=period, budget=figure, last_year=None)
        for period, figure in lines
    ])


def merged(*budgets):
    """Several workbooks as one, for fixtures that span markets or channels."""
    from app.perf.budget import Budget

    return Budget([line for budget in budgets for line in budget.lines])


# ------------------------------------------------------------------ reading a series


def test_a_missing_side_is_skipped_rather_than_zeroed():
    """A month the workbook does not cover is not a month whose gap closed.

    Filling it with zero would put a €0 gap into the trend, and the acceleration factor
    reads the last two gaps — so one missing plan would report a gap as closing on a
    market that had simply not been budgeted.
    """
    built = history.from_rows([
        row(period="2026-04", actual=900.0),
        row(period="2026-05", actual=900.0),
        row(period="2026-06", actual=800.0),
    ])
    track = built.track_for("Japan", ECOMMERCE)
    partial = plan(("2026-04", 1000.0), ("2026-06", 1000.0))

    assert track.gap_history_for(partial) == (-100.0, -200.0)


def test_the_run_below_plan_stops_at_the_first_month_that_met_it():
    built = history.from_rows([
        row(period="2026-01", actual=900.0),
        row(period="2026-02", actual=1100.0),
        row(period="2026-03", actual=900.0),
        row(period="2026-04", actual=950.0),
    ])
    track = built.track_for("Japan", ECOMMERCE)
    every_month = plan(
        ("2026-01", 1000.0), ("2026-02", 1000.0), ("2026-03", 1000.0), ("2026-04", 1000.0)
    )

    assert track.months_below_for(every_month) == 2


def test_nothing_is_measured_without_the_workbook():
    """The rows carry the warehouse's own targets, and using them would buy two years of
    depth instead of one. It would also mean ranking a CEO's attention on a source the
    business has ruled unreliable — one with no target at all for two fifths of what it
    sells. Fewer months of a real plan beats more months of a number nobody defends."""
    built = history.from_rows(months(24, actual=900.0, goal=1000.0))
    track = built.track_for("Japan", ECOMMERCE)

    assert track.against(None) == []
    assert track.gap_history_for(None) == ()
    assert track.months_below_for(None) == 0
    assert track.chronic_for(None) is None
    # The targets are still there, as data. Reading them is a diagnostic, not a judgement.
    assert track.months[0].goal == 1000.0


def test_store_formats_fold_into_one_track():
    """The same fold the current month uses, or the history would be keyed differently
    from the units it describes and every store line would find no track at all."""
    built = history.from_rows([
        row(channel="MALL STORE", period="2026-04", actual=600.0, goal=1000.0),
        row(channel="STREET STORE", period="2026-04", actual=300.0, goal=1000.0),
    ])

    track = built.track_for("Japan", "retail")
    assert track is not None
    assert track.months[0].actual == 900.0
    # Summed on both sides: the goals fact is at the same grain as the sales fact, so each
    # format carries its own target rather than repeating the channel's.
    assert track.months[0].goal == 2000.0


# ------------------------------------------------------------------ a mis-set plan


def test_a_year_of_the_same_steady_shortfall_is_a_mis_set_plan():
    rows = months(14, actual=lambda i: 940.0 - (i % 3) * 5)
    built = history.from_rows(rows)
    chronic = built.track_for("Japan", ECOMMERCE).chronic_for(plan(*rows, amount=1000.0))

    assert chronic is not None
    assert chronic.months == 14
    assert "plan" in chronic.sentence
    assert "%.0f%%" % chronic.shortfall_pct in chronic.sentence


def test_a_widening_gap_is_not_a_mis_set_plan():
    """It is a deterioration, and calling it a planning error would excuse it."""
    rows = months(14, actual=lambda i: 990.0 - i * 20)
    built = history.from_rows(rows)

    assert built.track_for("Japan", ECOMMERCE).chronic_for(plan(*rows, amount=1000.0)) is None


def test_a_deep_shortfall_is_not_a_mis_set_plan_however_steady():
    rows = months(14, actual=500.0)
    built = history.from_rows(rows)

    assert built.track_for("Japan", ECOMMERCE).chronic_for(plan(*rows, amount=1000.0)) is None


def test_a_run_shorter_than_a_year_is_not_yet_chronic():
    """Below the seasonal cycle it cannot be told apart from a plan that is wrong for
    winter and right for summer, which is a different problem."""
    rows = months(11, actual=940.0)
    built = history.from_rows(rows)

    assert built.track_for("Japan", ECOMMERCE).chronic_for(plan(*rows, amount=1000.0)) is None


def test_a_verdict_needs_the_workbook_to_cover_the_whole_run():
    """The workbook covers the current fiscal year, so today it reaches a few closed
    months, not twelve. The verdict therefore cannot appear yet — which is a true
    statement about what is known, and better than a confident one drawn from targets
    nobody stands behind."""
    rows = months(14, actual=940.0)
    built = history.from_rows(rows)
    # Only the last four months are covered, as the real workbook covers FY27 to date.
    recent = plan(*rows[-4:], amount=1000.0)

    assert built.track_for("Japan", ECOMMERCE).chronic_for(recent) is None


# ------------------------------------------------------------------ the year to date


def test_the_year_to_date_sums_matched_pairs_only():
    """The trap this whole module is arranged around. Summed into the total and compared
    with a plan that never covered it, a year behind budget reads as a year ahead."""
    built = history.from_rows([
        row(period="2026-04", actual=1000.0),
        row(period="2026-05", actual=1000.0),
        row(market="Korea", period="2026-05", actual=5000.0),
    ])
    ytd = built.ytd("2026-05", budget=plan(("2026-04", 1200.0), ("2026-05", 1200.0)))

    assert ytd.actual == 2000.0
    assert ytd.budget == 2400.0
    assert ytd.gap == -400.0
    # Named and counted, not absorbed. Nobody can act on a total that hides it.
    assert ytd.unbudgeted_actual == 5000.0
    assert ytd.unbudgeted_lines == 1


def test_a_plan_with_no_sales_against_it_is_counted_apart():
    built = history.from_rows([
        row(period="2026-04", actual=1000.0),
        row(market="Korea", period="2026-04", actual=None),
    ])
    ytd = built.ytd("2026-04", budget=merged(
        plan(("2026-04", 1000.0)),
        plan(("2026-04", 800.0), market="Korea"),
    ))

    assert ytd.budget == 1000.0
    assert ytd.unsold_budget == 800.0
    assert ytd.unsold_lines == 1


def test_the_year_to_date_opens_in_april():
    """The fiscal year, not the calendar one. Reading a year to date from January would
    put a quarter of the previous year's trading into this year's figure."""
    rows = [
        row(period="2026-02", actual=9000.0),
        row(period="2026-03", actual=9000.0),
        row(period="2026-04", actual=1000.0),
        row(period="2026-05", actual=1000.0),
    ]
    ytd = history.from_rows(rows).ytd("2026-05", budget=plan(*rows, amount=1200.0))

    assert ytd.first_period == "2026-04"
    assert ytd.months == 2
    assert ytd.actual == 2000.0
    assert ytd.label == "FY27 to date"


def test_a_month_before_the_fiscal_year_opens_looks_back_to_the_previous_april():
    rows = [row(period="2025-04", actual=100.0), row(period="2026-02", actual=100.0)]
    ytd = history.from_rows(rows).ytd("2026-02", budget=plan(*rows, amount=100.0))

    assert ytd.first_period == "2025-04"
    assert ytd.label == "FY26 to date"


def test_there_is_no_year_to_date_without_the_workbook():
    """The alternative would be a total measured against the warehouse's targets, which
    cover 57% of what is sold and which the business does not stand behind. A figure that
    looks quotable and is not is worse than no figure."""
    built = history.from_rows([row(period="2026-04", actual=1000.0, goal=900.0)])

    assert built.ytd("2026-04") is None


def test_the_year_to_date_says_what_share_of_sales_a_plan_covers():
    """A total with no denominator cannot be judged. Half a business with no plan is a
    different screen from a rounding error, and the euros alone do not say which."""
    built = history.from_rows([
        row(period="2026-04", actual=1_000_000.0),
        row(market="Korea", period="2026-04", actual=3_000_000.0),
    ])
    ytd = built.ytd("2026-04", budget=plan(("2026-04", 1_000_000.0)))

    assert ytd.outside == 3_000_000.0
    assert ytd.covered == 0.25


def test_the_year_to_date_percentage_is_a_fraction():
    """The same units as every other percentage in the cockpit. The template's filter
    multiplies by a hundred, so a figure already in percent would reach the screen a
    hundred times too large — and a headline that reads -1000% discredits the page."""
    built = history.from_rows([row(period="2026-04", actual=900.0)])
    ytd = built.ytd("2026-04", budget=plan(("2026-04", 1000.0)))

    assert ytd.pct == -0.1
    assert analytics.format_pct(ytd.pct) == "-10.0%"


def test_a_plan_of_zero_is_not_a_plan_that_was_beaten():
    """Paired with real sales, a plan of zero reads as "beat the plan by everything we
    sold" — the most flattering sentence this cockpit could produce and the least true.
    Nobody committed to nothing; nobody committed."""
    built = history.from_rows([
        row(period="2026-04", actual=1_000_000.0),
        row(period="2026-05", actual=1_000_000.0),
    ])
    ytd = built.ytd("2026-05", budget=plan(("2026-04", 0.0), ("2026-05", 1_200_000.0)))

    assert ytd.actual == 1_000_000.0
    assert ytd.budget == 1_200_000.0
    assert ytd.gap == -200_000.0
    # Named apart from a plainly missing line: a plan nobody wrote and a plan someone set
    # to nothing need different conversations.
    assert ytd.zero_goal_actual == 1_000_000.0
    assert ytd.unbudgeted_actual == 0.0


def test_a_plan_of_zero_does_not_enter_the_trend():
    """It is not a month the business was above or below — there was nothing to be above
    or below of."""
    rows = [
        row(period="2026-04", actual=800.0),
        row(period="2026-05", actual=900.0),
        row(period="2026-06", actual=700.0),
    ]
    track = history.from_rows(rows).track_for("Japan", ECOMMERCE)
    with_a_hole = plan(("2026-04", 1000.0), ("2026-05", 0.0), ("2026-06", 1000.0))

    assert track.gap_history_for(with_a_hole) == (-200.0, -300.0)
    assert track.months_below_for(with_a_hole) == 2


def test_a_closed_channel_planned_at_zero_is_counted_nowhere():
    """Zero planned, zero sold. Not a plan met and not a plan missing — a channel that is
    not trading, and a row nobody should have to read."""
    built = history.from_rows([row(period="2026-04", actual=0.0)])
    ytd = built.ytd("2026-04", budget=plan(("2026-04", 0.0)))

    assert ytd.actual == 0.0
    assert ytd.zero_goal_lines == 0
    assert ytd.unbudgeted_lines == 0


# ------------------------------------------------------------ reaching the screen


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
        row(period="2026-05", actual=800.0),
        row(period="2026-06", actual=700.0),
    ])
    workbook = plan(("2026-05", 1000.0), ("2026-06", 1000.0))
    mapped = mapping.units_from_rows(
        [{"market": "Japan", "channel": "E-COMMERCE", "period": "2026-06",
          "sales_actual": 700.0}],
        budget=workbook,
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


# ------------------------------------------- the record answers what the plan cannot


def _record(monthly, start=(2024, 8), count=24, market="Japan", channel="E-COMMERCE"):
    """`count` months of actuals, `monthly(index)` euros each."""
    return months(count, start=start, actual=monthly, market=market, channel=channel)


def test_a_plan_asking_for_growth_the_record_has_never_shown():
    """The reading that works today. Whether a plan is mis-set is answered by the sales
    history — trusted and two years deep — against a plan that need only cover the months
    ahead. Waiting for a year of plan to accumulate would answer in March 2027 a question
    that is on the table now."""
    # Flat for two years, then a plan asking for a quarter more.
    rows = _record(lambda i: 1_000_000.0)
    built = history.from_rows(rows)
    ahead = plan(*[("%s" % _later(rows[-1]["period"], n), 1_250_000.0) for n in range(1, 5)])

    moved = built.track_for("Japan", ECOMMERCE).trajectory(ahead)

    assert moved.growth == 0.0
    assert moved.plan_growth == 0.25
    assert moved.stretch == 0.25
    assert moved.is_ahead_of_record
    assert "the plan is above every reading of the record" in moved.sentence


def test_a_plan_that_merely_continues_the_trend_says_nothing():
    """Most plans do, and a line printed for every market is a line read for none."""
    rows = _record(lambda i: 1_000_000.0)
    built = history.from_rows(rows)
    steady = plan(*[("%s" % _later(rows[-1]["period"], n), 1_020_000.0) for n in range(1, 5)])

    moved = built.track_for("Japan", ECOMMERCE).trajectory(steady)

    assert not moved.is_ahead_of_record and not moved.is_behind_record
    assert moved.sentence == ""


def test_a_plan_below_what_the_business_already_delivers():
    rows = _record(lambda i: 1_000_000.0 + i * 40_000)
    built = history.from_rows(rows)
    timid = plan(*[("%s" % _later(rows[-1]["period"], n), 1_000_000.0) for n in range(1, 5)])

    moved = built.track_for("Japan", ECOMMERCE).trajectory(timid)

    assert moved.is_behind_record
    assert "the plan is below every reading of the record" in moved.sentence


def test_the_record_says_whether_the_business_is_speeding_up():
    """Three months against the same three a year earlier, compared with twelve against
    twelve. Both year on year, so the season cancels — a December read against a November
    says nothing."""
    # Flat for a year, then rising hard in the last quarter.
    def shape(i):
        return 1000.0 if i < 21 else 1600.0

    built = history.from_rows(_record(shape))
    moved = built.track_for("Japan", ECOMMERCE).trajectory(None)

    assert moved.direction == "accelerating"
    assert moved.momentum > 0


def test_a_shrinking_business_asked_to_grow_is_the_sharpest_case():
    """Slowing down and planned to accelerate. The record contradicts the plan twice, and
    the sentence has to say so — otherwise the market is asked in October why it missed a
    number nobody should have signed."""
    # A decline that is itself worsening. A single step down followed by a plateau is
    # not slowing — it is steady at a lower level, and the code is right to say so.
    def shape(i):
        if i < 12:
            return 1_000_000.0
        return 950_000.0 if i < 21 else 800_000.0

    rows = _record(shape)
    built = history.from_rows(rows)
    ahead = plan(
        *[("%s" % _later(rows[-1]["period"], n), 1_200_000.0) for n in range(1, 5)]
    )

    moved = built.track_for("Japan", ECOMMERCE).trajectory(ahead)

    assert moved.growth < 0
    assert moved.is_ahead_of_record
    assert "argues against it" in moved.sentence


def test_growth_is_absent_rather_than_guessed_on_a_short_history():
    """A market that started nine months ago has no year to compare with. Dividing by the
    months that exist would call a launch a growth rate."""
    built = history.from_rows(_record(lambda i: 1000.0, count=9))
    moved = built.track_for("Japan", ECOMMERCE).trajectory(None)

    assert moved.growth is None
    assert moved.direction == ""
    assert moved.sentence == ""


def _later(period, months_ahead):
    from app.perf.history import _shift

    return _shift(period, months_ahead)


def test_the_record_reaches_the_units_and_the_question():
    """The half that works today. `chronic_plan` needs a year of plan the workbook does
    not yet cover; this needs a year of sales, which exists and is trusted."""
    rows = _record(lambda i: 1_000_000.0)
    workbook = plan(*[(_later(rows[-1]["period"], n), 1_300_000.0) for n in range(1, 5)])
    mapped = mapping.units_from_rows(
        [{"market": "Japan", "channel": "E-COMMERCE", "period": "2026-07",
          "sales_actual": 700.0}],
        budget=workbook,
        history=history.from_rows(rows),
    )

    unit = mapped.units[0]
    assert "the plan is above every reading of the record" in unit.plan_vs_record
    assert unit.chronic_plan == ""

    fire = analytics.Fire(unit)
    assert "Was this plan ever reachable" in fire.question
    assert fire.plan_vs_record == unit.plan_vs_record


def test_a_business_that_has_already_turned_is_not_flagged():
    """The correctness fix that mattered. Measured against the trailing year alone, China
    e-commerce came back as planned for "growth it has not shown" while its last three
    months ran at +63%. It had just shown it. Four findings in five were positive that
    way — not a signal, a habit."""
    # Falling for a year, then recovering hard: trailing growth is deeply negative while
    # the recent quarter is far above the plan's ask.
    def shape(i):
        return 1000.0 if i < 12 else (500.0 if i < 21 else 1600.0)

    rows = _record(shape)
    built = history.from_rows(rows)
    # 550 against the 500 of the same months a year earlier: +10%, well above the
    # trailing year and well below what the last quarter is already running at.
    ahead_of_the_year = plan(
        *[(_later(rows[-1]["period"], n), 550.0) for n in range(1, 5)]
    )

    moved = built.track_for("Japan", ECOMMERCE).trajectory(ahead_of_the_year)

    assert moved.growth < 0                 # the year is still negative
    assert moved.recent > moved.plan_growth  # the quarter already beats the plan
    assert not moved.is_ahead_of_record
    assert moved.sentence == ""


def test_a_plan_in_line_with_the_recent_quarter_is_not_called_timid():
    """A plan below the trailing year but level with the recent quarter has taken the
    turn into account, which is what a plan is supposed to do."""
    def shape(i):
        return 1000.0 if i < 12 else (1000.0 if i < 21 else 700.0)

    rows = _record(shape)
    built = history.from_rows(rows)
    matching = plan(*[(_later(rows[-1]["period"], n), 700.0) for n in range(1, 5)])

    moved = built.track_for("Japan", ECOMMERCE).trajectory(matching)

    assert moved.stretch < 0
    assert not moved.is_behind_record
    assert moved.sentence == ""


# ------------------------------------------------------------------- sell-in


def _sell_in_plan(entity, market, segment, monthly, months=12):
    from app.perf.budget import Budget, BudgetLine

    return Budget([
        BudgetLine(market=market, region="R", segment=segment, channel="",
                   period="2026-%02d" % n, budget=monthly, last_year=None, entity=entity)
        for n in range(1, months + 1)
    ])


def test_the_sell_in_plan_is_confronted_with_what_partners_actually_bought():
    """Built from the two queries that already exist rather than a third nobody has run.
    Both sides are stated at the plan's own rates, which is the property that makes the
    sell-in reconciliation exact and is worth carrying over."""
    closed = [{"entity": "M_024", "segment": "DIS - Distributors",
               "period": "2025-%02d" % n, "value": 1_000_000.0} for n in range(1, 13)]
    current = [{"entity": "M_024", "segment": "DIS - Distributors",
                "period": "2026-%02d" % n, "sales_actual": 950_000.0,
                "sales_last_year": 1_000_000.0} for n in range(4, 8)]

    moved, = history.sell_in_trajectories(
        closed, current,
        _sell_in_plan("M_024", "Japan", "DIS - Distributors", 1_400_000.0)
    )

    assert moved.market == "Japan"
    # Floating point: the figures are a ratio of sums, not a decimal typed in.
    assert round(moved.plan_growth, 10) == 0.4
    assert round(moved.recent, 10) == -0.05
    assert moved.is_ahead_of_record
    assert "the fiscal year to date ran at" in moved.sentence


def test_the_sell_in_record_is_named_for_what_it_is():
    """The consolidation publishes a comparison, not a series: it says what a month did
    against the same month a year earlier and never what the twelve before it did. So the
    record is the fiscal year to date, and calling it anything else would be a small lie
    in the one sentence a reader takes away."""
    closed = [{"entity": "M_024", "segment": "DIS - Distributors",
               "period": "2025-%02d" % n, "value": 1000.0} for n in range(1, 13)]
    current = [{"entity": "M_024", "segment": "DIS - Distributors",
                "period": "2026-04", "sales_actual": 900.0, "sales_last_year": 1000.0}]

    moved, = history.sell_in_trajectories(
        closed, current, _sell_in_plan("M_024", "Japan", "DIS - Distributors", 1400.0)
    )

    assert moved.growth is None
    assert moved.records == [moved.recent]
    assert "twelve months" not in moved.sentence


def test_the_sell_in_join_uses_the_entity_code_with_its_suffix():
    """The workbook types the same entity two ways — bare for most, suffixed for a few —
    while the consolidation always writes the suffix. Joining on a country name instead
    would drop the eleven markets billed by a hub."""
    closed = [{"entity": "M_017_UNLOC", "segment": "DIS - Distributors",
               "period": "2025-%02d" % n, "value": 1000.0} for n in range(1, 13)]
    current = [{"entity": "M_017_UNLOC", "segment": "DIS - Distributors",
                "period": "2026-04", "sales_actual": 900.0, "sales_last_year": 1000.0}]

    moved, = history.sell_in_trajectories(
        closed, current, _sell_in_plan("M_017", "Korea", "DIS - Distributors", 1400.0)
    )

    assert moved.market == "Korea"


def test_a_sell_in_pair_the_plan_does_not_name_is_left_out():
    """Not guessed into a market by resemblance. A figure attributed to the wrong country
    is worse than a figure nobody sees."""
    closed = [{"entity": "M_999", "segment": "DIS - Distributors",
               "period": "2025-01", "value": 1000.0}]

    assert history.sell_in_trajectories(
        closed, [], _sell_in_plan("M_024", "Japan", "DIS - Distributors", 1400.0)
    ) == []


# --------------------------------------------------- money, never percentage points


def test_a_base_of_nothing_produces_no_growth_rate():
    """Sell-in carries returns and credit notes, so a base can be nothing or less than
    nothing. The first real run put Austria department stores at the top of the list at
    -1379% — a rounding error on a base of nothing, printed above every real finding."""
    closed = [{"entity": "M_024", "segment": "DIS - Distributors",
               "period": "2025-01", "value": -500.0}]
    current = [{"entity": "M_024", "segment": "DIS - Distributors",
                "period": "2026-04", "sales_actual": 900.0, "sales_last_year": -500.0}]

    moved, = history.sell_in_trajectories(
        closed, current, _sell_in_plan("M_024", "Japan", "DIS - Distributors", 1_400_000.0)
    )

    assert moved.plan_growth is None
    assert moved.recent is None
    assert moved.sentence == ""


def test_a_small_line_moving_hugely_is_not_a_finding():
    """400% on a line worth nothing matters to nobody; 12% on a large one is a
    conversation. Ranking by points puts the noise at the top, which is exactly what the
    first sell-in run did."""
    rows = _record(lambda i: 20_000.0)
    built = history.from_rows(rows)
    ahead = plan(*[(_later(rows[-1]["period"], n), 100_000.0) for n in range(1, 5)])

    moved = built.track_for("Japan", ECOMMERCE).trajectory(ahead)

    assert moved.is_ahead_of_record        # the shape is real
    assert not moved.is_material           # the money is not
    assert moved.sentence == ""


def test_the_finding_is_stated_in_euros():
    """A CEO acts on money. The percentage says how far the plan is from the record; the
    euros say whether it is worth an hour."""
    rows = _record(lambda i: 1_000_000.0)
    built = history.from_rows(rows)
    ahead = plan(*[(_later(rows[-1]["period"], n), 1_500_000.0) for n in range(1, 5)])

    moved = built.track_for("Japan", ECOMMERCE).trajectory(ahead)

    # Four planned months at 1.5m against four record months at 1.0m.
    assert moved.money_at_stake == 2_000_000.0
    assert "€2.0m of revenue the record does not account for" in moved.sentence
