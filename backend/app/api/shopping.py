import secrets
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import current_user
from ..models.meal_plan import MealPlan
from ..models.recipe import Recipe
from ..models.shopping import ShoppingItem as ShoppingItemRow
from ..models.user import User
from ..schemas.recipe import ShoppingItem, ShoppingListRequest
from ..services import achievement_service, grocery

router = APIRouter(tags=["shopping"])


@router.post("/shopping-list", response_model=list[ShoppingItem])
async def get_shopping_list(
    req: ShoppingListRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Liste calculée à la volée, sans rien enregistrer (utilisée par l'appli Android)."""
    # Filtre sur le proprietaire : sans lui, envoyer l'identifiant d'une
    # recette d'autrui suffirait a en lire les ingredients.
    result = await db.execute(
        select(Recipe).where(Recipe.id.in_(req.recipe_ids), Recipe.owner_id == user.id)
    )
    recipes = result.scalars().all()
    items = grocery.merge_ingredients([(r.title, r.ingredients) for r in recipes])
    await achievement_service.on_shopping_generated(db)
    return [ShoppingItem(**{k: item[k] for k in ("name", "quantity", "unit", "recipes")})
            for item in items]


# ---------------------------------------------------------------------------
# Liste persistée, groupée par rayon, cochable et partageable
# ---------------------------------------------------------------------------

class ShoppingItemOut(BaseModel):
    id: uuid.UUID
    name: str
    quantity: str | None = None
    unit: str | None = None
    aisle: str
    recipes: list[str] = []
    checked: bool = False

    model_config = {"from_attributes": True}


class ShoppingListOut(BaseModel):
    items: list[ShoppingItemOut]
    aisles: list[str]
    share_token: str | None = None


class GenerateIn(BaseModel):
    recipe_ids: list[uuid.UUID] = []
    # Planning : chaque repas planifié entre ces dates compte (une recette
    # prévue deux fois dans la semaine compte double).
    date_from: date | None = None
    date_to: date | None = None
    # False : ajoute à la liste existante au lieu de la remplacer.
    replace: bool = True


class ItemIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    quantity: str | None = Field(None, max_length=50)
    unit: str | None = Field(None, max_length=50)


class ItemPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=300)
    quantity: str | None = Field(None, max_length=50)
    unit: str | None = Field(None, max_length=50)
    aisle: str | None = Field(None, max_length=50)
    checked: bool | None = None


def _aisle_rank(aisle: str) -> int:
    try:
        return grocery.AISLES.index(aisle)
    except ValueError:
        return len(grocery.AISLES)


async def list_items(db: AsyncSession, owner_id: uuid.UUID) -> list[ShoppingItemRow]:
    rows = (await db.execute(
        select(ShoppingItemRow).where(ShoppingItemRow.owner_id == owner_id)
        .order_by(ShoppingItemRow.position, ShoppingItemRow.created_at)
    )).scalars().all()
    return sorted(rows, key=lambda r: (_aisle_rank(r.aisle), r.name.lower()))


async def _list_out(db: AsyncSession, user: User) -> ShoppingListOut:
    return ShoppingListOut(
        items=[ShoppingItemOut.model_validate(r) for r in await list_items(db, user.id)],
        aisles=list(grocery.AISLES),
        share_token=user.shopping_share_token,
    )


@router.get("/shopping/items", response_model=ShoppingListOut)
async def get_items(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return await _list_out(db, user)


@router.post("/shopping/items/generate", response_model=ShoppingListOut)
async def generate_items(
    req: GenerateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe_ids = list(dict.fromkeys(req.recipe_ids))
    if req.date_from and req.date_to:
        plans = (await db.execute(
            select(MealPlan.recipe_id).where(
                MealPlan.owner_id == user.id,
                MealPlan.date >= req.date_from, MealPlan.date <= req.date_to,
            )
        )).scalars().all()
        recipe_ids += plans
    if not recipe_ids:
        raise HTTPException(400, "Aucune recette sélectionnée ni planifiée sur cette période")

    recipes = {
        r.id: r for r in (await db.execute(
            select(Recipe).where(Recipe.id.in_(set(recipe_ids)), Recipe.owner_id == user.id)
        )).scalars().all()
    }
    merged = grocery.merge_ingredients(
        [(recipes[rid].title, recipes[rid].ingredients) for rid in recipe_ids if rid in recipes]
    )

    existing = [] if req.replace else [
        r for r in await list_items(db, user.id) if not r.checked
    ]
    if req.replace:
        await db.execute(delete(ShoppingItemRow).where(ShoppingItemRow.owner_id == user.id))
    position = (await db.execute(
        select(func.coalesce(func.max(ShoppingItemRow.position), 0))
        .where(ShoppingItemRow.owner_id == user.id)
    )).scalar_one()
    for item in merged:
        target = _find_mergeable(existing, item)
        if target:
            total = grocery.parse_quantity(target.quantity) + grocery.parse_quantity(item["quantity"])
            target.quantity, target.unit = grocery.format_quantity(total, target.unit)
            target.recipes = list(dict.fromkeys([*(target.recipes or []), *item["recipes"]]))
            continue
        position += 1
        db.add(ShoppingItemRow(owner_id=user.id, position=position, **item))
    await db.commit()
    await achievement_service.on_shopping_generated(db)
    return await _list_out(db, user)


def _find_mergeable(existing: list[ShoppingItemRow], item: dict) -> ShoppingItemRow | None:
    """Article déjà sur la liste auquel ajouter la quantité, s'il y en a un."""
    key = grocery.ingredient_key(item["name"])
    for row in existing:
        if (
            grocery.ingredient_key(row.name) == key
            and (row.unit or None) == (item["unit"] or None)
            and grocery.parse_quantity(row.quantity) is not None
            and grocery.parse_quantity(item["quantity"]) is not None
        ):
            return row
    return None


@router.post("/shopping/items", response_model=ShoppingItemOut, status_code=201)
async def add_item(
    data: ItemIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    position = (await db.execute(
        select(func.coalesce(func.max(ShoppingItemRow.position), 0))
        .where(ShoppingItemRow.owner_id == user.id)
    )).scalar_one()
    row = ShoppingItemRow(
        owner_id=user.id, name=data.name.strip(), quantity=data.quantity, unit=data.unit,
        aisle=grocery.guess_aisle(data.name), recipes=[], position=position + 1,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _owned_item(db: AsyncSession, item_id: uuid.UUID, owner_id: uuid.UUID) -> ShoppingItemRow:
    row = await db.get(ShoppingItemRow, item_id)
    if not row or row.owner_id != owner_id:
        raise HTTPException(404, "Article introuvable")
    return row


@router.patch("/shopping/items/{item_id}", response_model=ShoppingItemOut)
async def update_item(
    item_id: uuid.UUID,
    data: ItemPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    row = await _owned_item(db, item_id, user.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/shopping/items/{item_id}", status_code=204)
async def delete_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    row = await _owned_item(db, item_id, user.id)
    await db.delete(row)
    await db.commit()


@router.delete("/shopping/items", status_code=204)
async def clear_items(
    only_checked: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    q = delete(ShoppingItemRow).where(ShoppingItemRow.owner_id == user.id)
    if only_checked:
        q = q.where(ShoppingItemRow.checked.is_(True))
    await db.execute(q)
    await db.commit()


@router.post("/shopping/share", response_model=ShoppingListOut)
async def share_list(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    """Lien pour que le reste du foyer coche la liste sans compte."""
    if not user.shopping_share_token:
        user.shopping_share_token = secrets.token_urlsafe(16)
        await db.commit()
        await db.refresh(user)
    return await _list_out(db, user)


@router.delete("/shopping/share", response_model=ShoppingListOut)
async def unshare_list(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    user.shopping_share_token = None
    await db.commit()
    await db.refresh(user)
    return await _list_out(db, user)
