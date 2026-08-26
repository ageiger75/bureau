#!/usr/bin/env bash
# CEO OS — Decision Room · lancement depuis le Finder
#
# Fichier `.command` : double-cliquable depuis le Finder ou le Dock, qui l'ouvre dans
# Terminal. Il fait les trois gestes dans l'ordre — récupérer la dernière version,
# démarrer le serveur, ouvrir le navigateur — pour que l'usage courant ne demande aucune
# ligne de commande.
#
# Le développement se fait sur GitHub ; ce poste ne fait que lire et exécuter. C'est
# pourquoi la mise à jour est en avance rapide seulement : ce script ne fusionne rien et
# n'écrase aucun travail local.

set -uo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
URL="http://127.0.0.1:${PORT}"

echo "CEO OS — Decision Room"
echo

# --------------------------------------------------------------- mise à jour

if [ -d .git ]; then
  echo "→ Recherche d'une version plus récente sur GitHub"
  # --ff-only : si l'historique local a divergé, on s'arrête plutôt que de fusionner.
  # Un échec ici ne doit pas empêcher de travailler avec la version déjà présente.
  if git pull --ff-only 2>&1 | sed 's/^/   /'; then
    :
  else
    echo "   Mise à jour impossible — le dossier a divergé, ou GitHub est injoignable."
    echo "   Démarrage avec la version déjà présente."
  fi
else
  echo "→ Ce dossier n'est pas un clone Git : aucune mise à jour automatique."
  echo "   Pour en faire un clone une fois pour toutes, voir le README."
fi
echo

# --------------------------------------------------------------- navigateur

# Ouvert en tâche de fond : `run.sh` ne rend jamais la main, puisqu'il devient le serveur.
# On attend que le port réponde plutôt que de deviner un délai.
(
  for _ in $(seq 1 60); do
    if curl -s -o /dev/null "${URL}/health" 2>/dev/null; then
      open "$URL" 2>/dev/null || true
      exit 0
    fi
    sleep 0.5
  done
) &

# --------------------------------------------------------------- serveur

echo "→ Démarrage · ${URL}"
echo "   Pour arrêter : Ctrl-C dans cette fenêtre."
echo
exec bash run.sh "$@"
