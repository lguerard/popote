import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class UserStatus(str, enum.Enum):
    """Etat d'une demande de compte."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class User(Base):
    """Compte utilisateur.

    L'e-mail sert d'identifiant de connexion : il est stocke normalise
    (minuscules, sans espaces autour) pour qu'une casse differente ne
    cree pas un second compte.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Stocke en texte plutot qu'en type ENUM Postgres : ajouter une valeur
    # a un ENUM existant demande une migration, une chaine non.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserStatus.pending.value, index=True
    )
    # Peut valider ou rejeter les demandes d'inscription. Le tout premier
    # compte l'est d'office : sans lui, personne ne pourrait approuver.
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Date de la derniere decision sur ce compte. Sert a faire disparaitre
    # les vieux refus de la liste : created_at ne conviendrait pas, un
    # compte ancien revoque aujourd'hui doit rester visible une semaine.
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
