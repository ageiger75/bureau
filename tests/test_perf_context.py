"""What happened that the numbers cannot say.

The cockpit knew two ways a gap can appear: the business moved, or the measurement broke.
Brazil showed a third. A tax change moved net sales without moving gross sales, months
after the plan was committed — so the gap is real in the accounts and says nothing about
how the market is trading.

The danger is specific. Left alone, the screen ranks it as a commercial failure and puts a
country manager in front of a question about a government decision. That is the most
expensive mistake this product can make: confidently wrong, about a named person.
"""

from __future__ import annotations

import pytest

from app.perf import analytics, context
from app.perf.model import ECOMMERCE, RETAIL, BusinessUnit, Dataset, Drivers, Owner

OWNER = Owner("A. Manager", "Managing Director", "Brazil")


def note(kind=context.BASIS_CHANGE, market="Brazil", channel="", since="2026-06"):
    return context.Note(
        market=market,
        channel=channel,
        since=since,
        kind=kind,
        text="Sales tax changed in June; the plan predates it.",
        source="CEO",
    )


def unit(notes=(), **overrides):
    base = {
        "key": "brazil-retail",
        "label": "Brazil Retail",
        "market": "Brazil",
        "region": "BRAZIL",
        "channel": RETAIL,
        "owner": OWNER,
        "actual": Drivers.sales_only(2_600_000.0),
        "budget": Drivers.sales_only(3_100_000.0),
        "last_year": Drivers.sales_only(3_050_000.0),
        "forecast_sales": 0.0,
        "context_notes": notes,
    }
    base.update(overrides)
    return BusinessUnit(**base)


def dataset_of(*units):
    return Dataset(period_label="July 2026 sales", as_of="2026-08-27", units=units)


# ------------------------------------------------------------------- scope of a note


def test_a_note_starts_when_the_thing_it_describes_started():
    """A tax change in June does not explain a gap in April."""
    changed = note(since="2026-06")

    assert changed.applies_to("Brazil", RETAIL, "2026-07") is True
    assert changed.applies_to("Brazil", RETAIL, "2026-04") is False


def test_a_note_without_a_channel_covers_the_whole_market():
    """Usually right: a tax change does not stop at the shop door."""
    changed = note(channel="")

    assert changed.applies_to("Brazil", RETAIL, "2026-07") is True
    assert changed.applies_to("Brazil", ECOMMERCE, "2026-07") is True


def test_a_note_scoped_to_a_channel_stays_there():
    changed = note(channel=ECOMMERCE)

    assert changed.applies_to("Brazil", ECOMMERCE, "2026-07") is True
    assert changed.applies_to("Brazil", RETAIL, "2026-07") is False


def test_a_note_never_leaks_to_another_market():
    assert note().applies_to("Japan", RETAIL, "2026-07") is False


# ------------------------------------------------------------ what it changes on screen


def test_the_diagnosis_leads_with_the_context():
    """Everything else on the card explains a gap. This says whether the gap means what it
    appears to mean, which has to be read before, not after."""
    fire = analytics.fires(dataset_of(unit(notes=[note()])))[0]

    assert fire.diagnosis.startswith("The plan and the actual are not measured")
    assert "tax changed" in fire.diagnosis


def test_the_question_stops_being_about_trading():
    fire = analytics.fires(dataset_of(unit(notes=[note()])))[0]

    assert "rebased" in fire.question
    assert "30 days" not in fire.question


def test_nobody_is_challenged_for_a_tax_change():
    """The gap is real in the accounts and is not this person's to answer for."""
    fires = analytics.fires(dataset_of(unit(notes=[note()])))

    assert analytics.people_to_push(fires) == []


def test_the_gap_itself_is_untouched():
    """These are not corrections. A cockpit that quietly adjusts numbers towards what
    someone expected is worth less than one that shows an uncomfortable number and says
    why it is uncomfortable."""
    fire = analytics.fires(dataset_of(unit(notes=[note()])))[0]

    assert fire.gap == pytest.approx(-500_000.0)


def test_a_market_stays_in_the_ranking():
    """The money is real and belongs in the group's variance. Hiding it would be the
    opposite failure."""
    assert len(analytics.fires(dataset_of(unit(notes=[note()])))) == 1


