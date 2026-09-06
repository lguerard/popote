"""Comptes, sessions et réinitialisation de mot de passe.

Popote n'a pas de SMTP : la réinitialisation passe donc par un lien à usage
unique qu'un administrateur génère et transmet lui-même, ou par le script
`backend/reset_password.py` quand plus personne ne peut se connecter.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import PasswordResetToken, Session, User

MIN_PASSWORD_LENGTH = 8
SESSION_TTL = timedelta(days=30)
RESET_TTL = timedelta(hours=24)
SESSION_COOKIE = "popote_session"

# scrypt : coût mémoire volontairement élevé pour les attaques par dictionnaire.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 64


# --------------------------------------------------------------------- mots de passe


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN
    )
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_password(stored: str, password: str) -> bool:
    try:
        scheme, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=len(expected),
    )
    return hmac.compare_digest(derived, expected)


def password_problem(password: str) -> str | None:
    """Même règle partout : création de compte, changement, réinitialisation, CLI."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Mot de passe : {MIN_PASSWORD_LENGTH} caractères minimum."
    return None


# --------------------------------------------------------------------- sessions


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(db: AsyncSession, user_id) -> str:
    token = secrets.token_hex(32)
    db.add(
        Session(
            id=_hash_token(token),
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + SESSION_TTL,
        )
    )
    await db.commit()
    return token  # seul le client garde le jeton en clair


async def resolve_session(db: AsyncSession, token: str | None) -> User | None:
    if not token:
        return None
    row = await db.get(Session, _hash_token(token))
    if row is None:
        return None
    if row.expires_at <= datetime.now(timezone.utc):
        await db.delete(row)
        await db.commit()
        return None
    return await db.get(User, row.user_id)


async def destroy_session(db: AsyncSession, token: str | None) -> None:
    if not token:
        return
    await db.execute(delete(Session).where(Session.id == _hash_token(token)))
    await db.commit()


async def destroy_all_sessions(db: AsyncSession, user_id, keep_token: str | None = None) -> None:
    """Déconnecte tous les appareils du compte. `keep_token` laisse connecté
    celui qui vient de changer son propre mot de passe."""
    q = delete(Session).where(Session.user_id == user_id)
    if keep_token:
        q = q.where(Session.id != _hash_token(keep_token))
    await db.execute(q)
    await db.commit()


# --------------------------------------------------------------------- comptes


async def count_users(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(User))).scalar_one()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    normalized = email.strip().lower()
    return (
        await db.execute(select(User).where(User.email == normalized))
    ).scalar_one_or_none()


async def create_user(
    db: AsyncSession, email: str, display_name: str, password: str, is_admin: bool
) -> User:
    user = User(
        email=email.strip().lower(),
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def set_password(
    db: AsyncSession, user: User, password: str, keep_token: str | None = None
) -> None:
    """Remplace le mot de passe, déconnecte les autres appareils et annule les
    liens de réinitialisation encore en attente pour ce compte."""
    user.password_hash = hash_password(password)
    await db.commit()
    await destroy_all_sessions(db, user.id, keep_token)
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    await db.commit()


# --------------------------------------------------------------------- réinitialisation


async def create_reset_token(db: AsyncSession, user_id) -> str:
    """Renvoie le jeton en clair — affiché une seule fois, jamais stocké tel quel."""
    token = secrets.token_hex(32)
    # Un compte n'a besoin que d'un lien vivant à la fois.
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
    db.add(
        PasswordResetToken(
            id=_hash_token(token),
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + RESET_TTL,
        )
    )
    await db.commit()
    return token


async def find_reset_token(db: AsyncSession, token: str) -> User | None:
    """Cherche le compte visé sans consommer le jeton (pour afficher le formulaire)."""
    if not token:
        return None
    row = await db.get(PasswordResetToken, _hash_token(token))
    if row is None or row.used_at is not None:
        return None
    if row.expires_at <= datetime.now(timezone.utc):
        return None
    return await db.get(User, row.user_id)


async def consume_reset_token(db: AsyncSession, token: str, new_password: str) -> bool:
    """Consomme le jeton et applique le mot de passe. False si le lien est
    invalide, expiré ou déjà utilisé."""
    user = await find_reset_token(db, token)
    if user is None:
        return False
    row = await db.get(PasswordResetToken, _hash_token(token))
    row.used_at = datetime.now(timezone.utc)
    await db.commit()
    await set_password(db, user, new_password)
    return True
