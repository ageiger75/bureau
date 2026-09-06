"""La semaine : ce qui a bougé depuis lundi, marché par marché.

Ces tests gardent : des semaines pleines du lundi au dimanche, la dernière lue ; la
précédente et la même de l'an dernier, 364 jours en arrière ; une semaine entamée n'est pas
comptée ; un marché dont le 1er encaisse une campagne est nommé. Tout est inventé.
"""

from __future__ import annotations

import datetime

from app.perf import weekly as W

# Un samedi : la semaine du lundi 31 août au dimanche 6 septembre est entamée.
READ = datetime.date(2026, 9, 5)


def _rows(markets, days=42, before=True):
    rows = []
    for market, base in markets.items():
        for back in range(0, days):
            day = READ - datetime.timedelta(days=back)
            rows.append({"market": market, "iso2": "XX", "transaction_date": day.isoformat(),
                         "net_sales_eur": base})
            if before:
                rows.append({"market": market, "iso2": "XX",
                             "transaction_date": (day - datetime.timedelta(days=364)).isoformat(),
                             "net_sales_eur": base * 0.8})
    return rows


def test_the_last_complete_week_ends_on_the_last_sunday_read():
    span = W.last_complete_week(READ)

    assert span.start == datetime.date(2026, 8, 24) and span.end == datetime.date(2026, 8, 30)
    assert span.label == "du 24 au 30 août"
    assert W.last_complete_week(datetime.date(2026, 9, 6)).end == datetime.date(2026, 9, 6)
    assert W.Span(datetime.date(2026, 9, 6)).label == "du 31 août au 6 septembre"
    assert W.Span(datetime.date(2026, 9, 6)).first_of_month == datetime.date(2026, 9, 1)
    assert W.Span(datetime.date(2026, 8, 30)).first_of_month is None


def test_the_week_reads_against_the_previous_and_the_same_week_last_year():
    review = W.build(_rows({"NORTHLAND": 1000.0}), today=READ)

    assert review.usable
    assert review.title == "Semaine du 24 au 30 août"
    north = review.group.markets[0]
    assert north.week == 7000.0 and north.previous == 7000.0
    assert abs(north.last_year - 5600.0) < 1e-6
    assert north.wow_label == "+0 %" and north.yoy_label == "+25 %"
    assert review.days_note.startswith("6 jours lus depuis, non comptés")
    assert review.group.sentence.endswith("+0 % sur la semaine précédente, +25 % sur la même semaine l'an dernier")


def test_a_market_without_last_year_says_so_instead_of_a_growth():
    review = W.build(_rows({"NEWLAND": 500.0}, before=False), today=READ)
    line = review.group.markets[0]

    assert line.last_year is None and line.yoy_label == "—"
    assert "pas d'an dernier sur ces dates" in line.sentence


def test_a_campaign_market_is_named_only_when_a_first_of_month_is_in_a_compared_week():
    # Lu jusqu'au dimanche 6 septembre : la semaine du 31 août au 6 septembre est pleine et
    # contient le 1er.
    read = datetime.date(2026, 9, 6)
    rows = []
    for back in range(0, 42):
        day = read - datetime.timedelta(days=back)
        rows.append({"market": "LUMPLAND", "iso2": "XX", "transaction_date": day.isoformat(),
                     "net_sales_eur": 100.0 + (9000.0 if day.day == 1 else 0.0)})
    review = W.build(rows, lumpy=["Lumpland"], today=read)

    assert review.span.end == read
    assert review.group.markets[0].campaign
    assert "LUMPLAND" not in review.campaign_note and "Lumpland" in review.campaign_note
    quiet = W.build(_rows({"LUMPLAND": 100.0}), lumpy=["Lumpland"], today=READ)
    assert not quiet.group.markets[0].campaign and quiet.campaign_note == ""


def test_without_daily_rows_the_review_names_it():
    review = W.build([], today=READ)

    assert not review.usable
    assert review.absent == ["aucune vente au jour lue : la semaine ne se lit pas"]


def test_markets_are_grouped_by_perimeter_and_the_rest_is_loose(tmp_path):
    from tests.test_perf_owners import HEADER, directory_file
    from app.perf import owners

    directory = owners.load(directory_file(tmp_path, [
        ["Annuaire"], HEADER,
        ["Japon", "Aiko", "TANAKA", "General Manager, Japan", "Japon", "Patron de BU", "", "Tokyo"],
    ]))
    review = W.build(_rows({"JAPAN": 300.0, "ELSEWHERE": 100.0}), directory=directory, today=READ)

    assert [line.name for line in review.perimeters] == ["Japon"]
    assert review.for_name("Japon").week == 2100.0
    assert review.loose is not None and [line.name for line in review.loose.markets] == ["Elsewhere"]
    assert review.group.week == 2800.0
