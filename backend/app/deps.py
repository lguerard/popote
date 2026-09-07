"""Dependances FastAPI partagees."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .core.security import read_token
from .database import get_db
from .models.user import User


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Utilisateur porte par l'en-tete Authorization, ou 401.

    Toutes les routes de donnees en dependent : sans elle, une requete
    anonyme verrait la bibliotheque de tout le monde.
    """
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    user_id = read_token(token.strip()) if scheme.lower() == "bearer" else None
    if user_id is None:
        raise HTTPException(401, "Authentification requise")
    user = await db.get(User, user_id)
    if user is None:
        # Jeton valide mais compte supprime depuis.
        raise HTTPException(401, "Compte introuvable")
    return user
