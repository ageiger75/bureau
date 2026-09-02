"""Les trois classements faux, et les règles qui les rendent impossibles.

Chaque test garde une leçon payée : le classement qui rendait les plus gros magasins du
monde, celui qui rendait les plus petits comptes, celui qui rendait un seul marché. Aucun
n'était un bug — les trois étaient un critère unique appliqué correctement, ce qui est
exactement ce qui les rendait crédibles.

Chiffres inventés, taxonomie réelle.
"""

from __future__ import annotations

import io

import pytest

from app.perf import distribution as D


HEADER = ("base,window,market,entity_id,entity_name,channel,is_internal,revenue_12m,"
          "hero_share,hero_share_norm,depth_index,depth_index_norm,"
          "free_goods_value,norm_level,note\n")


def _write(tmp_path, body, header=HEADER):
    path = tmp_path / "distribution_signals.csv"
    with io.open(str(path), "w", encoding="utf-8", newline="") as handle:
        handle.write(header + body)
    return str(path)


def _row(base="sell_out", market="Northland", eid="S1", name="Store One",
         channel="STORE", internal="", revenue=1000.0, hero=0.5, hero_norm=0.4,
         depth=0.3, depth_norm=0.2, value=100.0, level="market_channel", note=""):
    def cell(x):
        return "" if x is None else ("%s" % x)
    return ",".join([base, "2025-07..2026-06", market, eid, name, channel, internal,
                     cell(revenue), cell(hero), cell(hero_norm), cell(depth),
                     cell(depth_norm), cell(value), level, note]) + "\n"


# --------------------------------------------------------------- découverte


def test_the_signals_are_discovered_and_never_written_down(tmp_path):
    """La liste est passée de six à sept puis à huit en trois jours. Un lecteur qui les
    nommait aurait cassé au neuvième — ou pire, se serait tu en n'en lisant que huit."""
    read = D.load(_write(tmp_path, _row()))

    assert read.usable
    assert read.signals == ["depth_index", "hero_share"]


def test_a_ninth_signal_is_read_without_touching_the_code(tmp_path):
    header = HEADER.replace("free_goods_value,",
                            "width_index,width_index_norm,free_goods_value,")
    body = _row().replace(",100.0,market_channel", ",0.9,0.4,100.0,market_channel")
    read = D.load(_write(tmp_path, body, header=header))

    assert read.usable
    assert "width_index" in read.signals
    assert read.entities[0].fired() == ["depth_index", "hero_share", "width_index"]


def test_a_file_without_a_single_paired_column_is_refused(tmp_path):
    read = D.load(_write(tmp_path, "sell_out,Northland,S1\n",
                         header="base,market,entity_id\n"))

    assert not read.usable
    assert "Aucun signal" in read.faults[0]


# ----------------------------------------------------------- deux conditions


def test_a_big_entity_that_is_normal_never_enters_the_ranking(tmp_path):
    """Le troisième classement faux : ordonner sur la valeur seule rend le plus gros
    marché, qu'il soit anormal ou non. La matérialité vient après l'anormalité, jamais
    avant."""
    path = _write(tmp_path,
                  _row(eid="HUGE", hero=0.2, hero_norm=0.4, depth=0.1, depth_norm=0.2,
                       value=9_000_000.0)
                  + _row(eid="ODD", hero=0.9, hero_norm=0.4, depth=0.8, depth_norm=0.2,
                         value=1_000.0))
    read = D.load(path)

    assert [item.entity_id for item in read.abnormal(D.SELL_OUT)] == ["ODD"]
    assert [item.entity_id
            for item in read.by_exposure(D.SELL_OUT, "free_goods_value")] == ["ODD"]


def test_among_the_abnormal_the_ranking_is_in_euros(tmp_path):
    path = _write(tmp_path,
                  _row(eid="SMALL", hero=0.9, hero_norm=0.4, value=1_000.0)
                  + _row(eid="LARGE", hero=0.6, hero_norm=0.4, value=800_000.0))
    read = D.load(path)

    assert [item.entity_id
            for item in read.by_exposure(D.SELL_OUT, "free_goods_value")] == ["LARGE",
                                                                              "SMALL"]


