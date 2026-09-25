import asyncio
import secrets
from datetime import date
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import func, select, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..deps import current_user
from ..models.cook_log import CookLog
from ..models.user import User
from ..models.recipe import Recipe, ExtractionStatus
from ..schemas.recipe import (
    CookedIn, CookLogOut, NutritionOut, PantryMatch, PantryRequest, RecipeCreate,
    RecipeOut, RecipeUpdate,
)
from ..services import achievement_service, grocery, image_service

router = APIRouter(prefix="/recipes", tags=["recipes"])

# jpeg/png/webp uniquement : ce que <input type="file" accept="image/*">
# produit en pratique, et ce que les navigateurs affichent tous nativement.
_ALLOWED_IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_MAX_UPLOAD_BYTES = 8 * 1024 * 1024
# Genereux : couvre le tout premier appel, qui doit en plus telecharger le
# modele (~2 Go) avant de generer quoi que ce soit. Tourne en arriere-plan
# (voir generate_thumbnail/_run_thumbnail_generation) donc rien n'attend
# cette duree sur une connexion HTTP — un appel synchrone plus tot a fini
# par depasser les delais de nginx/Cloudflare et casser la reponse.
_THUMBNAIL_GENERATION_TIMEOUT_SECONDS = 600

async def _owned_recipe(db: AsyncSession, recipe_id: UUID, user: User) -> Recipe:
    """Recupere une recette appartenant a l'utilisateur courant.

    Leve 404 -- et non 403 -- sur la recette de quelqu'un d'autre : un 403
    confirmerait son existence a qui essaie des identifiants au hasard.

    Parameters
    ----------
    db : AsyncSession
        Session courante.
    recipe_id : UUID
        Identifiant demande.
    user : User
        Utilisateur authentifie.

    Returns
    -------
    Recipe
        La recette, garantie appartenir a `user`.
    """
    recipe = await db.get(Recipe, recipe_id)
    if not recipe or recipe.owner_id != user.id:
        raise HTTPException(404, "Recette introuvable")
    return recipe


def _apply_update(recipe: Recipe, data: RecipeUpdate) -> None:
    """Applique une mise a jour partielle a une recette.

    Les valeurs nutritionnelles ne sont PAS effacees ici, meme quand les
    ingredients ou les portions changent : le recalcul est declenche a la
    main depuis la fiche ("Recalculer"), ce qui laisse le choix plutot que
    de faire disparaitre une analyse a chaque sauvegarde.

    Parameters
    ----------
    recipe : Recipe
        Recette en base, modifiee sur place.
    data : RecipeUpdate
        Champs envoyes par le client.
    """
    # exclude_unset (pas exclude_none) : un null explicite efface le champ
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(recipe, field, value)


