from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import current_user
from app.models.user import User
from app.models.achievement import Achievement
from app.services import achievement_service
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

router = APIRouter()


class AchievementOut(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    progress: int
    goal: int
    unlocked_at: Optional[datetime]
    category: str

    class Config:
        from_attributes = True


# Les succes restent COMMUNS a l'instance : le modele Achievement n'a pas
# de proprietaire, sa cle primaire est l'identifiant du succes lui-meme.
# Les rendre individuels demande une table de progression par utilisateur,
# hors du perimetre de cette etape. L'authentification est neanmoins
# exigee, pour qu'un visiteur anonyme ne lise pas la progression.
@router.get("/achievements", response_model=list[AchievementOut])
async def get_achievements(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    result = await db.execute(select(Achievement).order_by(Achievement.category, Achievement.goal))
    return result.scalars().all()


@router.post("/achievements/cooking-mode")
async def track_cooking_mode(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await achievement_service.on_cooking_mode_used(db)
    return {"ok": True}
