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


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _load_dotenv(path: Path) -> None:
    """Charge un .env sans dépendance externe. Une variable déjà définie n'est pas écrasée.

    `CEOOS_DOTENV=0` désactive entièrement la lecture du fichier. Ce n'est pas un réglage
    de test : un service qui reçoit sa configuration de son environnement n'a rien à
    prendre dans un fichier oublié à côté de lui, et la surprise est silencieuse.

    Elle l'a d'ailleurs été. La suite de tests lisait ce fichier et pointait donc sur le
    vrai entrepôt dès qu'un poste y avait écrit une connexion — des tests lents, non
    déterministes, qui consomment du crédit d'entrepôt, et dix-neuf qui échouaient en
    accusant le dernier commit. Une suite qui dépend de la configuration de la machine
    n'atteste de rien.
    """
    if _env("CEOOS_DOTENV", "1") in ("0", "false", "no"):
        return
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


#: Où les chiffres de performance sont lus. `mock` est le défaut et le restera : une
#: connexion à l'entrepôt se demande explicitement, elle ne s'obtient jamais par accident.
DATA_SOURCES = ("mock", "snowflake")
DEFAULT_DATA_SOURCE = "mock"

#: Classeur de planification : budget et an dernier, par marché et par mois. Il vit dans
#: `var/`, donc hors du dépôt — ce sont de vrais chiffres, et ils n'ont rien à faire dans
#: un historique Git.
DEFAULT_BUDGET_FILE = "var/budget.xlsx"

#: Annuaire des MD et GM pays. Comme le budget, il vit hors du dépôt : ce sont
#: de vraies personnes et leur périmètre réel, ce qui n'a rien à faire dans un git.
DEFAULT_OWNERS_FILE = "var/owners.xlsx"

#: Ce que les chiffres ne peuvent pas dire : un changement de taxes, un événement isolé.
#: Connaissance d'entreprise, pas mesure — donc hors du dépôt, comme le reste.
DEFAULT_CONTEXT_FILE = "var/context.csv"
#: Le jugement du lecteur, relu quelques fois par an et édité à la main.
DEFAULT_WEIGHTS_FILE = "var/weights.csv"
#: Le réalisé publié par la Finance, à la maille du plan. Déposé chaque mois.
DEFAULT_ACTUALS_FILE = "var/actuals.xlsx"
#: La ligne hiérarchique : les sept périmètres, leur MD, et les responsables pays
#: sous eux. Hors du dépôt comme l'annuaire : elle porte des noms et des adresses.
DEFAULT_ORG_FILE = "var/org.xlsx"
#: La distance mesurée entre les deux systèmes, marché par marché : ce qui décide à
#: quelle vitesse l'écran a le droit de tourner sur chaque marché.
DEFAULT_DIVERGENCE_FILE = "var/divergence.csv"

#: Les partenaires du digital non détenu, base par base. Écrit par Cortex depuis
#: l'entrepôt : la marque commerciale n'est dans aucune colonne et arrive avec le fichier.
DEFAULT_PARTNERS_FILE = "var/partners.csv"

#: Les signaux de distribution, entité par entité et fenêtre par fenêtre. Écrit par Cortex
#: depuis l'entrepôt : la norme de comparaison se calcule sur des dizaines de milliers de
#: lignes, ce que le cockpit ne fait pas et n'a pas à faire.
DEFAULT_DISTRIBUTION_FILE = "var/distribution_signals.csv"
#: La forme d'un mois, semaine par semaine, telle que l'an dernier l'a écrite. Sans elle,
#: « où j'en suis dans le mois » se calcule sur les jours écoulés — c'est-à-dire en
#: supposant qu'un mois se vend à plat, ce qu'aucun mois ne fait. Un décalage de calendrier
#: a déjà produit ici une chute apparente de quarante pour cent qui n'existait pas.
DEFAULT_PHASING_FILE = "var/phasing.csv"

#: Le calendrier des dates mobiles : quel événement, quel pays, quel exercice, quelle date.
#: Il ne sert qu'au rapprochement — aucune règle ne se déclenche dessus, et son absence ne
#: retire rien à la mesure des mois qui bougent, elle retire seulement les explications.
DEFAULT_CALENDAR_FILE = "var/calendar_events.csv"

