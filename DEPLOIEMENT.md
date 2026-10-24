# Guide de déploiement — Popote

## Sommaire

1. [Prérequis serveur](#1-prérequis-serveur)
2. [Drivers NVIDIA + Docker GPU](#2-drivers-nvidia--docker-gpu)
3. [Installer Docker](#3-installer-docker)
4. [Lancer Popote](#4-lancer-popote)
5. [Exposer sur Internet avec Cloudflare Tunnel](#5-exposer-sur-internet-avec-cloudflare-tunnel)
6. [App Android — connexion](#6-app-android--connexion)
7. [Mises à jour](#7-mises-à-jour)
8. [Dépannage](#8-dépannage)

---

## 1. Prérequis serveur

| Composant | Minimum |
|---|---|
| OS | Ubuntu 22.04 LTS |
| CPU | i9 9900k ou équivalent |
| GPU | RTX 3080 (10 GB VRAM) |
| RAM | 16 GB |
| Disque | 50 GB libres (modèles IA) |
| Réseau | Connexion Internet stable |

---

## 2. Drivers NVIDIA + Docker GPU

```bash
# Drivers NVIDIA (si pas déjà installés)
sudo apt update
sudo ubuntu-drivers autoinstall
sudo reboot

# Vérifier
nvidia-smi   # doit afficher la RTX 3080

# NVIDIA Container Toolkit (permet Docker d'accéder au GPU)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

---

## 3. Installer Docker

```bash
# Docker Engine
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Vérifier
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
# → doit afficher la RTX 3080
```

---

## 4. Lancer Popote

### 4.1 Cloner le projet

```bash
git clone https://github.com/<ton-user>/kitchen_ai.git
cd kitchen_ai
```

### 4.2 Configurer

```bash
cp .env.example .env
nano .env
```

Modifier au minimum :

```env
POSTGRES_PASSWORD=un-mot-de-passe-fort
SECRET_KEY=une-cle-secrete-aleatoire
# Optionnel : si tu veux utiliser Claude à la place d'Ollama
# CLAUDE_API_KEY=sk-ant-...
```

### 4.3 Premier démarrage

```bash
docker compose up -d --build
```

> **Premier démarrage** : Ollama va télécharger le modèle `gemma4:12b` (~8 GB).
> Surveiller avec : `docker compose logs -f ollama`

### 4.4 Vérifier

```bash
# Tous les conteneurs sont UP ?
docker compose ps

# Backend répond ?
curl http://localhost/api/health
# → {"status": "ok"}
```

L'interface est accessible sur **http://\<IP-locale\>** (port 80).

---

## 5. Exposer sur Internet avec Cloudflare Tunnel

Cloudflare Tunnel permet d'exposer le serveur sur Internet **sans ouvrir de ports**, sans IP fixe, avec HTTPS automatique.

### 5.1 Prérequis

- Un domaine géré par Cloudflare (ex : `mondomaine.com`)
- Un compte Cloudflare gratuit

### 5.2 Installer cloudflared

```bash
# Sur le serveur
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# Se connecter à Cloudflare
cloudflared tunnel login
# → ouvre un navigateur, autoriser le domaine
```

### 5.3 Créer le tunnel

```bash
# Créer le tunnel (une seule fois)
cloudflared tunnel create popote
# → retourne un UUID ex: a1b2c3d4-...

# Créer le fichier de config
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml << EOF
tunnel: <UUID-DU-TUNNEL>
credentials-file: /root/.cloudflared/<UUID-DU-TUNNEL>.json

ingress:
  - hostname: recettes.mondomaine.com
    service: http://localhost:80
  - service: http_status:404
EOF
```

### 5.4 Pointer le DNS

```bash
# Crée automatiquement l'entrée DNS chez Cloudflare
cloudflared tunnel route dns popote recettes.mondomaine.com
```

### 5.5 Lancer le tunnel comme service système

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# Vérifier
sudo systemctl status cloudflared
```

L'app est maintenant accessible sur **https://recettes.mondomaine.com** avec HTTPS automatique.

### 5.6 Protéger avec Cloudflare Access (optionnel mais recommandé)

Pour ne pas exposer tes recettes à tout le monde :

1. Dashboard Cloudflare → **Zero Trust** → **Access** → **Applications**
2. **Add an application** → Self-hosted
3. Domain : `recettes.mondomaine.com`
4. Policy : autoriser uniquement ton email
5. Enregistrer

→ Une page de login Google/GitHub apparaîtra avant d'accéder à l'app.

---

## 6. App Android — connexion

### Réseau local (Wi-Fi maison)

1. Trouver l'IP du serveur : `ip addr show | grep 192.168`
2. Dans l'app Android → **Paramètres** → entrer `http://192.168.1.xxx`
3. Appuyer sur **Tester** → doit afficher "Connecté !"

### Depuis l'extérieur (4G/5G ou autre réseau)

Si Cloudflare Tunnel est configuré :

→ Dans l'app Android → **Paramètres** → entrer `https://recettes.mondomaine.com`

### Astuce — partage depuis le navigateur Android

1. Dans Chrome, ouvrir une vidéo YouTube / page de recette
2. Menu partage → **Popote**
3. L'app ouvre directement l'écran d'extraction avec l'URL pré-remplie

---

## 7. Mises à jour

```bash
cd ~/server_setup/popote
git pull
./scripts/demarrer.sh --build
```

`scripts/demarrer.sh` fait un `docker compose up -d` ; si les conteneurs GPU
ne peuvent pas démarrer (pilote NVIDIA en panne), il relance Popote **en mode
CPU** (`docker-compose.cpu.yml`) plutôt que de le laisser injoignable. Relancer
le script une fois le GPU réparé suffit à revenir au GPU.

yt-dlp (lecture des vidéos) est mis à jour à chaque démarrage du backend :
`docker compose restart backend` suffit quand Instagram ou TikTok changent.

### Sauvegarder ses recettes

Chaque compte télécharge sa sauvegarde complète (recettes, images, notes,
avis, historique, carnets) depuis 💾 **Sauvegarde** sur le web ou
**Paramètres → Sauvegarde** sur Android, et la restaure au même endroit. La
restauration ajoute les recettes sans dupliquer celles déjà présentes.

Une sauvegarde avec beaucoup d'images peut peser plusieurs centaines de Mo :
le plan gratuit de Cloudflare refuse les envois de plus de 100 Mo. Pour
restaurer une grosse sauvegarde, faites-le **depuis le réseau local**
(`http://192.168.x.x`). Le planning et la liste de courses ne sont pas inclus ;
pour tout le serveur (tous les comptes), sauvegardez la base PostgreSQL et le
dossier des images (volume `media_data`).

---

## 8. Dépannage

### Le GPU n'est pas détecté

```bash
docker compose logs backend | grep -i cuda
# Si "CUDA not available" → vérifier nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker compose restart backend
```

Pour forcer CPU (plus lent) :
```env
# .env
WHISPER_DEVICE=cpu
```

### « failed to fulfil mount request: /run/nvidia-persistenced/socket »

Le pilote NVIDIA a souvent été mis à jour sans redémarrage :

```bash
nvidia-smi                      # « Driver/library version mismatch » → sudo reboot
sudo systemctl enable --now nvidia-persistenced
# Si le pilote va bien mais l'erreur persiste : régénérer la config GPU de Docker
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
sudo systemctl restart docker
./scripts/demarrer.sh
```

En attendant, `./scripts/demarrer.sh` garde Popote en ligne en mode CPU.

### Ollama ne répond pas / modèle pas chargé

```bash
docker compose logs ollama
# Si le modèle n'est pas téléchargé :
docker compose exec ollama ollama pull gemma4:12b
```

### Extraction échoue sur une vidéo

Popote ne garde que la recette du lien donné. Il la cherche, dans l'ordre :
1. dans la vidéo : légende, sous-titres, audio, texte affiché à l'écran ;
   pour un **carrousel Instagram ou un post photo TikTok**, le texte écrit sur
   les images (téléchargées par gallery-dl, lues par OCR) ;
2. dans la **légende du post lue sans compte** (page d'intégration Instagram,
   oEmbed TikTok), puis dans la page web. Une recette publiée par un site est
   lue par [recipe-scrapers](https://github.com/hhursev/recipe-scrapers)
   (lecteurs dédiés pour 700+ sites dont Marmiton, 750g, CuisineAZ, Jow ;
   schema.org en JSON-LD, microdata ou RDFa ailleurs) : telle quelle, sans IA ;
3. via le **lien de la recette complète** que l'auteur cite dans sa
   description (« recette complète : https://… ») : la même recette, publiée
   avec ses quantités exactes.

Rien n'est jamais cherché ailleurs ni inventé pour un lien : s'il ne contient
pas de recette, l'extraction échoue avec un message clair. (Seul un texte
sans lien — un nom de plat tapé — ou la photo d'un plat donne une recette
proposée par l'IA, marquée « à vérifier ».)

- **yt-dlp / gallery-dl trop anciens** (la plateforme a changé) : ils se
  mettent à jour à chaque démarrage, `docker compose restart backend` suffit.
- **Instagram exige une connexion** (« login required », « rate-limit » ;
  presque toujours pour les carrousels) : donner à Popote les cookies d'un
  compte Instagram (idéalement un compte secondaire), utilisés par yt-dlp et
  gallery-dl :
  1. dans Firefox ou Chrome connecté à Instagram, exporter les cookies au
     format Netscape (extension « Get cookies.txt LOCALLY » par exemple) ;
  2. copier le fichier sur le serveur : `~/server_setup/popote/cookies/cookies.txt` ;
  3. `docker compose up -d backend`.

  Le dossier `cookies/` n'est jamais versionné ; il est monté en lecture seule.
- **Voir pourquoi** : `docker compose logs backend --since 15m | grep -iE "extraction|vidéo|légende"`
- **En dernier recours** : copier la légende du post et la coller dans Popote,
  qui extrait la recette du texte.

### L'app Android affiche "Serveur injoignable"

Le message indique l'adresse configurée dans l'appli.

1. Vérifier que le serveur tourne : `docker compose ps` (sinon `./scripts/demarrer.sh`)
2. Une adresse `192.168.…` ne marche qu'en Wi-Fi à la maison : dehors, il faut
   l'adresse publique (Cloudflare Tunnel, section 5)
3. Vérifier l'URL dans les paramètres (pas d'espace, bon port)
4. Sur réseau local : désactiver le VPN sur le téléphone
5. Sur réseau externe : vérifier `sudo systemctl status cloudflared`

Une coupure pendant une extraction n'est plus un échec : l'appli réessaie
pendant ~3 minutes, et l'extraction continue de toute façon sur le serveur.

---

## Récapitulatif des commandes utiles

```bash
# Logs en temps réel
docker compose logs -f

# Redémarrer un service
docker compose restart backend

# Voir l'utilisation GPU
watch -n1 nvidia-smi

# Sauvegarder la base de données
docker compose exec db pg_dump -U popote popote > backup_$(date +%Y%m%d).sql

# Restaurer
cat backup_20241201.sql | docker compose exec -T db psql -U popote popote
```
