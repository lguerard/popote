import uuid
from datetime import date
from sqlalchemy import String, Date, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base
import enum


class MealType(str, enum.Enum):
    breakfast = "petit-déjeuner"
    lunch = "déjeuner"
    dinner = "dîner"
    snack = "snack"


class MealPlan(Base):
    __tablename__ = "meal_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[MealType] = mapped_column(SAEnum(MealType), nullable=False)
    recipe_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recipe_title: Mapped[str | None] = mapped_column(String(500))
    recipe_thumbnail: Mapped[str | None] = mapped_column(String(1000))
