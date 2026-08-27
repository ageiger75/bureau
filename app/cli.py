"""Commandes d'administration locale.

    python -m app.cli migrate        crée le schéma manquant
    python -m app.cli seed           insère les données fictives si la base est vide
    python -m app.cli seed --reset    efface tout et réinsère
    python -m app.cli check          vérifie la configuration et affiche le périmètre actif
    python -m app.cli warehouse      teste la connexion Snowflake sans lire de donnée métier
                                     --schemas / --tables SCHEMA / --columns SCHEMA.TABLE
    python -m app.cli budget         lit le classeur de planification et dit ce qu'il couvre
                                     --period AAAA-MM pour détailler un mois
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

    if settings.reads_warehouse:
        from .perf import queries

        print("Données perf        Snowflake, connexion « %s » de ~/.snowflake/connections.toml"
              % settings.snowflake_connection)
        print("                    aucun identifiant lu ni stocké par l'application")
        restant = queries.missing()
        if restant:
            print("Requêtes à écrire   %s" % ", ".join(restant))
        else:
            print("Requêtes            toutes écrites")
    else:
        print("Données perf        fictives (CEOOS_DATA_SOURCE=mock)")

    print("Écritures externes  aucune. Le cockpit prépare, signale et structure.")
    print("Appels externes     %s" % (
        "l'entrepôt Snowflake en lecture seule, et rien d'autre"
        if settings.reads_warehouse
        else "aucun (ni Microsoft 365, ni fournisseur IA)"))
    return 0


def cmd_budget(argv: List[str]) -> int:
    """Lit le classeur de planification et dit ce qu'il contient.

    Aucun réseau, aucune base : c'est un fichier sur le disque. La commande existe pour
    répondre à la seule question qui compte avant de brancher l'entrepôt — le budget
    couvre-t-il bien les marchés dont on va lire les ventes ? Un classeur illisible ou
    incomplet vaut mieux découvert ici que devant un écran serein.
    """
    from .perf import budget as budget_module

    if not settings.has_budget_file:
        print("Classeur absent : %s" % settings.budget_path, file=sys.stderr)
        print("Copier le fichier de planification à cet emplacement, puis relancer.",
              file=sys.stderr)
        return 2

    try:
        plan = budget_module.load(settings.budget_path)
    except Exception as exc:  # noqa: BLE001 — le message importe plus que le type
        print("Lecture impossible : %s" % exc, file=sys.stderr)
        return 1

    periods = plan.periods()
    markets = plan.markets()
    print("Classeur            %s" % settings.budget_path)
    print("Lignes              %d" % len(plan.lines))
    print("Marchés             %d" % len(markets))
    print("Périodes            %d, de %s à %s" % (
        len(periods), periods[0] if periods else "?", periods[-1] if periods else "?"))

    wanted = _option(argv, "--period")
    if wanted:
        if wanted not in periods:
            print("Période inconnue : %s" % wanted, file=sys.stderr)
            return 2
        _print_period(plan, wanted)
        return 0

    # Sans période demandée, un total par mois : une colonne vide ou un mois manquant
    # se voit d'un coup d'œil, ce qu'une somme annuelle cacherait.
    print("")
    print("%-10s %16s %16s" % ("Période", "Budget", "An dernier"))
    for period in periods:
        print("%-10s %16s %16s" % (
            period,
            _eur(plan.total_budget(period)),
            _eur(plan.total_last_year(period)),
        ))
    return 0


def _print_period(plan, period: str) -> None:
    lines = sorted(
        (l for l in plan.lines if l.period == period),
        key=lambda l: -(l.budget or 0.0),
    )
    print("")
    print("%-24s %-10s %16s %16s" % ("Marché", "Canal", "Budget", "An dernier"))
    for line in lines:
        print("%-24s %-10s %16s %16s" % (
            line.market[:24],
            line.channel,
            _eur(line.budget),
            _eur(line.last_year),
        ))


def _eur(value) -> str:
    """Des euros lisibles, et un tiret quand la case est vide.

    Un zéro affiché à la place d'une absence est exactement le mensonge que le reste du
    cockpit passe son temps à éviter.
    """
    if value is None:
        return "—"
    return "{:,.0f}".format(value).replace(",", " ")


def cmd_warehouse(argv: List[str]) -> int:
    """Prouve que la connexion fonctionne, sans lire une seule donnée métier."""
    if not settings.reads_warehouse:
        print("CEOOS_DATA_SOURCE n'est pas « snowflake » : rien à tester.", file=sys.stderr)
        return 2
    _silence_third_party_noise()
    from .perf import warehouse

    try:
        return _warehouse_action(warehouse, argv)
    except Exception as exc:  # noqa: BLE001 — le message importe plus que le type
        print("Échec : %s" % exc, file=sys.stderr)
        return 1


def _warehouse_action(warehouse, argv: List[str]) -> int:
    """Exploration en lecture seule, pour écrire les requêtes contre le vrai schéma."""
    facts = None

    if "--schemas" in argv:
        facts = warehouse.check()
        database = _option(argv, "--database") or facts.get("database")
        if not database:
            print("Aucune base : préciser --database NOM.", file=sys.stderr)
            return 2
        print("Schémas de %s :" % database)
        for name in warehouse.schemas(database):
            print("  %s" % name)
        return 0

    if "--tables" in argv:
        facts = warehouse.check()
        schema = _option(argv, "--tables")
        database = _option(argv, "--database") or facts.get("database")
        if not schema or not database:
            print("Usage : manage.py warehouse --tables SCHEMA [--database BASE]",
                  file=sys.stderr)
            return 2
        print("Objets de %s.%s :" % (database, schema))
        for item in warehouse.tables(database, schema, _option(argv, "--like") or ""):
            count = "" if item["rows"] is None else "  (%s lignes)" % item["rows"]
            print("  %-8s %s%s" % (item["kind"], item["name"], count))
        return 0

    if "--columns" in argv:
        facts = warehouse.check()
        target = _option(argv, "--columns") or ""
        parts = target.split(".")
        if len(parts) == 3:
            database, schema, table = parts
        elif len(parts) == 2:
            database, (schema, table) = facts.get("database"), parts
        else:
            print("Usage : manage.py warehouse --columns [BASE.]SCHEMA.TABLE",
                  file=sys.stderr)
            return 2
        print("Colonnes de %s.%s.%s :" % (database, schema, table))
        for column in warehouse.columns(database, schema, table):
            print("  %-34s %-18s %s" % (column["name"], column["type"], column["null"]))
        return 0

    print("Ouverture de la connexion « %s »." % settings.snowflake_connection)
    print("Une page d'authentification peut s'ouvrir dans le navigateur.")
    print()
    print(warehouse.describe_session())
    print()
    print("Explorer le schéma, sans lire de donnée métier :")
    print("  manage.py warehouse --schemas")
    print("  manage.py warehouse --tables SCHEMA [--like MOTIF%]")
    print("  manage.py warehouse --columns SCHEMA.TABLE")
    return 0


def _silence_third_party_noise() -> None:
    """Tait les avertissements des dépendances, jamais les nôtres.

    Le connecteur tire boto3 et une copie d'urllib3 qui préviennent, à chaque appel, que
    Python 3.9 vieillit et que macOS livre LibreSSL. Les deux sont vraies et sans effet
    ici, mais elles s'intercalent entre la question posée et la réponse — et une sortie
    illisible est une sortie qu'on cesse de lire.
    """
    import warnings

    for pattern in (
        r".*LibreSSL.*",
        r".*Boto3 will no longer support Python 3\.9.*",
        r".*Dependency 'keyring' is not installed.*",
    ):
        warnings.filterwarnings("ignore", message=pattern)


def _option(argv: List[str], flag: str) -> str:
    """Valeur suivant un drapeau, ou chaîne vide."""
    if flag in argv:
        position = argv.index(flag) + 1
        if position < len(argv) and not argv[position].startswith("--"):
            return argv[position]
    return ""


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
    if command == "warehouse":
        return cmd_warehouse(argv[1:])
    if command == "budget":
        return cmd_budget(argv[1:])
    if command == "serve":
        return cmd_serve(argv[1:])
    print("Commande inconnue : %s" % command, file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
