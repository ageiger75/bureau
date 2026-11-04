"""La balance comptable comme mois clos provisoire. Ces tests gardent la somme des mois de
l'exercice par marché et canal, le plan posé en face sur les mêmes entités seulement, la
règle « provisoire jusqu'au septième jour ouvré », les absents nommés avec leur plan, et la
vérification au centime contre l'extrait de référence. Tout est inventé."""

from __future__ import annotations

import datetime

from app.perf import balance as B
from app.perf.actuals import SHIPPED, SOLD
from app.perf.analytics import format_eur

MONTHS = ["2026-%02d" % m for m in range(4, 11)]


class _Line:
    def __init__(self, market, period, segment, budget, last_year, entity):
        self.market, self.period, self.segment = market, period, segment
        self.budget, self.last_year, self.entity = budget, last_year, entity


class _Budget:
    def __init__(self, lines):
        self.lines = lines


def _plan():
    lines = []
    for period in MONTHS + ["2026-11"]:
        lines.append(_Line("Northland", period, "RET - Retail", 100.0, 90.0, "M_901"))
        lines.append(_Line("Northland", period, "WEBP - Web Partners", 20.0, 15.0, "M_901"))
        lines.append(_Line("Travel retail North", period, "TRA - Travel retail", 50.0, 40.0, "M_901_TRA"))
        lines.append(_Line("Southland", period, "RET - Retail", 30.0, 25.0, "M_903"))
        # Une entité du plan que la balance range sous la société mère du même marché.
        lines.append(_Line("Northland", period, "RET - Retail", 10.0, 5.0, "M_905"))
    return _Budget(lines)


def _rows(months=MONTHS):
    rows = []
    for month in months:
        for entity, channel, amount in (("M_901", "RET", 110.0), ("M_901", "WEBP", 18.0),
                                        ("M_901", "TRA", 55.0), ("M_909", "RET", 5.0)):
            rows.append({"month": month, "entity": entity, "channel": channel, "currency": "EUR",
                         "amount_local": amount, "amount_eur": amount,
                         "loaded_at": "2026-11-04 01:26:54"})
    return rows


def test_the_months_of_the_year_are_summed_by_market_and_channel_against_the_plan_of_the_same_entities():
    reading = B.build(_rows(), _plan(), "2026-10", today=datetime.date(2026, 11, 4))

    assert reading.usable and reading.period == "2026-10" and reading.months == MONTHS
    by_key = {(line.market, line.channel): line for line in reading.lines}
    north = by_key[("Northland", "retail")]
    # Le plan du marché compte toutes ses entités, y compris celle que la balance range
    # sous la société mère : elle n'est pas absente, elle est dedans.
    assert (north.actual, north.budget, north.last_year, north.basis) == (770.0, 770.0, 665.0, SOLD)
    web = by_key[("Northland", "webp")]
    assert (web.actual, web.budget, web.last_year, web.basis) == (126.0, 140.0, 105.0, SHIPPED)
    # La pseudo-entité du plan rejoint l'entité de la balance par le canal.
    travel = by_key[("Travel retail North", "tra")]
    assert (travel.actual, travel.budget, travel.last_year) == (385.0, 350.0, 280.0)
    # Une entité que le plan ne nomme pas reste sous son code, sans plan en face, et est dite.
    assert by_key[("M_909", "retail")].actual == 35.0 and by_key[("M_909", "retail")].budget == 0.0
    assert reading.unplaced == ["M_909"]
    # L'entité du plan absente de la balance n'entre pas au plan : nommée, avec son plan.
    assert reading.absent == [("Southland", 210.0)]
    totals = reading.totals()
    assert totals["actual"] == 770.0 + 126.0 + 385.0 + 35.0 and totals["budget"] == 1260.0
    assert reading.loaded_at == "2026-11-04 01:26:54" and reading.source_label == "balance comptable"


