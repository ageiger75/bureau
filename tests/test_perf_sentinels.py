"""Le remplissage en forme de valeur, et pourquoi il faut un seul endroit pour le nommer.

Un `NULL` fait échouer une jointure, tomber un test, apparaître un trou : il s'annonce.
Une chaîne « N/A » joint, compare, s'agrège et se moyenne : elle voyage. Le défaut a été
trouvé quatre fois sur ce projet par quatre chemins différents, et chaque fois il avait
déjà produit une lecture fausse et confiante. Ces tests gardent les deux formes et, surtout,
la propriété qui compte : le lot des absents ne doit jamais se comporter comme une entité.
"""

from __future__ import annotations

from app.perf import sentinels


def test_the_two_ways_a_source_writes_an_absent_identifier_are_the_same_absence():
    """Une cellule vide et une cellule contenant « N/A » veulent dire la même chose. Les
    distinguer ferait dépendre le comportement de la façon dont la source a écrit son
    absence, ce qui est exactement ce qu'un lecteur ne doit pas voir."""
    for written in (None, "", "  ", "N/A", "n/a", " NULL ", "#N/A", "-", "none"):
        assert sentinels.missing_id(written), written

    for real in ("C00920", "0", "N", "NA1", "A/N"):
        assert not sentinels.missing_id(real), real


def test_an_absent_identifier_never_becomes_a_grouping_key():
    """C'est le défaut d'origine, sous sa forme la plus coûteuse : un regroupement sur une
    clé « N/A » avait attribué à un seul pays le lot mondial des codes absents. Rendre
    `None` est ce qui empêche le lot de se comporter comme une entité."""
    assert sentinels.identity("N/A") is None
    assert sentinels.identity("  ") is None
    assert sentinels.identity(" C00920 ") == "C00920"


def test_a_sentinel_date_is_an_absence_and_not_an_event():
    """Une date vide écrite comme une date du début du siècle dernier laisse passer tout
    calcul d'âge et rend un nombre plausible. Une colonne pleine de ces dates se lit comme
    une colonne complète."""
    for written in (None, "", "1900-01-01", "1900-01-01 00:00:00", "9999-12-31"):
        assert sentinels.missing_date(written), written

    assert not sentinels.missing_date("2026-09-03")
    assert sentinels.when("2026-09-03 14:00:00") == "2026-09-03"
    assert sentinels.when("1900-01-01") is None


def test_the_sql_condition_catches_both_forms_because_is_null_alone_cannot():
    """La condition est recopiée telle quelle dans les requêtes envoyées à l'entrepôt. Un
    `IS NULL` seul y est insuffisant par construction : une requête de couverture écrite
    ainsi n'a jamais pu se déclencher, et la conclusion tirée était que deux points de
    vente ne vendaient rien — ils vendaient."""
    condition = sentinels.SQL_MISSING_ID.format(column="store_code")

    assert "coalesce(store_code" in condition
    assert "'n/a'" in condition
    assert "lower" in condition and "trim" in condition


def test_the_distribution_reader_reads_from_here_and_not_from_its_own_list():
    """Une liste par lecteur garantit qu'un lecteur de plus la redécouvrira à ses frais.
    Celui-ci en avait une ; elle pointe désormais sur la liste commune."""
    from app.perf import distribution

    assert distribution.PLACEHOLDER_IDS is sentinels.MISSING_IDS
