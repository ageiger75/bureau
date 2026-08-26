#!/usr/bin/env python3
"""Point d'entrée indépendant du répertoire de travail.

`python -m app.cli` suppose que le répertoire courant est la racine du projet. Ce n'est pas
vrai quand le processus est démarré par un outil extérieur, qui hérite d'un autre
répertoire de travail — c'est exactement ce qui a cassé le lancement depuis le panneau de
prévisualisation. Ce script déduit la racine de son propre emplacement, ce qui rend la
commande valable depuis n'importe où :

    /chemin/vers/ceo-os/manage.py check
    /chemin/vers/ceo-os/manage.py serve

Toutes les commandes de `app/cli.py` sont acceptées telles quelles.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cli import main  # noqa: E402  (import après ajustement de sys.path)

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
