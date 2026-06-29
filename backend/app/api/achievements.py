from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
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


@router.get("/achievements", response_model=list[AchievementOut])
async def get_achievements(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Achievement).order_by(Achievement.category, Achievement.goal))
    return result.scalars().all()


@router.post("/achievements/cooking-mode")
async def track_cooking_mode(db: AsyncSession = Depends(get_db)):
    await achievement_service.on_cooking_mode_used(db)
    return {"ok": True}
