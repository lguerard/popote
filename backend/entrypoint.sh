#!/bin/sh
# Instagram, TikTok et YouTube changent régulièrement leurs pages : une
# version de yt-dlp (vidéos) ou de gallery-dl (posts en images) de quelques
# semaines suffit à tout faire échouer. Mise à jour à chaque démarrage du
# conteneur (désactivable avec YTDLP_AUTO_UPDATE=false) ; sans réseau, les
# versions de l'image sont gardées.
if [ "${YTDLP_AUTO_UPDATE:-true}" = "true" ]; then
    if timeout 180 pip install --quiet --no-cache-dir --upgrade yt-dlp gallery-dl >/dev/null 2>&1; then
        echo "yt-dlp $(python -m yt_dlp --version), gallery-dl $(gallery-dl --version) : à jour"
    else
        echo "yt-dlp / gallery-dl : mise à jour impossible, versions de l'image conservées"
    fi
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
