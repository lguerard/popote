# Image generique (pas de base CUDA officielle) : le runtime CUDA vient de
# la roue torch elle-meme (voir requirements.txt), le driver est injecte
# par le NVIDIA Container Toolkit au demarrage du conteneur, exactement
# comme pour le service ollama.
FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
