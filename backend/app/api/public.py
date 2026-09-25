"""Pages publiques en lecture seule, accessibles par lien sans compte.

Aucune de ces routes ne dépend de current_user : l'accès repose uniquement
sur un jeton aléatoire de 128 bits, révocable depuis l'application. Une
ressource non partagée (ou révoquée) répond 404, comme un jeton inventé.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.collection import Collection, CollectionRecipe
from ..models.recipe import ExtractionStatus, Recipe
from ..models.shopping import ShoppingItem as ShoppingItemRow
from ..models.user import User, UserStatus
from ..schemas.recipe import PublicRecipeOut
from ..services import grocery
from .collections import collection_recipes
from .shopping import ShoppingItemOut, list_items

router = APIRouter(prefix="/public", tags=["public"])


class PublicCollectionOut(BaseModel):
    name: str
    emoji: str | None = None
    description: str | None = None
    owner_name: str
    recipes: list[PublicRecipeOut]


class PublicShoppingOut(BaseModel):
    owner_name: str
    items: list[ShoppingItemOut]
    aisles: list[str]


class CheckIn(BaseModel):
    checked: bool


async def _active_owner(db: AsyncSession, owner_id) -> User:
    # Un compte révoqué ne doit plus rien exposer, même par un ancien lien.
    owner = await db.get(User, owner_id) if owner_id else None
    if not owner or owner.status != UserStatus.approved.value:
        raise HTTPException(404, "Lien invalide ou révoqué")
    return owner


@router.get("/recipes/{token}", response_model=PublicRecipeOut)
async def public_recipe(token: str, db: AsyncSession = Depends(get_db)):
    recipe = (await db.execute(
        select(Recipe).where(Recipe.share_token == token, Recipe.status == ExtractionStatus.done)
    )).scalar_one_or_none()
    if not recipe:
        raise HTTPException(404, "Lien invalide ou révoqué")
    await _active_owner(db, recipe.owner_id)
    return recipe


async def _shared_collection(db: AsyncSession, token: str) -> tuple[Collection, User]:
    collection = (await db.execute(
        select(Collection).where(Collection.share_token == token)
    )).scalar_one_or_none()
    if not collection:
        raise HTTPException(404, "Lien invalide ou révoqué")
    return collection, await _active_owner(db, collection.owner_id)


@router.get("/collections/{token}", response_model=PublicCollectionOut)
async def public_collection(token: str, db: AsyncSession = Depends(get_db)):
    collection, owner = await _shared_collection(db, token)
    recipes = await collection_recipes(db, collection)
    return PublicCollectionOut(
        name=collection.name, emoji=collection.emoji, description=collection.description,
        owner_name=owner.display_name,
        recipes=[PublicRecipeOut.model_validate(r) for r in recipes],
    )


@router.get("/collections/{token}/recipes/{recipe_id}", response_model=PublicRecipeOut)
async def public_collection_recipe(
    token: str, recipe_id: uuid.UUID, db: AsyncSession = Depends(get_db),
):
    collection, _owner = await _shared_collection(db, token)
    # Seulement une recette du carnet partagé : le jeton ne doit pas
    # ouvrir le reste de la bibliothèque.
    link = await db.get(CollectionRecipe, (collection.id, recipe_id))
    recipe = await db.get(Recipe, recipe_id) if link else None
    if not recipe or recipe.status != ExtractionStatus.done:
        raise HTTPException(404, "Recette introuvable")
    return recipe


async def _shopping_owner(db: AsyncSession, token: str) -> User:
    owner = (await db.execute(
        select(User).where(User.shopping_share_token == token)
    )).scalar_one_or_none()
    if not owner or owner.status != UserStatus.approved.value:
        raise HTTPException(404, "Lien invalide ou révoqué")
    return owner


@router.get("/shopping/{token}", response_model=PublicShoppingOut)
async def public_shopping(token: str, db: AsyncSession = Depends(get_db)):
    owner = await _shopping_owner(db, token)
    return PublicShoppingOut(
        owner_name=owner.display_name,
        items=[ShoppingItemOut.model_validate(r) for r in await list_items(db, owner.id)],
        aisles=list(grocery.AISLES),
    )


@router.patch("/shopping/{token}/items/{item_id}", response_model=ShoppingItemOut)
async def public_check_item(
    token: str, item_id: uuid.UUID, data: CheckIn, db: AsyncSession = Depends(get_db),
):
    """Cocher/décocher : la seule modification permise par le lien partagé."""
    owner = await _shopping_owner(db, token)
    row = await db.get(ShoppingItemRow, item_id)
    if not row or row.owner_id != owner.id:
        raise HTTPException(404, "Article introuvable")
    row.checked = data.checked
    await db.commit()
    await db.refresh(row)
    return row
