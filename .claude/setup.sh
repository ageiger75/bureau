#!/usr/bin/env bash
# Prépare une session : environnement virtuel, dépendances, schéma, données fictives.
# Idempotent — relançable sans effet de bord. Aucun appel réseau hors PyPI.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
fi

.venv/bin/python -m pip install --quiet -r requirements.txt

[ -f .env ] || cp .env.example .env

.venv/bin/python manage.py migrate >/dev/null
.venv/bin/python manage.py seed >/dev/null

echo "CEO OS prêt : .venv/bin/python -m pytest · .venv/bin/python manage.py serve"
