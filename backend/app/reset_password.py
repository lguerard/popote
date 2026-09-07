"""Reinitialise le mot de passe d'un compte, depuis le serveur.

Popote n'envoie pas d'e-mail : il n'existe donc aucun lien "mot de passe
oublie". Sur une instance personnelle c'est le bon compromis -- mais il
faut alors une porte de service, sinon un mot de passe perdu condamne le
compte et, s'il s'agit du premier, toute la bibliotheque qu'il possede.

Cette commande s'execute dans le conteneur, donc par quelqu'un qui a deja
un acces complet au serveur : elle ne donne aucun pouvoir supplementaire.

    docker compose exec -T backend python -m app.reset_password --list
    docker compose exec -T backend python -m app.reset_password moi@exemple.fr
    docker compose exec -T backend python -m app.reset_password moi@exemple.fr --password 'un-mot-de-passe'

Sans --password, un mot de passe est tire au hasard et affiche : c'est le
mode a preferer avec `exec -T`, ou aucun terminal ne permet de saisir
quoi que ce soit sans le laisser dans l'historique du shell.
"""

import argparse
import asyncio
import secrets
import sys

from sqlalchemy import select

from .core.security import hash_password, password_too_long
from .database import AsyncSessionLocal
from .models.user import User

LONGUEUR_MINIMALE = 8


async def _lister() -> int:
    async with AsyncSessionLocal() as db:
        comptes = (await db.execute(select(User).order_by(User.created_at))).scalars().all()
    if not comptes:
        print("Aucun compte. Mets ALLOW_SIGNUP=true et inscris-toi.")
        return 1
    for u in comptes:
        print(f"{u.email:40s} {u.display_name:20s} cree le {u.created_at:%Y-%m-%d}")
    return 0


async def _reinitialiser(email: str, mot_de_passe: str | None) -> int:
    email = email.strip().lower()
    genere = mot_de_passe is None
    if genere:
        mot_de_passe = secrets.token_urlsafe(12)
    if len(mot_de_passe) < LONGUEUR_MINIMALE:
        print(f"Mot de passe trop court ({LONGUEUR_MINIMALE} caracteres minimum).",
              file=sys.stderr)
        return 2
    if password_too_long(mot_de_passe):
        print("Mot de passe trop long (72 octets maximum).", file=sys.stderr)
        return 2

    async with AsyncSessionLocal() as db:
        user = (await db.execute(
            select(User).where(User.email == email)
        )).scalar_one_or_none()
        if user is None:
            print(f"Aucun compte avec l'adresse {email}. "
                  f"Liste des comptes : --list", file=sys.stderr)
            return 1
        user.password_hash = hash_password(mot_de_passe)
        await db.commit()

    print(f"Mot de passe change pour {email}.")
    if genere:
        print(f"Nouveau mot de passe : {mot_de_passe}")
        print("Change-le depuis l'application une fois connecte.")
    # Les jetons deja emis restent valables : ils ne portent que
    # l'identifiant du compte, pas le mot de passe. Se deconnecter des
    # autres appareils demanderait de faire tourner SECRET_KEY, ce qui
    # deconnecterait tout le monde.
    return 0


def main() -> int:
    parseur = argparse.ArgumentParser(
        prog="python -m app.reset_password",
        description="Reinitialise le mot de passe d'un compte Popote.",
    )
    parseur.add_argument("email", nargs="?", help="adresse du compte")
    parseur.add_argument("--password", help="mot de passe voulu (sinon : tire au hasard)")
    parseur.add_argument("--list", action="store_true", help="liste les comptes existants")
    args = parseur.parse_args()

    if args.list:
        return asyncio.run(_lister())
    if not args.email:
        parseur.error("indique une adresse, ou --list")
    return asyncio.run(_reinitialiser(args.email, args.password))


if __name__ == "__main__":
    raise SystemExit(main())
