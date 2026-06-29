import uuid
from datetime import datetime
from pydantic import BaseModel
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


class RecipeOut(RecipeBase):
    id: uuid.UUID
    status: ExtractionStatus
    error_msg: str | None = None
    similar_recipe_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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
