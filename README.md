# 🍳 Popote

Application self-hosted de gestion de recettes avec extraction par IA depuis
n'importe quelle source — vidéos YouTube/TikTok/Instagram, sites web, texte
brut, ou photo — accompagnée d'une application Android native.

---

## Fonctionnalités

### Extraction intelligente

- **Vidéos** (YouTube, TikTok, Instagram, et tout site supporté par yt-dlp)
  via transcription Whisper `large-v3` sur GPU
- **Sites web** via Playwright headless (Marmiton, 750g, etc.)
- **Texte libre** en n'importe quelle langue — converti automatiquement en
  français
- **Photo / OCR** — pointez votre caméra vers un livre de cuisine

### Gestion des recettes

- Scaling des quantités : ½× 1× 2× 3× ou valeur personnalisée
- Classification automatique par catégorie (LLM)
- Filtres : catégorie, temps de préparation, source, favoris
- Lien proéminent vers la vidéo ou le site source
- Détection de doublons à l'ajout
- Analyse nutritionnelle par portion (IA)
- Notes personnelles par recette

### Outils cuisiniers

- **Mode Cuisine** : plein écran, étape par étape, écran toujours allumé
- **Liste de courses** : sélectionnez plusieurs recettes → liste fusionnée
- **Planning des repas** : calendrier hebdomadaire (matin/midi/soir/snack)
- Export PDF via l'impression du navigateur

### Succès (achievements)

16 badges débloquables — collection, cuisine, organisation, découverte,
perfectionniste — avec barre de progression individuelle.

---

## Screenshots Android

### Accueil & Filtres

![Accueil](screenshots/android/home.png)

> Grille de recettes avec barre de recherche, filtres par catégorie, temps
> et source. Appui long pour sélection multiple (liste de courses).

### Détail d'une recette

![Détail recette](screenshots/android/detail.png)

> Scaling des ingrédients, lien source, analyse nutritionnelle, notes
> personnelles, bouton Mode Cuisine.

### Mode Cuisine

![Mode cuisine](screenshots/android/cooking.png)

> Vue plein écran, étape par étape, écran maintenu allumé via wake lock.

### Liste de courses

![Liste de courses](screenshots/android/shopping.png)

> Sélection multi-recettes → liste fusionnée avec cases à cocher.

### Planning des repas

![Planning](screenshots/android/planning.png)

> Grille hebdomadaire horizontale, ajout rapide par recherche de recette.

### Succès

![Succès](screenshots/android/achievements.png)

> Badges style Steam avec progression individuelle, regroupés par catégorie.

### Ajout par URL / Texte / Photo

![Ajouter](screenshots/android/add.png)

> Extraction en tâche de fond avec polling du statut en temps réel.

---

## Architecture

```text
Internet / LAN
     │
     ▼
[Cloudflare Tunnel] ──► popote.guyluron.fr
     │
     ▼
[Nginx :80]  ←── React SPA (Vite + Tailwind)
     │ /api proxy
     ▼
[FastAPI :8000]
     ├── PostgreSQL :5432   (recettes, planning, succès)
     ├── Ollama :11434      (LLM qwen2.5:14b, GPU)
     └── faster-whisper     (transcription, GPU CUDA)
```

### Stack technique

| Couche | Technologie |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy async, asyncpg |
| Base de données | PostgreSQL 16, JSONB pour ingrédients/étapes/tags |
| Transcription | faster-whisper `large-v3`, CUDA (RTX 3080) |
| Scraping | yt-dlp (vidéos), Playwright (web) |
| LLM | Ollama `qwen2.5:14b` + Claude `claude-sonnet-4-6` (fallback) |
| OCR | Claude Vision → Ollama llava → pytesseract |
| Frontend web | React 18, Vite, Tailwind CSS, React Query |
| App Android | Kotlin, Jetpack Compose, Material 3, Retrofit, Coil |
| Infrastructure | Docker Compose, NVIDIA Container Toolkit |
| Tunnel | Cloudflare Tunnel (HTTPS sans port ouvert) |
| CI/CD | GitHub Actions, git-cliff (auto-release) |

