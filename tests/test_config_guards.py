"""Garde-fous de configuration.

Le brief §13 exige qu'aucune action externe ne soit possible. Une interdiction qui n'est
qu'écrite dans un fichier de configuration finit par être desserrée un jour de pression.
Ces tests vérifient qu'elle est portée par le code : le service refuse de démarrer.
"""

from __future__ import annotations

import os

import pytest

from app import cli, config
from app.db import engine
from tests.conftest import TEST_DIR


def test_la_suite_ecrit_dans_une_base_jetable():
    """Garde-fou d'isolation.

    Si cette assertion tombe, un test est en train d'écrire dans `var/ceo-os.db`, donc de
    détruire les dossiers de travail. Elle vit ici et non dans `conftest.py` : pytest ne
    collecte pas les fonctions de test déclarées dans un conftest, où elle ne serait
    jamais exécutée.
    """
    assert str(TEST_DIR) in str(engine.url)
    assert "var/ceo-os.db" not in str(engine.url)


def test_execute_empeche_le_demarrage(monkeypatch):
    """CEOOS_AUTONOMY_LEVEL=EXECUTE n'est pas un réglage disponible."""
    monkeypatch.setenv("CEOOS_AUTONOMY_LEVEL", "EXECUTE")

    with pytest.raises(config.ConfigError) as excinfo:
        config.load_settings()

    message = str(excinfo.value)
    assert "EXECUTE" in message
    assert "gouvernance" in message  # le refus explique la raison, pas seulement la règle


def test_niveaux_autorises_sont_read_et_prepare():
    assert config.AUTONOMY_LEVELS == ("READ", "PREPARE")


@pytest.mark.parametrize("level", ["READ", "PREPARE", "prepare"])
def test_niveaux_valides_sont_acceptes(monkeypatch, level):
    monkeypatch.setenv("CEOOS_AUTONOMY_LEVEL", level)

    assert config.load_settings().autonomy_level == level.upper()


def test_secret_faible_est_refuse_hors_local(monkeypatch):
    """En local un secret par défaut est acceptable ; en pilote il ne l'est pas."""
    monkeypatch.setenv("CEOOS_ENV", "pilot")
    monkeypatch.setenv("CEOOS_SECRET_KEY", "trop-court")

    with pytest.raises(config.ConfigError) as excinfo:
        config.load_settings()

    assert "32" in str(excinfo.value)


def test_secret_absent_est_tolere_en_local(monkeypatch):
    monkeypatch.setenv("CEOOS_ENV", "local")
    monkeypatch.setenv("CEOOS_SECRET_KEY", "")

    settings = config.load_settings()

    assert settings.secret_key
    assert settings.is_local


def test_environnement_inconnu_est_refuse(monkeypatch):
    monkeypatch.setenv("CEOOS_ENV", "staging")

    with pytest.raises(config.ConfigError):
        config.load_settings()


def test_chemin_sqlite_est_rendu_absolu(monkeypatch):
    """Un chemin relatif se résoudrait selon le répertoire de travail : le serveur et les
    tests ouvriraient alors deux fichiers différents."""
    monkeypatch.setenv("CEOOS_DATABASE_URL", "sqlite:///var/exemple.db")

    path = config.load_settings().sqlite_path

    assert path is not None
    assert path.is_absolute()
    assert path.parent == config.ROOT / "var"


def test_url_postgresql_ne_produit_aucun_chemin_de_fichier(monkeypatch):
    monkeypatch.setenv(
        "CEOOS_DATABASE_URL", "postgresql+psycopg://user@host:5432/ceoos"
    )

    settings = config.load_settings()

    assert not settings.is_sqlite
    assert settings.sqlite_path is None


def test_adresse_d_ecoute_n_est_pas_configurable():
    """Le port est négociable, l'hôte non.

    L'environnement doit pouvoir assigner un port libre ; en revanche aucune variable ni
    aucun argument ne doit pouvoir faire écouter le service ailleurs que sur la boucle
    locale, sans quoi des dossiers confidentiels deviendraient accessibles sur le réseau.
    """
    assert cli.SERVE_HOST == "127.0.0.1"
    assert cli.serve_config()[0] == "127.0.0.1"


