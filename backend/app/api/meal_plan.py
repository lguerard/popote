import uuid
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..deps import current_user
from ..models.user import User
from ..models.meal_plan import MealPlan, MealType
from ..services import achievement_service

router = APIRouter(prefix="/meal-plans", tags=["meal-plan"])


class MealPlanCreate(BaseModel):
    date: date
    meal_type: MealType
    recipe_id: uuid.UUID
    recipe_title: str | None = None
    recipe_thumbnail: str | None = None


class MealPlanOut(BaseModel):
    id: uuid.UUID
    date: date
    meal_type: MealType
    recipe_id: uuid.UUID
    recipe_title: str | None = None
    recipe_thumbnail: str | None = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[MealPlanOut])
async def list_meal_plans(
    date_from: date | None = None,
    date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    q = (
        select(MealPlan)
        .where(MealPlan.owner_id == user.id)
        .order_by(MealPlan.date, MealPlan.meal_type)
    )
    if date_from:
        q = q.where(MealPlan.date >= date_from)
    if date_to:
        q = q.where(MealPlan.date <= date_to)
    plans = (await db.execute(q)).scalars().all()
    return await _display_titles(db, plans, user)


async def _display_titles(db: AsyncSession, plans: list[MealPlan], user: User) -> list:
    """Titre affiche dans la langue du compte (traduction deja en cache).

    recipe_title est une copie prise a l'ajout au planning, en francais :
    seule la reponse est traduite, jamais la ligne en base.
    """
    from ..models.recipe import Recipe
    from ..services import translation_service

    lang = getattr(user, "language", None)
    if lang not in translation_service.SUPPORTED_LANGUAGES or not plans:
        return plans
    ids = {p.recipe_id for p in plans}
    recipes = (await db.execute(
        select(Recipe).where(Recipe.id.in_(ids), Recipe.owner_id == user.id)
    )).scalars().all()
    titles = {}
    for recipe in recipes:
        translation = translation_service.cached_translation(recipe, lang)
        if translation and translation.get("title"):
            titles[recipe.id] = translation["title"]
    return [
        MealPlanOut.model_validate(p).model_copy(update={"recipe_title": titles[p.recipe_id]})
        if p.recipe_id in titles else p
        for p in plans
    ]


@router.post("", response_model=MealPlanOut, status_code=201)
async def create_meal_plan(
    data: MealPlanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    # Auto-fill recipe info if not provided
    if not data.recipe_title:
        from ..models.recipe import Recipe
        recipe = await db.get(Recipe, data.recipe_id)
        # Une recette qui n'est pas la sienne ne renseigne rien : le repas
        # est cree tel quel plutot que de reveler un titre d'autrui.
        if recipe and recipe.owner_id == user.id:
            data = data.model_copy(update={
                "recipe_title": recipe.title,
                "recipe_thumbnail": recipe.thumbnail_url,
            })
    plan = MealPlan(**data.model_dump(), owner_id=user.id)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    # "Semaine Complète" = 28 repas dans LA semaine du repas ajouté (lun-dim)
    week_start = data.date - timedelta(days=data.date.weekday())
    week_end = week_start + timedelta(days=6)
    week_count = (await db.execute(
        select(func.count()).select_from(MealPlan)
        .where(MealPlan.owner_id == user.id,
               MealPlan.date >= week_start, MealPlan.date <= week_end)
    )).scalar_one()
    await achievement_service.on_meal_plan_created(db, week_count)
    return plan


@router.delete("/{plan_id}", status_code=204)
async def delete_meal_plan(
    plan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    plan = await db.get(MealPlan, plan_id)
    if not plan or plan.owner_id != user.id:
        # 404 et non 403 : ne pas confirmer l'existence de l'entree.
        raise HTTPException(404, "Entrée introuvable")
    await db.delete(plan)
    await db.commit()
