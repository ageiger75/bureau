#!/usr/bin/env bash
# CEO OS — Performance Cockpit · lancement depuis le Finder
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

echo "CEO OS — Performance Cockpit"
echo

# --------------------------------------------------------------- mise à jour

if [ -d .git ]; then
  echo "→ Recherche d'une version plus récente sur GitHub"
  # --ff-only : si l'historique local a divergé, on s'arrête plutôt que de fusionner.
  # Un échec ici ne doit pas empêcher de travailler avec la version déjà présente.
  if git pull --ff-only 2>&1 | sed 's/^/   /'; then
    :
  else
    # « Le dossier a divergé » est exact et n'apprend rien. Deux causes très
    # différentes se cachent derrière, et une seule appelle un geste : du travail
    # commité ici et jamais poussé — ce qui arrive dès qu'un agent écrit du code sur
    # ce poste. Le dire, plutôt que de laisser chercher.
    AHEAD="$(git log --oneline @{u}..HEAD 2>/dev/null | wc -l | tr -d ' ')"
    if [ "${AHEAD:-0}" != "0" ]; then
      echo
      echo "   ${AHEAD} commit(s) fait(s) ici et jamais poussé(s) — c'est pour ça que la"
      echo "   mise à jour s'arrête. Rien n'est perdu. Dans une autre fenêtre :"
      echo "       cd $(pwd) && git pull --rebase && git push"
    else
      echo "   Mise à jour impossible — GitHub est injoignable, ou l'historique a divergé."
    fi
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
# Deux gestes une fois le serveur debout, dans cet ordre précis.
#
# D'abord ouvrir l'écran, qui s'affiche instantanément sur la dernière lecture. Puis
# demander une relecture en tâche de fond, qui prend des minutes et n'empêche personne de
# lire pendant ce temps.
#
# La version précédente oubliait le cache avant de démarrer, ce qui faisait payer
# l'attente complète à chaque ouverture — l'inverse de ce qu'on cherchait. Un écran vieux
# de quelques heures, affiché tout de suite et portant son heure de lecture, vaut mieux
# qu'un écran frais qu'on attend trois minutes et qu'on finit par ne plus ouvrir.
(
  for _ in $(seq 1 60); do
    if curl -s -o /dev/null "${URL}/health" 2>/dev/null; then
      open "$URL" 2>/dev/null || true
      # Relecture derrière l'écran déjà affiché. La page surveille elle-même l'arrivée
      # des chiffres du jour et se recharge : rien à faire, rien à guetter dans ce
      # journal — une consigne qui demande de lire une trace de serveur est une consigne
      # qui ne sera pas suivie, et qui n'a pas à l'être.
      curl -s -o /dev/null --max-time 900 "${URL}/?refresh=1" 2>/dev/null || true
      exit 0
    fi
    sleep 0.5
  done
) &

# --------------------------------------------------------------- serveur

echo "→ Démarrage · ${URL}"
echo
echo "   Cette fenêtre devient le serveur : elle n'accepte plus de commandes."
echo "   Pour taper autre chose, ouvrir une nouvelle fenêtre avec ⌘T, puis :"
echo "       cd $(pwd)"
echo
echo "   L'écran s'ouvre sur la dernière lecture, puis se rafraîchit en arrière-plan."
echo "   Rien à surveiller ici : la page se recharge d'elle-même quand les chiffres"
echo "   du jour arrivent, et l'horodatage en haut dit toujours lesquels sont affichés."
echo
echo "   Pour arrêter le serveur : Ctrl-C ici, ou fermer la fenêtre."
echo
exec bash run.sh "$@"