def test_the_two_rankings_do_not_overlap_and_both_are_needed(tmp_path):
    """L'une trouve où est l'argent, l'autre où est l'anomalie. Une petite entité très
    déviante n'apparaîtra jamais dans la première, et c'est pour elle que la seconde
    existe."""
    header = HEADER.replace("depth_index,depth_index_norm,",
                            "depth_index,depth_index_norm,a,a_norm,b,b_norm,c,c_norm,")
    def wide(eid, hero, depth, extra, value):
        return ("sell_out,W,Northland,%s,%s,STORE,,1000,%s,0.4,%s,0.2,%s,0.2,%s,0.2,"
                "%s,0.2,%s,market_channel,\n"
                % (eid, eid, hero, depth, extra, extra, extra, value))
    path = _write(tmp_path,
                  wide("HUGE", 0.45, 0.25, 0.25, 900_000.0)
                  + wide("TINY", 0.95, 0.90, 0.90, 900.0),
                  header=header)
    read = D.load(path)

    assert [i.entity_id for i in read.by_exposure(D.SELL_OUT, "free_goods_value")][0] == "HUGE"
    assert [i.entity_id for i in read.by_distance(D.SELL_OUT)][0] == "TINY"


# ------------------------------------------------------- dénominateur variable


def test_a_share_over_two_signals_does_not_outrank_a_share_over_seven(tmp_path):
    """Six des vingt premières places étaient occupées par des entités dont deux signaux
    seulement étaient calculables : elles affichaient 100 % en en déclenchant deux. Ce
    n'est pas un signal, c'est un petit dénominateur."""
    path = _write(tmp_path, _row(eid="THIN", depth=None, depth_norm=None))
    read = D.load(path)
    thin = read.entities[0]

    assert thin.fired() == ["hero_share"]
    assert thin.fired_share == 1.0
    assert not thin.is_rankable(read.floor)
    assert read.by_distance(D.SELL_OUT) == []
    assert [item.entity_id for item in read.unrankable(D.SELL_OUT)] == ["THIN"]


def test_a_value_without_its_norm_is_not_a_signal_at_rest(tmp_path):
    """Une valeur sans seuil ne se juge pas, et un seuil sans valeur ne juge rien. Compter
    l'un des deux ferait passer une mesure incomplète pour un signal au repos."""
    path = _write(tmp_path, _row(hero=0.9, hero_norm=None))
    entity = D.load(path).entities[0]

    assert "hero_share" not in entity.computable()
    assert entity.fired() == ["depth_index"]


def test_nothing_computable_gives_no_share_rather_than_zero(tmp_path):
    """Une entité qu'on n'a pas su mesurer n'est pas une entité sage."""
    path = _write(tmp_path, _row(hero=None, hero_norm=None,
                                 depth=None, depth_norm=None))
    entity = D.load(path).entities[0]

    assert entity.computable() == []
    assert entity.fired_share is None


# ------------------------------------------------------------------ internes


def test_an_internal_account_stays_in_the_file_and_out_of_the_ranking(tmp_path):
    """Un compte d'échantillons et de testeurs a par fonction un volume gratuit énorme.
    Il remonterait chaque mois sans que personne ait rien à en faire."""
    path = _write(tmp_path,
                  _row(eid="INTERNAL", internal="true", hero=0.99, value=500_000.0)
                  + _row(eid="REAL", hero=0.6, value=1_000.0))
    read = D.load(path)

    assert len(read) == 2
    assert [item.entity_id for item in read.internal(D.SELL_OUT)] == ["INTERNAL"]
    assert [item.entity_id for item in read.abnormal(D.SELL_OUT)] == ["REAL"]


# ---------------------------------------------------------------- couverture


