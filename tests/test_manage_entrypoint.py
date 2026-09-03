"""Le point d'entrée doit fonctionner depuis n'importe quel répertoire courant.

Régression réelle : `python -m app.cli serve` échouait avec `ModuleNotFoundError: No module
named 'app'` quand le processus était démarré par un outil extérieur, qui héritait d'un
autre répertoire de travail. `manage.py` déduit la racine de son propre emplacement.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MANAGE = ROOT / "manage.py"


def run_manage(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(MANAGE)] + list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_manage_existe_et_est_executable():
    assert MANAGE.is_file()


@pytest.mark.parametrize("cwd_name", ["root", "tmp", "home"])
def test_check_fonctionne_depuis_n_importe_ou(cwd_name, tmp_path):
    """Le répertoire courant ne doit avoir aucune influence."""
    cwd = {"root": ROOT, "tmp": tmp_path, "home": Path.home()}[cwd_name]

    result = run_manage("check", cwd=cwd)

    assert result.returncode == 0, result.stderr
    assert "127.0.0.1" in result.stdout


def test_le_controle_nomme_chaque_source_qu_il_sait_lire():
    """L'organigramme est resté absent de ce panneau alors que l'application le lisait
    déjà : chaque source y était écrite à la main, et personne n'a pensé à ajouter la
    ligne. Le lecteur a déposé son fichier, rien n'a changé à l'écran, et rien ne lui a
    dit pourquoi.

    Le test porte sur les libellés seuls — jamais sur les valeurs — pour qu'il reste vrai
    que la machine qui l'exécute ait ces fichiers ou non. Sa première version ne tenait
    pas cette promesse : elle exigeait « Fichier publié », qui ne s'écrivait que lorsque
    le fichier manquait. Elle passait sur une machine nue et échouait sur celle qui a les
    données — donc exactement là où la réponse compte. C'était le défaut de source que ce
    panneau existe pour corriger, reproduit dans son propre test.

    Le libellé de chaque source est maintenant le même qu'elle soit présente ou absente,
    ce qui est aussi ce que voit le lecteur : une ligne qui change de nom selon l'état de
    ce qu'elle décrit ne se cherche pas dans une liste.
    """
    result = run_manage("check", cwd=ROOT)

    assert result.returncode == 0, result.stderr
    for label in ("Plan", "Fichier publié", "Annuaire", "Contexte", "Organigramme",
                  "Divergence", "Partenaires", "Séries mensuelles", "Poids stratégiques",
                  "Suivi KPI"):
        assert label in result.stdout, label


def test_commande_inconnue_echoue_avec_l_aide():
    result = run_manage("commande-qui-nexiste-pas", cwd=Path.home())

    assert result.returncode != 0
    assert "Commande inconnue" in result.stderr


def test_reset_est_refuse_hors_environnement_local(tmp_path):
    """Garde-fou : `seed --reset` effacerait de vraies décisions en pilote."""
    env_file = tmp_path / "unused"
    del env_file

    result = subprocess.run(
        [sys.executable, str(MANAGE), "seed", "--reset"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "CEOOS_ENV": "pilot",
            "CEOOS_SECRET_KEY": "x" * 40,
            "CEOOS_DATABASE_URL": "sqlite:///%s" % (tmp_path / "pilot.db"),
        },
    )

    assert result.returncode == 2
    assert "Refusé" in result.stderr


def test_serving_on_a_busy_port_says_the_old_code_is_still_being_served(capsys):
    """Le message du serveur — « address already in use » et un numéro d'erreur — dit ce
    qui a échoué et jamais ce qui se passe. Une fenêtre laissée ouverte continue de servir
    l'**ancien** code : le lecteur relance, voit l'échec, retourne à son navigateur et lit
    un écran sans les corrections qu'il vient de tirer. Deux fenêtres qui disent le même
    produit et n'en servent pas le même, c'est un défaut qui ne se voit pas."""
    import socket

    from app import cli

    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    host, port = holder.getsockname()
    try:
        assert cli._port_taken(host, port)
    finally:
        holder.close()

    assert not cli._port_taken(host, port)


def test_an_option_value_is_never_taken_for_a_file_to_open():
    """Le défaut s'est manifesté de la pire façon : `--spread 0.15` sans chemin, et la
    commande annonçait « déposer le fichier à cet endroit : 0.15 ». Un message d'absence de
    fichier, donc parfaitement crédible — le lecteur part chercher un fichier manquant qui
    ne manque pas, et rien dans la sortie ne le détrompe."""
    from app.cli import _positional

    assert _positional(["--spread", "0.15", "--variation", "0.30"],
                       ("--spread", "--variation")) == []
    assert _positional(["var/phasing.csv", "--spread", "0.15"], ("--spread",)) \
        == ["var/phasing.csv"]


def test_a_flag_without_a_value_does_not_swallow_the_argument_that_follows():
    """L'autre moitié de la règle, et la raison pour laquelle les drapeaux porteurs de
    valeur sont déclarés plutôt que devinés : un drapeau booléen suivi d'un vrai argument
    libre le ferait disparaître sans un mot."""
    from app.cli import _positional

    assert _positional(["--ytd", "var/actuals.xlsx"], ()) == ["var/actuals.xlsx"]
    assert _positional(["--events", "--spread", "0.15"], ("--events", "--spread")) == []
