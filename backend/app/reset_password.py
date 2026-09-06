"""Dépannage des mots de passe depuis le serveur.

Sert quand plus personne ne peut se connecter à l'interface (seul
administrateur enfermé dehors, adresse oubliée), et à créer le premier compte
sans passer par le navigateur.

    docker compose exec backend python -m app.reset_password
    docker compose exec backend python -m app.reset_password toi@exemple.fr
    docker compose exec backend python -m app.reset_password toi@exemple.fr 'nouveau-mdp'
    docker compose exec backend python -m app.reset_password --create toi@exemple.fr 'mdp' 'Ton nom'
"""

import asyncio
import sys

from sqlalchemy import select

from .config import settings
from .database import AsyncSessionLocal, init_db
from .models.user import User
from .services import auth_service


async def _list(db) -> int:
    users = (await db.execute(select(User).order_by(User.created_at))).scalars().all()
    if not users:
        print("Aucun compte. Crée le premier depuis l'interface, ou ici :")
        print("  python -m app.reset_password --create toi@exemple.fr 'mot-de-passe' 'Ton nom'")
        return 0
    print("Comptes :")
    for u in users:
        print(f"  {u.email}{' (admin)' if u.is_admin else ''} — {u.display_name}")
    print("\nUsage : python -m app.reset_password <email> [nouveau-mot-de-passe]")
    return 0


async def _create(db, email: str, password: str, display_name: str) -> int:
    if await auth_service.get_user_by_email(db, email):
        print(f"Un compte existe déjà pour {email}.", file=sys.stderr)
        return 1
    problem = auth_service.password_problem(password)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    # Le premier compte créé est administrateur, comme via l'interface.
    is_admin = await auth_service.count_users(db) == 0
    user = await auth_service.create_user(db, email, display_name, password, is_admin=is_admin)
    print(f"Compte créé : {user.email}{' (admin)' if user.is_admin else ''}")
    return 0


async def _reset(db, email: str, password: str | None) -> int:
    user = await auth_service.get_user_by_email(db, email)
    if user is None:
        print(f"Aucun compte avec l'adresse {email}. Lance sans argument pour les lister.",
              file=sys.stderr)
        return 1

    if password:
        problem = auth_service.password_problem(password)
        if problem:
            print(problem, file=sys.stderr)
            return 1
        await auth_service.set_password(db, user, password)
        print(f"Mot de passe mis à jour pour {user.email}. Toutes ses sessions sont fermées.")
        return 0

    token = await auth_service.create_reset_token(db, user.id)
    base = (settings.public_url or "http://localhost").rstrip("/")
    print(f"Lien de réinitialisation à usage unique pour {user.email} (valable 24 h) :\n")
    print(f"  {base}/reinitialiser/{token}\n")
    if not settings.public_url:
        print("PUBLIC_URL n'est pas défini : remplace http://localhost par l'adresse réelle.")
    return 0


async def main() -> int:
    args = sys.argv[1:]
    # Les tables peuvent ne pas exister si le backend n'a jamais démarré.
    await init_db()
    async with AsyncSessionLocal() as db:
        if args and args[0] == "--create":
            if len(args) < 4:
                print("Usage : --create <email> <mot-de-passe> <nom affiché>", file=sys.stderr)
                return 1
            return await _create(db, args[1], args[2], args[3])
        if not args:
            return await _list(db)
        return await _reset(db, args[0], args[1] if len(args) > 1 else None)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
