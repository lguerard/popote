import uuid
from datetime import date, datetime
from pydantic import BaseModel, Field
from ..models.recipe import SourceType, ExtractionStatus


class Ingredient(BaseModel):
    quantity: str | None = None
    unit: str | None = None
    name: str
    notes: str | None = None


class Step(BaseModel):
    order: int
    text: str


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


class RecipeCreate(RecipeBase):
    pass


class RecipeUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    servings: int | None = None
    prep_time: int | None = None
    cook_time: int | None = None
    ingredients: list[dict] | None = None
    steps: list[dict] | None = None
    tags: list[str] | None = None
    category: str | None = None
    thumbnail_url: str | None = None
    notes: str | None = None
    nutrition: dict | None = None
    rating: int | None = Field(None, ge=1, le=5)
    cook_again: bool | None = None


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