---

## Prérequis

### Serveur

- GPU NVIDIA (testé RTX 3080, 10 GB VRAM)
- Docker + Docker Compose v2
- NVIDIA Container Toolkit
- ~20 GB disque (modèles Ollama + Whisper)

### Android

- Android 8.0 (API 26) minimum
- Accès réseau au serveur (LAN ou via Cloudflare Tunnel)

---

## Installation

### 1. Cloner et configurer

```bash
git clone https://github.com/lguerard/popote.git
cd popote
cp .env.example .env
# Éditer .env : POSTGRES_PASSWORD, SECRET_KEY, CLAUDE_API_KEY (optionnel)
```

### 2. Démarrer

```bash
docker compose up -d
```

Le premier démarrage télécharge `qwen2.5:14b` (~5 GB) — prévoir 10-15 min.

### 3. Accéder

- Web : `http://localhost` (ou votre domaine Cloudflare)
- Android : installer l'APK depuis les
  [Releases GitHub](https://github.com/lguerard/popote/releases)

Pour le déploiement complet avec Cloudflare Tunnel et accès externe,
voir [`DEPLOIEMENT.md`](DEPLOIEMENT.md).

---

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `POSTGRES_PASSWORD` | `kitchenai` | Mot de passe PostgreSQL |
| `OLLAMA_MODEL` | `qwen2.5:14b` | Modèle LLM local |
| `CLAUDE_API_KEY` | *(vide)* | Active Claude en priorité sur Ollama |
| `WHISPER_MODEL` | `large-v3` | Modèle Whisper |
| `WHISPER_DEVICE` | `cuda` | `cuda` ou `cpu` |
| `SECRET_KEY` | `changeme` | Clé secrète FastAPI |
| `PORT` | `80` | Port HTTP exposé |

---

## CI/CD

Chaque push sur `main` déclenche automatiquement :

1. **git-cliff** calcule la prochaine version semver depuis les commits
   conventionnels
2. Changelog généré en français
3. APK Android signé buildé (`versionCode` et `versionName` injectés)
4. Tag git annoté créé (`v0.x.y`)
5. GitHub Release créée avec l'APK en pièce jointe

Secrets requis dans **Settings → Secrets → Actions** :

| Secret | Description |
|---|---|
| `KEYSTORE_BASE64` | Keystore encodé en base64 |
| `KEYSTORE_PASSWORD` | Mot de passe du keystore |
| `KEY_ALIAS` | Alias de la clé de signature |
| `KEY_PASSWORD` | Mot de passe de la clé |

---

## Succès disponibles

| Badge | Condition |
|---|---|
| 🌟 Premier Pas | 1ère recette ajoutée |
| 📚 Collectionneur | 10 recettes |
| 🏛️ Bibliothèque | 50 recettes |
| 👨‍🍳 Grand Chef | 100 recettes |
| 🍳 En Cuisine ! | 1er Mode Cuisine |
| ⭐ Chef Confirmé | Mode Cuisine × 10 |
| 🌟 Chef Étoilé | Mode Cuisine × 50 |
| 🛒 Organisé | 1ère liste de courses |
| 📅 Planificateur | 1er planning |
| 🏆 Semaine Complète | 28 repas planifiés |
| 🍽️ Gourmet | 5 catégories explorées |
| 🌍 Tour du Monde | 3 langues sources |
| 🎬 Chasseur de Vidéos | 10 recettes depuis vidéo |
| ❤️ Coup de Cœur | 1er favori |
| 🥗 Nutritionniste | 5 analyses nutritionnelles |
| 📷 Photographe | 1ère recette par OCR |
| 📝 Carnet de Notes | Notes sur 3 recettes |

---

## Licence

MIT
