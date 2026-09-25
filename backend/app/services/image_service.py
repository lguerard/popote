"""Vignette de recette : upload manuel, ou génération IA de secours.

La génération appelle le micro-service `imagegen` (voir imagegen/README.md)
plutôt que de charger torch/diffusers ici : ce sont de grosses dépendances
avec leur propre runtime CUDA, isolées dans leur propre conteneur pour ne
jamais entrer en conflit avec les roues CUDA épinglées pour Whisper dans
CE conteneur.
"""

import logging
import uuid
from pathlib import Path

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

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


_DOWNLOAD_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024


async def download_image(url: str) -> tuple[bytes, str]:
    """(contenu, extension) d'une image distante (vignette de la source).

    Lève si ce n'est pas une image JPEG/PNG/WEBP de taille raisonnable.
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Popote/1.0)"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    ext = _DOWNLOAD_TYPES.get(content_type)
    if not ext:
        raise ValueError(f"Type d'image non géré : {content_type or 'inconnu'}")
    if len(resp.content) > _MAX_DOWNLOAD_BYTES:
        raise ValueError("Image trop volumineuse")
    return resp.content, ext


async def apply_source_image(recipe, source_url: str | None, replace: bool) -> None:
    """Met à jour l'image d'une recette après une réextraction.

    Sans ``replace``, une image importée ou générée par l'utilisateur
    (/media/…) prime sur celle de la source. Sinon l'image de la source est
    téléchargée et stockée ici : les liens d'Instagram/TikTok sont signés
    et expirent au bout de quelques jours (image cassée ensuite). Si le
    téléchargement échoue, le lien direct sert de repli.
    """
    if not source_url:
        return
    current = recipe.thumbnail_url or ""
    if current.startswith(f"/media/{THUMBNAIL_SUBDIR}/") and not replace:
        return
    try:
        data, ext = await download_image(source_url)
    except Exception:
        logger.warning("Image de la source non téléchargeable : %s", source_url, exc_info=True)
        recipe.thumbnail_url = source_url
    else:
        recipe.thumbnail_url = save_thumbnail_bytes(recipe.id, data, ext)
    if recipe.thumbnail_url != current:
        delete_local_thumbnail(current)


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


# Le modele d'image comprend surtout l'anglais : garder les mots-cles de
# categorie tels quels (en francais, comme stockes en base) donnait des
# images generiques qui ignoraient completement le type de plat.
_CATEGORY_EN = {
    "petit-déjeuner": "breakfast",
    "entrée": "starter",
    "plat": "main course",
    "dessert": "dessert",
    "snack": "snack",
    "boisson": "drink",
    "sauce": "sauce",
    "apéritif": "appetizer",
    "soupe": "soup",
}

# Placé APRÈS la description du plat : le modèle ne lit que 77 tokens, ce
# qui dépasse est ignoré. Le sujet d'abord, le style ensuite.
_STYLE = (
    "professional food photography, appetizing, natural window light, "
    "shallow depth of field, sharp focus, high detail"
)

NEGATIVE_PROMPT = (
    "text, watermark, logo, hands, people, blurry, low quality, deformed, "
    "cartoon, drawing, illustration, oversaturated"
)


def build_prompt(
    visual: str | None, title: str, category: str | None, ingredients: list[dict] | None,
) -> str:
    """Prompt final : description visuelle (LLM) + style photo.

    Sans description (LLM indisponible), repli sur un gabarit court : un
    prompt long en français était tronqué par le modèle avant même
    d'atteindre les consignes de style.
    """
    if visual:
        return f"{visual.rstrip('.')}. {_STYLE}"
    category_en = _CATEGORY_EN.get((category or "").lower(), "dish")
    names = [
        ing["name"] for ing in (ingredients or [])[:4]
        if isinstance(ing, dict) and ing.get("name")
    ]
    subject = f"{title}, a {category_en}"
    if names:
        subject += " with " + ", ".join(names)
    return f"{subject}, served on a plate, {_STYLE}"


async def generate_recipe_image(
    title: str, description: str | None, category: str | None,
    ingredients: list[dict] | None = None, steps: list | None = None,
) -> bytes:
    """Demande une image au service imagegen. Lève sur échec (délai géré par l'appelant)."""
    from . import llm_service

    visual = None
    try:
        visual = await llm_service.describe_dish_for_image(
            title, description, category, ingredients, steps,
        )
    except Exception:
        logger.warning("Description visuelle du plat indisponible, prompt de secours", exc_info=True)
    prompt = build_prompt(visual, title, category, ingredients)
    logger.info("Génération d'image pour « %s » : %s", title, prompt)

    if settings.image_gen_free_gpu:
        try:
            await llm_service.unload_ollama_model()
        except Exception:
            logger.warning("Impossible de libérer le GPU d'Ollama", exc_info=True)

    # Aligné sur _THUMBNAIL_GENERATION_TIMEOUT_SECONDS côté appelant (recipes.py) :
    # laisser le temps au premier appel de télécharger le modèle.
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(
            f"{settings.imagegen_base_url}/generate",
            json={"prompt": prompt, "negative_prompt": NEGATIVE_PROMPT},
        )
        resp.raise_for_status()
        return resp.content