def test_a_one_off_asks_a_different_question_from_a_basis_change():
    """Different things, different next steps: one asks whether the plan is still the
    right yardstick, the other asks what the run rate is underneath."""
    one_off = analytics.fires(dataset_of(unit(notes=[note(kind=context.ONE_OFF)])))[0]
    basis = analytics.fires(dataset_of(unit(notes=[note()])))[0]

    assert one_off.question != basis.question
    assert "set aside" in one_off.question


def test_an_ordinary_market_is_unaffected():
    fires = analytics.fires(dataset_of(unit(notes=[])))

    assert analytics.people_to_push(fires) != []


# ------------------------------------------------------------------- reading the file


def _write(tmp_path, rows):
    import csv

    path = tmp_path / "context.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["market", "channel", "since", "kind", "note", "source"])
        writer.writerows(rows)
    return path


def test_the_file_is_read(tmp_path):
    path = _write(tmp_path, [
        ["Brazil", "", "2026-06", "basis_change", "Sales tax changed.", "CEO"],
    ])

    loaded = context.load(path)

    assert len(loaded) == 1
    assert loaded.notes[0].source == "CEO"


def test_an_unknown_kind_is_dropped_rather_than_guessed(tmp_path):
    """Inventing a meaning for a word someone typed would attach a confident sentence to
    a note nobody wrote."""
    path = _write(tmp_path, [
        ["Brazil", "", "2026-06", "weather", "It rained a lot.", "CEO"],
    ])

    assert len(context.load(path)) == 0


def test_a_note_with_no_text_is_dropped(tmp_path):
    path = _write(tmp_path, [["Brazil", "", "2026-06", "basis_change", "", "CEO"]])

    assert len(context.load(path)) == 0


def test_market_and_channel_are_normalised_before_matching(tmp_path):
    """The file is typed by a person; the warehouse answers in its own vocabulary."""
    path = _write(tmp_path, [
        ["BRAZIL", "MALL STORE", "2026-06", "basis_change", "Sales tax changed.", ""],
    ])

    loaded = context.load(path)

    assert loaded.notes[0].market == "Brazil"
    assert loaded.notes[0].channel == RETAIL


def test_no_file_means_no_notes_rather_than_a_crash(monkeypatch, tmp_path):
    from app.config import settings

    context.reset()
    monkeypatch.setattr(
        type(settings), "context_path", property(lambda self: tmp_path / "absent.csv")
    )

    assert context.notes_for("Brazil", RETAIL, "2026-07") == []
    context.reset()


def test_a_malformed_file_does_not_take_the_cockpit_down(monkeypatch, tmp_path):
    broken = tmp_path / "context.csv"
    broken.write_bytes(b"\xff\xfe not a csv at all")

    from app.config import settings

    context.reset()
    monkeypatch.setattr(type(settings), "context_path", property(lambda self: broken))

    assert context.notes_for("Brazil", RETAIL, "2026-07") == []
    context.reset()


# ------------------------------------------------------------- writing a note by hand
#
# These get written the moment someone understands something, often between two meetings.
# A command reaches that moment; a spreadsheet does not.


@pytest.fixture
def notes_at(tmp_path, monkeypatch):
    from app.config import settings

    path = tmp_path / "context.csv"
    monkeypatch.setattr(type(settings), "context_path", property(lambda self: path))
    context.reset()
    yield path
    context.reset()


def test_a_note_is_written_from_the_command_line(notes_at, capsys):
    from app.cli import cmd_note

    assert cmd_note(["Brazil", "Sales tax changed in June."]) == 0

    loaded = context.load(notes_at)

    assert len(loaded) == 1
    assert loaded.notes[0].market == "Brazil"
    assert loaded.notes[0].kind == context.BASIS_CHANGE


def test_the_command_says_what_the_note_will_do(notes_at, capsys):
    """Writing a note that silently changes a screen is worse than editing a file: at
    least the file shows what it holds."""
    from app.cli import cmd_note

    cmd_note(["Brazil", "Sales tax changed in June."])
    out = capsys.readouterr().out

    assert "not measured on the same basis" in out
    assert "rebased" in out