def test_port_suit_la_variable_d_environnement(monkeypatch):
    monkeypatch.setenv("PORT", "8123")

    assert cli.serve_config() == ("127.0.0.1", 8123)


@pytest.mark.parametrize("value", ["", "abc", "0", "-1", "99999", "80.5"])
def test_port_invalide_retombe_sur_le_defaut(monkeypatch, value):
    """Un port illisible ne doit pas empêcher le démarrage : on prévient et on continue."""
    monkeypatch.setenv("PORT", value)

    assert cli.serve_config() == ("127.0.0.1", cli.DEFAULT_PORT)


def test_boucle_locale_inclut_le_client_de_test():
    """`testclient` est l'hôte présenté par starlette.testclient : sans lui, la suite de
    tests se heurterait au middleware qui n'accepte que la boucle locale."""
    assert "127.0.0.1" in config.LOOPBACK_HOSTS
    assert "testclient" in config.LOOPBACK_HOSTS


# ------------------------------------------------- la configuration du poste reste dehors
#
# Elle n'y restait pas. Dès qu'une connexion Snowflake était écrite dans `.env`, la suite
# lisait le vrai entrepôt : des tests lents, non déterministes, consommant du crédit, et
# dix-neuf qui échouaient en accusant le dernier commit poussé. Une suite qui dépend de la
# configuration de la machine n'atteste de rien — et elle avait l'air verte partout
# ailleurs, ce qui est la pire forme de ce défaut.


def test_le_fichier_env_peut_etre_ignore(tmp_path, monkeypatch):
    from app.config import _load_dotenv

    dotenv = tmp_path / ".env"
    dotenv.write_text("CEOOS_TEST_MARKER=depuis-le-fichier\n", encoding="utf-8")

    monkeypatch.delenv("CEOOS_TEST_MARKER", raising=False)
    monkeypatch.setenv("CEOOS_DOTENV", "0")
    _load_dotenv(dotenv)

    assert "CEOOS_TEST_MARKER" not in os.environ


def test_le_fichier_env_est_lu_par_defaut(tmp_path, monkeypatch):
    """Le garde-fou ne doit pas rendre le fichier inutile : c'est ainsi que le poste se
    configure une fois pour toutes."""
    from app.config import _load_dotenv

    dotenv = tmp_path / ".env"
    dotenv.write_text("CEOOS_TEST_MARKER=depuis-le-fichier\n", encoding="utf-8")

    monkeypatch.delenv("CEOOS_TEST_MARKER", raising=False)
    monkeypatch.delenv("CEOOS_DOTENV", raising=False)
    _load_dotenv(dotenv)

    assert os.environ["CEOOS_TEST_MARKER"] == "depuis-le-fichier"
    monkeypatch.delenv("CEOOS_TEST_MARKER", raising=False)


def test_la_suite_tourne_sur_des_donnees_fictives():
    """Quelle que soit la machine. Un test qui lit l'entrepôt de production est lent, non
    déterministe, et coûte de l'argent à chaque exécution."""
    from app.config import settings

    assert settings.reads_warehouse is False


def test_the_suite_never_reads_the_files_of_the_machine_it_runs_on():
    """The invariant eleven failing tests bought.

    Building business units reads the weights and the published actuals from disk on every
    call — correct in the application, and a hidden dependency in a suite. On a machine
    holding those files, fixtures worth an invented million came back carrying the house's
    real figures, and the suite failed while blaming the last commit. It was right to fail
    and wrong about the cause.

    So no path this suite can reach may resolve inside the working directory. Checked here
    rather than trusted to a fixture nobody re-reads: this test fails the moment a new file
    is added to the configuration and not redirected, which is precisely when the next
    person would otherwise spend an afternoon on it.
    """
    from pathlib import Path

    from app.config import ROOT, settings

    working = (ROOT / "var").resolve()
    for name in ("budget_path", "owners_path", "context_path", "kpi_path",
                 "weights_path", "actuals_path", "divergence_path", "actuals_folder"):
        path = Path(getattr(settings, name)).resolve()
        assert working not in path.parents and path != working, (
            "%s pointe dans le var/ de travail pendant les tests : la suite lirait les "
            "chiffres réels de la maison." % name)
