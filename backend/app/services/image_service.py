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


def _build_prompt(
    title: str, description: str | None, category: str | None, ingredients: list[dict] | None
) -> str:
    """Construit un prompt ancré dans le contenu réel de la recette.

    Se limiter au titre (et a la categorie) laissait le modele deviner a
    quoi ressemble le plat a partir du seul nom, souvent en francais : le
    resultat etait generique et ne reflétait ni les ingredients ni la
    preparation. Lister les ingredients reels donne des indices concrets
    (couleur, texture, composants visibles) que le titre seul ne donne pas.
    """
    category_en = _CATEGORY_EN.get((category or "").lower(), category)

    names = []
    for ing in (ingredients or [])[:6]:
        name = ing.get("name") if isinstance(ing, dict) else None
        if name:
            names.append(name)

    parts = [f"Professional food photography of {title}"]
    if category_en:
        parts.append(f"a {category_en}")
    if names:
        parts.append("made with " + ", ".join(names))
    if description:
        parts.append(description)
    parts.append(
        "served on a plate, appetizing, natural light, on a wooden table, "
        "shallow depth of field, high quality, detailed, realistic, 4k"
    )
    return ", ".join(parts)


async def generate_recipe_image(
    title: str, description: str | None, category: str | None, ingredients: list[dict] | None = None
) -> bytes:
    """Demande une image au service imagegen. Lève sur échec (délai géré par l'appelant)."""
    prompt = _build_prompt(title, description, category, ingredients)
    # Aligné sur _THUMBNAIL_GENERATION_TIMEOUT_SECONDS côté appelant (recipes.py) :
    # laisser le temps au premier appel de télécharger le modèle (~2 Go).
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(
            f"{settings.imagegen_base_url}/generate",
            json={
                "prompt": prompt,
                "negative_prompt": "text, watermark, logo, blurry, low quality, cartoon, drawing",
            },
        )
        resp.raise_for_status()
        return resp.content