#: Optionnel : quel marché de la maison correspond à quel pays du calendrier. Sans lui, le
#: rapprochement se fait sur le nom, et les marchés qu'il n'a pas su joindre sont nommés.
DEFAULT_MARKETS_FILE = "var/markets.csv"
#: Le taux de contribution moyen par canal, tel que la maison le connaît — et rien
#: d'autre. Il dit ce qu'un canal a rapporté, pas ce que le prochain euro rapporterait :
#: le taux marginal n'est dans aucune source lue ici, et ce fichier ne le remplace pas.
#: Un canal vendu qu'il ne nomme pas est absent, jamais pris à zéro ni à la moyenne.
DEFAULT_CONTRIBUTION_FILE = "var/contribution.csv"

#: Le référentiel immobilier, extrait de l'entrepôt boutique par boutique : le code, le
#: bail, la part de loyer variable telle qu'elle est écrite. C'est la seule source lue ici
#: qui dise ce qu'un euro de plus perd en loyer, et elle le dit par bail, jamais par pays.
DEFAULT_STORES_FILE = "var/stores.csv"

#: Les ventes par boutique telles que la consolidation les publie, avec leur budget — la
#: feuille par magasin de l'extraction de la CFO. Jointe au référentiel par le code.
DEFAULT_STORE_SALES_FILE = "var/stores-sales.xlsx"

#: Le budget EBITDA par BU de la Finance — la feuille de synthèse et le pont vers l'EBITDA
#: consolidé ajusté. Un plan, jamais un réel : la Finance ne produit pas d'EBITDA par BU au
#: mois, et le cockpit le dit plutôt que de le déduire d'un taux moyen.
DEFAULT_EBITDA_FILE = "var/ebitda-budget.xlsx"

#: La marge incrémentale par canal, mesurée au compte de gestion par l'agent entrepôt : le
#: taux du prochain euro, là où la série est stable, et un statut nommé partout ailleurs.
DEFAULT_INCREMENTAL_FILE = "var/incremental_margin_channels.csv"

#: Les mois précédents, gardés. Un fichier dit où on en est ; la série dit si un mois a
#: bougé après avoir été publié — la seule différence entre les deux systèmes qui soit
#: décidée plutôt que calculée, et donc la seule qu'aucune règle ne devinera.
DEFAULT_ACTUALS_FOLDER = "var/actuals"

#: The KPI tracker the business maintains: definitions, targets, cadence, owners. Beside
#: the plan workbook and gitignored with it, because it names people and states targets.
#: The warehouse supplies values; nothing there says what good is.
DEFAULT_KPI_FILE = "var/kpi-tracker.xlsx"


