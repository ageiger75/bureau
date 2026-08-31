"""Aucun chiffre réel de la maison dans le dépôt.

La règle est là depuis le premier jour et elle a cédé en une journée, un commentaire à
la fois : chaque fois qu'un montant expliquait *pourquoi* le code est écrit ainsi, il a
été inscrit. C'est une bonne habitude d'ingénierie et elle est exactement contraire à la
règle. Un principe qu'on applique de mémoire tient jusqu'au jour où l'on est absorbé par
autre chose — donc il est vérifié ici.

Ce que le code garde : le raisonnement, la forme de l'erreur, ce qu'il faut regarder.
Ce qu'il ne garde pas : combien. Les montants vivent dans `var/`, ignoré par git, avec
les classeurs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Les fichiers versionnés qui portent du texte écrit par nous.
SOURCES = sorted(
    path
    for pattern in ("app/**/*.py", "app/**/*.html", "tests/**/*.py", "*.py", "*.md")
    for path in ROOT.glob(pattern)
    if "__pycache__" not in path.parts and path.name != Path(__file__).name
)

#: Un montant en milliers ou en millions d'euros, écrit en toutes lettres. Le formatage
#: du code produit ces chaînes à l'exécution ; ce qui est interdit, c'est de les écrire
#: en dur — un montant littéral dans un commentaire vient forcément d'une vraie lecture.
MONEY = re.compile(r"\d[\d  ]*[.,]?\d*\s?(?:k€|M€|m€|k EUR)")

#: Les codes d'entité de la consolidation. `M_106`, `M_105_TRA` : chacun désigne une
#: société réelle, et la liste des codes est elle-même une information.
ENTITY = re.compile(r"\bM_0\d\d")

#: Ce que le formatage légitime produit, et qui n'est donc pas un montant écrit en dur.
ALLOWED = (
    "%.1f M€", "%.3f M€", "%.2f %%", "%9s", "k€\"", "M€\"",
    "%s M€", "%d k€", "{{", "eur }}",
)


def _offending(path: Path):
    """Les lignes qui portent un montant littéral ou un code d'entité."""
    found = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if any(token in line for token in ALLOWED):
            continue
        if MONEY.search(line) or ENTITY.search(line):
            found.append("%s:%d %s" % (path.relative_to(ROOT), number, line.strip()[:90]))
    return found


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_real_amount_or_entity_code_is_written_into_the_repository(path):
    """Un montant littéral ou un code d'entité vient forcément d'une vraie lecture.

    Si ce test échoue sur une ligne légitime, la bonne correction est presque toujours de
    reformuler — « un marché court de plusieurs millions » dit la même chose et ne porte
    rien. Ajouter la ligne à `ALLOWED` est le dernier recours, pas le premier.
    """
    offending = _offending(path)

    assert not offending, (
        "Chiffres réels ou codes d'entité dans un fichier versionné :\n  "
        + "\n  ".join(offending)
        + "\n\nCe dépôt ne porte aucun chiffre de la maison. Le raisonnement reste dans "
        "le code, les montants vont dans var/journal.md, qui est ignoré par git."
    )


def test_an_invented_scenario_never_wears_a_real_market_name():
    """A named market said to have no plan reads as a statement about that market.

    The rule this repository runs on is taxonomy real, values invented. An invented *fact*
    about a named market breaks it in the way that matters: a reader checked their own
    workbook, found the plan there, and reasonably concluded the screen had lost it. The
    scenario was fictional and the name was not, so the sentence was read as true.
    """
    import io
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    claims = ("no plan", "without a plan", "carrying no plan", "unbudgeted")
    for path in sorted((root / "tests").glob("test_*.py")):
        text = io.open(str(path), encoding="utf-8").read()
        for number, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            if not any(claim in lowered for claim in claims):
                continue
            # The fixtures that carry such a claim must not name a real market beside it.
            assert "taiwan" not in lowered, "%s:%d" % (path.name, number)


def test_a_workbook_is_ignored_wherever_it_is_dropped():
    """The rule above keeps the house's figures out of the versioned files. This one keeps
    the files themselves out, and it is the mechanism that actually protects the data.

    It was anchored to the repository root, which covers the accident it was written for —
    a workbook dropped beside `manage.py` — and misses the likelier one: a folder of
    published files copied into the working tree to be read. Twelve months of flash sat one
    distracted `git add -A` from being published. An ignore rule that holds only at the top
    level is not an ignore rule, so the patterns must carry no leading slash.
    """
    import io
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    lines = [line.strip()
             for line in io.open(str(root / ".gitignore"), encoding="utf-8").read().splitlines()]
    for suffix in ("xlsx", "xlsm", "csv"):
        assert "*.%s" % suffix in lines, (
            "Un classeur %s déposé dans un sous-dossier serait versionné." % suffix)
        assert "/*.%s" % suffix not in lines, (
            "La règle ancrée à la racine laisse passer les sous-dossiers.")
    assert "var/" in lines
    # Les exemples de docs/ restent versionnés : des colonnes, aucune valeur de la maison.
    assert "!docs/*.example.csv" in lines
