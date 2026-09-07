from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models.recipe import Recipe, ExtractionStatus
from ..schemas.recipe import RecipeCreate, RecipeUpdate, RecipeOut, NutritionOut
from ..services import achievement_service

router = APIRouter(prefix="/recipes", tags=["recipes"])

# Champs dont dependent les valeurs nutritionnelles : analyze_nutrition()
# n'estime qu'a partir des ingredients et du nombre de portions.
NUTRITION_INPUTS = ("ingredients", "servings")


def _apply_update(recipe: Recipe, data: RecipeUpdate) -> None:
    """Applique une mise a jour partielle et invalide ce qui devient faux.

    Parameters
    ----------
    recipe : Recipe
        Recette en base, modifiee sur place.
    data : RecipeUpdate
        Champs envoyes par le client.
    """
    # exclude_unset (pas exclude_none) : un null explicite efface le champ
    changes = data.model_dump(exclude_unset=True)
    stale = any(
        field in changes and changes[field] != getattr(recipe, field)
        for field in NUTRITION_INPUTS
    )
    for field, value in changes.items():
        setattr(recipe, field, value)
    # Les valeurs nutritionnelles sont estimees a partir des ingredients et
    # des portions : les conserver apres modification afficherait des
    # chiffres faux sans que rien ne le signale. On les efface, et le
    # bouton "Analyser" reapparait cote client (il s'affiche sur
    # nutrition == null). Un nutrition explicite dans la requete gagne :
    # le client qui vient de poser une valeur ne se la fait pas effacer.
    if stale and "nutrition" not in changes:
        recipe.nutrition = None


@router.get("", response_model=list[RecipeOut])
async def list_recipes(
    search: str | None = Query(None),
    tag: str | None = Query(None),
    category: str | None = Query(None),
    source_type: str | None = Query(None),
    max_time: int | None = Query(None, description="Temps total max en minutes"),
    favorites_only: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    # Extractions en cours/échouées suivies via /tasks/{id}, pas la collection
    q = (
        select(Recipe)
        .where(Recipe.status == ExtractionStatus.done)
        .order_by(Recipe.created_at.desc())
    )
    if search:
        pattern = f"%{search}%"
        q = q.where(or_(Recipe.title.ilike(pattern), Recipe.description.ilike(pattern)))
    if favorites_only:
        q = q.where(Recipe.is_favorite.is_(True))
    if tag:
        q = q.where(Recipe.tags.contains([tag]))
    if category:
        q = q.where(Recipe.category == category)
    if source_type:
        q = q.where(Recipe.source_type == source_type)
    if max_time:
        q = q.where((Recipe.prep_time + Recipe.cook_time) <= max_time)
    q = q.offset((page - 1) * limit).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=RecipeOut, status_code=201)
async def create_recipe(data: RecipeCreate, db: AsyncSession = Depends(get_db)):
    recipe = Recipe(**data.model_dump())
    db.add(recipe)
    await db.commit()
    await db.refresh(recipe)
    await achievement_service.on_recipe_added(db, recipe.source_type or "manual")
    return recipe


@router.get("/{recipe_id}", response_model=RecipeOut)
async def get_recipe(recipe_id: UUID, db: AsyncSession = Depends(get_db)):
    recipe = await db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(404, "Recette introuvable")
    return recipe


@router.put("/{recipe_id}", response_model=RecipeOut)
async def update_recipe(recipe_id: UUID, data: RecipeUpdate, db: AsyncSession = Depends(get_db)):
    recipe = await db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(404, "Recette introuvable")
    old_notes = recipe.notes
    _apply_update(recipe, data)
    await db.commit()
    await db.refresh(recipe)
    if recipe.notes and recipe.notes != old_notes:
        await achievement_service.on_notes_saved(db)
    return recipe


@router.patch("/{recipe_id}", response_model=RecipeOut)
async def patch_recipe(recipe_id: UUID, data: RecipeUpdate, db: AsyncSession = Depends(get_db)):
    recipe = await db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(404, "Recette introuvable")
    old_notes = recipe.notes
    _apply_update(recipe, data)
    await db.commit()
    await db.refresh(recipe)
    if recipe.notes and recipe.notes != old_notes:
        await achievement_service.on_notes_saved(db)
    return recipe


@router.delete("/{recipe_id}", status_code=204)
async def delete_recipe(recipe_id: UUID, db: AsyncSession = Depends(get_db)):
    recipe = await db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(404, "Recette introuvable")
    await db.delete(recipe)
    await db.commit()


@router.post("/{recipe_id}/favorite", response_model=RecipeOut)
async def toggle_favorite(recipe_id: UUID, db: AsyncSession = Depends(get_db)):
    recipe = await db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(404, "Recette introuvable")
    recipe.is_favorite = not recipe.is_favorite
    await db.commit()
    await db.refresh(recipe)
    if recipe.is_favorite:
        await achievement_service.on_favorite_toggled(db)
    return recipe


@router.post("/{recipe_id}/nutrition", response_model=NutritionOut)
async def analyze_nutrition(recipe_id: UUID, db: AsyncSession = Depends(get_db)):
    recipe = await db.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(404, "Recette introuvable")
    from ..services.nutrition_service import analyze_nutrition as _analyze
    nutrition = await _analyze(recipe.title, recipe.ingredients or [], recipe.servings)
    recipe.nutrition = nutrition
    await db.commit()
    await achievement_service.on_nutrition_analyzed(db)
    return nutrition
