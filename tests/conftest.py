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

# Le .env du poste ne doit jamais atteindre la suite. Il l'atteignait : dès qu'une
# connexion Snowflake y était écrite, les tests lisaient le vrai entrepôt — lents, non
# déterministes, consommant du crédit, et dix-neuf échouaient en accusant le dernier
# commit. Une suite qui dépend de la configuration de la machine n'atteste de rien.
os.environ["CEOOS_DOTENV"] = "0"

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
def fresh_warehouse_cache(monkeypatch):
    """No test inherits another's cached dataset.

    The cache is module-level by design — a per-request cache would never survive long
    enough to spare anyone the query — which means it outlives a test unless something
    clears it. Something does.
    """
    from app.config import settings
    from app.perf import context, owners, source

    # Pointed at the test directory, not at the working `var/`: a test run must never
    # write into — or read from — a cache a real screen is using. Every cache file, not
    # just the one for the current month: the history has its own, and a test that wiped
    # the real one would cost a two-year query the next time the screen was opened.
    source._cache_path = lambda name=source.CACHE_FILE: TEST_DIR / name

    # The notes go the same way, and for a sharper reason than the cache. `cmd_note`
    # appends to whatever `context_path` names — so a test that posts a note posts it
    # into the notes a real screen is reading, on the machine of whoever runs the suite.
    # This was not hypothetical: two notes reached the working `var/` before anyone
    # noticed, and the suite then read them back and failed on them.
    # `Settings` is frozen on purpose, so the derived property is what gets redirected
    # rather than the field behind it. `monkeypatch` puts it back afterwards, which a
    # hand-rolled override would have to remember to do.
    monkeypatch.setattr(
        type(settings), "context_path",
        property(lambda self: TEST_DIR / "context.csv"),
    )

    source.cache_forget()
    owners.reset()
    context.reset()
    yield
    source.cache_forget()
    owners.reset()
    context.reset()
    try:
        (TEST_DIR / "context.csv").unlink()
    except OSError:
        pass


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
