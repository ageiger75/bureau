"""Accès base de données — SQLAlchemy 2.0.

SQLite pour le prototype, PostgreSQL en cible (brief §12). La bascule doit se limiter à
`CEOOS_DATABASE_URL`. Pour que ce soit vrai, le code applicatif s'interdit :
  * les types propres à un moteur (pas de JSON natif, pas de UUID natif, pas de SERIAL) ;
  * les fonctions SQL propres à un moteur (pas de `datetime('now')`, pas de `strftime`) ;
  * les `PRAGMA` ailleurs qu'ici, derrière un test de dialecte.
"""

from __future__ import annotations

from typing import Iterator

from sqlalchemy import Engine, create_engine, event
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


def create_all() -> None:
    """Crée le schéma manquant.

    Suffisant pour un prototype mono-utilisateur. Alembic devient nécessaire dès qu'il
    faut faire évoluer un schéma contenant de vraies décisions — noté dans le README.
    """
    from . import models  # import tardif : évite un cycle models -> db -> models

    models.Base.metadata.create_all(bind=engine)


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
