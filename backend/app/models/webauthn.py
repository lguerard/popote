import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class WebAuthnCredential(Base):
    """Passkey enregistree par un compte, en alternative au mot de passe.

    Le mot de passe reste valable : supprimer toutes ses passkeys ne
    ferme donc jamais la porte a personne.
    """

    __tablename__ = "webauthn_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Identifiant attribue par l'authentificateur, en base64url. Unique sur
    # toute l'instance et cherchable seul : une connexion par passkey peut
    # commencer sans e-mail, c'est lui qui designe alors le compte.
    credential_id: Mapped[str] = mapped_column(String(1400), unique=True, index=True, nullable=False)
    # Cle publique COSE, en base64url. Rien de secret : elle sert seulement
    # a verifier les signatures.
    public_key: Mapped[str] = mapped_column(String, nullable=False)
    # Compteur de signatures annonce par l'authentificateur. S'il recule,
    # la cle a sans doute ete clonee : py_webauthn refuse la connexion.
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Transports separes par des virgules ("internal,hybrid") : renvoyes au
    # navigateur pour qu'il sache ou chercher la cle.
    transports: Mapped[str | None] = mapped_column(String(200))
    device_label: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebAuthnChallenge(Base):
    """Defi en attente entre le debut et la fin d'une ceremonie WebAuthn.

    L'API est sans session (JWT) : rien ne relie l'appel "start" a l'appel
    "finish". Le defi doit pourtant etre garde cote serveur pour etre
    compare a celui que l'authentificateur a signe. Une ligne courte duree
    suffit, plutot que d'introduire des sessions pour ce seul usage. Elle
    est supprimee des qu'elle a servi (succes ou echec : pas de rejeu), et
    les lignes perimees sont purgees au passage a chaque nouveau defi :
    pas besoin de tache planifiee.
    """

    __tablename__ = "webauthn_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    challenge: Mapped[str] = mapped_column(String(200), nullable=False)
    # "register" ou "login" : un defi d'enregistrement ne doit pas pouvoir
    # finir une connexion, et inversement.
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    # Connu pour un enregistrement, ou une connexion ou l'e-mail a ete
    # saisi. Vide pour une connexion sans e-mail : le compte n'est alors
    # connu qu'a la fin, par la passkey choisie.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
