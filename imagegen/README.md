# imagegen

Petit service HTTP autonome qui génère une image à partir d'un prompt
texte, en local, sur le GPU du serveur. Utilisé par le backend comme
vignette de secours quand une recette n'a pas de photo (voir
`backend/app/services/image_service.py` et `POST /api/recipes/{id}/thumbnail/generate`).

## Pourquoi un conteneur à part

Torch + diffusers sont de grosses dépendances avec leur propre runtime CUDA
embarqué dans la roue pip elle-même. Le backend utilise déjà des roues
CUDA épinglées précisément pour ctranslate2/Whisper (`nvidia-cublas-cu12`,
`nvidia-cudnn-cu12`) — les installer dans le même environnement Python que
torch risquerait un conflit de versions. Un conteneur séparé isole
complètement les deux, comme `ollama` est déjà son propre conteneur.

## Modèle

`stabilityai/sd-turbo` par défaut (`IMAGE_GEN_MODEL`) : un modèle distillé
pour générer en 1 à 4 pas d'inférence sans guidance, donc rapide (quelques
secondes sur GPU) et léger (~2 Go en fp16). Changeable via `.env`
(`IMAGE_GEN_MODEL`, `IMAGE_GEN_DEVICE=cuda|cpu`).

## Gestion de la VRAM

Le modèle n'est chargé qu'à la demande et libéré immédiatement après
chaque génération (`app.py:_generate_sync`) plutôt que gardé résident en
permanence comme le fait Ollama (`OLLAMA_KEEP_ALIVE=24h`) : sur un GPU de
10 Go déjà occupé aux trois quarts par le modèle Ollama, garder aussi ce
modèle résident dépasserait le budget disponible. En échange, chaque
génération ajoute quelques secondes de chargement — acceptable pour une
action ponctuelle (créer/éditer une recette), pas pour un usage répété.

Si le chargement GPU échoue (VRAM insuffisante, pilote absent...), repli
automatique sur CPU (beaucoup plus lent, mais fonctionnel).

## API

- `POST /generate` `{"prompt": "...", "negative_prompt": "..."}` → image
  PNG en réponse brute.
- `GET /health` → `{"status": "ok", "model": "...", "cuda_available": bool}`.

## Non testé en conditions réelles

Écrit et relu depuis un environnement sans GPU ni Docker disponible pour
un build réel — la version torch/CUDA (`torch==2.4.1+cu121`) est un choix
raisonnable mais pas vérifié sur votre matériel. Après
`docker compose build imagegen`, si le build ou le premier appel échoue,
regarder en priorité :
- `docker compose logs imagegen` pour une erreur CUDA/driver ;
- la compatibilité de votre pilote NVIDIA avec CUDA 12.1 (`nvidia-smi` en
  haut à droite indique la version CUDA maximale supportée) ;
- si besoin, changer `+cu121` dans `imagegen/requirements.txt` pour la
  version correspondant à votre pilote.
