"""Passkeys (WebAuthn) : connexion sans mot de passe, en option.

Le mot de passe reste valable : une passkey n'est qu'une seconde porte
vers le meme compte, et la connexion ouvre la meme session JWT que
/auth/login. Toute la cryptographie (signatures, origine, domaine,
compteur) est confiee a py_webauthn.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (
    base64url_to_bytes,
    bytes_to_base64url,
    options_to_json_dict,
    parse_authentication_credential_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..config import settings
from ..core.security import create_token
from ..database import get_db
from ..deps import current_user
from ..models.user import User, UserStatus
from ..models.webauthn import WebAuthnChallenge, WebAuthnCredential
from ..schemas.auth import TokenOut, UserOut
from ..schemas.webauthn import (
    FinishAuthenticationIn,
    FinishRegistrationIn,
    PasskeyOptionsOut,
    PasskeyOut,
    StartAuthenticationIn,
)

log = logging.getLogger("popote.passkeys")

router = APIRouter(prefix="/auth/passkeys", tags=["passkeys"])

CHALLENGE_TTL = timedelta(minutes=5)
PURPOSE_REGISTER = "register"
PURPOSE_LOGIN = "login"

# La passkey remplace le mot de passe, elle ne s'y ajoute pas : sans
# verification de l'utilisateur (code, empreinte, visage), posseder la
# cle suffirait a entrer. On l'exige donc, a l'enregistrement comme a la
# connexion.
USER_VERIFICATION = UserVerificationRequirement.REQUIRED

# Meme message pour une passkey inconnue, d'un autre compte ou mal signee :
# les distinguer renseignerait sur les comptes et les cles enregistres.
PASSKEY_REFUSEE = "Passkey non reconnue"

_TRANSPORTS = {t.value for t in AuthenticatorTransport}


def _relying_party(request: Request) -> tuple[str, str]:
    """Domaine (rp_id) et origine attendus pour cette requete.

    Sans WEBAUTHN_RP_ID, les deux viennent de la requete : rp_id de Host
    (que nginx transmet tel quel), l'origine de l'en-tete Origin que le
    navigateur pose sur tout POST -- request.url.scheme ne suffirait pas
    derriere un proxy HTTPS (Cloudflare Tunnel), il y vaut "http". Les
    deux doivent designer le meme hote : sinon la ceremonie echouerait de
    toute facon, autant le dire clairement.

    Avec WEBAUTHN_RP_ID, le domaine est fige ; l'origine reste lue dans
    Origin, mais n'est retenue que si elle est ce domaine ou un de ses
    sous-domaines (ce que WebAuthn autorise), pour garder le port d'un
    serveur de developpement. A defaut : https://<rp_id>.
    """
    origin = request.headers.get("origin")
    origin_host = urlsplit(origin).hostname if origin else None

    if settings.webauthn_rp_id:
        rp_id = settings.webauthn_rp_id.strip().lower()
        if origin_host and (origin_host == rp_id or origin_host.endswith("." + rp_id)):
            return rp_id, origin
        return rp_id, f"https://{rp_id}"

    host = request.headers.get("host", "")
    rp_id = urlsplit(f"//{host}").hostname if host else None
    if not rp_id:
        raise HTTPException(400, "Domaine de la requete introuvable (en-tete Host absent)")
    if not origin:
        origin, origin_host = f"{request.url.scheme}://{host}", rp_id
    if origin_host != rp_id:
        raise HTTPException(
            400,
            "Origine de la requete et domaine du serveur differents : "
            "renseigne WEBAUTHN_RP_ID si Popote est derriere un proxy",
        )
    return rp_id, origin


def _descriptor(cred: WebAuthnCredential) -> PublicKeyCredentialDescriptor:
    transports = [AuthenticatorTransport(t) for t in (cred.transports or "").split(",") if t]
    return PublicKeyCredentialDescriptor(
        id=base64url_to_bytes(cred.credential_id), transports=transports or None
    )


async def _new_challenge(
    db: AsyncSession, challenge: bytes, purpose: str, user_id: uuid.UUID | None
) -> WebAuthnChallenge:
    now = datetime.now(timezone.utc)
    # Purge au passage : les ceremonies abandonnees ne laissent rien
    # s'accumuler, sans tache planifiee.
    await db.execute(delete(WebAuthnChallenge).where(WebAuthnChallenge.expires_at < now))
    row = WebAuthnChallenge(
        challenge=bytes_to_base64url(challenge),
        purpose=purpose,
        user_id=user_id,
        created_at=now,
        expires_at=now + CHALLENGE_TTL,
    )
    db.add(row)
    await db.commit()
    return row


async def _consume_challenge(
    db: AsyncSession, challenge_id: uuid.UUID, purpose: str, user_id: uuid.UUID | None = None
) -> tuple[bytes, uuid.UUID | None]:
    """Retire le defi de la base et renvoie sa valeur et son compte, ou 400.

    Supprime AVANT la verification, en une seule requete (DELETE ...
    RETURNING) : quelle que soit l'issue, il ne resservira pas, et deux
    appels simultanes avec le meme defi ne peuvent pas passer tous les
    deux.
    """
    q = delete(WebAuthnChallenge).where(
        WebAuthnChallenge.id == challenge_id, WebAuthnChallenge.purpose == purpose
    )
    if user_id is not None:
        q = q.where(WebAuthnChallenge.user_id == user_id)
    row = (await db.execute(
        q.returning(
            WebAuthnChallenge.challenge, WebAuthnChallenge.user_id, WebAuthnChallenge.expires_at
        )
    )).one_or_none()
    await db.commit()
    if row is None:
        raise HTTPException(400, "Demande de passkey inconnue ou deja utilisee, recommence")
    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, "Demande de passkey expiree, recommence")
    return base64url_to_bytes(row.challenge), row.user_id


# ---------------------------------------------------------------------------
# Gestion des passkeys du compte connecte
# ---------------------------------------------------------------------------

@router.post("/start-registration", response_model=PasskeyOptionsOut)
async def start_registration(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    rp_id, _ = _relying_party(request)
    existantes = (await db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
    )).scalars().all()
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=settings.webauthn_rp_name,
        # Identifiant stable plutot qu'aleatoire : l'authentificateur range
        # toutes les passkeys du compte sous le meme utilisateur, et la
        # connexion peut verifier que la cle presentee lui appartient. Un
        # UUID ne revele rien de la personne, contrairement a l'e-mail.
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.display_name,
        # Cle "residente" souhaitee : c'est ce qui permet de se connecter
        # sans saisir d'e-mail. Seulement preferee, pour ne pas ecarter
        # les cles de securite qui n'ont plus de place.
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=USER_VERIFICATION,
        ),
        exclude_credentials=[_descriptor(c) for c in existantes],
    )
    row = await _new_challenge(db, options.challenge, PURPOSE_REGISTER, user.id)
    return PasskeyOptionsOut(options=options_to_json_dict(options), challenge_id=row.id)


@router.post("/finish-registration", response_model=PasskeyOut, status_code=201)
async def finish_registration(
    data: FinishRegistrationIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    expected_challenge, _ = await _consume_challenge(
        db, data.challenge_id, PURPOSE_REGISTER, user.id
    )
    rp_id, origin = _relying_party(request)
    try:
        verified = verify_registration_response(
            credential=data.credential,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except Exception as exc:  # py_webauthn leve des types varies selon l'etape
        log.info("Enregistrement de passkey refuse pour %s : %s", user.id, exc)
        raise HTTPException(400, "Passkey refusee, recommence")

    response = data.credential.get("response")
    transports = response.get("transports") if isinstance(response, dict) else None
    transports = [t for t in transports if t in _TRANSPORTS] if isinstance(transports, list) else []

    cred = WebAuthnCredential(
        user_id=user.id,
        credential_id=bytes_to_base64url(verified.credential_id),
        public_key=bytes_to_base64url(verified.credential_public_key),
        sign_count=verified.sign_count,
        transports=",".join(transports) or None,
        device_label=data.label,
    )
    db.add(cred)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Cette passkey est deja enregistree")
    await db.refresh(cred)
    return cred


@router.get("", response_model=list[PasskeyOut])
async def list_passkeys(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return (await db.execute(
        select(WebAuthnCredential)
        .where(WebAuthnCredential.user_id == user.id)
        .order_by(WebAuthnCredential.created_at.desc())
    )).scalars().all()


@router.delete("/{passkey_id}", status_code=204)
async def delete_passkey(
    passkey_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    cred = await db.get(WebAuthnCredential, passkey_id)
    if cred is None or cred.user_id != user.id:
        raise HTTPException(404, "Passkey introuvable")
    await db.delete(cred)
    await db.commit()


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------

@router.post("/start-authentication", response_model=PasskeyOptionsOut)
async def start_authentication(
    data: StartAuthenticationIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Debut de connexion, avec ou sans e-mail.

    Sans e-mail, ou si l'adresse ne mene a aucune passkey, la liste des
    cles autorisees reste vide : le navigateur propose alors les passkeys
    qu'il connait pour ce domaine. Meme forme de reponse dans tous les cas.
    """
    rp_id, _ = _relying_party(request)
    user_id = None
    allow = []
    if data.email:
        user = (await db.execute(
            select(User).where(User.email == data.email)
        )).scalar_one_or_none()
        if user is not None:
            creds = (await db.execute(
                select(WebAuthnCredential).where(WebAuthnCredential.user_id == user.id)
            )).scalars().all()
            if creds:
                user_id = user.id
                allow = [_descriptor(c) for c in creds]
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=allow,
        user_verification=USER_VERIFICATION,
    )
    row = await _new_challenge(db, options.challenge, PURPOSE_LOGIN, user_id)
    return PasskeyOptionsOut(options=options_to_json_dict(options), challenge_id=row.id)


