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


def test_when_the_sheet_does_not_say_closed_the_dossier_does_not_call_a_store_mute():
    class _Store:
        def __init__(self, code, name, market, status, actual, last_year):
            self.code, self.name, self.market, self.status = code, name, market, status
            self.actual, self.last_year, self.budget, self.is_bulk = actual, last_year, None, False

    class _Sales:
        usable = True
        stores = [_Store("S1", "Une boutique", "China", "2", 0.0, 50_000.0),
                  _Store("S2", "Une autre", "China", "", 0.0, 80_000.0)]

    dossier = visit.build("China", store_sales=_Sales(), closed_statuses=())
    assert not dossier.closure_vocabulary_known
    assert dossier.mute_stores == [] and sorted(dossier.silent_statuses) == ["(vide)", "2"]
    assert not any("Fermée, ou muette" in q for q in dossier.questions)
    text = "\n".join(dossier.lines())
    assert "le dossier ne tranche pas" in text and "CEOOS_STORE_CLOSED_STATUSES" in text


def test_a_configured_status_code_counts_as_a_closure_and_the_rest_stay_mute():
    class _Store:
        def __init__(self, code, name, market, status, actual, last_year):
            self.code, self.name, self.market, self.status = code, name, market, status
            self.actual, self.last_year, self.budget, self.is_bulk = actual, last_year, None, False

    class _Sales:
        usable = True
        stores = [_Store("S1", "Une fermée", "China", "4", 0.0, 50_000.0),
                  _Store("S2", "Une autre fermée", "China", "4", 0.0, 30_000.0),
                  _Store("S3", "Une nouvelle muette", "China", "1", 0.0, 80_000.0),
                  _Store("S4", "Une qui tient", "China", "1", 40_000.0, 42_000.0)]

    blind = visit.build("China", store_sales=_Sales(), closed_statuses=())
    assert blind.silent_status_counts == [("4", 2), ("1", 1)]
    assert blind.silent_statuses_sentence == "« 4 » ×2, « 1 » ×1"
    assert blind.mute_stores == []

    dossier = visit.build("China", store_sales=_Sales(), closed_statuses=("4",))
    assert dossier.closure_vocabulary_known
    assert [m.code for m in dossier.mute_stores] == ["S3"]
    assert any("Une nouvelle muette" in q and "Fermée, ou muette" in q for q in dossier.questions)
    assert "2 fermées selon la feuille" in "\n".join(dossier.lines())


def test_the_closed_status_setting_is_read_from_the_environment(monkeypatch):
    from app import config

    monkeypatch.setenv("CEOOS_STORE_CLOSED_STATUSES", " 4, 9 ,4,")
    assert config.load_settings().store_closed_statuses == ("4", "9")
    monkeypatch.setenv("CEOOS_STORE_CLOSED_STATUSES", "")
    assert config.load_settings().store_closed_statuses == ()


def test_the_grey_reads_as_three_figures_marked_plan_and_unmarked():
    dossier = _dossier()
    assert dossier.marked_bulk > 0 and dossier.unmarked_bulk > 0
    assert dossier.measured_bulk == dossier.marked_bulk + dossier.unmarked_bulk
    assert dossier.plan_bulk_label == "plan sans ligne" and dossier.measured_vs_plan == ""
    assert dossier.grey_sentence.startswith("China : mesuré %s, dont marqué par l'entrepôt %s"
                                            % (dossier.measured_bulk_label, dossier.marked_bulk_label))
    assert "le plan attend plan sans ligne" in dossier.grey_sentence

    dossier.expected_to_date = dossier.measured_bulk / 2
    assert dossier.measured_vs_plan == "au-dessus du plan"
    assert dossier.grey_sentence.endswith("— au-dessus du plan")

    empty = visit.build("Westland")
    assert empty.unmarked_bulk_label == "non lu" and empty.grey_sentence == "aucun vrac lu sur Westland"


def test_the_dossier_carries_what_sells_by_product_on_this_market_alone():
    from app.perf import products

    review = products.for_markets(mock.product_rows(), ["China"], "China")
    dossier = visit.build("China", dataset=mock.dataset(), products=review)
    assert dossier.products is review and review.usable
    text = "\n".join(dossier.lines())
    assert "PRODUITS — ce qui pousse et ce qui recule" in text
    assert text.index("CANAUX") < text.index("PRODUITS") < text.index("CE QUI L'ALIMENTE")
    assert any(line.startswith("    pousse") or line.startswith("    recule") for line in dossier.lines())

    bare = visit.build("Westland")
    assert "la lecture produit n'est pas déposée" in "\n".join(bare.lines())


class _Unit:
    def __init__(self, market, channel, sales, last_year, gap=0.0, sell_in=False):
        self.market, self.channel, self.label = market, channel, "%s %s" % (market, channel)
        self.sales_actual, self.sales_last_year, self.gap_vs_budget = sales, last_year, gap
        self.is_sell_in, self.is_aggregate, self.budget_known = sell_in, False, True
        self.no_breakdown_reason = ""


class _Dataset:
    period_label = "Août 2026"

    def __init__(self, units):
        self.units = units


def test_the_grey_says_what_the_sell_in_weighs_and_opens_the_scissors_when_partners_outbuy_the_shops():
    # Sell-out en recul de 10 %, sell-in en hausse de 30 % pour 40 % du mois : le ciseau
    # s'ouvre, et la question le dit. Un marché sans sell-in dit que la lecture le couvre.
    units = [_Unit("Southland", "retail", 600.0, 667.0),
             _Unit("Southland", "wholesale", 400.0, 308.0, sell_in=True)]
    dossier = visit.build("Southland", dataset=_Dataset(units))
    assert abs(dossier.sell_in_share - 0.4) < 1e-9 and dossier.sell_in_share_label == "40 %"
    assert dossier.scissors is not None and dossier.scissors > visit.SCISSORS_POINTS
    assert dossier.scissors_open
    assert "hors de toute lecture du gris" in dossier.sell_in_grey_sentence
    assert "ressort ailleurs" in dossier.sell_in_grey_sentence
    assert any("Qui achète, et où ça ressort" in q for q in dossier.questions)
    assert "le sell-in fait 40 %" in "\n".join(dossier.lines())

    calm = visit.build("Southland", dataset=_Dataset([
        _Unit("Southland", "retail", 600.0, 600.0),
        _Unit("Southland", "wholesale", 400.0, 400.0, sell_in=True)]))
    assert not calm.scissors_open and not any("Qui achète" in q for q in calm.questions)

    shops_only = visit.build("Southland", dataset=_Dataset([_Unit("Southland", "retail", 600.0, 600.0)]))
    assert shops_only.sell_in_share is None and shops_only.sell_in_share_label == "aucun"
    assert "que la lecture couvre" in shops_only.sell_in_grey_sentence


def test_a_market_without_a_validated_flag_says_method_not_absence():
    from app.perf import grey as grey_module

    rows = [dict(r, market="Westland") for r in mock.shadow_rows() if r.get("market") == "China"]
    shadow_review = shadow.build(rows)
    dossier = visit.build("Westland", shadow_review=shadow_review)
    assert not dossier.flag_validated and dossier.marked is None
    assert dossier.marked_bulk_label == grey_module.FLAG_NOT_VALIDATED
    assert "zéro de méthode" in dossier.marked_sentence and "zéro de méthode" in dossier.grey_sentence
    assert dossier.questions and "n'est pas validé ici" in dossier.questions[0]
    assert not any("quand les grands comptes le portent" in q for q in dossier.questions)

    china = _dossier()
    assert china.flag_validated and "zéro de méthode" not in china.marked_sentence
