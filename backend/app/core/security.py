"""Hachage des mots de passe et jetons de session.

bcrypt pour les mots de passe, JWT signe avec SECRET_KEY pour la session.
Aucune session cote serveur : le jeton porte l'identifiant et sa date
d'expiration, ce qui evite une table de sessions a nettoyer.
"""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from ..config import settings

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(days=30)

# bcrypt ne prend en compte que les 72 premiers OCTETS. Tronquer
# silencieusement affaiblirait le mot de passe sans que personne ne le
# sache : on refuse plutot, et l'API renvoie un message clair.
MAX_PASSWORD_BYTES = 72


def password_too_long(password: str) -> bool:
    """Dit si le mot de passe depasse ce que bcrypt sait traiter."""
    return len(password.encode("utf-8")) > MAX_PASSWORD_BYTES


def hash_password(password: str) -> str:
    """Hache un mot de passe avec un sel aleatoire."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verifie un mot de passe contre son hachage.

    Renvoie False plutot que de lever si le hachage stocke est illisible :
    une entree corrompue en base ne doit pas rendre l'API indisponible.
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_token(user_id: uuid.UUID) -> str:
    """Fabrique un jeton de session pour cet utilisateur."""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + TOKEN_TTL},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def read_token(token: str) -> uuid.UUID | None:
    """Lit un jeton et renvoie l'identifiant, ou None s'il est invalide.

    Couvre aussi bien la signature fausse que l'expiration ou un `sub`
    qui n'est pas un UUID : dans tous les cas l'appelant traite
    l'utilisateur comme non authentifie.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None
