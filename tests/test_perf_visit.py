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