def test_an_option_value_is_never_mistaken_for_the_note(notes_at):
    """`--since 2026-06` looks exactly like a positional argument to a naive split, and
    would have been filed as the text of the note."""
    from app.cli import cmd_note

    cmd_note(["Japan", "A flagship closed.", "--kind", "one_off", "--since", "2026-07"])

    written = context.load(notes_at).notes[0]

    assert written.text == "A flagship closed."
    assert written.since == "2026-07"
    assert written.kind == context.ONE_OFF


def test_an_unknown_kind_is_refused_with_the_choices(notes_at, capsys):
    from app.cli import cmd_note

    assert cmd_note(["Brazil", "Something happened.", "--kind", "weather"]) == 2
    assert "basis_change" in capsys.readouterr().err


def test_notes_accumulate_rather_than_replace(notes_at):
    from app.cli import cmd_note

    cmd_note(["Brazil", "Sales tax changed."])
    cmd_note(["Japan", "A flagship closed.", "--kind", "one_off"])

    assert len(context.load(notes_at)) == 2


def test_a_note_can_be_taken_back(notes_at):
    from app.cli import cmd_note

    cmd_note(["Brazil", "Sales tax changed."])
    cmd_note(["Japan", "A flagship closed.", "--kind", "one_off"])

    assert cmd_note(["--forget", "1"]) == 0

    remaining = context.load(notes_at)

    assert len(remaining) == 1
    assert remaining.notes[0].market == "Japan"


def test_several_notes_can_be_taken_back_at_once(notes_at):
    """Notes are posted in pairs — a boundary has two sides — so they come back in pairs.
    One at a time, every removal renumbers the rest, and a second command aimed at the
    old numbering deletes somebody else's note. The numbers are therefore applied from
    the highest down, and the caller never has to recount between two commands.
    """
    from app.cli import cmd_note

    cmd_note(["United States", "Filed under web partners.", "--kind", "reclassified"])
    cmd_note(["United States", "The other side of it.", "--kind", "reclassified"])
    cmd_note(["Brazil", "Sales tax changed."])

    assert cmd_note(["--forget", "1,2"]) == 0

    remaining = context.load(notes_at)

    assert len(remaining) == 1
    assert remaining.notes[0].market == "Brazil"


def test_a_bad_number_in_the_list_takes_nothing(notes_at):
    """All or nothing. Deleting the valid half and reporting a failure would leave the
    file in a state the caller did not ask for and cannot see."""
    from app.cli import cmd_note

    cmd_note(["Brazil", "Sales tax changed."])
    cmd_note(["Japan", "A flagship closed.", "--kind", "one_off"])

    assert cmd_note(["--forget", "1,9"]) == 2
    assert len(context.load(notes_at)) == 2


def test_forgetting_a_note_that_is_not_there_is_refused(notes_at, capsys):
    from app.cli import cmd_note

    cmd_note(["Brazil", "Sales tax changed."])

    assert cmd_note(["--forget", "7"]) == 2


def test_listing_with_nothing_written_says_how_to_start(notes_at, capsys):
    from app.cli import cmd_note

    assert cmd_note(["--list"]) == 0
    assert "Aucune note" in capsys.readouterr().out


def test_a_market_name_is_normalised_on_the_way_in(notes_at):
    """Typed by a person, matched against the warehouse's vocabulary."""
    from app.cli import cmd_note

    cmd_note(["USA", "Something changed."])

    assert context.load(notes_at).notes[0].market == "United States"


def test_a_commented_line_is_documentation_not_a_note(tmp_path):
    """The example file, copied verbatim, put a market nobody named on the screen. A line
    the writer commented out is meant to be read, not obeyed."""
    path = tmp_path / "context.csv"
    path.write_text(
        "market,channel,since,kind,note,source\n"
        "# Exampleland,,2026-06,basis_change,An example line.,Someone\n"
        "Japan,,2026-07,one_off,A flagship closed.,CEO\n",
        encoding="utf-8",
    )

    loaded = context.load(path)

    assert len(loaded) == 1
    assert loaded.notes[0].market == "Japan"


def test_the_shipped_template_creates_nothing_when_copied():
    """It is a template. Copying it must leave the cockpit exactly as it was."""
    assert len(context.load("docs/context.example.csv")) == 0


