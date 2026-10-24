import asyncio
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, BackgroundTasks, UploadFile, File, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..deps import current_user
from ..models.user import User
from ..models.recipe import Recipe, ExtractionStatus
from ..schemas.recipe import (
    BatchExtractionRequest, BatchExtractionResponse, BatchItem, ExtractionRequest, ExtractionResponse, RecipeOut,
)
from ..services.extractor import MAX_BATCH_LINKS, extract, links_in
from ..services.extraction_steps import EXTRACTION_TIMEOUT_SECONDS, StepTracker, error_text
from ..services import sharing
from ..services.llm_service import offload_hint

logger = logging.getLogger(__name__)

router = APIRouter(tags=["extraction"])


# Champs qu'une extraction a le droit d'ecrire sur la recette. Le modele ne
# suit pas toujours le schema du prompt a la lettre (ex: un champ "notes"
# invente, en plus de ceux demandes) : un setattr non filtre sur l'ORM
# ecrirait une valeur de mauvais type sur une colonne existante (ici
# `notes`, reservee aux notes personnelles de l'utilisateur) et ferait
# echouer le commit. Toute cle hors de cette liste est silencieusement
# ignoree plutot que de planter l'ecriture en base.
_EXTRACTED_FIELDS = {
    "title", "description", "source_url", "source_type", "language",
    "servings", "prep_time", "cook_time", "ingredients", "steps", "tags",
    "category", "thumbnail_url", "similar_recipe_id",
}


def _apply_extracted_fields(recipe: Recipe, data: dict) -> None:
    for field, value in data.items():
        if field in _EXTRACTED_FIELDS and hasattr(recipe, field) and value is not None:
            setattr(recipe, field, value)


