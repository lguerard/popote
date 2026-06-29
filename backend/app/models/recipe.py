import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, DateTime, Enum as SAEnum
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
