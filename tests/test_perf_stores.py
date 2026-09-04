"""La part loyer du prochain euro, boutique par boutique — la deuxième pièce de B5.

Ces tests gardent la jointure par le code, les trois états d'un bail qui ne se confondent
jamais, et un taux qui ne parle que des boutiques dont le bail est connu, avec sa
couverture à côté. Toutes les valeurs sont inventées.
"""

from __future__ import annotations

from app.perf import stores as S
from tests.test_perf_actuals import MAISON, _workbook


def _register(tmp_path, text):
    path = tmp_path / "stores.csv"
    path.write_text(text, encoding="utf-8")
    return S.load(str(path))


REGISTER = ("store_code,conso_code,store_name,market,channel_code,ownership,"
            "var_rent_percent,opened,closed,status\n"
            "01OCST001,01OCST001,Main Street,NORTHLAND,RET,Owned,8.5,,,Open\n"
            "01OCST002,,Harbour Mall,NORTHLAND,RET,Owned,0.00,,,Open\n"
            "01OCST003,01OCST003,Station,NORTHLAND,RET,Not Owned,,,,Open\n"
            "98TR0001,,Airport,NORTHLAND,TRA,Owned,0.12,,,Open\n")


def _sales_book(tmp_path, rows):
    blank = [None, None]
    sheet = [
        [None, None, "SAL_RE_015 - Sales Data Set"],
        blank + [None] * 7 + ["Published rate", None, "Constant rate", None, "Published rate"],
        blank + [None] * 7 + ["Actual 2027", "Actual 2026", "Actual 2027", "Actual 2026",
                              "Budget 2027"],
        blank + ["Brand", "Entities", "Management Unit - Parent", "Management Unit - Lowest",
                 "Code PCC", "Desc PCC", "Status", "Sales", "Sales", "Sales", "Sales", "Sales"],
        blank + [None] * 7 + ["Actual 2027", "Actual 2026", "Actual 2027", "Actual 2026",
                              "Budget 2027"],
        blank + [None] * 7 + ["Sales"] * 5,
    ] + [blank + list(row) for row in rows]
    return _workbook(tmp_path / "stores-sales.xlsx", {"Sales Data by Store MTD": sheet})


def _row(code, name, market, actual, budget=0.0, status=1.0, brand=MAISON):
    return [brand, "E001 - Northland", "Greater Europe", market, code, name, status,
            999.0, 999.0, actual, actual, budget]


# ----------------------------------------------------------------- le référentiel


def test_the_register_keeps_the_three_states_of_a_lease_apart(tmp_path):
    """Une part écrite, un zéro écrit, rien d'écrit. Le troisième n'est pas un zéro, et
    un lecteur qui les confondrait mettrait toutes les boutiques inconnues en loyer fixe."""
    register = _register(tmp_path, REGISTER)

    assert not register.faults
    assert register.of("01OCST001").state == S.VARIABLE
    assert abs(register.of("01OCST001").var_rent - 0.085) < 1e-9
    assert register.of("01OCST002").state == S.NONE_WRITTEN
    assert register.of("01OCST003").state == S.UNKNOWN
    assert register.of("01OCST003").var_rent is None
    # Une part écrite en fraction se lit comme une part écrite en pour cent.
    assert abs(register.of("98TR0001").var_rent - 0.12) < 1e-9


def test_a_lease_joins_on_either_code(tmp_path):
    register = _register(tmp_path, REGISTER)

    assert register.of("01ocst002").name == "Harbour Mall"
    assert register.of("nowhere") is None


def test_a_missing_register_is_empty_and_a_missing_column_is_named(tmp_path):
    assert S.load(str(tmp_path / "nulle-part.csv")).is_empty
    read = _register(tmp_path, "store_code,market\n01OCST001,NORTHLAND\n")
    assert read.is_empty and "var_rent_percent" in read.faults[0]