@router.post("/extract", response_model=ExtractionResponse, status_code=202)
async def submit_extraction(
    req: ExtractionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = Recipe(title="Extraction en cours…", status=ExtractionStatus.pending,
                    owner_id=user.id)
    db.add(recipe)
    await db.commit()
    await db.refresh(recipe)

    background_tasks.add_task(_run_extraction, recipe.id, req.input)

    return ExtractionResponse(
        recipe_id=recipe.id,
        status=ExtractionStatus.pending,
        message="Extraction démarrée",
    )


@router.post("/extract/batch", response_model=BatchExtractionResponse, status_code=202)
async def submit_batch_extraction(
    req: BatchExtractionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Plusieurs liens d'un coup (reels enregistrés, favoris…), extraits l'un
    après l'autre : en parallèle, ils se disputeraient le modèle et la carte
    graphique, et finiraient tous par dépasser le temps imparti."""
    links = links_in(req.text)
    if not links:
        raise HTTPException(400, "Aucun lien trouvé dans le texte.")
    saved = set((await db.execute(
        select(Recipe.source_url).where(
            Recipe.owner_id == user.id, Recipe.status == ExtractionStatus.done, Recipe.source_url.in_(links),
        )
    )).scalars())
    todo = [link for link in links if link not in saved]
    ignored = max(0, len(todo) - MAX_BATCH_LINKS)
    todo = todo[:MAX_BATCH_LINKS]

    recipes = [
        Recipe(title="En attente…", status=ExtractionStatus.pending, owner_id=user.id, source_url=link,
               progress_message=f"En file d'attente ({n}/{len(todo)})")
        for n, link in enumerate(todo, 1)
    ]
    db.add_all(recipes)
    await db.commit()
    jobs = [(recipe.id, link) for recipe, link in zip(recipes, todo)]
    if jobs:
        background_tasks.add_task(_run_batch, jobs)
    return BatchExtractionResponse(
        items=[BatchItem(recipe_id=recipe_id, input=link) for recipe_id, link in jobs],
        already_saved=[link for link in links if link in saved],
        ignored=ignored,
    )


async def _run_batch(jobs: list[tuple[UUID, str]]) -> None:
    for recipe_id, link in jobs:
        try:
            await _run_extraction(recipe_id, link)
        except Exception:  # une recette en échec n'arrête pas les suivantes
            logger.exception("Import groupé : échec inattendu pour %s", link)


@router.get("/tasks", response_model=list[RecipeOut])
async def get_tasks_status(
    ids: str = Query(..., max_length=5000, description="Identifiants séparés par des virgules"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """État de plusieurs extractions en une requête (suivi d'un import groupé)."""
    try:
        wanted = [UUID(part) for part in ids.split(",") if part.strip()][:MAX_BATCH_LINKS]
    except ValueError:
        raise HTTPException(400, "Identifiant invalide")
    rows = (await db.execute(
        select(Recipe).where(Recipe.id.in_(wanted), Recipe.owner_id == user.id)
    )).scalars().all()
    by_id = {recipe.id: recipe for recipe in rows}
    return [by_id[i] for i in wanted if i in by_id]


@router.post("/extract/image", response_model=ExtractionResponse, status_code=202)
async def submit_image_extraction(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Fichier image requis (JPEG, PNG, WEBP…)")
    image_bytes = await file.read()
    mime_type = file.content_type

    recipe = Recipe(title="OCR en cours…", status=ExtractionStatus.pending,
                    owner_id=user.id)
    db.add(recipe)
    await db.commit()
    await db.refresh(recipe)

    background_tasks.add_task(_run_image_extraction, recipe.id, image_bytes, mime_type)

    return ExtractionResponse(
        recipe_id=recipe.id,
        status=ExtractionStatus.pending,
        message="OCR démarré",
    )


async def sweep_stuck_extractions(db: AsyncSession) -> int:
    """Marque en échec les extractions laissées "processing" par un redémarrage.

    Les extractions tournent en arrière-plan dans le processus : un
    redémarrage (déploiement, crash) les tue sans jamais toucher leur ligne,
    qui resterait "processing" pour toujours sinon — rien ne la relance.
    Appelé une fois au démarrage.
    """
    result = await db.execute(
        update(Recipe)
        # En file d'attente aussi : l'import groupé meurt avec le processus.
        .where(Recipe.status.in_([ExtractionStatus.processing, ExtractionStatus.pending]))
        .values(
            status=ExtractionStatus.failed,
            error_msg="Extraction interrompue par un redémarrage du serveur.",
            progress_message=None,
            title="Extraction échouée",
        )
    )
    await db.commit()
    return result.rowcount


@router.get("/tasks/{recipe_id}", response_model=RecipeOut)
async def get_task_status(
    recipe_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = await db.get(Recipe, recipe_id)
    if not recipe or recipe.owner_id != user.id:
        raise HTTPException(404, "Tâche introuvable")
    return recipe


async def _record_achievement(db: AsyncSession, source_type) -> None:
    """Succès débloqués par une recette ajoutée, sans jamais faire échouer
    l'extraction : la recette est déjà enregistrée à ce stade, un souci ici
    la faisait pourtant passer en « échec »."""
    from ..services import achievement_service
    try:
        await achievement_service.on_recipe_added(db, source_type)
    except Exception:
        await db.rollback()
        logger.warning("Succès non mis à jour après l'ajout d'une recette", exc_info=True)


async def _run_extraction(recipe_id: UUID, input_text: str):
    from ..database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        recipe = await db.get(Recipe, recipe_id)
        if not recipe:
            return

        recipe.status = ExtractionStatus.processing
        await db.commit()
        steps = StepTracker(f"extraction {input_text.strip()[:80]}")

        async def report_progress(message: str) -> None:
            steps.record(message)
            recipe.progress_message = message
            await db.commit()

        try:
            data = await asyncio.wait_for(
                extract(input_text, db=db, on_progress=report_progress, owner_id=recipe.owner_id),
                timeout=EXTRACTION_TIMEOUT_SECONDS,
            )
            _apply_extracted_fields(recipe, data)
            # Image de la source stockée ici : les liens Instagram/TikTok
            # expirent au bout de quelques jours (image cassée ensuite).
            from ..services import image_service
            await report_progress("Enregistrement de l'image…")
            await image_service.apply_source_image(recipe, data.get("thumbnail_url"), replace=False)
            steps.record("terminé")
            recipe.status = ExtractionStatus.done
            recipe.error_msg = None
            recipe.progress_message = None
            await db.commit()
        except TimeoutError:
            # wait_for a annulé extract() en plein vol, potentiellement au
            # milieu d'une requete sur `db` (report_progress commite depuis
            # extract()) : la session doit etre nettoyee avant de pouvoir
            # s'en resservir pour ecrire l'echec.
            await db.rollback()
            recipe.status = ExtractionStatus.failed
            recipe.error_msg = steps.timeout_message(hint=offload_hint())
            recipe.progress_message = None
            recipe.title = "Extraction échouée"
            await db.commit()
        except Exception as e:
            # Une exception pendant la flush (ex: valeur du LLM du mauvais
            # type pour une colonne) laisse la session dans un etat que
            # SQLAlchemy refuse de recommiter sans rollback prealable —
            # sans lui, ce commit lève a son tour, non rattrapé puisqu'on
            # est deja dans le except, et la recette reste "processing"
            # pour toujours au lieu de passer a "failed".
            await db.rollback()
            recipe.status = ExtractionStatus.failed
            recipe.error_msg = error_text(e)
            recipe.progress_message = None
            recipe.title = "Extraction échouée"
            await db.commit()
        else:
            await _record_achievement(db, recipe.source_type or "manual")
            await sharing.auto_share(db, recipe)


# Au-delà, le texte lu sur une photo est plus qu'un nom de plat ou un menu.
_LONG_OCR_TEXT_CHARS = 300


async def _run_image_extraction(recipe_id: UUID, image_bytes: bytes, mime_type: str):
    from ..database import AsyncSessionLocal
    from ..services.ocr_service import extract_text_from_image
    from ..services.extractor import recipe_for_dish
    from ..services.llm_service import extract_recipe_from_image, extract_recipe_with_llm

    async with AsyncSessionLocal() as db:
        recipe = await db.get(Recipe, recipe_id)
        if not recipe:
            return

        recipe.status = ExtractionStatus.processing
        await db.commit()

        async def report(message: str) -> None:
            recipe.progress_message = message
            await db.commit()

        async def run_ocr_and_llm() -> dict:
            # 1. La photo lue directement par le modèle de vision : un seul
            #    appel, la mise en page (colonnes, quantités en marge) aidant.
            await report("Lecture de la recette sur la photo…")
            data = None
            try:
                data = await extract_recipe_from_image(image_bytes, mime_type)
            except Exception:
                # Modèle sans vision, délai dépassé, réponse illisible : on
                # retombe sur le chemin texte, Tesseract compris.
                logger.warning("Lecture directe de la photo impossible — repli sur l'OCR", exc_info=True)
            if data is not None and "error" not in data:
                return data

            # 2. Pas de recette écrite (plat, menu…) ou lecture directe en
            #    échec : le texte de l'image (ou le nom du plat montré).
            await report("Lecture du texte de l'image (OCR)…")
            text = await extract_text_from_image(image_bytes, mime_type)
            if not text.strip():
                raise ValueError("Aucun texte lisible sur cette image.")
            # Texte long : sans doute une recette que la lecture directe a
            # manquée, l'analyse texte a sa chance avant le « plat reconnu ».
            if data is None or len(text.strip()) > _LONG_OCR_TEXT_CHARS:
                await report("Analyse de la recette par l'IA…")
                data = await extract_recipe_with_llm(text)
            if "error" in data:
                # Photo d'un plat, d'un menu, recette partielle : une vraie
                # recette du plat reconnu (web, sinon IA) plutôt qu'un échec.
                data, image = await recipe_for_dish(text, report)
                if "error" in data:
                    data = {"error": "Aucune recette ni aucun plat reconnaissable sur cette image."}
                elif image:
                    data["thumbnail_url"] = image
            return data

        try:
            data = await asyncio.wait_for(run_ocr_and_llm(), timeout=EXTRACTION_TIMEOUT_SECONDS)
            if "error" in data:
                raise ValueError(data["error"])
            from ..models.recipe import SourceType
            data["source_type"] = SourceType.text
            _apply_extracted_fields(recipe, data)
            recipe.status = ExtractionStatus.done
            recipe.error_msg = None
            recipe.progress_message = None
            await db.commit()
        except TimeoutError:
            await db.rollback()
            recipe.status = ExtractionStatus.failed
            recipe.error_msg = (
                f"Extraction trop longue (plus de {EXTRACTION_TIMEOUT_SECONDS // 60} "
                "minutes) : abandonnée."
            )
            recipe.progress_message = None
            recipe.title = "OCR échoué"
            await db.commit()
        except Exception as e:
            await db.rollback()
            recipe.status = ExtractionStatus.failed
            recipe.error_msg = error_text(e)
            recipe.progress_message = None
            recipe.title = "OCR échoué"
            await db.commit()
        else:
            # "image" is not a stored SourceType: it only routes the
            # achievement so "Photographe" is reachable
            await _record_achievement(db, "image")
            await sharing.auto_share(db, recipe)
