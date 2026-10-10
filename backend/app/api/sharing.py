"""Partage de recettes avec d'autres comptes de cette instance."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import current_user
from ..models.library_share import LibraryShare
from ..models.recipe import ExtractionStatus, Recipe
from ..models.user import User, UserStatus
from ..services import sharing

router = APIRouter(prefix="/sharing", tags=["sharing"])


class AccountOut(BaseModel):
    id: uuid.UUID
    display_name: str

    model_config = {"from_attributes": True}


class SendIn(BaseModel):
    user_id: uuid.UUID
    # Recettes choisies, ou toute la bibliothèque avec all=true.
    recipe_ids: list[uuid.UUID] = []
    all: bool = False
    # Envoie aussi, à l'avenir, chaque nouvelle recette à ce compte.
    automatic: bool = False


class SendOut(BaseModel):
    copied: int
    skipped: int
    automatic: bool


class AutomaticOut(BaseModel):
    # Comptes qui reçoivent automatiquement mes nouvelles recettes…
    outgoing: list[AccountOut]
    # …et comptes dont je reçois automatiquement les nouvelles recettes.
    incoming: list[AccountOut]


@router.get("/users", response_model=list[AccountOut])
async def shareable_accounts(
    db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
):
    """Les autres comptes validés, à qui l'on peut envoyer des recettes."""
    rows = await db.execute(
        select(User)
        .where(User.status == UserStatus.approved.value, User.id != user.id)
        .order_by(User.display_name)
    )
    return rows.scalars().all()


@router.post("/send", response_model=SendOut)
async def send_recipes(
    data: SendIn, db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
):
    target = await sharing.approved_user(db, data.user_id)
    if not target or target.id == user.id:
        raise HTTPException(404, "Compte introuvable")
    if not data.all and not data.recipe_ids and not data.automatic:
        raise HTTPException(400, "Aucune recette à partager")

    q = select(Recipe).where(Recipe.owner_id == user.id, Recipe.status == ExtractionStatus.done)
    if not data.all:
        q = q.where(Recipe.id.in_(data.recipe_ids))
    recipes = (await db.execute(q)).scalars().all() if (data.all or data.recipe_ids) else []
    if data.recipe_ids and not data.all and len(recipes) != len(set(data.recipe_ids)):
        # Une recette d'un autre compte : 404 comme partout ailleurs.
        raise HTTPException(404, "Recette introuvable")

    copied, skipped = await sharing.share_recipes(db, user, list(recipes), target)
    if data.automatic and not await db.get(LibraryShare, (user.id, target.id)):
        db.add(LibraryShare(owner_id=user.id, target_id=target.id))
        await db.commit()
    return SendOut(copied=copied, skipped=skipped, automatic=data.automatic)


@router.get("/automatic", response_model=AutomaticOut)
async def automatic_shares(
    db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
):
    outgoing = await db.execute(
        select(User).join(LibraryShare, LibraryShare.target_id == User.id)
        .where(LibraryShare.owner_id == user.id).order_by(User.display_name)
    )
    incoming = await db.execute(
        select(User).join(LibraryShare, LibraryShare.owner_id == User.id)
        .where(LibraryShare.target_id == user.id).order_by(User.display_name)
    )
    return AutomaticOut(
        outgoing=[AccountOut.model_validate(u) for u in outgoing.scalars()],
        incoming=[AccountOut.model_validate(u) for u in incoming.scalars()],
    )


@router.delete("/automatic/{user_id}", status_code=204)
async def stop_sending(
    user_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
):
    """Arrête d'envoyer mes nouvelles recettes à ce compte."""
    await db.execute(delete(LibraryShare).where(
        LibraryShare.owner_id == user.id, LibraryShare.target_id == user_id,
    ))
    await db.commit()


@router.delete("/automatic/from/{user_id}", status_code=204)
async def stop_receiving(
    user_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
):
    """Ne plus recevoir automatiquement les nouvelles recettes de ce compte."""
    await db.execute(delete(LibraryShare).where(
        LibraryShare.owner_id == user_id, LibraryShare.target_id == user.id,
    ))
    await db.commit()
