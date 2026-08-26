"""Commandes d'administration locale.

    python -m app.cli migrate        crée le schéma manquant
    python -m app.cli seed           insère les données fictives si la base est vide
    python -m app.cli seed --reset    efface tout et réinsère
    python -m app.cli check          vérifie la configuration et affiche le périmètre actif
    python -m app.cli serve          démarre le serveur (port lu dans PORT, défaut 8000)
"""

from __future__ import annotations

import os
import sys
from typing import List, Tuple

from .config import settings
from .db import create_all, database_label

# L'adresse d'écoute est une constante du code, pas un argument de ligne de commande :
# un `--host 0.0.0.0` collé par erreur exposerait des dossiers confidentiels sur le réseau.
SERVE_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def serve_config() -> Tuple[str, int]:
    """Adresse et port d'écoute.

    Le port vient de la variable `PORT` afin que l'environnement puisse en assigner un
    libre ; l'hôte, lui, n'est pas configurable. Une valeur de port illisible retombe sur
    le défaut plutôt que d'empêcher le démarrage.
    """
    raw = os.environ.get("PORT", "").strip()
    try:
        port = int(raw) if raw else DEFAULT_PORT
    except ValueError:
        print(
            "PORT=%r illisible, repli sur %d." % (raw, DEFAULT_PORT), file=sys.stderr
        )
        port = DEFAULT_PORT
    if not 1 <= port <= 65535:
        print(
            "PORT=%d hors bornes, repli sur %d." % (port, DEFAULT_PORT), file=sys.stderr
        )
        port = DEFAULT_PORT
    return SERVE_HOST, port


def cmd_migrate() -> int:
    create_all()
    print("Schéma à jour · %s" % database_label())
    return 0


def cmd_seed(argv: List[str]) -> int:
    reset = "--reset" in argv
    if reset and not settings.is_local:
        # Un --reset hors local effacerait de vraies décisions.
        print(
            "Refusé : --reset n'est autorisé que si CEOOS_ENV=local (actuel : %s)."
            % settings.env,
            file=sys.stderr,
        )
        return 2

    from seed.demo import seed

    print("Données de démonstration · %s" % seed(reset=reset))
    return 0


def cmd_check() -> int:
    host, port = serve_config()
    print("Environnement       %s" % settings.env)
    print("Base                %s" % database_label())
    print("Niveau d'autonomie  %s" % settings.autonomy_level)
    print("Écoute              %s:%d (boucle locale uniquement)" % (host, port))
    print("Appels externes     aucun (ni Microsoft 365, ni fournisseur IA)")
    return 0


def cmd_serve(argv: List[str]) -> int:
    """Démarre le serveur. `--reload` pour le développement."""
    import uvicorn

    create_all()
    host, port = serve_config()
    print("CEO OS · http://%s:%d" % (host, port))
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload="--reload" in argv,
        log_level="info",
    )
    return 0


def main(argv: List[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    command = argv[0]
    if command == "migrate":
        return cmd_migrate()
    if command == "seed":
        return cmd_seed(argv[1:])
    if command == "check":
        return cmd_check()
    if command == "serve":
        return cmd_serve(argv[1:])
    print("Commande inconnue : %s" % command, file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