@router.post("/finish-authentication", response_model=TokenOut)
async def finish_authentication(
    data: FinishAuthenticationIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Pas de filtre par compte ici : sans e-mail saisi, le defi n'en a pas,
    # c'est la passkey presentee qui le designera.
    expected_challenge, challenge_user = await _consume_challenge(
        db, data.challenge_id, PURPOSE_LOGIN
    )
    rp_id, origin = _relying_party(request)

    try:
        parsed = parse_authentication_credential_json(data.credential)
        credential_id = bytes_to_base64url(parsed.raw_id)
    except Exception:
        raise HTTPException(400, PASSKEY_REFUSEE)

    cred = (await db.execute(
        select(WebAuthnCredential).where(WebAuthnCredential.credential_id == credential_id)
    )).scalar_one_or_none()
    # Un e-mail saisi au depart restreint la connexion a ce compte-la.
    if cred is None or (challenge_user is not None and cred.user_id != challenge_user):
        raise HTTPException(400, PASSKEY_REFUSEE)
    # La cle peut annoncer son utilisateur : il doit etre le proprietaire
    # connu en base, sinon quelque chose ne colle pas.
    if parsed.response.user_handle is not None and parsed.response.user_handle != cred.user_id.bytes:
        raise HTTPException(400, PASSKEY_REFUSEE)

    try:
        verified = verify_authentication_response(
            credential=parsed,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=base64url_to_bytes(cred.public_key),
            credential_current_sign_count=cred.sign_count,
            require_user_verification=True,
        )
    except Exception as exc:  # signature fausse, compteur qui recule (cle clonee)...
        log.info("Connexion par passkey refusee (passkey %s) : %s", cred.id, exc)
        raise HTTPException(400, PASSKEY_REFUSEE)

    cred.sign_count = verified.new_sign_count
    user = await db.get(User, cred.user_id)
    # Comme /auth/login : le statut n'est dit qu'une fois la possession
    # de la passkey prouvee par la signature.
    if user.status == UserStatus.pending.value:
        await db.commit()
        raise HTTPException(403, "Demande en attente de validation")
    if user.status == UserStatus.rejected.value:
        await db.commit()
        raise HTTPException(403, "Demande refusee")
    cred.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user))
