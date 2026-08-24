"""Garde-fous de configuration.

Le brief §13 exige qu'aucune action externe ne soit possible. Une interdiction qui n'est
qu'écrite dans un fichier de configuration finit par être desserrée un jour de pression.
Ces tests vérifient qu'elle est portée par le code : le service refuse de démarrer.
"""

from __future__ import annotations

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