def test_a_total_says_how_much_of_the_file_it_covers(tmp_path):
    """Un cinquième des lignes n'a pas de valeur calculable. Le total qu'on en tire n'est
    pas faux, il est incomplet — et la différence disparaît dès qu'on l'affiche sans le
    dire. Rendue comme un couple : « deux sur trois » se conteste, « 66,7 % » s'accepte."""
    path = _write(tmp_path,
                  _row(eid="A", value=100.0) + _row(eid="B", value=200.0)
                  + _row(eid="C", value=None))
    read = D.load(path)

    assert read.total(D.SELL_OUT, "free_goods_value") == 300.0
    assert read.coverage(D.SELL_OUT, "free_goods_value") == (2, 3)


def test_the_amount_per_market_is_what_makes_a_world_average_readable(tmp_path):
    """Onze pour cent en moyenne ne décrit aucun marché réel quand un seul en porte quatre
    cinquièmes."""
    path = _write(tmp_path,
                  _row(eid="A", market="Eastland", value=100.0)
                  + _row(eid="B", market="Northland", value=900.0)
                  + _row(eid="C", market="Northland", value=50.0))
    read = D.load(path)

    assert read.by_market(D.SELL_OUT, "free_goods_value") == [
        ("Northland", 950.0, 2, 2), ("Eastland", 100.0, 1, 1)]


# --------------------------------------------------------------- deux bases


def test_a_total_without_a_named_base_cannot_be_asked_for(tmp_path):
    read = D.load(_write(tmp_path, _row()))

    with pytest.raises(ValueError):
        read.of_base("les deux")


def test_the_same_entity_in_two_windows_is_two_rows(tmp_path):
    """Une part se lit dans le temps : la même entité sur deux fenêtres n'est pas un
    doublon, c'est une trajectoire."""
    path = _write(tmp_path, _row(eid="S1") + _row(eid="S1").replace("2025-07..2026-06",
                                                                    "2024-07..2025-06"))
    read = D.load(path)

    assert read.usable
    assert len(read) == 2


def test_the_same_entity_twice_in_one_window_is_a_fault(tmp_path):
    path = _write(tmp_path, _row(eid="S1") + _row(eid="S1"))
    read = D.load(path)

    assert not read.usable
    assert "figure déjà" in read.faults[0]


def test_an_absent_file_says_so_instead_of_reading_as_empty(tmp_path):
    read = D.load(str(tmp_path / "nulle-part.csv"))

    assert not read.usable
    assert "absent" in read.faults[0]


def test_the_floor_follows_the_file_and_is_never_written_down(tmp_path):
    """Le plancher a d'abord été écrit à cinq, pendant que la source portait huit signaux.
    Sur un fichier qui n'en porte que quatre, plus rien n'était classable et le lecteur
    rendait une liste vide sans rien dire. Un seuil absolu ne survit pas au fichier qui
    change de forme, et celui-ci en a changé trois fois en trois jours."""
    read = D.load(_write(tmp_path, _row()))

    assert read.signals == ["depth_index", "hero_share"]
    assert read.floor == D.MIN_COMPUTABLE == 2
    assert read.entities[0].is_rankable(read.floor)
    assert read.by_distance(D.SELL_OUT) != []


def test_the_floor_rounds_up_because_at_least_means_at_least(tmp_path):
    """Un arrondi au plus proche rendrait deux sur quatre — la moitié — pour une règle qui
    en demande trois cinquièmes."""
    header = HEADER.replace("free_goods_value,",
                            "w,w_norm,x,x_norm,free_goods_value,")
    body = _row().replace(",100.0,market_channel", ",0.9,0.4,0.9,0.4,100.0,market_channel")
    read = D.load(_write(tmp_path, body, header=header))

    assert len(read.signals) == 4
    assert read.floor == 3


