#!/usr/bin/env bash
# Verification mensuelle : un nouveau modele Ollama fait-il mieux que
# l'actuel, tout en tenant sur le GPU ? Voir scripts/model_watch/README.md.
#
# A lancer via cron depuis le host (pas depuis un conteneur : il a besoin
# de `docker compose` pour piloter les conteneurs). Idempotent et sans
# argument.
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

echo "model_watch: lancement de l'évaluation (peut prendre longtemps — téléchargement de modèles)…"
RESULT="$(docker compose exec -T backend python -m app.scripts.model_watch.run_eval)"

OK="$(echo "$RESULT" | jq -r '.ok')"
if [ "$OK" != "true" ]; then
  echo "model_watch: échec de l'évaluation : $(echo "$RESULT" | jq -r '.error')" >&2
  set -a; source .env; set +a
  python3 "$SCRIPT_DIR/send_report.py" --old-model "$OLD_MODEL" --new-model "$OLD_MODEL" --error "$(echo "$RESULT" | jq -r '.error')"
  exit 1
fi

WINNER="$(echo "$RESULT" | jq -r '.winner // empty')"
NEW_MODEL="$OLD_MODEL"

if [ -n "$WINNER" ] && [ "$WINNER" != "$OLD_MODEL" ]; then
  echo "model_watch: nouveau modèle retenu : $WINNER (ancien : $OLD_MODEL)"
  sed -i.bak "s|^OLLAMA_MODEL=.*|OLLAMA_MODEL=${WINNER}|" .env && rm -f .env.bak
  docker compose up -d --no-deps backend
  sleep 5
  STATUS="$(docker compose ps backend --format '{{.Status}}' 2>/dev/null || echo inconnu)"
  echo "model_watch: backend redémarré avec $WINNER — statut : $STATUS"
  NEW_MODEL="$WINNER"
else
  echo "model_watch: aucun modèle candidat n'a fait significativement mieux — pas de changement."
fi

set -a; source .env; set +a
echo "$RESULT" | python3 "$SCRIPT_DIR/send_report.py" --old-model "$OLD_MODEL" --new-model "$NEW_MODEL"
