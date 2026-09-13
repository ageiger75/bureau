"""Une frontière datée dans les comptes : la note de reclassement cesse quand le centre de
profit qu'elle nomme se tait, et le panneau dit où le partenaire est passé. Codes, noms et
valeurs inventés.
"""

from __future__ import annotations

from app.perf import boundary as B
from app.perf import context as C


def _rows(code, label, channel, months, iso2="NL"):
    return [{"period": period, "code": code, "label": label, "channel": channel,
             "iso2": iso2, "net_eur": value} for period, value in months.items()]


def _months(start, through, value):
    year, month = int(start[:4]), int(start[5:7])
    out = {}
    while "%04d-%02d" % (year, month) <= through:
        out["%04d-%02d" % (year, month)] = value
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return out


OLD = "500PARTWP"
NEW = "500PARTNR"
FRESH = "500NEWWEB"
ROWS = (_rows(OLD, "PARTNER ONE", "WEBP", _months("2025-04", "2026-04", 700.0))
        + _rows(NEW, "PARTNER ONE", "WHOCH", _months("2026-05", "2026-08", 900.0))
        + _rows(FRESH, "NEW WEB SHOP", "WEBP", _months("2026-06", "2026-08", 300.0))
        + _rows("500AMZWEB", "BIG RIVER", "WEBP", _months("2025-04", "2026-08", 2000.0)))


def _note(text="Le centre %s est rangé du mauvais côté" % OLD, source=""):
    return C.Note(market="Northland", channel="webp", since="2025-09",
                  kind=C.RECLASSIFIED, text=text, source=source)


def test_codes_are_read_from_the_note_and_its_source():
    assert B.codes_in("centre de profit %s" % OLD, "Consolidation — %s" % NEW) == [OLD, NEW]
    assert B.codes_in("rien ici", "") == []


def test_a_centre_that_went_quiet_dates_the_note_and_names_where_the_partner_went():
    note = _note()
    readings = B.apply([note], ROWS, {}, "2026-08", today=__import__("datetime").date(2026, 9, 13))

    assert len(readings) == 1
    reading = readings[0]
    assert reading.closed_since == "2026-05" and note.closed_since == "2026-05"
    assert reading.destination == NEW and reading.destination_channel == "whoch"
    assert reading.destination_since == "2026-05" and reading.moved == 900.0
    assert [code for code, _label, _amount in reading.newcomers] == [FRESH]
    assert "ne facture plus depuis mai 2026" in reading.sentence
    assert "Chain Wholesale depuis mai 2026" in reading.sentence
    assert "sans note" in reading.sentence and "New Web Shop" in reading.sentence


def test_a_dated_note_stops_applying_from_that_month_and_not_before():
    note = _note()
    B.apply([note], ROWS, {}, "2026-08", today=__import__("datetime").date(2026, 9, 13))

    assert note.applies_to("Northland", "webp", "2026-04")
    assert not note.applies_to("Northland", "webp", "2026-05")
    assert not note.applies_to("Northland", "webp", "2026-08")
    assert note.applies_to("Northland", "webp", "2026-08", include_closed=True)


def test_a_centre_still_invoicing_leaves_the_note_as_it_was():
    note = _note()
    readings = B.apply([note], ROWS, {}, "2026-03", today=__import__("datetime").date(2026, 9, 13))

    assert readings and not readings[0].closed
    assert note.closed_since == "" and note.applies_to("Northland", "webp", "2026-03")


def test_without_invoices_or_without_a_code_nothing_is_dated():
    note = _note()
    assert B.apply([note], [], {}, "2026-08") == []
    assert note.closed_since == "" and note.boundary is None
    plain = _note(text="Une frontière sans code")
    assert B.apply([plain], ROWS, {}, "2026-08") == []


def test_the_partner_is_matched_by_the_readers_names_before_the_warehouse_label():
    rows = (_rows(OLD, "SOME LABEL", "WEBP", _months("2025-04", "2026-04", 700.0))
            + _rows(NEW, "ANOTHER LABEL", "WHOCH", _months("2026-05", "2026-08", 900.0)))
    note = _note()
    readings = B.apply([note], rows, {OLD: "Partner One", NEW: "partner one"}, "2026-08",
                       today=__import__("datetime").date(2026, 9, 13))
    assert readings[0].destination == NEW
    unnamed = B.apply([_note()], rows, {}, "2026-08", today=__import__("datetime").date(2026, 9, 13))
    assert unnamed[0].destination == ""


def test_a_dated_boundary_reaches_the_check_and_its_message(monkeypatch):
    from app.perf import analytics
    from app.perf.model import Dataset
    from tests.test_perf_context import _noted

    note = _note()
    B.apply([note], ROWS, {}, "2026-08", today=__import__("datetime").date(2026, 9, 13))
    C.install([note])
    try:
        left = _noted("Northland E-retailers", "webp", 34_474_000.0, 30_000_000.0)
        left.context_notes = []  # datée : la note ne s'applique plus à l'unité
        right = _noted("Northland Chain Wholesale", "whoch", 18_500_000.0, 19_000_000.0)
        left.market = right.market = "Northland"
        dataset = Dataset(period_label="August 2026", as_of="", units=[left, right],
                          period="2026-08")
        check, = analytics.reclassification_checks(dataset)
        assert check.dated is not None
        assert "ne facture plus depuis mai 2026" in check.message
        assert "s'écarte du plan par lui-même" in check.message
        assert "mauvais côté" not in check.message
    finally:
        C.reset()