@router.get("", response_model=list[RecipeOut])
async def list_recipes(
    search: str | None = Query(None),
    tag: str | None = Query(None),
    category: str | None = Query(None),
    source_type: str | None = Query(None),
    max_time: int | None = Query(None, description="Temps total max en minutes"),
    favorites_only: bool = Query(False),
    never_cooked: bool = Query(False, description="Seulement les recettes jamais cuisinées"),
    cook_again: bool = Query(False, description="Seulement celles marquées « à refaire »"),
    sort: str = Query("recent", pattern="^(recent|rating|last_cooked|most_cooked|title)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    # Extractions en cours/échouées suivies via /tasks/{id}, pas la collection
    order = {
        "recent": (Recipe.created_at.desc(),),
        "rating": (Recipe.rating.desc().nulls_last(), Recipe.created_at.desc()),
        "last_cooked": (Recipe.last_cooked_at.desc().nulls_last(), Recipe.created_at.desc()),
        "most_cooked": (Recipe.cooked_count.desc(), Recipe.created_at.desc()),
        "title": (func.lower(Recipe.title),),
    }[sort]
    q = (
        select(Recipe)
        .where(Recipe.owner_id == user.id)
        .where(Recipe.status == ExtractionStatus.done)
        .order_by(*order)
    )
    if search:
        pattern = f"%{search}%"
        q = q.where(or_(Recipe.title.ilike(pattern), Recipe.description.ilike(pattern)))
    if favorites_only:
        q = q.where(Recipe.is_favorite.is_(True))
    if never_cooked:
        q = q.where(Recipe.cooked_count == 0)
    if cook_again:
        q = q.where(Recipe.cook_again.is_(True))
    if tag:
        q = q.where(Recipe.tags.contains([tag]))
    if category:
        q = q.where(Recipe.category == category)
    if source_type:
        q = q.where(Recipe.source_type == source_type)
    if max_time:
        # COALESCE : sinon un prep_time ou cook_time NULL (frequent sur les
        # recettes manuelles simples, ex: pas de vraie "cuisson") propage sa
        # nullite a toute la somme en SQL, et la recette sort du filtre
        # meme quand le temps rempli, a lui seul, est bien sous le seuil.
        total_time = func.coalesce(Recipe.prep_time, 0) + func.coalesce(Recipe.cook_time, 0)
        q = q.where(total_time <= max_time)
    q = q.offset((page - 1) * limit).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/what-to-cook", response_model=list[PantryMatch])
async def what_to_cook(
    req: PantryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """« Qu'est-ce que je cuisine ? » : ses recettes classées selon le frigo."""
    rows = (await db.execute(
        select(Recipe)
        .where(Recipe.owner_id == user.id, Recipe.status == ExtractionStatus.done)
    )).scalars().all()
    by_id = {str(r.id): r for r in rows}
    ranked = grocery.rank_by_pantry(
        [{"id": str(r.id), "ingredients": r.ingredients or []} for r in rows],
        req.ingredients,
        assume_staples=req.assume_staples,
    )
    if req.max_missing is not None:
        ranked = [r for r in ranked if len(r["missing"]) <= req.max_missing]
    return [
        PantryMatch(
            recipe=RecipeOut.model_validate(by_id[r["recipe"]["id"]]),
            matched=r["matched"], missing=r["missing"], coverage=r["coverage"],
        )
        for r in ranked[:60]
    ]


@router.post("", response_model=RecipeOut, status_code=201)
async def create_recipe(
    data: RecipeCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = Recipe(**data.model_dump(), owner_id=user.id)
    db.add(recipe)
    await db.commit()
    await db.refresh(recipe)
    await achievement_service.on_recipe_added(db, recipe.source_type or "manual")
    return recipe


@router.get("/{recipe_id}", response_model=RecipeOut)
async def get_recipe(
    recipe_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = await _owned_recipe(db, recipe_id, user)
    return recipe


@router.put("/{recipe_id}", response_model=RecipeOut)
async def update_recipe(
    recipe_id: UUID,
    data: RecipeUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = await _owned_recipe(db, recipe_id, user)
    old_notes = recipe.notes
    _apply_update(recipe, data)
    await db.commit()
    await db.refresh(recipe)
    if recipe.notes and recipe.notes != old_notes:
        await achievement_service.on_notes_saved(db)
    return recipe


@router.patch("/{recipe_id}", response_model=RecipeOut)
async def patch_recipe(
    recipe_id: UUID,
    data: RecipeUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = await _owned_recipe(db, recipe_id, user)
    old_notes = recipe.notes
    _apply_update(recipe, data)
    await db.commit()
    await db.refresh(recipe)
    if recipe.notes and recipe.notes != old_notes:
        await achievement_service.on_notes_saved(db)
    return recipe


@router.delete("/{recipe_id}", status_code=204)
async def delete_recipe(
    recipe_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = await _owned_recipe(db, recipe_id, user)
    await db.delete(recipe)
    await db.commit()


@router.post("/{recipe_id}/favorite", response_model=RecipeOut)
async def toggle_favorite(
    recipe_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = await _owned_recipe(db, recipe_id, user)
    recipe.is_favorite = not recipe.is_favorite
    await db.commit()
    await db.refresh(recipe)
    if recipe.is_favorite:
        await achievement_service.on_favorite_toggled(db)
    return recipe


@router.post("/{recipe_id}/thumbnail", response_model=RecipeOut)
async def upload_thumbnail(
    recipe_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = await _owned_recipe(db, recipe_id, user)
    ext = _ALLOWED_IMAGE_TYPES.get(file.content_type)
    if not ext:
        raise HTTPException(400, "Image requise (JPEG, PNG ou WEBP)")
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(400, "Image trop volumineuse (8 Mo maximum)")

    image_service.delete_local_thumbnail(recipe.thumbnail_url)
    recipe.thumbnail_url = image_service.save_thumbnail_bytes(recipe.id, data, ext)
    await db.commit()
    await db.refresh(recipe)
    return recipe


@router.post("/{recipe_id}/thumbnail/generate", response_model=RecipeOut, status_code=202)
async def generate_thumbnail(
    recipe_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Lance la génération en arrière-plan ; le client suit via GET /recipes/{id}.

    La toute première génération doit télécharger le modèle (~2 Go) avant
    de produire quoi que ce soit : une réponse synchrone dépasserait les
    délais de nginx/Cloudflare et casserait la connexion en plein milieu,
    exactement le même problème que l'extraction de recette avait déjà
    résolu avec ce même pattern tâche de fond + statut interrogé par le
    client.
    """
    recipe = await _owned_recipe(db, recipe_id, user)
    recipe.thumbnail_generating = True
    recipe.thumbnail_error = None
    await db.commit()
    await db.refresh(recipe)
    background_tasks.add_task(_run_thumbnail_generation, recipe.id)
    return recipe


async def _run_thumbnail_generation(recipe_id: UUID):
    from ..database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        recipe = await db.get(Recipe, recipe_id)
        if not recipe:
            return
        try:
            image_bytes = await asyncio.wait_for(
                image_service.generate_recipe_image(
                    recipe.title, recipe.description, recipe.category,
                    recipe.ingredients, recipe.steps,
                ),
                timeout=_THUMBNAIL_GENERATION_TIMEOUT_SECONDS,
            )
            image_service.delete_local_thumbnail(recipe.thumbnail_url)
            recipe.thumbnail_url = image_service.save_thumbnail_bytes(recipe.id, image_bytes, "png")
            recipe.thumbnail_generating = False
            recipe.thumbnail_error = None
            await db.commit()
        except TimeoutError:
            # wait_for annule la coroutine en plein vol, potentiellement
            # en pleine requete sur `db` : la session doit etre nettoyee
            # avant de pouvoir s'en resservir (meme lecon que pour
            # l'extraction de recette, voir api/extract.py).
            await db.rollback()
            recipe.thumbnail_generating = False
            recipe.thumbnail_error = (
                f"Génération trop longue (plus de {_THUMBNAIL_GENERATION_TIMEOUT_SECONDS // 60} minutes)."
            )
            await db.commit()
        except Exception as e:
            await db.rollback()
            recipe.thumbnail_generating = False
            recipe.thumbnail_error = str(e)
            await db.commit()


async def sweep_stuck_thumbnails(db: AsyncSession) -> int:
    """Marque en échec les générations laissées 'en cours' par un redémarrage.

    Meme raisonnement que sweep_stuck_extractions dans api/extract.py :
    une tache de fond ne survit pas a un redemarrage du processus, donc
    toute recette encore thumbnail_generating=true au demarrage est
    forcement un reste d'un ancien processus, jamais une tache en cours.
    """
    result = await db.execute(
        update(Recipe)
        .where(Recipe.thumbnail_generating.is_(True))
        .values(
            thumbnail_generating=False,
            thumbnail_error="Génération interrompue par un redémarrage du serveur.",
        )
    )
    await db.commit()
    return result.rowcount


@router.post("/{recipe_id}/nutrition", response_model=NutritionOut)
async def analyze_nutrition(
    recipe_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = await _owned_recipe(db, recipe_id, user)
    from ..services.nutrition_service import analyze_nutrition as _analyze
    nutrition = await _analyze(recipe.title, recipe.ingredients or [], recipe.servings)
    recipe.nutrition = nutrition
    await db.commit()
    await achievement_service.on_nutrition_analyzed(db)
    return nutrition


# ---------------------------------------------------------------------------
# Historique « cuisinée le… »
# ---------------------------------------------------------------------------

async def _refresh_cook_stats(db: AsyncSession, recipe: Recipe) -> None:
    count, last = (await db.execute(
        select(func.count(), func.max(CookLog.cooked_on)).where(CookLog.recipe_id == recipe.id)
    )).one()
    recipe.cooked_count = count
    recipe.last_cooked_at = last


@router.post("/{recipe_id}/cooked", response_model=RecipeOut, status_code=201)
async def mark_cooked(
    recipe_id: UUID,
    data: CookedIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = await _owned_recipe(db, recipe_id, user)
    db.add(CookLog(
        owner_id=user.id, recipe_id=recipe.id, cooked_on=data.cooked_on or date.today(),
        rating=data.rating, comment=(data.comment or "").strip() or None,
    ))
    await db.flush()
    await _refresh_cook_stats(db, recipe)
    if data.rating:
        recipe.rating = data.rating
    await db.commit()
    await db.refresh(recipe)
    return recipe


@router.get("/{recipe_id}/history", response_model=list[CookLogOut])
async def cook_history(
    recipe_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = await _owned_recipe(db, recipe_id, user)
    return (await db.execute(
        select(CookLog).where(CookLog.recipe_id == recipe.id)
        .order_by(CookLog.cooked_on.desc(), CookLog.created_at.desc())
    )).scalars().all()


@router.delete("/{recipe_id}/history/{log_id}", response_model=RecipeOut)
async def delete_cook_log(
    recipe_id: UUID,
    log_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = await _owned_recipe(db, recipe_id, user)
    log = await db.get(CookLog, log_id)
    if not log or log.recipe_id != recipe.id:
        raise HTTPException(404, "Entrée introuvable")
    await db.delete(log)
    await db.flush()
    await _refresh_cook_stats(db, recipe)
    await db.commit()
    await db.refresh(recipe)
    return recipe


# ---------------------------------------------------------------------------
# Partage par lien public
# ---------------------------------------------------------------------------

@router.post("/{recipe_id}/share", response_model=RecipeOut)
async def share_recipe(
    recipe_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = await _owned_recipe(db, recipe_id, user)
    if not recipe.share_token:
        recipe.share_token = secrets.token_urlsafe(16)
        await db.commit()
        await db.refresh(recipe)
    return recipe


@router.delete("/{recipe_id}/share", response_model=RecipeOut)
async def unshare_recipe(
    recipe_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Révoque le lien : l'ancien jeton cesse aussitôt de fonctionner."""
    recipe = await _owned_recipe(db, recipe_id, user)
    recipe.share_token = None
    await db.commit()
    await db.refresh(recipe)
    return recipe


# ---------------------------------------------------------------------------
# Réextraction depuis la source
# ---------------------------------------------------------------------------

# Ce qu'une réextraction remplace. Jamais les notes, favoris, avis ni
# historique : ils sont à l'utilisateur, pas à la source. Ni
# similar_recipe_id : la recherche de doublons trouverait la recette
# elle-même.
_REEXTRACTED_FIELDS = (
    "title", "description", "language", "servings", "prep_time", "cook_time",
    "ingredients", "steps", "tags", "category",
)


@router.post("/{recipe_id}/reextract", response_model=RecipeOut, status_code=202)
async def reextract_recipe(
    recipe_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Relance l'extraction sur l'URL d'origine et met la recette à jour sur place.

    La recette reste visible pendant ce temps (statut inchangé) ; le client
    suit ``reextracting`` / ``progress_message`` via GET /recipes/{id}.
    """
    recipe = await _owned_recipe(db, recipe_id, user)
    if not recipe.source_url:
        raise HTTPException(400, "Cette recette n'a pas de source à réextraire")
    if recipe.reextracting:
        return recipe
    recipe.reextracting = True
    recipe.error_msg = None
    recipe.progress_message = "En attente…"
    await db.commit()
    await db.refresh(recipe)
    background_tasks.add_task(_run_reextraction, recipe.id)
    return recipe


async def _run_reextraction(recipe_id: UUID):
    from ..database import AsyncSessionLocal
    from ..services.extractor import extract
    from ..services.extraction_steps import EXTRACTION_TIMEOUT_SECONDS, StepTracker

    async with AsyncSessionLocal() as db:
        recipe = await db.get(Recipe, recipe_id)
        if not recipe:
            return
        steps = StepTracker(f"réextraction {(recipe.source_url or '')[:80]}")

        async def report_progress(message: str) -> None:
            steps.record(message)
            recipe.progress_message = message
            await db.commit()

        try:
            data = await asyncio.wait_for(
                extract(recipe.source_url, on_progress=report_progress),
                timeout=EXTRACTION_TIMEOUT_SECONDS,
            )
            steps.record("terminé")
            for field in _REEXTRACTED_FIELDS:
                if data.get(field) not in (None, "", []):
                    setattr(recipe, field, data[field])
            # Une image importée ou générée par l'utilisateur (/media/…)
            # prime sur celle de la source.
            if data.get("thumbnail_url") and not (recipe.thumbnail_url or "").startswith("/media/"):
                recipe.thumbnail_url = data["thumbnail_url"]
            recipe.error_msg = None
        except TimeoutError:
            await db.rollback()
            from ..services.llm_service import offload_hint
            recipe.error_msg = steps.timeout_message(
                "Réextraction", "la recette n'a pas été modifiée.", offload_hint(),
            )
        except Exception as e:
            await db.rollback()
            recipe.error_msg = f"Réextraction échouée, la recette n'a pas été modifiée : {e}"
        recipe.reextracting = False
        recipe.progress_message = None
        await db.commit()


async def sweep_stuck_reextractions(db: AsyncSession) -> int:
    """Même principe que sweep_stuck_thumbnails, pour les réextractions."""
    result = await db.execute(
        update(Recipe)
        .where(Recipe.reextracting.is_(True))
        .values(
            reextracting=False,
            progress_message=None,
            error_msg="Réextraction interrompue par un redémarrage du serveur.",
        )
    )
    await db.commit()
    return result.rowcount
