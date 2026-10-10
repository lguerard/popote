"""Partage de recettes entre comptes.

Une recette partagée est COPIÉE dans le compte destinataire, avec le nom de
l'expéditeur pour le badge « de … » : le destinataire peut ensuite la mettre
en favori, la noter, la planifier, l'annoter ou la modifier comme les
siennes, sans toucher à l'original (ces informations sont rangées sur la
recette elle-même, une recette commune les mélangerait).
"""

import logging
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.library_share import LibraryShare
from ..models.recipe import ExtractionStatus, Recipe
from ..models.user import User, UserStatus
from . import image_service

logger = logging.getLogger(__name__)

# Le contenu de la recette, sans ce qui est propre à son propriétaire
# (favori, note, avis, historique, lien public).
COPIED_FIELDS = (
    "title", "description", "source_url", "source_type", "language", "servings",
    "prep_time", "cook_time", "ingredients", "steps", "tags", "category", "nutrition",
)


def origin_of(recipe) -> uuid.UUID:
    """La recette d'origine : une copie d'une copie remonte à l'original."""
    return recipe.origin_recipe_id or recipe.id


def copy_fields(recipe) -> dict:
    return {
        field: (list(value) if isinstance(value, list) else value)
        for field in COPIED_FIELDS
        for value in [getattr(recipe, field)]
    }


async def share_recipes(
    db: AsyncSession, sender: User, recipes: list[Recipe], target: User,
) -> tuple[int, int]:
    """Copie `recipes` dans le compte `target`. Retourne (copiées, ignorées).

    Ignorées : extractions non terminées, et recettes que le destinataire a
    déjà (il en est l'auteur, ou en a déjà reçu une copie).
    """
    ready = [r for r in recipes if r.status == ExtractionStatus.done]
    origins = {origin_of(r) for r in ready}
    already = set()
    if origins:
        rows = await db.execute(
            select(Recipe.id, Recipe.origin_recipe_id).where(
                Recipe.owner_id == target.id,
                or_(Recipe.id.in_(origins), Recipe.origin_recipe_id.in_(origins)),
            )
        )
        for recipe_id, origin_id in rows:
            already.add(recipe_id)
            if origin_id:
                already.add(origin_id)

    copied = 0
    for recipe in ready:
        origin = origin_of(recipe)
        if origin in already:
            continue
        already.add(origin)
        new_id = uuid.uuid4()
        db.add(Recipe(
            id=new_id,
            **copy_fields(recipe),
            thumbnail_url=image_service.copy_local_thumbnail(recipe.thumbnail_url, new_id),
            owner_id=target.id,
            status=ExtractionStatus.done,
            shared_by_id=sender.id,
            shared_by_name=sender.display_name,
            origin_recipe_id=origin,
        ))
        copied += 1
    await db.commit()
    return copied, len(recipes) - copied


async def approved_user(db: AsyncSession, user_id) -> User | None:
    user = await db.get(User, user_id)
    return user if user and user.status == UserStatus.approved.value else None


async def auto_share(db: AsyncSession, recipe: Recipe) -> None:
    """Envoie une nouvelle recette aux comptes en partage automatique.

    Seulement ses propres recettes : une recette reçue n'est pas renvoyée
    plus loin. Ne fait jamais échouer l'ajout de la recette.
    """
    if recipe.shared_by_id or recipe.owner_id is None:
        return
    try:
        targets = (await db.execute(
            select(LibraryShare.target_id).where(LibraryShare.owner_id == recipe.owner_id)
        )).scalars().all()
        if not targets:
            return
        sender = await db.get(User, recipe.owner_id)
        for target_id in targets:
            target = await approved_user(db, target_id)
            if sender and target:
                await share_recipes(db, sender, [recipe], target)
    except Exception:
        await db.rollback()
        logger.warning("Partage automatique de la recette %s impossible", recipe.id, exc_info=True)
