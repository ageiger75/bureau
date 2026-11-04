"""Les distributeurs déclarés par le lecteur : un centre de profit que l'entrepôt type comme
une filiale et que le cockpit doit compter dans le sell-in. Tout est inventé."""

from __future__ import annotations

from app.perf import distributors as D


def test_the_file_declares_profit_centres_and_names_them(tmp_path):
    path = tmp_path / "distributors.csv"
    path.write_text("profit_centre,name,reason\n"
                    "pc-north-1,Northland distributor,un distributeur\n"
                    "PC-SOUTH-1,,sans nom\n"
                    ",Nobody,sans code\n"
                    "PC-NORTH-1,Twice,doublon\n", encoding="utf-8")
    declared = D.load(path)

    assert declared.codes == {"PC-NORTH-1", "PC-SOUTH-1"}
    assert declared.name_of("pc-north-1") == "Northland distributor"
    assert declared.name_of("PC-SOUTH-1") == "PC-SOUTH-1" and declared.name_of("PC-NOWHERE") == "PC-NOWHERE"
    assert declared.faults == ["ligne 4 sans centre de profit, ignorée",
                               "ligne 5 : centre de profit PC-NORTH-1 déjà déclaré, ignorée"]


def test_without_the_file_nothing_is_declared(tmp_path):
    assert D.current().is_empty and D.current().faults == []
    bad = tmp_path / "bad.csv"
    bad.write_text("code,name\nx,y\n", encoding="utf-8")
    assert "colonnes manquantes" in D.load(bad).faults[0]
