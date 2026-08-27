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
