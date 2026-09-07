import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.security import (
    create_token,
    hash_password,
    password_too_long,
    verify_password,
)
from ..database import get_db
from ..deps import current_admin, current_user
from ..models.user import User, UserStatus
from ..schemas.auth import LoginIn, RegisterIn, RegisterOut, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


async def _adopt_orphan_data(db: AsyncSession, user: User) -> None:
    """Donne au premier compte les donnees creees avant les comptes.

    Popote a longtemps fonctionne sans utilisateurs : les recettes et les
    repas existants n'ont pas de proprietaire. Sans cette reprise, le
    premier compte verrait une bibliotheque vide et les anciennes donnees
    resteraient invisibles pour tout le monde.
    """
    for table in ("recipes", "meal_plans"):
        await db.execute(
            text(f"UPDATE {table} SET owner_id = :owner WHERE owner_id IS NULL"),
            {"owner": user.id},
        )


@router.post("/register", response_model=RegisterOut, status_code=201)
async def register(data: RegisterIn, db: AsyncSession = Depends(get_db)):
    """Enregistre une DEMANDE de compte.

    Rien n'est accorde ici : le compte est cree en attente et ne peut ni
    se connecter ni lire quoi que ce soit tant qu'un administrateur ne
    l'a pas valide. Seule exception, le tout premier compte -- il n'y a
    alors personne pour valider, et c'est lui qui devient administrateur.
    """
    if password_too_long(data.password):
        raise HTTPException(400, "Mot de passe trop long (72 octets maximum)")
    if not settings.allow_signup:
        raise HTTPException(403, "Les inscriptions sont fermees sur cette instance")

    exists = (await db.execute(
        select(User).where(User.email == data.email)
    )).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "Un compte existe deja avec cette adresse")

    premier = (await db.execute(
        select(func.count()).select_from(User)
    )).scalar_one() == 0

    user = User(
        email=data.email,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
        status=UserStatus.approved.value if premier else UserStatus.pending.value,
        is_admin=premier,
    )
    db.add(user)
    await db.flush()
    if premier:
        await _adopt_orphan_data(db, user)
    await db.commit()

    if premier:
        return RegisterOut(
            status=UserStatus.approved.value,
            message="Compte administrateur cree. Connecte-toi.",
        )
    return RegisterOut(
        status=UserStatus.pending.value,
        message="Demande enregistree. Un administrateur doit la valider "
                "avant que tu puisses te connecter.",
    )


@router.post("/login", response_model=TokenOut)
async def login(data: LoginIn, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(
        select(User).where(User.email == data.email)
    )).scalar_one_or_none()
    # Meme message pour un compte inconnu et un mot de passe faux :
    # distinguer les deux dirait quelles adresses sont enregistrees.
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Adresse ou mot de passe incorrect")
    # En revanche, une fois le mot de passe prouve, la personne a le droit
    # de savoir ou en est sa demande.
    if user.status == UserStatus.pending.value:
        raise HTTPException(403, "Demande en attente de validation")
    if user.status == UserStatus.rejected.value:
        raise HTTPException(403, "Demande refusee")
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return user


# ---------------------------------------------------------------------------
# Administration des inscriptions
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(current_admin),
):
    """Tous les comptes, demandes en attente d'abord."""
    rows = (await db.execute(
        select(User).order_by(User.status != UserStatus.pending.value,
                              User.created_at.desc())
    )).scalars().all()
    return rows


async def _decider(
    db: AsyncSession, admin: User, user_id: uuid.UUID, statut: UserStatus
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Compte introuvable")
    if user.id == admin.id:
        # Se rejeter soi-meme peut laisser l'instance sans aucun
        # administrateur, donc sans personne pour valider quoi que ce soit.
        raise HTTPException(400, "Un administrateur ne peut pas se juger lui-meme")
    user.status = statut.value
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/users/{user_id}/approve", response_model=UserOut)
async def approve_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(current_admin),
):
    return await _decider(db, admin, user_id, UserStatus.approved)


@router.post("/users/{user_id}/reject", response_model=UserOut)
async def reject_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(current_admin),
):
    """Refuse une demande, ou revoque un compte deja approuve.

    Le compte et ses donnees sont conserves : un refus se corrige d'un
    clic, une suppression ne se rattrape pas.
    """
    return await _decider(db, admin, user_id, UserStatus.rejected)