def test_a_basis_change_names_the_drivers_it_moved():
    """The decomposition stays exact and says "most of the movement comes from AOV" —
    true, and useless as a management signal. A tax change lands entirely on money per
    unit sold: the basket a shopper fills is untouched, the euros recognised against it
    are not."""
    from app.perf.model import ecommerce_drivers

    taxed = unit(
        key="brazil-ecommerce",
        channel=ECOMMERCE,
        notes=[note()],
        actual=ecommerce_drivers(2_600_000.0, 1_000_000.0, 40_000.0),
        budget=Drivers.sales_only(3_100_000.0),
        last_year=ecommerce_drivers(3_050_000.0, 1_000_000.0, 40_000.0),
    )

    fire = analytics.fires(dataset_of(taxed))[0]

    assert "AOV" in fire.basis_caveat
    assert "volume drivers beside it do not" in fire.basis_caveat


def test_a_market_with_no_basis_change_carries_no_caveat():
    """A warning that appears everywhere is a warning nobody reads."""
    from app.perf.model import ecommerce_drivers

    ordinary = unit(
        key="japan-ecommerce",
        channel=ECOMMERCE,
        notes=[],
        actual=ecommerce_drivers(2_600_000.0, 1_000_000.0, 40_000.0),
        budget=Drivers.sales_only(3_100_000.0),
        last_year=ecommerce_drivers(3_050_000.0, 1_000_000.0, 40_000.0),
    )

    assert analytics.fires(dataset_of(ordinary))[0].basis_caveat == ""


def test_a_one_off_does_not_claim_the_basis_moved():
    """A store closing is not a change of yardstick. Saying so would blunt the warning
    for the case that needs it."""
    from app.perf.model import ecommerce_drivers

    closed = unit(
        key="japan-ecommerce",
        channel=ECOMMERCE,
        notes=[note(kind=context.ONE_OFF, market="Japan")],
        market="Japan",
        actual=ecommerce_drivers(2_600_000.0, 1_000_000.0, 40_000.0),
        budget=Drivers.sales_only(3_100_000.0),
        last_year=ecommerce_drivers(3_050_000.0, 1_000_000.0, 40_000.0),
    )

    assert analytics.fires(dataset_of(closed))[0].basis_caveat == ""


def test_a_market_with_no_drivers_at_all_carries_no_caveat():
    """Nothing to qualify where nothing was decomposed."""
    fire = analytics.fires(dataset_of(unit(notes=[note()])))[0]

    assert fire.basis_caveat == ""


# ------------------------------------------- a boundary drawn in two different places
#
# Nothing changed and nobody is wrong about a number. A customer sits on the line between
# two segments — a retailer's own web shop is both a chain and a web partner — and each
# source files it on its own side. The market total is identical; only the split differs.
#
# Left unsaid this is worse than one wrong figure, because it produces two: a segment
# above plan and its neighbour below it by exactly the same amount, both confident, both
# meaningless.


def test_a_reclassification_is_not_a_statement_about_trading():
    reclassified = unit(
        key="us-webp",
        market="United States",
        channel="webp",
        notes=[context.Note("United States", "webp", "2025-09", context.RECLASSIFIED,
                            "Sephora.com is filed under chains in the accounts.", "CEO")],
    )

    fire = analytics.fires(dataset_of(reclassified))[0]

    assert "boundary rather than a result" in fire.diagnosis
    assert analytics.people_to_push([fire]) == []


def test_the_question_points_at_the_neighbouring_plan():
    """The actionable half. If the accounts are right, the neighbouring segment's plan is
    wrong by the same amount — and that distorts a target conversation for a year."""
    reclassified = unit(
        key="us-webp",
        market="United States",
        channel="webp",
        notes=[context.Note("United States", "webp", "", context.RECLASSIFIED,
                            "Sephora.com is filed under chains.", "CEO")],
    )

    assert "neighbouring segment" in analytics.fires(dataset_of(reclassified))[0].question


