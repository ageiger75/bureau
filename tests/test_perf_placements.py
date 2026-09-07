"""Les placements décidés : un marché rangé sous un périmètre par décision, pour un temps.

Ces tests gardent trois choses : le fichier s'applique par-dessus l'annuaire et jamais à sa
place ; une décision expirée ne s'applique plus et le dit ; le mois range le marché sous le
périmètre décidé quel que soit le fichier qui l'avait placé. Tout est inventé.
"""

from __future__ import annotations

from datetime import date

from app.perf import month, owners, placements as P
from tests.test_perf_owners import HEADER, directory_file

TODAY = date(2026, 9, 6)

FILE = ("market,perimeter,until,reason\n"
        "Hong Kong,APAC,2027-03-31,périmètre constant jusqu'à la fin de l'exercice\n"
        "Macau,APAC,2027-03-31,périmètre constant jusqu'à la fin de l'exercice\n"
        "Old Market,EMEA,2026-03-31,une décision de l'exercice précédent\n"
        "Forever,Japan,,sans date de fin\n")


def _read(tmp_path, text=FILE, today=TODAY):
    path = tmp_path / "placements.csv"
    path.write_text(text, encoding="utf-8")
    return P.load(str(path), today)


def test_only_the_rules_still_in_force_apply(tmp_path):
    decided = _read(tmp_path)

    assert sorted(decided.active) == ["Forever", "Hong Kong", "Macau"]
    assert [rule.market for rule in decided.expired] == ["Old Market"]
    assert decided.perimeter_of("Hong Kong") == "APAC"
    assert decided.perimeter_of("Old Market") is None
    assert decided.apply({"Hong Kong": "Greater China", "China": "Greater China"}) == {
        "Hong Kong": "APAC", "China": "Greater China", "Macau": "APAC", "Forever": "Japan"}


def test_the_screen_says_what_is_decided_and_what_has_expired(tmp_path):
    notes = _read(tmp_path).notes

    # Une ligne par décision, pas par marché : les marchés rangés ensemble sont nommés ensemble.
    assert notes[0].startswith("Placement décidé : ")
    assert "Hong Kong" in notes[0] and "→ APAC jusqu'au 2027-03-31 (périmètre constant" in notes[0]
    assert "Macau" in notes[0]  # rangé sous le même périmètre à la même date : la même ligne
    assert any(note.startswith("Placement expiré, plus appliqué : Old Market → EMEA") for note in notes)


def test_a_bad_date_or_a_missing_column_is_named(tmp_path):
    bad = _read(tmp_path, "market,perimeter,until\nX,APAC,demain\n")
    assert bad.is_empty and "illisible" in bad.faults[0]
    missing = _read(tmp_path, "market\nX\n")
    assert missing.is_empty and "colonnes manquantes" in missing.faults[0]
    assert P.load(str(tmp_path / "nulle-part.csv"), TODAY).is_empty


def _directory(tmp_path):
    return owners.load(directory_file(tmp_path, [
        ["Annuaire"],
        HEADER,
        ["Greater China", "Wei", "ZHANG", "Managing Director, China", "Chine + Hong Kong",
         "Patron de BU", "", "Shanghai"],
        ["APAC", "Mei", "LIM", "Managing Director, APAC", "APAC (multi-pays)",
         "Patron de BU", "", "Singapore"],
    ]))


def test_the_directory_moves_the_market_under_the_decided_head(tmp_path):
    """Hong Kong answers through the MD of APAC while the decision holds, and Macau — placed
    nowhere by the file — is placed too. The directory itself is not rewritten."""
    directory = _directory(tmp_path)
    assert directory.entry_for("Hong Kong").bu == "Greater China"

    faults = directory.place({"Hong Kong": "APAC", "Macau": "APAC", "Nowhere": "Mars"})

    assert directory.entry_for("Hong Kong").name == "Mei LIM"
    assert directory.entry_for("Macau").bu == "APAC"
    assert "Hong Kong" in directory.markets_of("APAC")
    assert "Hong Kong" not in directory.markets_of("Greater China")
    assert faults == ["placement de Nowhere : aucun MD pour « Mars » dans l'annuaire"]


def test_the_month_ranks_the_market_under_the_decided_perimeter(tmp_path, monkeypatch):
    decided = _read(tmp_path)
    monkeypatch.setattr(P, "current", lambda: decided)
    directory = _directory(tmp_path)

    placed, _leads = month.place_markets(["Hong Kong", "China", "Macau"], None, directory)

    assert placed == {"Hong Kong": "APAC", "China": "Greater China", "Macau": "APAC"}
