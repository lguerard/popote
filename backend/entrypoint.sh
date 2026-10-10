#!/bin/sh
# Instagram, TikTok et YouTube changent régulièrement leurs pages : une
# version de yt-dlp de quelques semaines suffit à faire échouer toutes les
# vidéos. Mise à jour à chaque démarrage du conteneur (désactivable avec
# YTDLP_AUTO_UPDATE=false) ; sans réseau, la version de l'image est gardée.
if [ "${YTDLP_AUTO_UPDATE:-true}" = "true" ]; then
    if timeout 120 pip install --quiet --no-cache-dir --upgrade yt-dlp >/dev/null 2>&1; then
        echo "yt-dlp à jour : $(python -m yt_dlp --version)"
    else
        echo "yt-dlp : mise à jour impossible, version de l'image conservée"
    fi
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