def test_a_reclassification_does_not_claim_the_money_drivers_moved():
    """A change of basis moves money per unit sold. A reclassification moves the whole
    line to a neighbour and leaves every driver where it was. Saying otherwise would blunt
    the warning for the case that needs it."""
    from app.perf.model import ecommerce_drivers

    reclassified = unit(
        key="us-ecommerce",
        market="United States",
        channel=ECOMMERCE,
        notes=[context.Note("United States", "", "", context.RECLASSIFIED,
                            "Filed differently.", "CEO")],
        actual=ecommerce_drivers(2_600_000.0, 1_000_000.0, 40_000.0),
        budget=Drivers.sales_only(3_100_000.0),
        last_year=ecommerce_drivers(3_050_000.0, 1_000_000.0, 40_000.0),
    )

    assert analytics.fires(dataset_of(reclassified))[0].basis_caveat == ""


# --------------------------------------------------- naming a segment however you have it


def test_a_note_can_name_a_segment_instead_of_a_channel():
    """Three vocabularies name the same thing: the channel the screen shows, the segment
    label the plan uses, the bare code. Asking someone to remember which one this file
    wants is a good way to have the note written wrongly, or not at all."""
    assert context.resolve_channel("WEBP - Web Partners") == "webp"
    assert context.resolve_channel("WEBP") == "webp"
    assert context.resolve_channel("retail") == RETAIL
    assert context.resolve_channel("") == ""


def test_a_segment_scoped_note_is_written_that_way(notes_at):
    from app.cli import cmd_note

    cmd_note([
        "United States", "Sephora.com is filed under chains.",
        "--kind", "reclassified", "--channel", "WEBP - Web Partners",
    ])

    written = context.load(notes_at).notes[0]

    assert written.channel == "webp"
    assert written.kind == context.RECLASSIFIED


def test_a_segment_scoped_note_stays_on_its_segment(notes_at):
    from app.cli import cmd_note

    cmd_note([
        "United States", "Sephora.com is filed under chains.",
        "--kind", "reclassified", "--channel", "WEBP",
    ])

    book = context.load(notes_at)

    assert book.notes_for("United States", "webp", "2025-09")
    assert book.notes_for("United States", "whoch", "2025-09") == []


def test_a_note_can_carry_its_own_question(notes_at):
    """The kind's default question is a good guess at what to do next. Whoever writes the
    note sometimes knows better — and sometimes knows the default has been answered.
    Showing someone a question they have settled teaches them to skip the panel."""
    from app.cli import cmd_note

    cmd_note([
        "United States", "Filed under chains in the accounts; the plan is the reference.",
        "--kind", "reclassified",
        "--ask", "Ask finance to move it, not the market to explain it.",
    ])

    written = context.load(notes_at).notes[0]

    assert written.question == "Ask finance to move it, not the market to explain it."


def test_a_note_without_a_question_keeps_the_default(notes_at):
    from app.cli import cmd_note

    cmd_note(["Brazil", "Sales tax changed."])

    assert context.load(notes_at).notes[0].question == (
        context.KIND_QUESTION[context.BASIS_CHANGE]
    )


def test_the_custom_question_reaches_the_screen():
    reclassified = unit(
        key="us-webp",
        market="United States",
        channel="webp",
        notes=[context.Note("United States", "webp", "", context.RECLASSIFIED,
                            "Filed under chains in the accounts.", "CEO",
                            asked="Ask finance to move it.")],
    )

    assert analytics.fires(dataset_of(reclassified))[0].question == "Ask finance to move it."


def test_the_ask_value_is_not_mistaken_for_the_note(notes_at):
    from app.cli import cmd_note

    cmd_note(["Brazil", "Sales tax changed.", "--ask", "Rebase the plan?"])

    written = context.load(notes_at).notes[0]

    assert written.text == "Sales tax changed."
    assert written.question == "Rebase the plan?"


# --------------------------------------------------- a reclassification is a testable claim


def _noted(label, channel, actual, budget, market="United States"):
    """One noted channel of a market, with its reclassification note attached."""
    return BusinessUnit(
        key="%s-%s" % (market.lower().replace(" ", "-"), channel),
        label=label,
        market=market,
        region="AMERICAS",
        channel=channel,
        owner=OWNER,
        actual=Drivers.sales_only(actual),
        budget=Drivers.sales_only(budget),
        last_year=Drivers.sales_only(budget),
        forecast_sales=0.0,
        context_notes=[
            note(kind=context.RECLASSIFIED, market=market, channel=channel,
                 since="2025-09")
        ],
    )


