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
