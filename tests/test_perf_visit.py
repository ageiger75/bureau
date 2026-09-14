"""Le dossier de visite : un marché en une page, avec ses trois questions générées de ce que
les chiffres montrent de plus net. Sur les lectures inventées du cockpit."""

from __future__ import annotations

from app.perf import grey, mock, shadow, visit


def _dossier(market="China"):
    dataset = mock.dataset()
    grey_review = grey.build(mock.kpi_rows(), bulk_rows=mock.bulk_rows())
    shadow_review = shadow.build(mock.shadow_rows())
    return visit.build(market, dataset=dataset, grey_review=grey_review,
                       shadow_review=shadow_review, iso2_by_market={"China": "CN"}, owner="Une MD")


def test_the_dossier_asks_three_questions_and_starts_with_the_unmarked_bulk():
    dossier = _dossier()

    assert dossier.name == "China" and dossier.owner == "Une MD"
    assert len(dossier.questions) == 3
    assert "cinquante unités" in dossier.questions[0] and "ST-CN-0410" in dossier.questions[0]
    assert any("hors vrac ou vrac compris" in q for q in dossier.questions)
    assert dossier.shadow is not None and dossier.shadow.quantity.marks_its_bulk is False
    assert dossier.marked is not None and dossier.accounts
    assert dossier.stores_note == "le fichier par boutique n'est pas déposé"


def test_the_dossier_renders_as_text_in_a_fixed_order():
    text = "\n".join(_dossier().lines())
    for heading in ("LES TROIS QUESTIONS", "CANAUX", "BOUTIQUES", "GRIS", "CE QUI L'ALIMENTE",
                    "PARTENAIRES FACTURÉS DEPUIS CN", "REGISTRE ET NOTES"):
        assert heading in text
    assert text.index("LES TROIS QUESTIONS") < text.index("CANAUX") < text.index("GRIS")


def test_a_market_without_readings_still_has_a_dossier():
    dossier = visit.build("Westland")
    assert dossier.name == "Westland" and dossier.questions == []
    assert "rien d'écrit" in "\n".join(dossier.lines())


def test_the_first_question_is_about_the_unmarked_euros_when_they_weigh():
    dossier = _dossier()
    piece = dossier.shadow.quantity
    assert piece.unmarked_share is not None and piece.unmarked_share >= visit.UNMARKED_WORTH_ASKING
    assert dossier.questions[0].startswith(piece.unmarked_label)
    assert "ne portent pas le drapeau" in dossier.questions[0]


def test_a_channel_without_a_plan_says_so_instead_of_a_gap_equal_to_its_sales():
    class _Unit:
        label = "Westland Travel Retail"; channel = "travel"; sales_actual = 1000.0
        gap_vs_budget = 1000.0; sales_last_year = 900.0; is_sell_in = True
        no_breakdown_reason = ""; budget_known = False; market = "Westland"; is_aggregate = False

    channel = visit.Channel(_Unit())
    assert channel.gap_label == "plan non lu" and channel.gap == 0.0
    feed = visit.Feed("Westland Travel Retail", 1000.0, 1000.0, 900.0, budget_known=False)
    assert "plan non lu" in feed.sentence and "contre le plan" not in feed.sentence


def test_a_silent_store_without_a_closure_is_a_question_and_a_closed_one_is_not():
    class _Store:
        def __init__(self, code, name, market, status, actual, last_year):
            self.code, self.name, self.market, self.status = code, name, market, status
            self.actual, self.last_year, self.budget, self.is_bulk = actual, last_year, None, False

    class _Sales:
        usable = True
        stores = [_Store("S1", "Une boutique fermée", "China", "Closed", 0.0, 50_000.0),
                  _Store("S2", "Une boutique muette", "China", "New", 0.0, 80_000.0),
                  _Store("S3", "Une boutique qui tient", "China", "Open", 40_000.0, 42_000.0)]

    dossier = visit.build("China", store_sales=_Sales())
    assert [m.code for m in dossier.silent] == ["S2", "S1"] or [m.code for m in dossier.silent] == ["S1", "S2"]
    assert [m.code for m in dossier.mute_stores] == ["S2"]
    assert any("Une boutique muette" in q and "Fermée, ou muette" in q for q in dossier.questions)
    assert not any("Une boutique fermée" in q for q in dossier.questions)
    assert "1 fermées selon la feuille" in "\n".join(dossier.lines())
