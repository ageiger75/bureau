"""Le gris et le vrac : le vrac lu marché par marché contre l'an dernier, d'où il vient,
et le budget des flux à nettoyer en face, en ordre de grandeur. Marchés et valeurs inventés.
"""

from __future__ import annotations

from app.perf import grey as G


def _rows(scope, sales, bulk_share, start="2025-04", through="2026-08", bump=None):
    rows = []
    year, month = int(start[:4]), int(start[5:7])
    while "%04d-%02d" % (year, month) <= through:
        period = "%04d-%02d" % (year, month)
        share = bulk_share
        if bump and period >= bump[0]:
            share = bump[1]
        rows.append({"scope": scope, "kpi_key": "net_sales", "period": period, "value": sales})
        rows.append({"scope": scope, "kpi_key": "net_sales_hors_bulk", "period": period,
                     "value": sales * (1 - share)})
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return rows


class _Line:
    def __init__(self, name, sales):
        self.name, self.sales = name, sales


class _Plan:
    unhealthy = [_Line("FLUX UN", 600.0), _Line("FLUX DEUX", 600.0)]
    unhealthy_total = _Line("TOTAL", 1200.0)


def test_the_bulk_is_read_per_market_with_its_origin_and_its_growth():
    rows = (_rows("LOEP", 1000.0, 0.05, bump=("2026-04", 0.06))
            + _rows("Northland", 500.0, 0.08, bump=("2026-04", 0.10))
            + _rows("Eastland", 300.0, 0.02) + _rows("Westland", 200.0, 0.0))
    review = G.build(rows)

    assert review.usable and review.start == "2026-04" and review.through == "2026-08"
    assert G.build(_rows("LOEP", 1.0, 0.1) + _rows("HONG KONG", 1.0, 0.1)).shown[0].scope == "Hong Kong"
    assert review.group.bulk == 300.0 and review.group.bulk_ly == 250.0
    assert review.group.word == "monte" and "le vrac lu monte" in review.headline
    assert [item.scope for item in review.shown] == ["Northland", "Eastland"]
    assert review.origin_sentence == "il vient de Northland 83 %, Eastland 10 %"
    assert review.shown[0].share_label == "10 %" and review.shown[0].word == "monte"
    assert review.shown[1].word == "tient"
    assert review.question.startswith("Northland : le vrac monte de 25.0 %")
    assert len(review.series) == 6 and review.series[-1][0] == "2026-08"


def test_the_budget_s_cleaning_flows_sit_in_front_as_an_order_of_magnitude():
    rows = _rows("LOEP", 1000.0, 0.05) + _rows("Northland", 500.0, 0.10)
    review = G.build(rows, plan=_Plan())
    assert review.expected_to_date == 500.0
    assert "FLUX UN, FLUX DEUX" in review.plan_sentence
    assert "en dessous" in review.plan_sentence and "ne marque pas" in review.plan_sentence

    without = G.build(rows)
    assert "pas de ligne de plan" in without.plan_sentence


def test_shares_never_exceed_the_markets_sum_when_the_group_is_read_smaller():
    rows = _rows("LOEP", 1000.0, 0.01) + _rows("Northland", 500.0, 0.10)
    review = G.build(rows)
    assert review.total_bulk == 250.0 and review.origin_sentence == "il vient de Northland 100 %"


def test_without_the_two_bases_the_reading_is_a_stated_absence():
    review = G.build([{"scope": "LOEP", "kpi_key": "net_sales", "period": "2026-08", "value": 1.0}])
    assert not review.usable and "deux bases" in review.note


# ------------------------------------------------------------------ ligne à ligne


def _bulk_rows(shapes, start="2025-04", through="2026-08"):
    """`shapes` : (marché, drapeau, sous-canal, point de vente, gamme, mensuel, mensuel l'an
    dernier)."""
    rows = []
    year, month = int(start[:4]), int(start[5:7])
    while "%04d-%02d" % (year, month) <= through:
        period = "%04d-%02d" % (year, month)
        for market, flag, sub_channel, store, range_name, now, before in shapes:
            value = now if period >= "2026-04" else before
            rows.append({"period": period, "market": market, "flag": flag,
                         "sub_channel": sub_channel, "store": store, "range_name": range_name,
                         "net_eur": value, "lines": 3})
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return rows


