"""Dépendances d'authentification partagées par tous les routeurs."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .models.user import User
from .services import auth_service


def read_token(request: Request) -> str | None:
    """Cookie de session (web) ou en-tête Bearer (application Android)."""
    header = request.headers.get("authorization")
    if header and header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.cookies.get(auth_service.SESSION_COOKIE)


async def current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    user = await auth_service.resolve_session(db, read_token(request))
    if user is None:
        raise HTTPException(401, "Authentification requise")
    return user


async def current_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Réservé aux administrateurs")
    return user
