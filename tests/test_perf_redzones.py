"""Les zones rouges : cinq fronts nommés par le lecteur, une ligne chacun, à tenir.

Ces tests gardent la règle : une zone porte une mesure que le cockpit connaît, sinon elle
entre « à brancher » et jamais avec un chiffre deviné ; au plus cinq ; et chaque mesure
lit ce que la page a déjà lu. Valeurs inventées.
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

from app.perf import redzones as Z

EXAMPLE = pathlib.Path(__file__).resolve().parent.parent / "docs" / "red_zones.example.csv"


def _board(tmp_path, text=None):
    path = tmp_path / "red_zones.csv"
    path.write_text(text if text is not None else EXAMPLE.read_text(encoding="utf-8"),
                    encoding="utf-8")
    return Z.load(str(path))


def test_the_example_file_reads_five_zones_with_their_measures(tmp_path):
    board = _board(tmp_path)

    assert not board.faults
    assert [zone.name for zone in board.zones] == [
        "Japon", "Travel Retail", "Chine retail", "Brésil", "Enseigne US"]
    assert [zone.measure for zone in board.zones] == [
        Z.SAMESTORE, Z.SELL_IN_CHANNEL, Z.RETAIL_EX_BULK, Z.YEAR_GAP, Z.PROFIT_CENTRE]
    assert board.zones[1].argument == "Travel Retail"


def test_an_unknown_measure_is_refused_by_name_and_a_sixth_zone_waits(tmp_path):
    text = "zone,scope,measure\n" + "".join(
        "Z%d,Market%d,year_gap\n" % (n, n) for n in range(6)) + "Vague,Somewhere,vibes\n"
    board = _board(tmp_path, text)

    assert len(board.shown) == Z.MOST and len(board.zones) == 6
    assert any("vibes" in fault for fault in board.faults)
    assert any("6 zones" in fault for fault in board.faults)


def test_a_measure_the_cockpit_cannot_read_yet_says_so_instead_of_a_figure(tmp_path):
    board = _board(tmp_path, "zone,scope,measure\nEnseigne US,United States,profit_centre:ENSEIGNE\n")

    review = Z.build(board)

    assert review.readings[0].word == Z.NOT_WIRED
    assert not review.readings[0].wired
    assert "ne le lit pas encore" in review.readings[0].sentence


def test_the_same_store_zone_reads_the_kpi_rows_of_its_market(tmp_path):
    board = _board(tmp_path, "zone,scope,measure,target\nJapon,Japan,samestore,≥ 0 %\n")
    rows = [{"scope": "Japan", "kpi_key": "same_store_sales", "period": p, "value": v}
            for p, v in (("2025-08", 100.0), ("2026-08", 96.0))]

    reading = Z.build(board, kpi_rows=rows).readings[0]

    assert reading.word == "-4.0 %"
    assert reading.direction == "en retard"
    assert "cible ≥ 0 %" in reading.sentence
    assert not Z.build(board, kpi_rows=[]).readings[0].wired


def test_the_sell_in_zone_reads_the_channel_line_of_the_month(tmp_path):
    board = _board(tmp_path, "zone,scope,measure\nTravel Retail,Travel Retail,sell_in_channel:Travel Retail\n")
    line = SimpleNamespace(name="Travel Retail", current=5_000_000.0, growth=0.07,
                           growth_label="+7 %", same_dates_label="-17 %")
    invoiced = SimpleNamespace(usable=True, channels=[line])

    reading = Z.build(board, invoiced=invoiced).readings[0]

    assert reading.word == "+7 %" and reading.direction == "en avance"
    assert "à jours ouvrés égaux" in reading.sentence
    assert not Z.build(board, invoiced=SimpleNamespace(usable=True, channels=[])).readings[0].wired


def test_the_year_gap_zone_reads_the_perimeter_verdict(tmp_path):
    board = _board(tmp_path, "zone,scope,measure\nBrésil,Brazil,year_gap\n")
    year = SimpleNamespace(usable=True, label="en retard", gap_label="-15.7 %")
    month = SimpleNamespace(usable=True, early=True, label="trop tôt", gap_label="")
    track = SimpleNamespace(perimeters=[SimpleNamespace(name="Brazil", year=year, month=month)])

    reading = Z.build(board, track=track).readings[0]

    assert reading.word == "-15.7 %" and reading.direction == "en retard"
    assert "mois trop tôt" in reading.sentence


def test_without_the_file_the_review_names_it():
    review = Z.build(None)

    assert not review.usable
    assert "red_zones.csv absent" in review.absent[0]


def test_the_demo_rows_read_the_bulk_zone():
    from app.perf import mock

    board = Z.Board([Z.Zone("Chine retail", "China", Z.RETAIL_EX_BULK)], [])
    reading = Z.build(board, kpi_rows=mock.kpi_rows()).readings[0]

    assert reading.wired and "hors bulk" in reading.sentence
