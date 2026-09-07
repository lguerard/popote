# Tag Debian epingle : python:3.11-slim suit la derniere stable et bascule
# de version majeure sans preavis, ce qui change les paquets apt installes
# juste en dessous et casse le build sans qu'aucun fichier n'ait bouge.
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install browsers with the SAME playwright version pinned in requirements.txt
# (installing them before would fetch a mismatched chromium revision)
RUN playwright install chromium --with-deps

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
