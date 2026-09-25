import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import current_user
from ..models.collection import Collection, CollectionRecipe
from ..models.recipe import ExtractionStatus, Recipe
from ..models.user import User
from ..schemas.recipe import RecipeOut

router = APIRouter(prefix="/collections", tags=["collections"])


class CollectionIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    emoji: str | None = Field(None, max_length=16)
    description: str | None = None


class CollectionPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    emoji: str | None = Field(None, max_length=16)
    description: str | None = None


class CollectionOut(BaseModel):
    id: uuid.UUID
    name: str
    emoji: str | None = None
    description: str | None = None
    share_token: str | None = None
    created_at: datetime
    recipe_count: int = 0
    covers: list[str] = []
    # Renseigné seulement quand la liste est demandée avec ?recipe_id= :
    # sert à cocher les carnets qui contiennent déjà la recette.
    contains_recipe: bool | None = None


class CollectionDetail(CollectionOut):
    recipes: list[RecipeOut] = []


async def _owned(db: AsyncSession, collection_id: uuid.UUID, user: User) -> Collection:
    collection = await db.get(Collection, collection_id)
    if not collection or collection.owner_id != user.id:
        raise HTTPException(404, "Carnet introuvable")
    return collection


async def collection_recipes(db: AsyncSession, collection: Collection) -> list[Recipe]:
    return (await db.execute(
        select(Recipe)
        .join(CollectionRecipe, CollectionRecipe.recipe_id == Recipe.id)
        .where(CollectionRecipe.collection_id == collection.id,
               Recipe.status == ExtractionStatus.done)
        .order_by(CollectionRecipe.added_at.desc())
    )).scalars().all()


def _out(collection: Collection, rows: list[Recipe], cls=CollectionOut, **extra):
    return cls(
        id=collection.id, name=collection.name, emoji=collection.emoji,
        description=collection.description, share_token=collection.share_token,
        created_at=collection.created_at, recipe_count=len(rows),
        covers=[r.thumbnail_url for r in rows if r.thumbnail_url][:4],
        **extra,
    )


@router.get("", response_model=list[CollectionOut])
async def list_collections(
    recipe_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    collections = (await db.execute(
        select(Collection).where(Collection.owner_id == user.id).order_by(Collection.name)
    )).scalars().all()
    result = []
    for collection in collections:
        recipes = await collection_recipes(db, collection)
        extra = {}
        if recipe_id:
            extra["contains_recipe"] = any(r.id == recipe_id for r in recipes)
        result.append(_out(collection, recipes, **extra))
    return result


@router.post("", response_model=CollectionOut, status_code=201)
async def create_collection(
    data: CollectionIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    collection = Collection(owner_id=user.id, **data.model_dump())
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return _out(collection, [])


@router.get("/{collection_id}", response_model=CollectionDetail)
async def get_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    collection = await _owned(db, collection_id, user)
    recipes = await collection_recipes(db, collection)
    return _out(collection, recipes, CollectionDetail,
                recipes=[RecipeOut.model_validate(r) for r in recipes])


@router.patch("/{collection_id}", response_model=CollectionOut)
async def update_collection(
    collection_id: uuid.UUID,
    data: CollectionPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    collection = await _owned(db, collection_id, user)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(collection, field, value)
    await db.commit()
    await db.refresh(collection)
    return _out(collection, await collection_recipes(db, collection))


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Supprime le carnet, jamais les recettes qu'il contient."""
    collection = await _owned(db, collection_id, user)
    await db.delete(collection)
    await db.commit()


@router.put("/{collection_id}/recipes/{recipe_id}", status_code=204)
async def add_to_collection(
    collection_id: uuid.UUID,
    recipe_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    collection = await _owned(db, collection_id, user)
    recipe = await db.get(Recipe, recipe_id)
    if not recipe or recipe.owner_id != user.id:
        raise HTTPException(404, "Recette introuvable")
    exists = await db.get(CollectionRecipe, (collection.id, recipe.id))
    if not exists:
        db.add(CollectionRecipe(collection_id=collection.id, recipe_id=recipe.id))
        await db.commit()


@router.delete("/{collection_id}/recipes/{recipe_id}", status_code=204)
async def remove_from_collection(
    collection_id: uuid.UUID,
    recipe_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    collection = await _owned(db, collection_id, user)
    await db.execute(delete(CollectionRecipe).where(
        CollectionRecipe.collection_id == collection.id,
        CollectionRecipe.recipe_id == recipe_id,
    ))
    await db.commit()


@router.post("/{collection_id}/share", response_model=CollectionOut)
async def share_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    collection = await _owned(db, collection_id, user)
    if not collection.share_token:
        collection.share_token = secrets.token_urlsafe(16)
        await db.commit()
        await db.refresh(collection)
    return _out(collection, await collection_recipes(db, collection))


@router.delete("/{collection_id}/share", response_model=CollectionOut)
async def unshare_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    collection = await _owned(db, collection_id, user)
    collection.share_token = None
    await db.commit()
    await db.refresh(collection)
    return _out(collection, await collection_recipes(db, collection))
