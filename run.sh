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

# Le défaut est la démonstration, et c'est volontaire : l'entrepôt ne se joint jamais par
# accident. Mais un écran de démonstration ressemble assez à l'écran réel pour qu'on le
# lise sans s'en apercevoir — d'où cette ligne, dite au lancement plutôt que découverte en
# bas de page.
if grep -qE '^CEOOS_DATA_SOURCE=mock' .env 2>/dev/null && [ -z "${CEOOS_DATA_SOURCE:-}" ]; then
  echo "→ Données de démonstration. Pour les vrais chiffres, dans .env :"
  echo "     CEOOS_DATA_SOURCE=snowflake"
  echo "     CEOOS_SNOWFLAKE_CONNECTION=<le nom entre crochets de ~/.snowflake/connections.toml>"
fi

# Un serveur déjà lancé donne « Address already in use », qui ne dit ni qui occupe le port
# ni quoi faire. Le cas est fréquent — on relance dans une seconde fenêtre en oubliant la
# première — et le message par défaut envoie chercher au mauvais endroit.
PORT_USED="${PORT:-8000}"
if command -v lsof >/dev/null 2>&1; then
  BUSY="$(lsof -ti ":$PORT_USED" 2>/dev/null || true)"
  if [ -n "$BUSY" ]; then
    echo "Le port $PORT_USED est déjà occupé (processus $BUSY)."
    echo "C'est presque toujours un CEO OS lancé dans une autre fenêtre."
    echo
    echo "  Arrêter l'autre :  lsof -ti :$PORT_USED | xargs kill"
    echo "  Ou en ouvrir un second ailleurs :  PORT=8001 ./run.sh"
    exit 1
  fi
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
