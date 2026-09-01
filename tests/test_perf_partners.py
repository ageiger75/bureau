"""Les partenaires, et les additions qu'il ne faut jamais faire.

Le fichier réel a coûté trois retournements avant d'exister : le nom du partenaire ne se
lit pas dans le code du centre de profit, le libellé qu'on croyait absent était à une
jointure, et deux codes annonçant une plateforme sont facturés à des opérateurs tiers.
Chaque test ci-dessous garde l'une des conclusions de ce parcours.

Chiffres inventés, taxonomie réelle — comme partout dans cette suite.
"""

from __future__ import annotations

import io

import pytest

from app.perf import partners as P


HEADER = ("base,profit_centre,customer_id,partner,legal_name,country_field,country_is,"
          "months_seen,revenue_12m,gross_12m,net_12m,note\n")


def _write(tmp_path, body, header=HEADER):
    path = tmp_path / "partners.csv"
    with io.open(str(path), "w", encoding="utf-8", newline="") as handle:
        handle.write(header + body)
    return str(path)


# ------------------------------------------------------------------------- deux bases


def test_a_total_without_a_named_base_cannot_be_asked_for():
    """Le mélange que ce module existe pour empêcher n'est pas signalé, il est
    impossible : `total()` n'a pas de valeur par défaut, et une base inconnue est refusée
    plutôt que rangée dans l'une des deux."""
    read = P.Partners([], [], "")

    with pytest.raises(ValueError) as refused:
        read.total("les deux")

    assert P.SELL_IN in str(refused.value)


def test_each_base_keeps_its_own_total(tmp_path):
    path = _write(tmp_path,
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,12,900,1500,900,\n"
                  "sell_out,37OCMP001,,Northmart,Northmart Store,NORTHLAND,marche,12,400,600,400,\n")
    read = P.load(path)

    assert read.usable
    assert read.total(P.SELL_IN) == 900.0
    assert read.total(P.SELL_OUT) == 400.0
    # Aucune propriété ne rend la somme des deux : il n'y a rien à appeler par mégarde.
    assert not hasattr(read, "grand_total")


def test_a_name_living_on_both_sides_is_named_and_never_summed(tmp_path):
    """La plateforme qui nous achète et la boutique qu'on exploite chez elle portent le
    même nom sans être le même métier. Le module les signale au lieu de les réunir."""
    path = _write(tmp_path,
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,12,900,,,\n"
                  "sell_out,37OCMP001,,Northmart,Northmart Store,NORTHLAND,marche,12,400,,,\n"
                  "sell_in,999BBBWP,SAP-2,Eastshop,Eastshop SA,SPAIN,facturation,12,100,,,\n")
    read = P.load(path)

    assert read.named_in_both_bases() == ["Northmart"]


def test_a_third_base_is_refused_and_makes_the_file_unusable(tmp_path):
    """Une base inconnue rangée d'office dans l'une des deux ferait entrer de l'expédié
    dans un total de vendu, sans que rien ne le dise."""
    path = _write(tmp_path,
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,12,900,,,\n"
                  "b2bt,999CCCWP,SAP-3,Hospitality,Hospitality SA,FRANCE,facturation,12,50,,,\n")
    read = P.load(path)

    assert not read.usable
    assert "b2bt" in read.faults[0]


# --------------------------------------------------------------------------- sans nom


def test_a_line_without_a_brand_keeps_its_place_and_its_amount(tmp_path):
    """Deux lignes du fichier réel pèsent à elles seules plus que la moitié des
    partenaires nommés. Les cacher rendrait un total faux ; leur inventer un nom rendrait
    un total juste et une conversation fausse."""
    path = _write(tmp_path,
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,12,900,,,\n"
                  "sell_in,999GLBWP,SAP-9,,Operator Holdings Ltd,HONG KONG,facturation,12,700,,,"
                  "centre intitulé pour une plateforme mais facturé à un opérateur\n")
    read = P.load(path)

    assert read.usable
    assert read.total(P.SELL_IN) == 1600.0
    assert read.unnamed_total(P.SELL_IN) == 700.0
    orphan = read.unnamed(P.SELL_IN)[0]
    assert orphan.partner == ""
    # Affichable sans être nommé : la raison sociale à défaut de marque, le code à défaut
    # de raison sociale, et jamais une marque déduite de l'intitulé du centre.
    assert orphan.label == "Operator Holdings Ltd"
    assert orphan.note.startswith("centre intitulé")


def test_unnamed_lines_are_not_grouped_together(tmp_path):
    """Elles n'ont rien en commun qu'une absence. Les réunir sous « autres » inventerait
    un partenaire de la taille de la somme de ses inconnues."""
    path = _write(tmp_path,
                  "sell_in,999GLBWP,SAP-9,,Operator Holdings Ltd,HONG KONG,facturation,12,700,,,\n"
                  "sell_in,999SUPWP,SAP-8,,Another Operator Co,NORTHLAND,facturation,12,300,,,\n")
    read = P.load(path)

    rows = read.by_partner(P.SELL_IN)
    assert len(rows) == 2
    assert [row.revenue for row in rows] == [700.0, 300.0]


# ------------------------------------------------------------------------ regroupement


