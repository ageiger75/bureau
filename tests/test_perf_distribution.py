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

    assert read.by_market(D.SELL_OUT, "free_goods_value") == [("Northland", 950.0),
                                                              ("Eastland", 100.0)]


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
