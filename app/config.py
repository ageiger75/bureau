"""Configuration de CEO OS — Decision Room.

Les garde-fous sont appliqués ici, au chargement du module, et non dans l'interface :
une configuration invalide doit empêcher le démarrage plutôt que produire un
comportement dégradé silencieux (brief §13).

Python 3.9 : pas de `X | None`, pas de match/case.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

# Niveaux d'autonomie du brief §13. EXECUTE n'est pas une valeur acceptée : le produit
# ne doit pouvoir ni envoyer, ni modifier, ni engager quoi que ce soit à l'extérieur.
AUTONOMY_LEVELS = ("READ", "PREPARE")

# L'application n'écoute que sur la boucle locale. Cette constante est vérifiée par le
# middleware de app/main.py en plus de l'argument --host passé à uvicorn.
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost", "testclient")


class ConfigError(RuntimeError):
    """Configuration refusée : le service ne doit pas démarrer."""


def _load_dotenv(path: Path) -> None:
    """Charge un .env sans dépendance externe. Une variable déjà définie n'est pas écrasée."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


#: Où les chiffres de performance sont lus. `mock` est le défaut et le restera : une
#: connexion à l'entrepôt se demande explicitement, elle ne s'obtient jamais par accident.
DATA_SOURCES = ("mock", "snowflake")
DEFAULT_DATA_SOURCE = "mock"

#: Classeur de planification : budget et an dernier, par marché et par mois. Il vit dans
#: `var/`, donc hors du dépôt — ce sont de vrais chiffres, et ils n'ont rien à faire dans
#: un historique Git.
DEFAULT_BUDGET_FILE = "var/budget.xlsx"


@dataclass(frozen=True)
class Settings:
    env: str
    secret_key: str
    database_url: str
    autonomy_level: str
    data_source: str = DEFAULT_DATA_SOURCE
    budget_file: str = DEFAULT_BUDGET_FILE
    #: Nom d'une connexion déclarée dans ~/.snowflake/connections.toml — le fichier que
    #: la CLI Snowflake et Cortex Code utilisent déjà. Aucun identifiant n'est lu, stocké
    #: ni transporté par l'application, et aucun n'a sa place dans ce dépôt.
    snowflake_connection: str = ""

    @property
    def is_local(self) -> bool:
        return self.env == "local"

    @property
    def reads_warehouse(self) -> bool:
        return self.data_source == "snowflake"

    @property
    def budget_path(self) -> Path:
        path = Path(self.budget_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_budget_file(self) -> bool:
        return self.budget_path.exists()

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def sqlite_path(self) -> Optional[Path]:
        """Chemin du fichier SQLite, ou None si la cible est PostgreSQL."""
        if not self.is_sqlite:
            return None
        raw = self.database_url.split("sqlite:///", 1)[-1]
        if raw in ("", ":memory:"):
            return None
        path = Path(raw)
        return path if path.is_absolute() else ROOT / path


def load_settings() -> Settings:
    _load_dotenv(ROOT / ".env")

    env = _env("CEOOS_ENV", "local").lower()
    if env not in ("local", "pilot", "production"):
        raise ConfigError("CEOOS_ENV doit valoir local, pilot ou production.")

    secret_key = _env("CEOOS_SECRET_KEY")
    if env != "local" and len(secret_key) < 32:
        raise ConfigError(
            "CEOOS_SECRET_KEY doit faire au moins 32 caracteres hors environnement local."
        )
    if not secret_key:
        secret_key = "local-development-secret-not-for-pilot"

    autonomy = _env("CEOOS_AUTONOMY_LEVEL", "PREPARE").upper()
    if autonomy not in AUTONOMY_LEVELS:
        raise ConfigError(
            "CEOOS_AUTONOMY_LEVEL doit valoir READ ou PREPARE. EXECUTE n'est pas "
            "implemente et requiert une gouvernance separee (brief §13)."
        )

    data_source = (_env("CEOOS_DATA_SOURCE") or DEFAULT_DATA_SOURCE).lower()
    if data_source not in DATA_SOURCES:
        raise ConfigError(
            "CEOOS_DATA_SOURCE doit valoir %s." % " ou ".join(DATA_SOURCES)
        )

    snowflake_connection = _env("CEOOS_SNOWFLAKE_CONNECTION")
    if data_source == "snowflake" and not snowflake_connection:
        raise ConfigError(
            "CEOOS_DATA_SOURCE=snowflake exige CEOOS_SNOWFLAKE_CONNECTION : le nom d'une "
            "connexion declaree dans ~/.snowflake/connections.toml. L'application ne lit "
            "ni ne stocke d'identifiant elle-meme."
        )

    return Settings(
        env=env,
        secret_key=secret_key,
        database_url=_env("CEOOS_DATABASE_URL", "sqlite:///var/ceo-os.db"),
        autonomy_level=autonomy,
        data_source=data_source,
        budget_file=_env("CEOOS_BUDGET_FILE") or DEFAULT_BUDGET_FILE,
        snowflake_connection=snowflake_connection,
    )


settings = load_settings()
