# Surveillance mensuelle des modèles Ollama

Vérifie une fois par mois si un nouveau modèle Ollama ferait mieux que
celui utilisé pour l'extraction de recettes (`OLLAMA_MODEL`), tout en
tenant dans la VRAM du GPU. Si oui, bascule dessus automatiquement et
t'envoie un email ; sinon, t'envoie un rapport "rien de nouveau".

## Comment ça marche

1. `check_model.sh` (ce dossier, lancé sur le host via cron) exécute
   l'évaluation **dans le conteneur backend** — c'est le seul endroit qui a
   accès au réseau Ollama et au code d'extraction du projet :
   ```
   docker compose exec -T backend python -m app.scripts.model_watch.run_eval
   ```
2. `run_eval.py` (dans `backend/app/scripts/model_watch/`) :
   - mesure la VRAM du GPU en direct (`nvidia-smi`), moins une marge de
     sécurité (`MODEL_WATCH_VRAM_HEADROOM_GB`) ;
   - construit une liste de modèles candidats : une petite liste de
     familles reconnues (`candidates.py:CURATED_FAMILIES`) plus une
     tentative de récupérer les nouveautés sur `ollama.com/library` (best
     effort — si le site a changé de structure, ça se dégrade juste vers
     la liste curée, sans planter) ;
   - pour chaque candidat, ne garde que la plus grosse variante qui tient
     dans le budget VRAM, d'après la taille **réelle** du manifest Ollama
     (pas une estimation à partir du nombre de paramètres) ;
   - `ollama pull` le modèle actuel et chaque candidat, puis fait tourner
     **le même prompt système et le même code de normalisation JSON que la
     vraie app** (`app.services.llm_service`) sur 3 recettes de test
     (`eval_cases.json` : une propre, une bruitée façon page web, une
     façon transcription orale) ;
   - note chaque extraction avec `scoring.py` (JSON valide, bons
     ingrédients trouvés, nombre d'étapes plausible, catégorie/langue
     correctes, portions correctes — voir le fichier pour le détail des
     points) ;
   - un candidat "gagne" s'il dépasse le score du modèle actuel d'au moins
     `MODEL_WATCH_MIN_IMPROVEMENT` points (5 par défaut, pour éviter de
     changer de modèle sur du bruit de mesure) ;
   - supprime (`ollama rm`) les candidats testés qui n'ont pas gagné, pour
     ne pas accumuler des dizaines de Go de modèles inutilisés. **Le
     modèle précédent n'est PAS supprimé** en cas de changement, pour que
     revenir en arrière soit instantané (pas besoin de re-télécharger).
   - imprime un seul objet JSON sur stdout (les logs vont sur stderr).
3. `check_model.sh` lit ce JSON. S'il y a un gagnant :
   - modifie `OLLAMA_MODEL=` dans `.env` ;
   - `docker compose up -d --no-deps backend` (recrée le conteneur avec la
     nouvelle variable d'env — un simple `restart` ne suffit pas, Compose
     ne relit `.env` qu'à la création du conteneur).
4. `send_report.py` envoie le rapport par email (SMTP, voir plus bas) et
   en garde toujours une copie locale dans `reports/YYYY-MM-DD.txt`, même
   si l'email échoue.

## Revenir en arrière si le nouveau modèle déçoit

L'email de changement donne toujours l'ancien modèle. Pour revenir :
```
# Dans .env :
OLLAMA_MODEL=<ancien modèle indiqué dans l'email>
# Puis :
docker compose up -d --no-deps backend
```
Le modèle précédent est toujours installé localement (non supprimé lors
d'un changement), donc ce redémarrage est immédiat.

## Installation

1. Configurer l'envoi d'email dans `.env` (voir la section "Surveillance
   mensuelle des modèles" de `.env.example`) — `MODEL_WATCH_SMTP_HOST` et
   `MODEL_WATCH_SMTP_TO` au minimum. Sans ça, le rapport est seulement
   écrit dans `scripts/model_watch/reports/`.
2. Vérifier que `jq` est installé sur le host (`apt install jq`).
3. Ajouter une tâche cron (voir `crontab.example`, chemin à adapter si
   besoin) : `crontab -e` puis coller la ligne.
4. Tester manuellement avant de laisser tourner en cron — ça peut prendre
   du temps la première fois (téléchargement de plusieurs modèles) :
   ```
   ./scripts/model_watch/check_model.sh
   ```

## Limites à connaître

- Le "score" est une heuristique déterministe (pas un jugement par un
  autre LLM) : il mesure ce qui compte pour CETTE app (JSON exploitable,
  bons ingrédients, structure plausible), pas une qualité générale du
  modèle. Un modèle peut être meilleur "en général" sans gagner ici, et
  inversement.
- La découverte de nouveaux modèles sur ollama.com est un scraping HTML
  best-effort : si le site change de structure, ça se dégrade silencieusement
  vers la liste curée (un avertissement apparaît dans le rapport).
- Chaque run peut télécharger plusieurs Go par candidat testé — surveiller
  `MODEL_WATCH_MAX_CANDIDATES` si la bande passante ou le disque sont
  limités.
- L'estimation VRAM (taille sur disque × 1.15 + 0.5 Go) est une marge
  raisonnable mais pas une garantie absolue ; `MODEL_WATCH_VRAM_HEADROOM_GB`
  existe pour ajuster la prudence.
