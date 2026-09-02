"""Accès base de données — SQLAlchemy 2.0.

SQLite pour le prototype, PostgreSQL en cible (brief §12). La bascule doit se limiter à
`CEOOS_DATABASE_URL`. Pour que ce soit vrai, le code applicatif s'interdit :
  * les types propres à un moteur (pas de JSON natif, pas de UUID natif, pas de SERIAL) ;
  * les fonctions SQL propres à un moteur (pas de `datetime('now')`, pas de `strftime`) ;
  * les `PRAGMA` ailleurs qu'ici, derrière un test de dialecte.
"""

from __future__ import annotations

from typing import Iterator, List, Optional, Tuple

from sqlalchemy import Engine, MetaData, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .config import ROOT, settings


def _engine_url() -> str:
    """URL de connexion, avec chemin absolu pour SQLite.

    Un chemin relatif se résoudrait par rapport au répertoire de travail : le serveur et
    les tests ouvriraient alors deux fichiers différents.
    """
    if not settings.is_sqlite:
        return settings.database_url
    path = settings.sqlite_path
    if path is None:
        return settings.database_url  # sqlite:///:memory:
    path.parent.mkdir(parents=True, exist_ok=True)
    return "sqlite:///%s" % path


def _create_engine(url: str) -> Engine:
    kwargs = {"future": True, "echo": False}
    if url.startswith("sqlite"):
        # check_same_thread=False : uvicorn sert les requêtes depuis un pool de threads.
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine: Engine = _create_engine(_engine_url())

SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_connection, connection_record) -> None:
    """Contraintes de clés étrangères activées : SQLite les ignore par défaut, PostgreSQL
    ne le fait pas. Sans ce réglage, un bug de suppression passerait les tests locaux et
    exploserait en pilote.

    Le dialecte est déduit de la connexion elle-même, et non de `engine` : les tests
    ouvrent leur propre moteur, et un écouteur posé sur la classe les voit aussi.
    """
    del connection_record
    if not type(dbapi_connection).__module__.startswith("sqlite3"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def get_session() -> Iterator[Session]:
    """Dépendance FastAPI : une session par requête, fermée quoi qu'il arrive."""
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


def create_all() -> Tuple[List[str], List[str]]:
    """Mettre la base au niveau des modèles, additivement.

    Les tables manquantes sont créées, puis les colonnes manquantes ajoutées aux tables
    qui existaient déjà. Le second geste manquait, et son absence a arrêté l'écran sur une
    base qui portait de vrais sujets : les modèles avaient gagné une colonne, `create_all`
    ne créait que des tables, et rien ne rattrapait l'écart.

    Ne lève pas et n'affiche rien — les deux listes rendues (ajouté, refusé) sont affichées
    par `manage.py migrate` et par `manage.py check`, qui sont les endroits où l'état du
    schéma se lit.
    """
    from . import models  # import tardif : évite un cycle models -> db -> models

    models.Base.metadata.create_all(bind=engine)
    return add_missing_columns()


def _metadata() -> "MetaData":
    from . import models

    return models.Base.metadata


def _literal_default(column) -> Optional[str]:
    """La valeur de départ d'une colonne, écrite en SQL — ou rien si elle ne s'écrit pas.

    Les défauts de ce projet sont posés côté Python (`default=False`, `default=""`), ce que
    la base ignore : une colonne ajoutée sans défaut littéral laisserait NULL dans chaque
    ligne existante, et une colonne NOT NULL serait refusée par le moteur. Un défaut
    calculé — un identifiant, un horodatage — n'a pas de littéral, et il ne s'invente pas.
    """
    default = getattr(column, "default", None)
    if default is None or not getattr(default, "is_scalar", False):
        return None
    value = default.arg
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return "'%s'" % value.replace("'", "''")
    return None


def pending_columns(metadata: Optional["MetaData"] = None) -> List[Tuple[str, object]]:
    """Les colonnes que les modèles déclarent et que la base n'a pas.

    Seules les tables déjà présentes sont examinées : une table absente est créée entière
    par `create_all`, et l'annoncer comme une colonne manquante ferait passer une création
    ordinaire pour une migration.
    """
    schema = metadata if metadata is not None else _metadata()
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    pending: List[Tuple[str, object]] = []
    for table in schema.sorted_tables:
        if table.name not in existing:
            continue
        present = {info["name"] for info in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in present:
                pending.append((table.name, column))
    return pending


def add_missing_columns(
    metadata: Optional["MetaData"] = None,
) -> Tuple[List[str], List[str]]:
    """Ajouter à la base les colonnes que les modèles ont gagnées depuis sa création.

    Le besoin est né d'une panne : une colonne ajoutée à `management_issues` a rendu
    illisible une base qui portait déjà des sujets. `create_all` ne crée que des tables
    manquantes, jamais des colonnes manquantes, et l'écran s'arrêtait sur une erreur SQL
    au lieu de s'adapter. Effacer la base aurait été la réponse courte — et elle aurait
    effacé la mémoire, c'est-à-dire la seule chose que ce module existe pour garder.

    **Strictement additif.** `ADD COLUMN` est la seule opération émise, et c'est la seule
    que SQLite et PostgreSQL exécutent de la même façon sans réécrire la table. Renommer,
    retyper ou supprimer une colonne demande une vraie migration versionnée — Alembic, le
    jour où ce prototype portera plusieurs postes. Une colonne devenue inutile reste donc
    en place, ce qui ne coûte rien, plutôt que d'être supprimée par une commande qui
    perdrait ses données sans le dire.

    Rend deux listes : ce qui a été ajouté, et ce qui a été **refusé** avec son motif. Une
    colonne obligatoire dont le défaut se calcule — un identifiant, un horodatage — n'est
    pas ajoutée avec une valeur inventée : elle est nommée, et l'appelant décide.
    """
    added: List[str] = []
    refused: List[str] = []
    for table_name, column in pending_columns(metadata):
        literal = _literal_default(column)
        if literal is None and not column.nullable:
            refused.append(
                "%s.%s — colonne obligatoire sans valeur de départ écrivable ; "
                "une migration versionnée est nécessaire" % (table_name, column.name))
            continue
        clause = "%s %s" % (column.name, column.type.compile(engine.dialect))
        if not column.nullable:
            clause += " NOT NULL"
        if literal is not None:
            clause += " DEFAULT %s" % literal
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE %s ADD COLUMN %s" % (table_name, clause)))
        added.append("%s.%s" % (table_name, column.name))
    return added, refused


def drop_all() -> None:
    """Réservé aux tests et à `cli.py seed --reset`."""
    from . import models

    models.Base.metadata.drop_all(bind=engine)


def database_label() -> str:
    """Description lisible de la base active, affichée dans le pied de page."""
    if settings.is_sqlite:
        path = settings.sqlite_path
        if path is None:
            return "SQLite (mémoire)"
        try:
            return "SQLite · %s" % path.relative_to(ROOT)
        except ValueError:
            return "SQLite · %s" % path
    return "PostgreSQL"