def test_two_lines_for_one_code_keep_the_first_and_name_the_second(tmp_path):
    read = _register(tmp_path, "store_code,market,var_rent_percent\n"
                               "01OCST001,NORTHLAND,5\n01OCST001,NORTHLAND,9\n")

    assert abs(read.of("01OCST001").var_rent - 0.05) < 1e-9
    assert read.faults == ["ligne 3 : code 01OCST001 déjà porté par la ligne 2"]


# ------------------------------------------------------------- les ventes par boutique


def test_the_store_sheet_reads_constant_rate_sales_in_euros(tmp_path):
    path = _sales_book(tmp_path, [
        _row("01OCST001", "Main Street", "Northland", 120.0, 100.0),
        _row("99OCST001", "Elsewhere", "Northland", 5.0, brand="Another Maison"),
    ])
    sales = S.load_sales(path)

    assert not sales.faults
    assert [store.code for store in sales.stores] == ["01OCST001"]
    assert sales.stores[0].actual == 120_000.0
    assert sales.stores[0].budget == 100_000.0
    assert sales.stores[0].status == "1"
    assert sales.stores[0].market == "Northland"


def test_a_workbook_without_the_store_sheet_says_so(tmp_path):
    path = _workbook(tmp_path / "other.xlsx", {"Summary": [["x"]]})
    sales = S.load_sales(path)

    assert not sales.usable
    assert sales.faults[0].startswith("aucune feuille 'Sales Data by Store MTD'")


# ------------------------------------------------------------------------ la jointure


def _review(tmp_path):
    path = _sales_book(tmp_path, [
        _row("01OCST001", "Main Street", "Northland", 300.0),
        _row("01OCST002", "Harbour Mall", "Northland", 100.0),
        _row("01OCST003", "Station", "Northland", 200.0),
        _row("01OCST004", "Pop up", "Northland", 50.0),
        _row("02OCST001", "Old Town", "Southland", 80.0),
    ])
    return S.build(S.load_sales(path), _register(tmp_path, REGISTER))


def test_the_rent_share_speaks_only_for_the_leases_it_knows(tmp_path):
    """Trois boutiques sur quatre jointes, deux au bail connu : le taux est pondéré sur ces
    deux-là — 8,5 % sur 300 et 0 sur 100 — et la couverture dit qu'elles font 400 sur 650
    des ventes. Rien n'est étendu aux deux autres."""
    review = _review(tmp_path)
    north = next(market for market in review.markets if market.name == "Northland")

    assert north.count == 4
    assert len(north.joined) == 3
    assert len(north.informed) == 2
    assert abs(north.rent_share - (0.085 * 300 + 0.0 * 100) / 400) < 1e-9
    assert north.rent_share_label == "6.4 %"
    assert abs(north.coverage - 400 / 650) < 1e-9
    assert len(north.none_written) == 1
    assert north.unmatched == ["01OCST004"]


def test_a_market_with_no_known_lease_has_no_rate_not_a_zero(tmp_path):
    review = _review(tmp_path)
    south = next(market for market in review.markets if market.name == "Southland")

    assert south.rent_share is None
    assert south.rent_share_label == "—"
    assert south.coverage_label == "0 %"


def test_markets_are_ordered_by_sales_and_the_whole_is_counted(tmp_path):
    review = _review(tmp_path)

    assert [market.name for market in review.markets] == ["Northland", "Southland"]
    assert review.stores == 5 and review.joined == 3 and review.informed == 2
    assert review.join_label.startswith("5 boutiques au fichier de la CFO · 3 jointes")
    assert review.coverage_label == "55 %"
    assert "part du coût marginal" in review.marginal


def test_without_sales_nothing_is_rendered_and_the_file_is_named():
    review = S.build(None, None)

    assert not review.usable
    assert any("stores-sales.xlsx" in reason for reason in review.absent)


def test_without_a_register_the_stores_are_read_and_the_file_is_named(tmp_path):
    path = _sales_book(tmp_path, [_row("01OCST001", "Main Street", "Northland", 300.0)])
    review = S.build(S.load_sales(path), None)

    assert review.usable
    assert review.joined == 0
    assert any("stores.csv" in reason for reason in review.absent)