def test_the_month_is_provisional_until_the_seventh_business_day_and_the_caveat_says_it():
    early = B.build(_rows(), _plan(), "2026-10", today=datetime.date(2026, 11, 4))
    assert early.business_days == 3 and early.provisional
    assert early.status == "provisoire, 3 jours ouvrés après la fin du mois"
    assert early.caveat.startswith("Mois clos lu dans la balance comptable, provisoire, 3 jours ouvrés")
    assert "rechargée le 2026-11-04 01:26:54" in early.caveat
    assert "absents de la balance : Southland (%s au plan)" % format_eur(210.0) in early.caveat
    assert "sous leur code : M_909" in early.caveat

    frozen = B.build(_rows(), _plan(), "2026-10", today=datetime.date(2026, 11, 11))
    assert frozen.business_days == 8 and not frozen.provisional
    assert frozen.status.startswith("tenue pour figée, 8 jours ouvrés")
    assert B.business_days_after("2026-10", datetime.date(2026, 11, 1)) == 0
    assert B.business_days_after("2026-09", datetime.date(2026, 10, 8)) == 6


def test_without_the_month_or_with_a_hole_the_reading_says_so_and_is_not_usable():
    without = B.build(_rows(MONTHS[:-1]), _plan(), "2026-10", today=datetime.date(2026, 11, 4))
    assert not without.usable and without.faults == ["la balance ne porte pas encore octobre"]
    hole = B.build(_rows([m for m in MONTHS if m != "2026-07"]), _plan(), "2026-10",
                   today=datetime.date(2026, 11, 4))
    assert not hole.usable and "mois sans ligne dans la balance : juillet" in hole.faults
    assert B.months_through("2026-10") == MONTHS
    assert B.months_through("2027-02") == MONTHS + ["2026-11", "2026-12", "2027-01", "2027-02"]
    assert B.entity_prefix("M_901_TRA") == "M_901" and B.entity_prefix("m_901") == "M_901"


def test_the_check_against_the_reference_is_at_the_cent_month_by_month():
    rows = _rows()
    reference = [dict(row) for row in rows if row["month"] in ("2026-09", "2026-10")]
    # Octobre a bougé depuis l'extrait : une entité en plus côté cockpit, un montant qui diffère.
    rows.append({"month": "2026-10", "entity": "M_904", "channel": "DIS", "currency": "EUR",
                 "amount_local": 7.0, "amount_eur": 7.0, "loaded_at": ""})
    for item in reference:
        if item["month"] == "2026-10" and item["entity"] == "M_901" and item["channel"] == "RET":
            item["amount_eur"] = 109.99
    check = B.compare_reference(rows, reference)

    # Seuls les mois de la référence se comparent : le cockpit en lit d'autres, sans juge.
    assert check.months == ["2026-09", "2026-10"]
    assert check.identical("2026-09") and check.sentence("2026-09") == "septembre : identique au centime sur 4 couples"
    assert not check.identical("2026-10")
    assert check.sentence("2026-10") == ("octobre : 3 couples identiques, 1 qui diffèrent, 1 que le "
                                         "cockpit seul lit, 0 que la référence seule porte")
    assert check.differing == [("2026-10", "M_901", "RET", 110.0, 109.99)]
    assert check.only_here == [("2026-10", "M_904", "DIS", 7.0)]
    # Un mois que la référence ne porte pas n'est ni identique ni faux : rien à comparer.
    assert not check.identical("2026-04") and not any(item[0] == "2026-04" for item in check.only_here)


def test_the_command_reads_the_balance_and_checks_the_reference(tmp_path, monkeypatch, capsys):
    import csv

    from app import cli
    from app.perf import mock

    assert cli.cmd_balance([]) == 2

    monkeypatch.setattr(mock, "balance_rows", lambda: _rows())
    path = tmp_path / "reference.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["month", "entity", "channel", "currency",
                                                    "amount_local", "amount_eur"])
        writer.writeheader()
        for row in _rows(["2026-09"]):
            writer.writerow({key: row[key] for key in writer.fieldnames})
    assert cli.cmd_balance(["--check", str(path)]) == 0
    out = capsys.readouterr().out
    assert "septembre : identique au centime sur 4 couples" in out
