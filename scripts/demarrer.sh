#!/usr/bin/env bash
# Démarre (ou met à jour) Popote. Si les conteneurs GPU ne peuvent pas
# démarrer (pilote NVIDIA en panne, mise à jour non suivie d'un
# redémarrage…), relance tout en mode CPU plutôt que de laisser l'appli
# injoignable. Les arguments sont passés à `docker compose up -d`
# (ex. : ./scripts/demarrer.sh --build).
set -u
cd "$(dirname "$0")/.."

backend_running() {
    docker compose ps --status running --services 2>/dev/null | grep -qx backend
}

if docker compose up -d "$@" && backend_running; then
    echo "✓ Popote est démarré (GPU)."
    exit 0
fi

echo
echo "⚠ Les conteneurs GPU ne démarrent pas. Vérifie le pilote : nvidia-smi"
echo "  (souvent réglé par un redémarrage après une mise à jour du pilote)."
echo "  Popote redémarre en mode CPU : tout fonctionne, en plus lent."
echo
if docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d "$@" && backend_running; then
    echo "✓ Popote est démarré en mode CPU. Une fois le GPU réparé : ./scripts/demarrer.sh"
else
    echo "✗ Popote ne démarre pas, même sans GPU : docker compose logs backend"
    exit 1
fi
