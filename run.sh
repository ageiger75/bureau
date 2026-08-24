#!/usr/bin/env bash
# CEO OS — Decision Room · démarrage local
# Crée le venv si absent, applique les migrations, sème les données fictives, lance le serveur.
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python

if [ ! -x "$PY" ]; then
  echo "→ Création de l'environnement virtuel"
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi

if [ ! -f .env ]; then
  echo "→ .env absent : copie de .env.example"
  cp .env.example .env
fi

echo "→ Migrations"
$PY -m app.cli migrate

if [ "${1:-}" = "--reset" ]; then
  echo "→ Réinitialisation des données fictives"
  $PY -m app.cli seed --reset
else
  $PY -m app.cli seed
fi

# L'adresse d'écoute n'est pas passée en argument : elle est fixée dans app/cli.py, pour
# qu'aucune commande ne puisse exposer le service hors de la boucle locale.
# Le port suit la variable PORT si elle est définie, sinon 8000.
exec $PY -m app.cli serve --reload
