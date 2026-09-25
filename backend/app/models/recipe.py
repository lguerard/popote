import uuid
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Date, String, Text, Integer, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base
import enum


class SourceType(str, enum.Enum):
    video = "video"
    web = "web"
    text = "text"
    manual = "manual"


class ExtractionStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Nullable : les recettes creees avant les comptes n'en ont pas.
    # Le premier compte cree les adopte (voir api/auth.py).
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[SourceType] = mapped_column(SAEnum(SourceType), default=SourceType.manual)
    language: Mapped[str | None] = mapped_column(String(20))
    servings: Mapped[int | None] = mapped_column(Integer)
    prep_time: Mapped[int | None] = mapped_column(Integer)
    cook_time: Mapped[int | None] = mapped_column(Integer)
    ingredients: Mapped[list] = mapped_column(JSONB, default=list)
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    category: Mapped[str | None] = mapped_column(String(50))
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    is_favorite: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    nutrition: Mapped[dict | None] = mapped_column(JSONB)
    similar_recipe_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[ExtractionStatus] = mapped_column(SAEnum(ExtractionStatus), default=ExtractionStatus.done)
    error_msg: Mapped[str | None] = mapped_column(Text)
    progress_message: Mapped[str | None] = mapped_column(Text)
    # Generation de vignette IA : suivie a part du statut d'extraction
    # ci-dessus, qui concerne toute la recette. La confondre la ferait
    # disparaitre de la liste (filtree sur status=done) le temps de
    # regenerer juste l'image d'une recette deja terminee.
    thumbnail_generating: Mapped[bool] = mapped_column(default=False)
    thumbnail_error: Mapped[str | None] = mapped_column(Text)
    # Réextraction depuis la source : la recette reste "done" (donc visible)
    # pendant qu'elle tourne, progress_message et error_msg servent au suivi.
    reextracting: Mapped[bool] = mapped_column(Boolean, default=False)
    # Avis personnel. cooked_count/last_cooked_at sont dérivés du journal
    # (cook_logs) mais gardés ici pour trier et filtrer la liste sans jointure.
    rating: Mapped[int | None] = mapped_column(Integer)
    cook_again: Mapped[bool | None] = mapped_column(Boolean)
    cooked_count: Mapped[int] = mapped_column(Integer, default=0)
    last_cooked_at: Mapped[date | None] = mapped_column(Date)
    # Lien public en lecture seule (/partage/r/<jeton>) ; None = non partagée.
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
