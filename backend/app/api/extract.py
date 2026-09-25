import asyncio
from uuid import UUID
from fastapi import APIRouter, Depends, BackgroundTasks, UploadFile, File, HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..deps import current_user
from ..models.user import User
from ..models.recipe import Recipe, ExtractionStatus
from ..schemas.recipe import ExtractionRequest, ExtractionResponse, RecipeOut
from ..services.extractor import extract
from ..services.extraction_steps import EXTRACTION_TIMEOUT_SECONDS, StepTracker

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
        .where(Recipe.status == ExtractionStatus.processing)
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
            steps.record("terminé")
            _apply_extracted_fields(recipe, data)
            recipe.status = ExtractionStatus.done
            recipe.error_msg = None
            recipe.progress_message = None
            await db.commit()
            from ..services import achievement_service
            await achievement_service.on_recipe_added(db, recipe.source_type or "manual")
        except TimeoutError:
            # wait_for a annulé extract() en plein vol, potentiellement au
            # milieu d'une requete sur `db` (report_progress commite depuis
            # extract()) : la session doit etre nettoyee avant de pouvoir
            # s'en resservir pour ecrire l'echec.
            await db.rollback()
            recipe.status = ExtractionStatus.failed
            recipe.error_msg = steps.timeout_message()
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
            recipe.error_msg = str(e)
            recipe.progress_message = None
            recipe.title = "Extraction échouée"
            await db.commit()


async def _run_image_extraction(recipe_id: UUID, image_bytes: bytes, mime_type: str):
    from ..database import AsyncSessionLocal
    from ..services.ocr_service import extract_text_from_image
    from ..services.llm_service import extract_recipe_with_llm

    async with AsyncSessionLocal() as db:
        recipe = await db.get(Recipe, recipe_id)
        if not recipe:
            return

        recipe.status = ExtractionStatus.processing
        await db.commit()

        async def run_ocr_and_llm() -> dict:
            recipe.progress_message = "Lecture du texte de l'image (OCR)…"
            await db.commit()
            text = await extract_text_from_image(image_bytes, mime_type)

            recipe.progress_message = "Analyse de la recette par l'IA…"
            await db.commit()
            return await extract_recipe_with_llm(text)

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
            from ..services import achievement_service
            # "image" is not a stored SourceType: it only routes the
            # achievement so "Photographe" is reachable
            await achievement_service.on_recipe_added(db, "image")
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
            recipe.error_msg = str(e)
            recipe.progress_message = None
            recipe.title = "OCR échoué"
            await db.commit()