def test_one_partner_over_several_profit_centres_is_one_line(tmp_path):
    """Un partenaire occupe légitimement plusieurs centres de profit, et le fichier réel
    en a un sur trois. Le regroupement se fait à la lecture, pas à la source."""
    path = _write(tmp_path,
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,12,900,1500,900,\n"
                  "sell_in,999AAAXX,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,6,100,200,100,\n"
                  "sell_in,999BBBWP,SAP-2,Eastshop,Eastshop SA,SPAIN,facturation,12,400,800,400,\n")
    read = P.load(path)

    rows = read.by_partner(P.SELL_IN)
    assert [row.partner for row in rows] == ["Northmart", "Eastshop"]
    assert rows[0].revenue == 1000.0
    assert rows[0].profit_centre == "999AAAWP + 999AAAXX"
    assert rows[0].months_seen == 12


# -------------------------------------------------------------------------- déduction


def test_the_deduction_rate_reads_from_gross_and_net(tmp_path):
    path = _write(tmp_path,
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,12,900,1500,900,\n")
    line = P.load(path).lines[0]

    assert line.deduction == pytest.approx(0.4)


def test_an_empty_gross_column_yields_no_rate_rather_than_a_hundred_percent(tmp_path):
    """Un marché a sa colonne brute vide en permanence. Rendre 100 % ferait d'une colonne
    absente le pire partenaire du portefeuille, et personne ne verrait la différence."""
    path = _write(tmp_path,
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,NORTHLAND,facturation,12,900,,900,\n"
                  "sell_in,999BBBWP,SAP-2,Eastshop,Eastshop SA,EASTLAND,facturation,12,400,0,400,\n")
    read = P.load(path)

    assert all(line.deduction is None for line in read.lines)


def test_a_missing_gross_contaminates_the_group_rather_than_counting_as_zero(tmp_path):
    """Additionner un brut connu et un brut absent donnerait un taux calculé sur un
    périmètre plus petit que son net : flatteur, plausible, et faux."""
    path = _write(tmp_path,
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,12,900,1500,900,\n"
                  "sell_in,999AAAXX,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,6,100,,100,\n")
    grouped = P.load(path).by_partner(P.SELL_IN)[0]

    assert grouped.revenue == 1000.0
    assert grouped.deduction is None


def test_a_net_above_its_gross_makes_the_file_unusable(tmp_path):
    """Ce n'est pas une remise négative : c'est un rapprochement de deux définitions, hors
    taxe d'un côté et toutes taxes de l'autre. Le dépôt l'a déjà rencontré, et le taux qui
    en sort reste un nombre plausible — c'est ce qui le rend coûteux."""
    path = _write(tmp_path,
                  "sell_out,37OCMP001,,Northmart,Northmart Store,NORTHLAND,marche,12,900,800,900,\n")
    read = P.load(path)

    assert not read.usable
    assert "net au-dessus du brut" in read.faults[0]


# -------------------------------------------------------------------------- lecture


def test_the_country_kind_is_read_and_never_assumed(tmp_path):
    """Côté sell-in, la colonne pays donne l'immatriculation du client, pas le marché : un
    écran qui la traiterait comme un marché rangerait des flux mondiaux sous le pays d'une
    entité de facturation."""
    path = _write(tmp_path,
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,12,900,,,\n"
                  "sell_out,37OCMP001,,Eastshop,Eastshop Store,EASTLAND,marche,12,400,,,\n")
    read = P.load(path)

    assert [line.country_is for line in read.lines] == [P.BILLING, P.MARKET]


def test_an_unknown_country_kind_is_refused(tmp_path):
    path = _write(tmp_path,
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,expedition,12,900,,,\n")
    read = P.load(path)

    assert not read.usable


def test_the_same_centre_and_customer_twice_is_a_fault(tmp_path):
    """Une ligne répétée doublerait un partenaire sans rien changer à l'allure du fichier."""
    path = _write(tmp_path,
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,12,900,,,\n"
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,12,900,,,\n")
    read = P.load(path)

    assert not read.usable
    assert "figure déjà" in read.faults[0]


def test_the_same_centre_under_two_customers_is_legitimate(tmp_path):
    """Six partenaires du fichier réel vivent sous deux comptes clients du même groupe.
    L'identité d'une ligne est le couple centre + client, pas le centre seul."""
    path = _write(tmp_path,
                  "sell_in,999AAAWP,SAP-1,Northmart,Northmart Ltd,LUXEMBOURG,facturation,12,900,,,\n"
                  "sell_in,999AAAWP,SAP-2,Northmart,Northmart Retail BV,LUXEMBOURG,facturation,12,300,,,\n")
    read = P.load(path)

    assert read.usable
    assert read.total(P.SELL_IN) == 1200.0


def test_a_missing_column_stops_the_read_rather_than_half_reading(tmp_path):
    path = _write(tmp_path, "sell_in,999AAAWP,Northmart\n",
                  header="base,profit_centre,partner\n")
    read = P.load(path)

    assert not read.usable
    assert "revenue_12m" in read.faults[0]


def test_an_absent_file_says_so_instead_of_reading_as_empty(tmp_path):
    read = P.load(str(tmp_path / "nulle-part.csv"))

    assert not read.usable
    assert "absent" in read.faults[0]