def test_a_reclassified_pair_that_cancels_confirms_the_note():
    """The American case: the accounts file Sephora under Web Partners, the plan under
    chain wholesale. What one channel gains the other loses, to the euro, and the market
    total is untouched."""
    dataset = Dataset(
        period_label="July 2026",
        as_of="",
        units=[
            _noted("United States E-retailers", "webp", 34_474_000.0, 30_000_000.0),
            _noted("United States Chain Wholesale", "whoch", 14_526_000.0, 19_000_000.0),
        ],
    )
    check, = analytics.reclassification_checks(dataset)

    assert check.offsets
    assert check.net == 0.0
    assert "The note holds" in check.message


def test_a_reclassified_pair_that_does_not_cancel_says_so_without_accusing():
    """Two things can produce it — a note written backwards, or real trading in the same
    channels — and this cannot tell them apart. So it names both and asks. Claiming the
    note is wrong would be the same overconfidence the note exists to prevent."""
    dataset = Dataset(
        period_label="July 2026",
        as_of="",
        units=[
            _noted("United States E-retailers", "webp", 34_474_000.0, 30_000_000.0),
            _noted("United States Chain Wholesale", "whoch", 18_500_000.0, 19_000_000.0),
        ],
    )
    check, = analytics.reclassification_checks(dataset)

    assert not check.offsets
    assert "wrong side" in check.message
    assert "trading away from plan" in check.message


def test_a_boundary_with_only_one_side_described_is_not_checked():
    """A boundary has two sides. One of them being noted says nothing about whether the
    note is right, and a verdict drawn from half a claim would be a guess with a number
    attached."""
    dataset = Dataset(
        period_label="July 2026",
        as_of="",
        units=[_noted("United States E-retailers", "webp", 34_474_000.0, 30_000_000.0)],
    )

    assert analytics.reclassification_checks(dataset) == []


def test_the_residual_is_judged_against_the_larger_leg():
    """Against the sum of the legs it would be compared with a figure that already
    contains it, and a pair that barely moved would look as sound as one that cancelled
    exactly."""
    dataset = Dataset(
        period_label="July 2026",
        as_of="",
        units=[
            _noted("United States E-retailers", "webp", 31_000_000.0, 30_000_000.0),
            _noted("United States Chain Wholesale", "whoch", 18_200_000.0, 19_000_000.0),
        ],
    )
    check, = analytics.reclassification_checks(dataset)

    assert check.gross == 1_000_000.0
    assert check.net == 200_000.0
    assert check.offsets


def test_the_check_states_which_side_gained():
    """The half the euros cannot reach. A note whose prose describes the boundary
    backwards passes the offset test in silence — the two gaps cancel either way. Saying
    which side the revenue landed on puts that sentence beside the note on screen, where
    the contradiction becomes visible to the person who wrote it."""
    dataset = Dataset(
        period_label="July 2026",
        as_of="",
        units=[
            _noted("United States E-retailers", "webp", 34_474_000.0, 30_000_000.0),
            _noted("United States Chain Wholesale", "whoch", 14_526_000.0, 19_000_000.0),
        ],
    )
    check, = analytics.reclassification_checks(dataset)

    assert check.direction == (
        "The revenue lands in United States E-retailers and is missing from "
        "United States Chain Wholesale."
    )
    assert check.direction in check.message


def test_the_note_is_carried_to_the_check():
    """So the screen can print the claim next to the verdict on it."""
    dataset = Dataset(
        period_label="July 2026",
        as_of="",
        units=[
            _noted("United States E-retailers", "webp", 34_474_000.0, 30_000_000.0),
            _noted("United States Chain Wholesale", "whoch", 14_526_000.0, 19_000_000.0),
        ],
    )
    check, = analytics.reclassification_checks(dataset)

    # One note, not two: both channels carry the same sentence in this fixture, and
    # printing it twice would read as two independent findings.
    assert len(check.notes) == 1
    assert check.notes[0].kind == context.RECLASSIFIED
