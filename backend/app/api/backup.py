"""Sauvegarde et restauration du compte (voir services/backup.py)."""

import asyncio
import logging
import os
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import current_user
from ..models.user import User
from ..services import backup

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backup", tags=["backup"])

# Images comprises : plusieurs centaines de recettes font vite quelques
# centaines de Mo (voir aussi client_max_body_size dans nginx.conf).
_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
_CHUNK = 1024 * 1024


class RestoreReport(BaseModel):
    recipes_added: int
    recipes_skipped: int
    invalid: int
    images: int
    collections_added: int


def _temp_zip() -> Path:
    fd, name = tempfile.mkstemp(prefix="popote-", suffix=".zip")
    os.close(fd)
    return Path(name)


@router.get("")
async def download_backup(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Toutes les recettes du compte (images, carnets, historique) en un .zip."""
    path = _temp_zip()
    try:
        await backup.build_backup(db, user.id, path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    background_tasks.add_task(path.unlink, missing_ok=True)
    return FileResponse(
        path, media_type="application/zip",
        filename=f"popote-sauvegarde-{date.today().isoformat()}.zip",
    )


@router.post("/import", response_model=RestoreReport)
async def import_backup(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """Ajoute au compte le contenu d'une sauvegarde, sans créer de doublons."""
    path = _temp_zip()
    try:
        size = 0
        with path.open("wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if size > _MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Sauvegarde trop volumineuse (2 Go maximum).")
                await asyncio.to_thread(out.write, chunk)
        try:
            report = await backup.restore_backup(db, user.id, path)
        except backup.BackupError as e:
            await db.rollback()
            raise HTTPException(400, str(e))
        logger.info("Sauvegarde importée pour %s : %s", user.id, report)
        return report
    finally:
        path.unlink(missing_ok=True)
