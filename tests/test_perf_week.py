"""Une lecture, et le compte rendu qu'elle rend plutôt qu'imprime.

Le passage qui lit les sources vivait dans la ligne de commande et affichait au fur et à
mesure ; l'écran ne pouvait donc pas s'en servir sans le réécrire. Ces tests gardent la
séparation et, surtout, la seule propriété du compte rendu qui puisse mentir : une source
absente ne doit jamais se lire comme une source vide.
"""

from __future__ import annotations

from app.perf import week as week_module


def test_a_source_that_was_not_read_is_not_a_source_that_was_empty():
    """`None` veut dire « je n'ai pas regardé », `0` veut dire « rien à signaler ». Les
    confondre ferait lire une absence comme un feu vert — le défaut que ce cockpit passe
    son temps à fermer partout ailleurs, et qui se serait glissé dans le compte rendu qui
    sert à le détecter."""
    silent = week_module.Sources()
    looked = week_module.Sources(units=0, partners=0, owners_given=0)

    assert silent.missing == ["écran de performance", "partenaires", "annuaire"]
    assert looked.missing == []


def test_the_directory_being_absent_is_named_rather_than_counted_as_zero():
    """Sans annuaire, « personne n'en répond » s'applique à tous les sujets à la fois et
    cesse d'ordonner. Zéro rattachement parce qu'il n'y a rien à rattacher et zéro parce
    qu'aucun annuaire n'a été lu appellent deux phrases différentes à l'écran."""
    assert "annuaire" in week_module.Sources(units=3, partners=1).missing
    assert "annuaire" not in week_module.Sources(units=3, partners=1,
                                                 owners_given=0).missing


def test_a_scan_that_fired_nothing_does_not_ask_for_a_write():
    """Écrire un registre inchangé réattribuerait des horodatages sans qu'aucun fait ne
    l'ait justifié, et une référence citée dans un compte rendu doit rester stable."""
    assert not week_module.Scan(week_module.Sources()).changed
    assert week_module.Scan(week_module.Sources(), fired=2).changed


def test_the_screen_may_hand_over_the_dataset_it_has_already_read(db_session, monkeypatch):
    """L'écran a déjà chargé les chiffres pour le reste de la page. Les relire coûterait
    une seconde requête à l'entrepôt — et deux lectures d'un même écran ne porteraient pas
    forcément la même heure, donc pas forcément les mêmes chiffres."""
    called = []

    class Refused:
        def dataset(self):
            called.append(True)
            raise AssertionError("la source ne doit pas être relue")

    monkeypatch.setattr("app.perf.source.current_source", lambda: Refused())

    class Dataset:
        units = ()
        period = "2026-08"

    result, scan = week_module.read(db_session, "2026-09-01", dataset=Dataset())

    assert called == []
    assert scan.sources.period == "2026-08"
    # Aucune unité : la source a été regardée et n'a rien donné, ce qui n'est pas la même
    # chose que de ne pas l'avoir ouverte.
    assert scan.sources.units is None
    assert result.attention == [] and result.watch == []


def test_a_reading_that_only_looks_leaves_no_trace(db_session, monkeypatch):
    """Une surface qui regarde n'écrit pas. Le paramètre est explicite dans les deux sens :
    alimenter le registre est un geste, pas un effet de bord de l'affichage."""
    written = []
    monkeypatch.setattr("app.perf.memory.save",
                        lambda session, register: written.append(register))

    class Dataset:
        units = ()
        period = "2026-08"

    result, scan = week_module.read(db_session, "2026-09-01", dataset=Dataset(),
                                    save=False)

    assert written == []
    assert result.considered == 0 and not scan.changed


def test_a_reading_that_found_nothing_does_not_write_either(db_session, monkeypatch):
    """Écrire un registre qu'aucun fait n'a fait bouger réattribuerait des horodatages
    sans raison, et une référence citée dans un compte rendu doit désigner le même sujet
    la semaine suivante."""
    written = []
    monkeypatch.setattr("app.perf.memory.save",
                        lambda session, register: written.append(register))

    class Dataset:
        units = ()
        period = "2026-08"

    week_module.read(db_session, "2026-09-01", dataset=Dataset(), save=True)

    assert written == []
