import uuid
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator
from ..models.recipe import SourceType, ExtractionStatus


class Ingredient(BaseModel):
    quantity: str | None = None
    unit: str | None = None
    name: str
    notes: str | None = None
    section: str | None = None  # partie de la recette (« Pâte », « Garniture »)


class Step(BaseModel):
    order: int
    text: str
    section: str | None = None


class RecipeBase(BaseModel):
    title: str
    description: str | None = None
    source_url: str | None = None
    source_type: SourceType = SourceType.manual
    language: str | None = None
    servings: int | None = None
    prep_time: int | None = None
    cook_time: int | None = None
    ingredients: list[dict] = []
    steps: list[dict] = []
    tags: list[str] = []
    category: str | None = None
    thumbnail_url: str | None = None
    is_favorite: bool = False
    notes: str | None = None
    nutrition: dict | None = None


# Bornes des colonnes en base : au-delà, l'enregistrement échouait en erreur 500.
_Title = Field(min_length=1, max_length=500)
_Minutes = Field(None, ge=0, le=100_000)


class RecipeCreate(RecipeBase):
    title: str = _Title
    language: str | None = Field(None, max_length=20)
    servings: int | None = Field(None, ge=0, le=10_000)
    prep_time: int | None = _Minutes
    cook_time: int | None = _Minutes
    category: str | None = Field(None, max_length=50)


def _text_or_none(value) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _section(value) -> str | None:
    text = _text_or_none(value)
    return " ".join(text.split()).rstrip(" :")[:100] or None if text else None


class RecipeUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    servings: int | None = Field(None, ge=0, le=10_000)
    prep_time: int | None = _Minutes
    cook_time: int | None = _Minutes
    ingredients: list[dict] | None = None
    steps: list[dict] | None = None
    tags: list[str] | None = None
    category: str | None = Field(None, max_length=50)
    thumbnail_url: str | None = None
    notes: str | None = None
    nutrition: dict | None = None
    rating: int | None = Field(None, ge=1, le=5)
    cook_again: bool | None = None

    # Saisie à la main (web, appli) : les lignes laissées vides ne doivent
    # pas finir en base — un ingrédient sans nom fait planter l'appli, qui
    # l'exige, et un titre d'espaces s'affiche comme une carte vide.
    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value):
        if value is None:
            return None
        value = " ".join(value.split())
        if not value:
            raise ValueError("Le titre ne peut pas être vide.")
        return value

    @field_validator("ingredients")
    @classmethod
    def _drop_empty_ingredients(cls, value):
        if value is None:
            return None
        cleaned = []
        for item in value:
            fields = {k: _text_or_none(item.get(k)) for k in ("quantity", "unit", "name", "notes")}
            section = _section(item.get("section"))
            if fields["name"]:
                cleaned.append({**fields, "section": section} if section else fields)
        return cleaned

    @field_validator("steps")
    @classmethod
    def _drop_empty_steps(cls, value):
        if value is None:
            return None
        kept = [(_section(step.get("section")), _text_or_none(step.get("text"))) for step in value]
        return [
            {"order": n, "text": text, **({"section": section} if section else {})}
            for n, (section, text) in enumerate(((s, t) for s, t in kept if t), 1)
        ]


class RecipeOut(RecipeBase):
    id: uuid.UUID
    status: ExtractionStatus
    error_msg: str | None = None
    progress_message: str | None = None
    thumbnail_generating: bool = False
    thumbnail_error: str | None = None
    similar_recipe_id: uuid.UUID | None = None
    reextracting: bool = False
    rating: int | None = None
    cook_again: bool | None = None
    cooked_count: int = 0
    last_cooked_at: date | None = None
    share_token: str | None = None
    # Renseigné quand la recette a été envoyée par un autre compte (badge).
    shared_by_name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PublicRecipeOut(BaseModel):
    """Recette vue par un lien public : sans notes, avis ni historique."""

    id: uuid.UUID
    title: str
    description: str | None = None
    source_url: str | None = None
    servings: int | None = None
    prep_time: int | None = None
    cook_time: int | None = None
    ingredients: list[dict] = []
    steps: list[dict] = []
    tags: list[str] = []
    category: str | None = None
    thumbnail_url: str | None = None

    model_config = {"from_attributes": True}


class CookedIn(BaseModel):
    cooked_on: date | None = None
    rating: int | None = Field(None, ge=1, le=5)
    comment: str | None = None


class CookLogOut(BaseModel):
    id: uuid.UUID
    cooked_on: date
    rating: int | None = None
    comment: str | None = None

    model_config = {"from_attributes": True}


class PantryRequest(BaseModel):
    ingredients: list[str]
    assume_staples: bool = True
    max_missing: int | None = None


class PantryMatch(BaseModel):
    recipe: RecipeOut
    matched: list[str]
    missing: list[str]
    coverage: float


class ShoppingListRequest(BaseModel):
    recipe_ids: list[uuid.UUID]


class ShoppingItem(BaseModel):
    name: str
    quantity: str | None = None
    unit: str | None = None
    recipes: list[str] = []


class NutritionOut(BaseModel):
    calories: float | None = None
    proteins: float | None = None
    carbs: float | None = None
    fat: float | None = None
    fiber: float | None = None


class ExtractionRequest(BaseModel):
    input: str  # URL ou texte brut


class ExtractionResponse(BaseModel):
    recipe_id: uuid.UUID
    status: ExtractionStatus
    message: str = ""