@dataclass(frozen=True)
class Settings:
    env: str
    secret_key: str
    database_url: str
    autonomy_level: str
    data_source: str = DEFAULT_DATA_SOURCE
    budget_file: str = DEFAULT_BUDGET_FILE
    owners_file: str = DEFAULT_OWNERS_FILE
    context_file: str = DEFAULT_CONTEXT_FILE
    weights_file: str = DEFAULT_WEIGHTS_FILE
    actuals_file: str = DEFAULT_ACTUALS_FILE
    actuals_folder_name: str = DEFAULT_ACTUALS_FOLDER
    divergence_file: str = DEFAULT_DIVERGENCE_FILE
    partners_file: str = DEFAULT_PARTNERS_FILE
    distribution_file: str = DEFAULT_DISTRIBUTION_FILE
    phasing_file: str = DEFAULT_PHASING_FILE
    calendar_file: str = DEFAULT_CALENDAR_FILE
    markets_file: str = DEFAULT_MARKETS_FILE
    contribution_file: str = DEFAULT_CONTRIBUTION_FILE
    stores_file: str = DEFAULT_STORES_FILE
    store_sales_file: str = DEFAULT_STORE_SALES_FILE
    ebitda_file: str = DEFAULT_EBITDA_FILE
    incremental_file: str = DEFAULT_INCREMENTAL_FILE
    org_file: str = DEFAULT_ORG_FILE
    kpi_file: str = DEFAULT_KPI_FILE
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
    def owners_path(self) -> Path:
        path = Path(self.owners_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def context_path(self) -> Path:
        path = Path(self.context_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def kpi_path(self) -> Path:
        path = Path(self.kpi_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_kpi_file(self) -> bool:
        return self.kpi_path.exists()

    @property
    def weights_path(self) -> Path:
        path = Path(self.weights_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def actuals_path(self) -> Path:
        path = Path(self.actuals_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_actuals_file(self) -> bool:
        return self.actuals_path.exists()

    @property
    def org_path(self) -> Path:
        path = Path(self.org_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_org_file(self) -> bool:
        return self.org_path.exists()

    @property
    def divergence_path(self) -> Path:
        path = Path(self.divergence_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_divergence_file(self) -> bool:
        return self.divergence_path.exists()

    @property
    def partners_path(self) -> Path:
        path = Path(self.partners_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_partners_file(self) -> bool:
        return self.partners_path.exists()

    @property
    def distribution_path(self) -> Path:
        path = Path(self.distribution_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_distribution_file(self) -> bool:
        return self.distribution_path.exists()

    @property
    def phasing_path(self) -> Path:
        path = Path(self.phasing_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_phasing_file(self) -> bool:
        return self.phasing_path.exists()

    @property
    def calendar_path(self) -> Path:
        path = Path(self.calendar_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_calendar_file(self) -> bool:
        return self.calendar_path.exists()

    @property
    def markets_path(self) -> Path:
        path = Path(self.markets_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_markets_file(self) -> bool:
        return self.markets_path.exists()

    @property
    def contribution_path(self) -> Path:
        path = Path(self.contribution_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_contribution_file(self) -> bool:
        return self.contribution_path.exists()

    @property
    def stores_path(self) -> Path:
        path = Path(self.stores_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_stores_file(self) -> bool:
        return self.stores_path.exists()

    @property
    def store_sales_path(self) -> Path:
        path = Path(self.store_sales_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_store_sales_file(self) -> bool:
        return self.store_sales_path.exists()

    @property
    def ebitda_path(self) -> Path:
        path = Path(self.ebitda_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_ebitda_file(self) -> bool:
        return self.ebitda_path.exists()

    @property
    def incremental_path(self) -> Path:
        path = Path(self.incremental_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_incremental_file(self) -> bool:
        return self.incremental_path.exists()

    @property
    def actuals_folder(self) -> Path:
        path = Path(self.actuals_folder_name)
        return path if path.is_absolute() else ROOT / path

    @property
    def has_actuals_folder(self) -> bool:
        return self.actuals_folder.is_dir()

    @property
    def has_weights_file(self) -> bool:
        return self.weights_path.exists()

    @property
    def has_context_file(self) -> bool:
        return self.context_path.exists()

    @property
    def has_owners_file(self) -> bool:
        return self.owners_path.exists()

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
        owners_file=_env("CEOOS_OWNERS_FILE") or DEFAULT_OWNERS_FILE,
        context_file=_env("CEOOS_CONTEXT_FILE") or DEFAULT_CONTEXT_FILE,
        kpi_file=_env("CEOOS_KPI_FILE") or DEFAULT_KPI_FILE,
        weights_file=_env("CEOOS_WEIGHTS_FILE") or DEFAULT_WEIGHTS_FILE,
        actuals_file=_env("CEOOS_ACTUALS_FILE") or DEFAULT_ACTUALS_FILE,
        actuals_folder_name=_env("CEOOS_ACTUALS_FOLDER") or DEFAULT_ACTUALS_FOLDER,
        divergence_file=_env("CEOOS_DIVERGENCE_FILE") or DEFAULT_DIVERGENCE_FILE,
        partners_file=_env("CEOOS_PARTNERS_FILE") or DEFAULT_PARTNERS_FILE,
        distribution_file=(_env("CEOOS_DISTRIBUTION_FILE")
                           or DEFAULT_DISTRIBUTION_FILE),
        phasing_file=_env("CEOOS_PHASING_FILE") or DEFAULT_PHASING_FILE,
        calendar_file=_env("CEOOS_CALENDAR_FILE") or DEFAULT_CALENDAR_FILE,
        markets_file=_env("CEOOS_MARKETS_FILE") or DEFAULT_MARKETS_FILE,
        org_file=_env("CEOOS_ORG_FILE") or DEFAULT_ORG_FILE,
        snowflake_connection=snowflake_connection,
    )


settings = load_settings()
