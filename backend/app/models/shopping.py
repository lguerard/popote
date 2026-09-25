import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class ShoppingItem(Base):
    """Article de la liste de courses, conservée côté serveur.

    Persistée (et non recalculée à chaque affichage) pour que les cases
    cochées en magasin se retrouvent sur tous les appareils du foyer.
    """

    __tablename__ = "shopping_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[str | None] = mapped_column(String(50))
    unit: Mapped[str | None] = mapped_column(String(50))
    aisle: Mapped[str] = mapped_column(String(50), nullable=False)
    recipes: Mapped[list] = mapped_column(JSONB, default=list)
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
