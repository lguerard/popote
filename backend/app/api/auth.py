from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import current_admin, current_user, read_token
from ..models.user import User
from ..schemas.auth import (
    AuthStatus,
    ChangePasswordRequest,
    LoginOut,
    LoginRequest,
    ResetLinkOut,
    ResetPasswordRequest,
    ResetTargetOut,
    SetupRequest,
    UserCreate,
    UserOut,
)
from ..services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        auth_service.SESSION_COOKIE,
        token,
        max_age=int(auth_service.SESSION_TTL.total_seconds()),
        httponly=True,
        # lax : le cookie n'accompagne pas les requêtes POST venues d'un autre
        # site, ce qui suffit à bloquer le CSRF sur une API JSON.
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _reset_url(request: Request, token: str) -> str:
    """Lien absolu, collable tel quel dans un message. `PUBLIC_URL` prime :
    derrière un tunnel Cloudflare, l'URL vue par le backend n'est pas celle
    que la personne ouvrira."""
    base = (settings.public_url or str(request.base_url)).rstrip("/")
    return f"{base}/reinitialiser/{token}"


@router.get("/status", response_model=AuthStatus)
async def status(request: Request, db: AsyncSession = Depends(get_db)):
    """Consultable sans être connecté : dit au client s'il doit afficher
    l'écran de création du premier compte, l'écran de connexion, ou rien."""
    if await auth_service.count_users(db) == 0:
        return AuthStatus(needs_setup=True)
    user = await auth_service.resolve_session(db, read_token(request))
    return AuthStatus(needs_setup=False, user=UserOut.model_validate(user) if user else None)


@router.post("/setup", response_model=LoginOut, status_code=201)
async def setup(data: SetupRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Crée le premier compte, qui est administrateur. Refusée dès qu'un
    compte existe — sinon n'importe qui pourrait s'en créer un."""
    if await auth_service.count_users(db) > 0:
        raise HTTPException(409, "Un compte existe déjà. Connecte-toi.")
    user = await auth_service.create_user(
        db, data.email, data.display_name, data.password, is_admin=True
    )
    token = await auth_service.create_session(db, user.id)
    _set_cookie(response, token)
    return LoginOut(token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=LoginOut)
async def login(data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await auth_service.get_user_by_email(db, data.email)
    if user is None or not auth_service.verify_password(user.password_hash, data.password):
        # Même message dans les deux cas : ne dit pas si l'adresse existe.
        raise HTTPException(401, "Identifiants incorrects")
    token = await auth_service.create_session(db, user.id)
    _set_cookie(response, token)
    return LoginOut(token=token, user=UserOut.model_validate(user))


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await auth_service.destroy_session(db, read_token(request))
    response.delete_cookie(auth_service.SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return user


@router.post("/change-password", status_code=204)
async def change_password(
    data: ChangePasswordRequest,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if not auth_service.verify_password(user.password_hash, data.current_password):
        raise HTTPException(400, "Mot de passe actuel incorrect")
    if data.new_password == data.current_password:
        raise HTTPException(400, "Le nouveau mot de passe est identique à l'ancien")
    # Garde connecté l'appareil qui fait le changement, déconnecte les autres.
    await auth_service.set_password(db, user, data.new_password, keep_token=read_token(request))


@router.get("/reset/{token}", response_model=ResetTargetOut)
async def check_reset_token(token: str, db: AsyncSession = Depends(get_db)):
    """Permet au formulaire d'afficher à qui appartient le lien. Un jeton
    invalide ne révèle rien."""
    user = await auth_service.find_reset_token(db, token)
    return ResetTargetOut(valid=user is not None, email=user.email if user else None)


@router.post("/reset", status_code=204)
async def reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    if not await auth_service.consume_reset_token(db, data.token, data.new_password):
        raise HTTPException(400, "Lien invalide, expiré ou déjà utilisé")


# ------------------------------------------------------------------ administration


@router.get("/users", response_model=list[UserOut])
async def list_users(_: User = Depends(current_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at))
    return result.scalars().all()


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    data: UserCreate, _: User = Depends(current_admin), db: AsyncSession = Depends(get_db)
):
    if await auth_service.get_user_by_email(db, data.email):
        raise HTTPException(409, "Cette adresse est déjà utilisée")
    return await auth_service.create_user(
        db, data.email, data.display_name, data.password, data.is_admin
    )


@router.post("/users/{user_id}/reset-link", response_model=ResetLinkOut)
async def create_reset_link(
    user_id: UUID,
    request: Request,
    _: User = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Génère un lien à usage unique à transmettre par le canal de son choix.
    Il n'est affiché qu'une fois : seul son hash est conservé."""
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "Compte introuvable")
    token = await auth_service.create_reset_token(db, target.id)
    return ResetLinkOut(
        email=target.email,
        reset_url=_reset_url(request, token),
        expires_at=datetime.now(timezone.utc) + auth_service.RESET_TTL,
    )


class RoleUpdate(BaseModel):
    is_admin: bool


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def set_user_role(
    user_id: UUID,
    data: RoleUpdate,
    _: User = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "Compte introuvable")
    if not data.is_admin and target.is_admin:
        # Sans administrateur, plus personne ne peut générer de lien de
        # réinitialisation : il ne resterait que le script en ligne de commande.
        admins = (
            await db.execute(select(func.count()).select_from(User).where(User.is_admin.is_(True)))
        ).scalar_one()
        if admins <= 1:
            raise HTTPException(400, "Il doit rester au moins un administrateur")
    target.is_admin = data.is_admin
    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID, admin: User = Depends(current_admin), db: AsyncSession = Depends(get_db)
):
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "Compte introuvable")
    if target.id == admin.id:
        raise HTTPException(400, "Impossible de supprimer son propre compte")
    await db.delete(target)
    await db.commit()
