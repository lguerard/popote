from uuid import UUID
from fastapi import APIRouter, Depends, BackgroundTasks, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models.recipe import Recipe, ExtractionStatus
from ..schemas.recipe import ExtractionRequest, ExtractionResponse, RecipeOut
from ..services.extractor import extract

router = APIRouter(tags=["extraction"])


@router.post("/extract", response_model=ExtractionResponse, status_code=202)
async def submit_extraction(
    req: ExtractionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    recipe = Recipe(title="Extraction en cours…", status=ExtractionStatus.pending)
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
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Fichier image requis (JPEG, PNG, WEBP…)")
    image_bytes = await file.read()
    mime_type = file.content_type

    recipe = Recipe(title="OCR en cours…", status=ExtractionStatus.pending)
    db.add(recipe)
    await db.commit()
    await db.refresh(recipe)

    background_tasks.add_task(_run_image_extraction, recipe.id, image_bytes, mime_type)

    return ExtractionResponse(
        recipe_id=recipe.id,
        status=ExtractionStatus.pending,
        message="OCR démarré",
    )


@router.get("/tasks/{recipe_id}", response_model=RecipeOut)
async def get_task_status(recipe_id: UUID, db: AsyncSession = Depends(get_db)):
    recipe = await db.get(Recipe, recipe_id)
    if not recipe:
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

        try:
            data = await extract(input_text, db=db)
            for field, value in data.items():
                if hasattr(recipe, field) and value is not None:
                    setattr(recipe, field, value)
            recipe.status = ExtractionStatus.done
            recipe.error_msg = None
        except Exception as e:
            recipe.status = ExtractionStatus.failed
            recipe.error_msg = str(e)
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

        try:
            text = await extract_text_from_image(image_bytes, mime_type)
            data = await extract_recipe_with_llm(text)
            if "error" in data:
                raise ValueError(data["error"])
            from ..models.recipe import SourceType
            data["source_type"] = SourceType.text
            for field, value in data.items():
                if hasattr(recipe, field) and value is not None:
                    setattr(recipe, field, value)
            recipe.status = ExtractionStatus.done
            recipe.error_msg = None
        except Exception as e:
            recipe.status = ExtractionStatus.failed
            recipe.error_msg = str(e)
            recipe.title = "OCR échoué"

        await db.commit()
