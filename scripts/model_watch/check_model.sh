#!/usr/bin/env bash
# Verification mensuelle : un nouveau modele Ollama fait-il mieux que
# l'actuel, tout en tenant sur le GPU ? Voir scripts/model_watch/README.md.
#
# A lancer via cron depuis le host (pas depuis un conteneur : il a besoin
# de `docker compose` pour piloter les conteneurs). Idempotent et sans
# argument.
#
# Par défaut, RAPPORT SEULEMENT : le meilleur candidat est signalé dans le
# rapport, .env n'est jamais modifié. Bascule automatique (réécriture de
# OLLAMA_MODEL dans .env + redémarrage du backend) uniquement avec
# MODEL_WATCH_AUTO_SWITCH=true dans .env ou l'environnement.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

for bin in docker jq python3; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "model_watch: '$bin' est requis mais introuvable dans PATH" >&2
    exit 1
  fi
done

if [ ! -f .env ]; then
  echo "model_watch: .env introuvable dans $REPO_ROOT" >&2
  exit 1
fi

OLD_MODEL="$(grep -E '^OLLAMA_MODEL=' .env | head -1 | cut -d= -f2-)"
echo "model_watch: modèle actuel = ${OLD_MODEL:-?}"

set -a; source .env; set +a
AUTO_SWITCH="${MODEL_WATCH_AUTO_SWITCH:-false}"

# Les réglages MODEL_WATCH_* de .env ne font pas partie de l'environnement
# du conteneur backend : on les lui transmet pour cette commande.
EXEC_ENV=()
while IFS= read -r assignment; do
  EXEC_ENV+=(-e "$assignment")
done < <(env | grep -E '^MODEL_WATCH_(VRAM_[A-Z_]+|MAX_CANDIDATES|MIN_IMPROVEMENT)=.+' || true)

echo "model_watch: lancement de l'évaluation (peut prendre longtemps — téléchargement de modèles)…"
RESULT="$(docker compose exec -T ${EXEC_ENV[@]+"${EXEC_ENV[@]}"} backend python -m app.scripts.model_watch.run_eval)"

OK="$(echo "$RESULT" | jq -r '.ok')"
if [ "$OK" != "true" ]; then
  echo "model_watch: échec de l'évaluation : $(echo "$RESULT" | jq -r '.error')" >&2
  python3 "$SCRIPT_DIR/send_report.py" --old-model "$OLD_MODEL" --new-model "$OLD_MODEL" --error "$(echo "$RESULT" | jq -r '.error')"
  exit 1
fi

WINNER="$(echo "$RESULT" | jq -r '.winner // empty')"
NEW_MODEL="$OLD_MODEL"

if [ -n "$WINNER" ] && [ "$WINNER" != "$OLD_MODEL" ]; then
  if [ "$AUTO_SWITCH" = "true" ]; then
    echo "model_watch: nouveau modèle retenu : $WINNER (ancien : $OLD_MODEL)"
    sed -i.bak "s|^OLLAMA_MODEL=.*|OLLAMA_MODEL=${WINNER}|" .env && rm -f .env.bak
    docker compose up -d --no-deps backend
    sleep 5
    STATUS="$(docker compose ps backend --format '{{.Status}}' 2>/dev/null || echo inconnu)"
    echo "model_watch: backend redémarré avec $WINNER — statut : $STATUS"
    NEW_MODEL="$WINNER"
  else
    echo "model_watch: $WINNER fait mieux que $OLD_MODEL — non appliqué (rapport seulement, MODEL_WATCH_AUTO_SWITCH=true pour basculer)."
  fi
else
  echo "model_watch: aucun modèle candidat n'a fait significativement mieux — pas de changement."
fi

echo "$RESULT" | python3 "$SCRIPT_DIR/send_report.py" --old-model "$OLD_MODEL" --new-model "$NEW_MODEL" --winner "${WINNER:-}"
