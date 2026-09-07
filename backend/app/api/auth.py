from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import (
    create_token,
    hash_password,
    password_too_long,
    verify_password,
)
from ..database import get_db
from ..deps import current_user
from ..models.user import User
from ..schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


async def _adopt_orphan_data(db: AsyncSession, user: User) -> None:
    """Donne au premier compte les donnees creees avant les comptes.

    Popote a longtemps fonctionne sans utilisateurs : les recettes et les
    repas existants n'ont pas de proprietaire. Sans cette reprise, le
    premier compte cree verrait une bibliotheque vide et les anciennes
    donnees resteraient invisibles pour tout le monde.
    """
    for table in ("recipes", "meal_plans"):
        await db.execute(
            text(f"UPDATE {table} SET owner_id = :owner WHERE owner_id IS NULL"),
            {"owner": user.id},
        )


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(data: RegisterIn, db: AsyncSession = Depends(get_db)):
    if password_too_long(data.password):
        raise HTTPException(400, "Mot de passe trop long (72 octets maximum)")

    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    # Le tout premier compte s'inscrit toujours : c'est l'amorcage. Les
    # suivants seulement si l'inscription est ouverte -- Popote est
    # publie derriere un nom de domaine public, une inscription libre
    # laisserait n'importe qui se creer un compte.
    from ..config import settings
    if count > 0 and not settings.allow_signup:
        raise HTTPException(403, "Les inscriptions sont fermees sur cette instance")

    exists = (await db.execute(
        select(User).where(User.email == data.email)
    )).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "Un compte existe deja avec cette adresse")

    user = User(
        email=data.email,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    if count == 0:
        await _adopt_orphan_data(db, user)
    await db.commit()
    await db.refresh(user)
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
async def login(data: LoginIn, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(
        select(User).where(User.email == data.email)
    )).scalar_one_or_none()
    # Meme message dans les deux cas : distinguer "compte inconnu" de
    # "mauvais mot de passe" dirait a un attaquant quelles adresses sont
    # enregistrees.
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Adresse ou mot de passe incorrect")
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return user