def test_on_eight_signals_the_floor_is_the_five_that_had_been_hardcoded(tmp_path):
    header = ("base,window,market,entity_id,entity_name,channel,is_internal,revenue_12m,"
              + ",".join("s%d,s%d_norm" % (n, n) for n in range(8))
              + ",free_goods_value,norm_level,note\n")
    body = ("sell_out,W,Northland,S1,Store,STORE,,1000,"
            + ",".join("0.5,0.4" for _ in range(8)) + ",100,market_channel,\n")
    read = D.load(_write(tmp_path, body, header=header))

    assert len(read.signals) == 8
    assert read.floor == 5


def test_a_market_nobody_measured_is_not_a_market_at_zero(tmp_path):
    """Sept marchés de la vraie source sont couverts à zéro pour cent, dont un qui pèse
    plus de vingt millions. Leur zéro euro se lit comme « rien à signaler » alors qu'il
    veut dire « je n'ai pas regardé » — c'est l'absence qui ressemble à un feu vert, et
    elle a déjà été payée quatre fois dans ce dépôt."""
    path = _write(tmp_path,
                  _row(eid="A", market="Mesuré", value=100.0)
                  + _row(eid="B", market="Mesuré", value=200.0)
                  + _row(eid="C", market="Aveugle", value=None)
                  + _row(eid="D", market="Aveugle", value=None))
    read = D.load(path)
    rows = {name: (amount, valued, total)
            for name, amount, valued, total in read.by_market(D.SELL_OUT,
                                                              "free_goods_value")}

    assert rows["Mesuré"] == (300.0, 2, 2)
    assert rows["Aveugle"] == (0.0, 0, 2)
    assert D.Distribution.measured(2, 2)
    assert not D.Distribution.measured(0, 2)
    # Un marché couvert à moitié passe : c'est un plancher, pas une cécité.
    assert D.Distribution.measured(1, 2)


def test_rows_without_an_identifier_are_kept_and_counted_once(tmp_path):
    """Soixante lignes de la vraie source portaient « N/A », et la règle de doublon les a
    toutes rejetées comme des répétitions les unes des autres — en imprimant soixante
    avertissements identiques qui noyaient la seule ligne portant une information. Le dépôt
    connaissait déjà ce défaut sur cette valeur exacte, et le lecteur y est retombé."""
    path = _write(tmp_path,
                  _row(eid="N/A", market="Northland")
                  + _row(eid="N/A", market="Eastland")
                  + _row(eid="N/A", market="Westland"))
    read = D.load(path)

    assert len(read) == 3
    assert len(read.faults) == 1
    assert "3 ligne(s) sans identifiant" in read.faults[0]


def test_a_real_duplicate_is_still_refused(tmp_path):
    """La tolérance porte sur l'absence d'identifiant, pas sur la répétition d'un vrai."""
    path = _write(tmp_path, _row(eid="S1") + _row(eid="S1"))
    read = D.load(path)

    assert len(read) == 1
    assert "figure déjà" in read.faults[0]


# ------------------------------------------------------------------- périmètres


def test_an_outlet_is_measured_against_outlets_and_never_against_retail(tmp_path):
    """Un outlet vend des héros en profondeur à des acheteurs par lots — c'est sa
    définition, pas une anomalie. Deux outlets américains et un anglais occupaient le
    classement pendant que la maison les tenait pour sains, et c'est le groupe témoin qui
    l'a montré. Ils sont séparés, jamais retirés : ôter des lignes pour faire taire un
    signal est la façon la plus rapide de rendre un détecteur inutile."""
    path = _write(tmp_path,
                  _row(eid="SHOP", channel="STREET STORE", hero=0.9, value=1000.0)
                  + _row(eid="OUT", channel="OUTLET", hero=0.9, value=5000.0)
                  + _row(eid="FACTORY", channel="FACTORY OUTLET", hero=0.9, value=2000.0))
    read = D.load(path)

    assert [i.entity_id for i in read.of_base(D.SELL_OUT, D.RETAIL)] == ["SHOP"]
    assert [i.entity_id
            for i in read.of_base(D.SELL_OUT, D.OUTLET)] == ["OUT", "FACTORY"]
    assert len(read.of_base(D.SELL_OUT, D.ALL)) == 3
    # Reconnu sur le mot et non sur l'égalité : « FACTORY OUTLET » serait resté dans le
    # retail avec une comparaison stricte, et sans rien dire.
    assert read.of_base(D.SELL_OUT, D.OUTLET)[1].is_outlet


