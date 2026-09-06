"""Ce qui arrive : les temps forts des six semaines, par périmètre, pesés l'an dernier.
Tout est inventé."""

from __future__ import annotations

import datetime

from app.perf import gifting as G

TODAY = datetime.date(2026, 10, 20)

FILE = ("event,market,start,end,share_of_month_pct,uplift_pct,sales_last_year_eur,measured_on,note\n"
        "Singles Day,Japan,2026-11-01,2026-11-11,18.4,140,3200000,2025-11-01..2025-11-11,fenêtre de la plateforme\n"
        "Black Friday,Southland,2026-11-27,2026-11-30,12.1,95,800000,2025-11-28..2025-12-01,\n"
        "Noël,Southland,2026-12-01,2026-12-24,,,,,pas encore pesé\n"
        "Fête des mères,Southland,2026-05-25,2026-05-31,9,60,400000,2025-05-26..2025-06-01,\n"
        "Cassé,Japan,2026-11-40,2026-11-11,,,,,\n")


def _calendar(tmp_path, text=FILE):
    path = tmp_path / "gifting.csv"
    path.write_text(text, encoding="utf-8")
    return G.load(str(path))


def test_the_calendar_is_read_and_a_bad_window_is_named(tmp_path):
    calendar = _calendar(tmp_path)

    assert [event.name for event in calendar.events] == ["Singles Day", "Black Friday", "Noël", "Fête des mères"]
    assert calendar.faults == ["ligne 6 : fenêtre illisible pour « Cassé »"]
    singles = calendar.events[0]
    assert singles.measured and abs(singles.share - 0.184) < 1e-9 and singles.sales == 3_200_000.0
    assert singles.when == "du 1er au 11 novembre".replace("1er", "1") or singles.when == "du 1 au 11 novembre"
    assert singles.weight.startswith("18 % du mois l'an dernier, ")
    assert "+140 % par jour contre les semaines autour" in singles.weight
    assert calendar.events[2].weight == "non pesé"


def test_only_what_is_ahead_within_the_horizon_is_kept_nearest_first(tmp_path):
    calendar = _calendar(tmp_path)
    ahead = calendar.upcoming(TODAY)

    assert [event.name for event in ahead] == ["Singles Day", "Black Friday", "Noël"]
    assert [event.name for event in calendar.upcoming(datetime.date(2026, 11, 12))] == ["Black Friday", "Noël"]
    assert calendar.upcoming(datetime.date(2027, 2, 1)) == []


def test_events_are_grouped_by_perimeter_and_the_unmeasured_are_said(tmp_path):
    from tests.test_perf_owners import HEADER, directory_file
    from app.perf import owners

    directory = owners.load(directory_file(tmp_path, [
        ["Annuaire"], HEADER,
        ["Japon", "Aiko", "TANAKA", "General Manager, Japan", "Japon", "Patron de BU", "", "Tokyo"],
    ]))
    review = G.build(_calendar(tmp_path), directory=directory, today=TODAY)

    assert review.usable and review.count == 3
    assert review.title == "Ce qui arrive dans les 6 semaines"
    assert [group.name for group in review.groups] == ["Japon"]
    assert review.for_name("Japon").events[0].name == "Singles Day"
    assert review.loose is not None and [event.name for event in review.loose.events] == ["Black Friday", "Noël"]
    assert review.unmeasured_note == "non pesés, portés avec leur date seule : Noël"
    assert any("Cassé" in reason for reason in review.absent)


def test_without_the_file_or_without_anything_ahead_the_review_says_so(tmp_path):
    absent = G.build(None, today=TODAY)
    assert not absent.usable and absent.absent == ["var/gifting.csv absent : les temps forts à venir ne sont pas lus"]
    quiet = G.build(_calendar(tmp_path), today=datetime.date(2027, 2, 1))
    assert not quiet.usable and "aucun temps fort dans les 6 prochaines semaines" in quiet.absent
    assert quiet.beyond_note == ""


def test_an_empty_horizon_still_says_what_comes_next_and_in_how_many_days(tmp_path):
    early = G.build(_calendar(tmp_path), today=datetime.date(2026, 9, 6))

    assert not early.usable
    assert early.beyond_note.startswith("le prochain au-delà : Singles Day, Japan, du 1 au 11 novembre")
    assert early.beyond_note.endswith(", dans 56 jours")


def test_market_names_are_normalised_like_the_rest_of_the_cockpit(tmp_path):
    calendar = _calendar(tmp_path, "event,market,start,end\nBlack Friday,USA,2026-11-27,2026-11-29\n"
                                   "Noël,UK,2026-12-01,2026-12-24\n")

    assert [event.market for event in calendar.events] == ["United States", "United Kingdom"]
