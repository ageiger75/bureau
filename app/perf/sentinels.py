"""Les valeurs de remplissage de l'entrepôt, en un seul endroit.

Un défaut de cette famille a été trouvé quatre fois sur ce projet, chaque fois par un
chemin différent, et chaque fois il avait déjà produit une lecture fausse et confiante :

* un code magasin valant la chaîne « N/A » a été pris pour une identité, et un
  regroupement a étiqueté d'un seul pays le lot mondial des codes absents ;
* le même « N/A » a fait rendre au lecteur de distribution soixante lignes de défaut
  identiques, parce qu'il comptait le lot comme une entité ;
* une date vide écrite comme une date du début du siècle dernier a fait passer une colonne
  pour complète, et tout âge calculé dessus était faux ;
* une requête de couverture testant `is null` sur un code n'a jamais pu se déclencher,
  parce que l'absence y est écrite « N/A » — et la conclusion tirée était que deux points
  de vente ne vendaient rien, alors qu'ils vendaient.

Le mécanisme est toujours le même et il mérite d'être nommé : **une valeur manquante
s'annonce et se traite ; un remplissage en forme de valeur se consomme en silence et
voyage.** Un `NULL` fait échouer une jointure, tomber un test, apparaître un trou. Une
chaîne « N/A » joint, compare, s'agrège et se moyenne.

D'où ce module. Les sentinelles n'étaient pas inconnues du dépôt — elles vivaient dans un
tuple à l'intérieur d'un lecteur et dans de la prose au registre de provenance — mais un
lecteur de plus les aurait redécouvertes à ses frais. Elles sont ici, nommées, testées, et
citables telles quelles dans une requête envoyée à l'entrepôt.
"""

from __future__ import annotations

from typing import Optional

#: Ce qu'une source écrit à la place d'un identifiant absent. Comparées en minuscules et
#: sans espaces autour ; la chaîne vide en fait partie, parce qu'une cellule vide et une
#: cellule contenant « N/A » veulent dire la même chose et doivent se traiter pareil.
MISSING_IDS = ("", "n/a", "na", "n.a.", "-", "--", "—", "null", "none", "nil",
               "#n/a", "unknown", "inconnu", "sans code")

#: Ce qu'une source écrit à la place d'une date absente. Un `NULL` aurait fait tomber tout
#: calcul d'âge ; ces dates-là le laissent passer et rendent un nombre plausible.
MISSING_DATES = ("1900-01-01", "1899-12-30", "1899-12-31", "0001-01-01",
                 "1970-01-01", "9999-12-31")


def missing_id(value: Optional[str]) -> bool:
    """L'identifiant est-il un remplissage plutôt qu'une identité ?

    Rend vrai pour `None` comme pour la chaîne de remplissage : côté application les deux
    veulent dire « je ne sais pas de qui il s'agit », et les distinguer ferait dépendre le
    comportement de la façon dont la source a écrit son absence.
    """
    if value is None:
        return True
    return str(value).strip().lower() in MISSING_IDS


def missing_date(value: Optional[str]) -> bool:
    """La date est-elle une sentinelle plutôt qu'un événement ?

    La comparaison porte sur les dix premiers caractères : une source qui écrit
    « 1900-01-01 00:00:00 » écrit la même absence qu'une source qui écrit « 1900-01-01 ».
    """
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    return text[:10] in MISSING_DATES


def identity(value: Optional[str]) -> Optional[str]:
    """L'identifiant s'il en est un, `None` s'il n'en est pas un.

    À utiliser comme clé de regroupement. Rendre `None` plutôt que la chaîne de
    remplissage est ce qui empêche le lot des absents de se comporter comme une entité —
    c'est exactement le défaut qui a fait naître ce module.
    """
    return None if missing_id(value) else str(value).strip()


def when(value: Optional[str]) -> Optional[str]:
    """La date si elle en est une, `None` si c'est une sentinelle."""
    return None if missing_date(value) else str(value).strip()[:10]


#: La condition SQL à écrire dans une requête pour attraper les deux formes d'absence.
#: Recopiée telle quelle dans les briefs envoyés à l'entrepôt : un `IS NULL` seul y est
#: insuffisant par construction, et l'a déjà prouvé.
SQL_MISSING_ID = ("lower(trim(coalesce({column}, ''))) IN "
                  "('', 'n/a', 'na', 'n.a.', '-', '--', 'null', 'none', 'nil', '#n/a')")