def test_the_perimeter_is_asked_for_and_never_assumed(tmp_path):
    """Changer un défaut change silencieusement ce que tous les appelants existants
    demandaient."""
    read = D.load(_write(tmp_path, _row(channel="OUTLET")))

    assert len(read.of_base(D.SELL_OUT)) == 1
    with pytest.raises(ValueError):
        read.of_base(D.SELL_OUT, "boutique")


def test_the_euro_floor_is_not_eaten_by_the_signal_floor(tmp_path):
    """Deux planchers, et ils ne mesurent pas la même chose : l'un compte des signaux,
    l'autre des euros. La première version les appelait tous les deux `floor` et le second
    écrasait le premier dès la première ligne — le plancher de matérialité était donc
    inopérant, ce qui a laissé remonter une entité à deux mille fois ses seuils pour deux
    cent trente-six euros."""
    path = _write(tmp_path,
                  _row(eid="TINY", hero=0.99, depth=0.99, value=236.0)
                  + _row(eid="REAL", hero=0.6, depth=0.3, value=90_000.0))
    read = D.load(path)

    assert [i.entity_id for i in read.by_distance(D.SELL_OUT)] == ["TINY", "REAL"]
    assert [i.entity_id
            for i in read.by_distance(D.SELL_OUT, "free_goods_value", 25_000.0)] == ["REAL"]


def test_a_single_extreme_signal_is_not_a_behaviour(tmp_path):
    """Le magasin historique de la maison sortait premier mondial à quarante fois ses
    seuils, sur un seul signal. Or une part est bornée par un : quand sa norme vaut deux et
    demi pour cent, le ratio maximal atteignable est quarante sans que la valeur ait rien
    d'extraordinaire. Un ratio sur une grandeur bornée ne se compare pas à un ratio sur une
    grandeur qui ne l'est pas — et la distance étant une moyenne sur les signaux franchis,
    avec un seul elle **est** ce signal."""
    path = _write(tmp_path,
                  _row(eid="SPIKE", hero=1.0, hero_norm=0.025, depth=0.1, depth_norm=0.2,
                       value=100_000.0)
                  + _row(eid="BROAD", hero=1.2, hero_norm=0.4, depth=0.6, depth_norm=0.2,
                         value=100_000.0))
    read = D.load(path)

    assert read.entities[0].distance() == 40.0
    # Sortie du classement, et rendue à part : séparer plutôt que taire.
    assert [i.entity_id for i in read.by_distance(D.SELL_OUT)] == ["BROAD"]
    assert [i.entity_id for i in read.single_signal(D.SELL_OUT)] == ["SPIKE"]


def test_a_column_the_reader_ignores_is_named_on_screen(tmp_path, capsys):
    """Dix colonnes de rang sont arrivées dans le fichier un jour, et l'écran n'a rien dit.
    Un signal a besoin de sa colonne de norme pour exister — c'est la règle, elle est
    bonne — mais une colonne reçue et non lue doit se voir, sinon celui qui l'a produite
    croit qu'elle sert."""
    from app import cli

    path = tmp_path / "signals.csv"
    path.write_text(
        "base,market,entity_id,entity_name,channel,hero_share,hero_share_norm,"
        "depth,depth_norm,hero_share_rank\n"
        "sell_out,Northland,E1,Boutique,retail,0.4,0.2,3.0,1.5,91.0\n",
        encoding="utf-8")

    cli.cmd_distribution([str(path)])

    printed = capsys.readouterr().out
    assert "hero_share_rank" in printed
    assert "Colonnes non lues" in printed
