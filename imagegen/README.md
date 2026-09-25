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

`stabilityai/sdxl-turbo` par défaut (`IMAGE_GEN_MODEL`) : SDXL distillé
pour générer en 4 pas sans guidance, quelques secondes sur GPU, ~7 Go de
VRAM en fp16. Bien meilleur que `stabilityai/sd-turbo` (l'ancien défaut,
~2 Go), qui reste le bon choix sans GPU ou avec peu de RAM : sur CPU,
sdxl-turbo demande ~12 Go de RAM. Licence de sdxl-turbo : usage non
commercial (usage personnel OK).

Tout modèle diffusers texte→image fonctionne (`IMAGE_GEN_MODEL`, par
exemple un SDXL photoréaliste). Les modèles « turbo » connus ont leurs
réglages (pas, guidance, taille) dans `_PRESETS` ; pour les autres, 25 pas,
guidance 6, 768 px, surchargeables via `IMAGE_GEN_STEPS`,
`IMAGE_GEN_GUIDANCE`, `IMAGE_GEN_SIZE`.

## Le prompt

Le backend ne transmet pas le titre brut : le LLM (Ollama ou Claude)
décrit d'abord en anglais, en une phrase, à quoi ressemble le plat servi
(contenant, couleurs, garniture), à partir du titre, des ingrédients et
des dernières étapes (souvent le dressage). Le style photo vient après.
Deux raisons : ces modèles comprennent mal le français, et ils ne lisent
que 77 tokens (un titre français + une liste d'ingrédients remplissait
tout, style compris).

## Gestion de la VRAM

Le modèle n'est chargé qu'à la demande et libéré immédiatement après
chaque génération (`app.py:_generate_sync`) plutôt que gardé résident en
permanence comme le fait Ollama (`OLLAMA_KEEP_ALIVE=24h`) : sur un GPU de
10 Go déjà occupé aux trois quarts par le modèle Ollama, garder aussi ce
modèle résident dépasserait le budget disponible. En échange, chaque
génération ajoute quelques secondes de chargement — acceptable pour une
action ponctuelle (créer/éditer une recette), pas pour un usage répété.

Le modèle Ollama occupant presque tout le GPU, le backend le décharge
juste avant de demander une image (`IMAGE_GEN_FREE_GPU=true`, par défaut) ;
Ollama le recharge tout seul à la prochaine extraction, en quelques
secondes. Si le chargement GPU échoue quand même (VRAM insuffisante,
pilote absent...), repli automatique sur CPU (beaucoup plus lent, mais
fonctionnel).

## API

- `POST /generate` `{"prompt": "...", "negative_prompt": "..."}` → image
  PNG en réponse brute.
- `GET /health` → modèle, pas, guidance, taille et disponibilité de CUDA.

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
