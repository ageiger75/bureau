"""At what speed the screen may run, market by market.

The cockpit said for weeks that it runs at two speeds and says which one it is on. Stated
globally, that told a reader to distrust the warehouse everywhere because it cannot be
trusted somewhere — which is close to useless. Measured market by market it becomes an
instrument: most of the estate can be steered three weeks before the accounts close, and
the markets that cannot are named.
"""

from __future__ import annotations

import io

from app.perf import divergence


def _row(market="Somewhere", months=12, mean=0.0, sigma=0.0, low=None, high=None):
    low = mean - 0.001 if low is None else low
    high = mean + 0.001 if high is None else high
    return divergence.Market(market, months, mean, sigma, low, high, "measured")


def test_a_market_the_file_does_not_carry_is_not_aligned():
    """The failure this repository keeps meeting is an absence that looks like a pass. A
    market nobody measured has not been found to agree; it has not been looked at."""
    read = divergence.Divergence([_row(market="Measured")], [])

    assert read.grade_of("Measured") == divergence.ALIGNED
    assert read.grade_of("Never looked at") == divergence.NOT_GRADED


def test_a_file_with_one_fault_grades_nothing():
    """Degrading to \"nothing is proven\" is the only safe direction. A half-read file would
    hand a pass to the markets whose rows happened to parse."""
    read = divergence.Divergence([_row(market="Measured")], ["une ligne illisible"])

    assert not read.usable
    assert read.grade_of("Measured") == divergence.NOT_GRADED


def test_the_three_shapes_ask_for_three_different_things():
    """Agreement means the warehouse is not a degraded stand-in — it says the same thing
    earlier. A constant displacement is a rule someone can write. A distance that moves is
    decided at the close, and no rule reaches a decision."""
    aligned = _row(mean=0.001, sigma=0.003)
    offset = _row(mean=0.010, sigma=0.012)
    unstable = _row(mean=0.018, sigma=0.074, low=-0.053, high=0.272)

    assert aligned.grade == divergence.ALIGNED
    assert offset.grade == divergence.OFFSET
    assert unstable.grade == divergence.UNSTABLE


def test_too_few_months_is_its_own_answer():
    """A grade computed on a handful of months describes those months. A market missing a
    third of the year cannot earn a pass on the strength of what remains."""
    thin = _row(months=divergence.MINIMUM_MONTHS - 1, mean=0.001, sigma=0.002)

    assert thin.grade == divergence.NOT_GRADED


def test_a_distance_that_never_changes_sign_is_a_different_finding():
    """A standard deviation files it with the closing decisions and it is not one. A
    distance staying on its own side is business one system counts and the other does not,
    growing as that perimeter grows — same spread, different question, different person."""
    growing = _row(mean=-0.047, sigma=0.051, low=-0.187, high=-0.0001)
    swinging = _row(mean=0.018, sigma=0.084, low=-0.033, high=0.288)

    assert growing.sign_holds
    assert not swinging.sign_holds
    assert growing.grade == swinging.grade == divergence.UNSTABLE


def test_a_mean_outside_its_own_range_is_refused(tmp_path):
    """A row assembled from two different windows would grade as steady while describing
    nothing. Refused rather than repaired: nobody can tell which window was meant."""
    path = tmp_path / "divergence.csv"
    path.write_text(
        "market,months,mean,sigma,low,high,evidence\n"
        "Somewhere,12,0.400,0.010,-0.004,0.006,measured\n", encoding="utf-8")
    read = divergence.load(str(path))

    assert not read.usable
    assert any("hors de l'intervalle" in fault for fault in read.faults)


def test_one_market_measured_twice_is_refused(tmp_path):
    path = tmp_path / "divergence.csv"
    path.write_text(
        "market,months,mean,sigma,low,high,evidence\n"
        "Somewhere,12,0.001,0.002,-0.001,0.003,measured\n"
        "Somewhere,12,0.090,0.002,0.088,0.092,measured\n", encoding="utf-8")
    read = divergence.load(str(path))

    assert not read.usable
    assert any("figure déjà" in fault for fault in read.faults)


def test_the_shipped_example_parses_under_its_own_rules():
    """The file in docs/ is the form the measurements are written in. It carries columns
    and invented values, and it has to survive the loader or it teaches the wrong shape."""
    read = divergence.load("docs/divergence.example.csv")

    assert read.usable, read.faults
    assert set(row.grade for row in read.rows) == {
        divergence.ALIGNED, divergence.OFFSET, divergence.UNSTABLE, divergence.NOT_GRADED}


def test_every_grade_says_what_the_screen_may_do():
    """A grade nobody translated into an action is a statistic on a screen."""
    for grade in (divergence.ALIGNED, divergence.OFFSET, divergence.UNSTABLE,
                  divergence.NOT_GRADED):
        assert divergence.SPEED[grade].strip()


def test_an_average_near_zero_is_not_agreement():
    """A market swinging several points either way averages to nothing and agrees with
    nobody. The movement is the finding and the mean hides it — which is why a grade rests
    on both terms and never on the average alone. One real market sits exactly here."""
    cancelling = _row(mean=0.0066, sigma=0.043, low=-0.061, high=0.050)

    assert abs(cancelling.mean) < 0.01
    assert cancelling.grade == divergence.UNSTABLE
    assert not cancelling.sign_holds


def test_a_displacement_larger_than_the_movement_is_its_own_state():
    """Two causes can sit on one market. The close explains what moves month to month; it
    does not explain a floor that never lifts. When the average exceeds its own spread the
    displacement is the dominant term, it is a perimeter question, and it is answerable
    without waiting for any close."""
    both = _row(mean=0.051, sigma=0.043, low=-0.053, high=0.102)
    only_moving = _row(mean=0.0066, sigma=0.043, low=-0.061, high=0.050)

    assert both.grade == only_moving.grade == divergence.UNSTABLE
    assert both.displaced
    assert not only_moving.displaced
