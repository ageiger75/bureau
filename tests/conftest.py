"""Fixtures de test.

Les variables d'environnement sont posées **avant** tout import de `app` : la
configuration est lue au chargement du module `app.config`, et le moteur SQLAlchemy est
construit à l'import de `app.db`. Sans cette précaution, les tests écriraient dans la base
de travail locale.
"""

from __future__ import annotations

import html
import os
import tempfile
from pathlib import Path

import pytest

TEST_DIR = Path(tempfile.mkdtemp(prefix="ceoos-tests-"))

os.environ["CEOOS_ENV"] = "local"
os.environ["CEOOS_AUTONOMY_LEVEL"] = "PREPARE"
os.environ["CEOOS_SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["CEOOS_DATABASE_URL"] = "sqlite:///%s" % (TEST_DIR / "test.db")

from starlette.testclient import TestClient  # noqa: E402

from app.db import SessionFactory, create_all, drop_all  # noqa: E402
from app.domain.enums import UserRole  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_warehouse_cache():
    """No test inherits another's cached dataset.

    The cache is module-level by design — a per-request cache would never survive long
    enough to spare anyone the query — which means it outlives a test unless something
    clears it. Something does.
    """
    from app.perf import owners, source

    source.cache_clear()
    owners.reset()
    yield
    source.cache_clear()
    owners.reset()


@pytest.fixture(autouse=True)
def fresh_database():
    """Schéma vierge avant chaque test : aucun test ne dépend de l'ordre d'exécution."""
    drop_all()
    create_all()
    yield
    drop_all()


@pytest.fixture
def db_session():
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def ceo(db_session) -> User:
    """Identité minimale : la tranche 1 prend l'utilisateur courant dans la base."""
    user = User(
        email="ceo@test.local",
        display_name="CEO de test",
        role=UserRole.CEO.value,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def client(ceo):
    del ceo  # présence requise, pas l'objet
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def empty_client():
    """Client sur une base sans aucun utilisateur, pour vérifier l'écran d'amorçage."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seeded_client():
    """Client sur les données de démonstration."""
    from seed.demo import seed

    seed()
    with TestClient(app) as test_client:
        yield test_client


def page_text(response) -> str:
    """Contenu de la page, entités HTML résolues.

    Jinja2 échappe les apostrophes en `&#39;` — ce qui est exactement ce qu'on veut en
    production. Les assertions portant sur du texte français doivent donc comparer sur la
    version décodée, sinon chaque apostrophe casse le test pour une bonne raison technique
    mais un mauvais motif fonctionnel. Le test d'échappement, lui, lit `response.text` brut.
    """
    return html.unescape(response.text)


def create_case(client: TestClient, **overrides) -> str:
    """Crée un dossier via l'interface et retourne son identifiant.

    Passer par le vrai formulaire plutôt que par l'ORM : un test qui insère directement en
    base ne prouve pas que le parcours utilisateur fonctionne.
    """
    payload = {
        "title": "Dossier de test",
        "question": "Faut-il faire A plutôt que B avant la fin du trimestre ?",
        "context": "Contexte de test.",
        "deadline": "2026-12-31",
        "confidentiality": "confidential",
    }
    payload.update(overrides)
    response = client.post("/cases", data=payload, follow_redirects=False)
    assert response.status_code == 303, response.text
    return response.headers["location"].rsplit("/", 1)[-1]
