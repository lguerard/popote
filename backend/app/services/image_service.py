"""Vignette de recette : upload manuel, ou génération IA de secours.

La génération appelle le micro-service `imagegen` (voir imagegen/README.md)
plutôt que de charger torch/diffusers ici : ce sont de grosses dépendances
avec leur propre runtime CUDA, isolées dans leur propre conteneur pour ne
jamais entrer en conflit avec les roues CUDA épinglées pour Whisper dans
CE conteneur.
"""

import uuid
from pathlib import Path

import httpx

from ..config import settings

THUMBNAIL_SUBDIR = "recipes"


def _thumbnail_dir() -> Path:
    path = Path(settings.media_dir) / THUMBNAIL_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_thumbnail_bytes(recipe_id, image_bytes: bytes, ext: str) -> str:
    """Écrit l'image sur disque et retourne l'URL publique (servie par /media)."""
    # Suffixe aleatoire : un nouvel upload sur la meme recette doit avoir
    # une URL differente, sinon le navigateur garde l'ancienne image en
    # cache et l'utilisateur ne voit jamais le changement.
    filename = f"{recipe_id}-{uuid.uuid4().hex[:8]}.{ext}"
    (_thumbnail_dir() / filename).write_bytes(image_bytes)
    return f"/media/{THUMBNAIL_SUBDIR}/{filename}"


def delete_local_thumbnail(thumbnail_url: str | None) -> None:
    """Supprime l'ancien fichier local, sans jamais toucher une URL externe.

    Une recette extraite d'une page web ou d'une vidéo a une thumbnail_url
    qui pointe vers le site source (og:image, vignette YouTube...) : ça ne
    vit pas sur ce disque et ça ne doit pas être touché.
    """
    if not thumbnail_url or not thumbnail_url.startswith(f"/media/{THUMBNAIL_SUBDIR}/"):
        return
    path = Path(settings.media_dir) / thumbnail_url.removeprefix("/media/")
    path.unlink(missing_ok=True)


async def generate_recipe_image(title: str, description: str | None, category: str | None) -> bytes:
    """Demande une image au service imagegen. Lève sur échec (délai géré par l'appelant)."""
    subject = ", ".join(filter(None, [title, category]))
    prompt = (
        f"Professional food photography of {subject}, appetizing, natural light, "
        "on a wooden table, high quality, detailed, 4k"
    )
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.imagegen_base_url}/generate",
            json={
                "prompt": prompt,
                "negative_prompt": "text, watermark, logo, blurry, low quality, cartoon, drawing",
            },
        )
        resp.raise_for_status()
        return resp.content