SHAPES = (
    ("NORTHLAND", 2, "WHOLESALE", "ST-01", "Gamme A", 100.0, 60.0),
    ("NORTHLAND", 2, "WHOLESALE", "ST-01", "Gamme B", 50.0, 40.0),
    ("EASTLAND", 3, "TRAVEL", "ST-02", "Gamme A", 30.0, 50.0),
    ("WESTLAND", 5, "CORPORATE", "ST-03", "Gamme C", 5.0, 5.0),
)


def test_the_line_by_line_reading_says_who_carries_the_bulk_and_how_it_moves():
    detail = G.detail(_bulk_rows(SHAPES), through="2026-08")

    assert detail.usable and detail.window_label == "exercice à date, avril à août"
    assert detail.total == 5 * 185.0
    first = detail.accounts[0]
    assert first.label == "Northland · ST-01 · WHOLESALE" and first.market == "Northland"
    assert first.ytd == 5 * 150.0 and first.ytd_ly == 5 * 100.0 and first.word == "monte"
    assert [line.label for line in detail.accounts] == [
        "Northland · ST-01 · WHOLESALE", "Eastland · ST-02 · TRAVEL", "Westland · ST-03 · CORPORATE"]
    assert detail.accounts[1].word == "se tasse"
    assert [line.label for line in detail.kinds] == ["type 2", "type 3", "type 5"]
    assert [line.label for line in detail.ranges] == ["Gamme A", "Gamme B", "Gamme C"]
    assert detail.concentration == 1
    assert detail.headline.startswith("925 € de vrac lu ligne à ligne ; un compte en fait 80 %")
    assert "Northland · ST-01 · WHOLESALE (monte) à 81 %" in detail.headline
    assert detail.question.startswith("Northland · ST-01 · WHOLESALE : 750 € de vrac à date, +50.0 %")


def test_the_line_by_line_window_stops_where_the_kpi_readings_stop():
    """Deux lectures qui parlent du même exercice à date : le vrac ligne à ligne ne dépasse
    pas le dernier mois que les relevés tiennent, sinon la part et la croissance changent
    de base sans que rien ne le dise."""
    detail = G.detail(_bulk_rows(SHAPES, through="2026-09"), through="2026-08")
    assert detail.through == "2026-08" and detail.total == 5 * 185.0


def test_without_rows_the_detail_says_so_and_the_review_still_stands():
    review = G.build(_rows("LOEP", 1000.0, 0.05) + _rows("Northland", 500.0, 0.08),
                     bulk_rows=[], bulk_note="pas encore lu")
    assert review.usable
    assert not review.detail.usable and review.detail.note == "pas encore lu"
    assert G.detail([]).note == "le vrac ligne à ligne n'est pas encore lu"


def test_the_dossier_finds_the_subjects_that_speak_of_grey_by_their_words():
    from app.domain import issues as I

    register = I.Register()
    grey = register.observe(I.Observation(kind="gap_to_plan", scope="Northland",
                                          seen_at="2026-07-31",
                                          statement="Le vrac répond à la place des clients"))
    grey.reinterpret("Deux commandes de duty free", at="2026-07-31")
    other = register.observe(I.Observation(kind="hero_decline", scope="Eastland",
                                           seen_at="2026-07-31", statement="Héros en recul"))
    closed = register.observe(I.Observation(kind="mix", scope="Westland", seen_at="2026-05-31",
                                            statement="Daigou en baisse"))
    closed.move_to(I.WATCHED)
    closed.close(by="Une dirigeante", reason="Réglé")

    found = G.dossier(register)

    assert [item.issue_id for item in found] == [grey.issue_id, closed.issue_id]
    assert other.issue_id not in [item.issue_id for item in found]
    assert found[0].status_word == "détecté" and found[0].conclusion == "Deux commandes de duty free"
    assert found[1].status_word == "clos"
    assert G.dossier(I.Register()) == []
