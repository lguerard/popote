"""Outils de l'assistant : ce que le modèle peut lire et modifier.

Chaque outil ne voit que les données du compte connecté (owner_id), comme
les routes de l'API. Le partage entre comptes COPIE les recettes chez le
destinataire (services/sharing.py) : filtrer sur le propriétaire couvre
donc aussi les recettes reçues, sans jamais exposer celles d'autrui.

Aucun outil ne supprime ni ne modifie une recette : les seules écritures
sont des AJOUTS (au planning, à la liste de courses, et une nouvelle
recette rédigée par l'assistant), signalés à l'interface par une « action ».

Les arguments viennent du modèle : ils sont validés strictement (champs
inconnus refusés, bornes de longueur), et toute erreur revient au modèle
comme résultat d'outil, pour qu'il corrige ou explique, sans faire échouer
la conversation.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Annotated, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import Text, and_, cast, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.meal_plan import MealPlan, MealType
from ..models.recipe import ExtractionStatus, Recipe, SourceType
from . import achievement_service, grocery, recipe_parsing, sharing, shopping_list, substitutions
from .recipe_parsing import CATEGORIES, as_list

logger = logging.getLogger(__name__)

# Garde-fous de taille : la fenêtre du modèle local est de 8192 tokens.
MAX_SEARCH_RESULTS = 8
MAX_PANTRY_RESULTS = 6
MAX_SHOPPING_LINES = 60
MAX_TOOL_RESULT_CHARS = 2500
MAX_STEP_CHARS = 400
MAX_SIMILAR_RESULTS = 5
# En tête de la description d'une recette rédigée par l'assistant.
GENERATED_NOTICE = "Recette créée par l'assistant : quantités et temps à vérifier."

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = (
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
    "septembre", "octobre", "novembre", "décembre",
)
MEALS = tuple(m.value for m in MealType)
# Le modèle écrit volontiers « diner » ou « soir » : même repas.
_MEAL_ALIASES = {
    "petit-dejeuner": "petit-déjeuner", "petit dejeuner": "petit-déjeuner",
    "petit déjeuner": "petit-déjeuner", "matin": "petit-déjeuner",
    "dejeuner": "déjeuner", "midi": "déjeuner",
    "diner": "dîner", "soir": "dîner", "souper": "dîner",
    "gouter": "snack", "goûter": "snack", "collation": "snack",
}


def date_fr(day: date) -> str:
    """« lundi 26 octobre 2026 »."""
    return f"{JOURS[day.weekday()]} {day.day} {MOIS[day.month - 1]} {day.year}"


class ToolError(Exception):
    """Erreur expliquée au modèle (recette introuvable, date hors limites…)."""


@dataclass
class ToolContext:
    db: AsyncSession
    user_id: uuid.UUID
    today: date


@dataclass
class ToolOutcome:
    """Résultat d'un outil.

    result : renvoyé au modèle (compact).
    recipes : cartes « recettes trouvées » pour l'interface.
    action : écriture effectuée, affichée en pastille ({kind, label}).
    """

    result: dict
    recipes: list[dict] = field(default_factory=list)
    action: dict | None = None
    error: bool = False


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ShortText = Annotated[str, Field(min_length=1, max_length=60)]


def _recipe_uuid(value) -> uuid.UUID:
    try:
        return uuid.UUID(str(value).strip())
    except ValueError:
        raise ValueError("identifiant de recette invalide (attendu : l'id renvoyé par un outil)")


class SearchArgs(_Args):
    texte: str | None = Field(None, max_length=100)
    ingredients: list[ShortText] | None = Field(None, max_length=8)
    categorie: str | None = None
    max_minutes: int | None = Field(None, ge=1, le=1440)
    favoris: bool | None = None

    @field_validator("categorie")
    @classmethod
    def _category(cls, value):
        if value is None:
            return None
        value = value.strip().lower()
        if value not in CATEGORIES:
            raise ValueError(f"catégorie inconnue, choisir parmi : {', '.join(CATEGORIES)}")
        return value


class PantryArgs(_Args):
    ingredients: list[ShortText] = Field(..., min_length=1, max_length=15)
    manque_max: int | None = Field(None, ge=0, le=20)


class RecipeArgs(_Args):
    recette_id: str

    @field_validator("recette_id")
    @classmethod
    def _id(cls, value):
        return str(_recipe_uuid(value))


class ScaleArgs(RecipeArgs):
    portions: int = Field(..., ge=1, le=100)


class PlanningArgs(_Args):
    semaine: date | None = None


class PlanEntry(_Args):
    recette_id: str
    date: date
    repas: str

    @field_validator("recette_id")
    @classmethod
    def _id(cls, value):
        return str(_recipe_uuid(value))

    @field_validator("repas")
    @classmethod
    def _meal(cls, value):
        key = value.strip().lower()
        key = _MEAL_ALIASES.get(key, key)
        if key not in MEALS:
            raise ValueError(f"repas inconnu, choisir parmi : {', '.join(MEALS)}")
        return key


class AddPlanArgs(_Args):
    elements: list[PlanEntry] = Field(..., min_length=1, max_length=14)


class NoArgs(_Args):
    pass


class ShoppingEntry(_Args):
    nom: str = Field(..., min_length=1, max_length=300)
    quantite: str | None = Field(None, max_length=50)
    unite: str | None = Field(None, max_length=50)

    @field_validator("quantite", "unite", mode="before")
    @classmethod
    def _text(cls, value):
        # « 2 » arrive souvent en nombre.
        if value is None or isinstance(value, str):
            return value or None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f"{value:g}"
        raise ValueError("texte attendu")


class SubstituteArgs(_Args):
    ingredient: str = Field(..., min_length=1, max_length=80)
    recette_id: str | None = None

    @field_validator("recette_id")
    @classmethod
    def _id(cls, value):
        return None if value is None else str(_recipe_uuid(value))


def _as_text(value):
    """« 2 » arrive souvent en nombre."""
    if value is None or isinstance(value, str):
        return value or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}"
    raise ValueError("texte attendu")


class NewIngredient(_Args):
    nom: str = Field(..., min_length=1, max_length=200)
    quantite: str | None = Field(None, max_length=30)
    unite: str | None = Field(None, max_length=30)
    precision: str | None = Field(None, max_length=200)
    section: str | None = Field(None, max_length=60)

    @field_validator("quantite", "unite", mode="before")
    @classmethod
    def _text(cls, value):
        return _as_text(value)


StepText = Annotated[str, Field(min_length=1, max_length=1000)]


class CreateArgs(_Args):
    titre: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=500)
    portions: int | None = Field(None, ge=1, le=100)
    preparation_min: int | None = Field(None, ge=0, le=1440)
    cuisson_min: int | None = Field(None, ge=0, le=2880)
    categorie: str | None = None
    ingredients: list[NewIngredient] = Field(..., min_length=1, max_length=40)
    etapes: list[StepText] = Field(..., min_length=1, max_length=30)
    tags: list[ShortText] | None = Field(None, max_length=5)

    @field_validator("etapes", mode="before")
    @classmethod
    def _drop_blank_steps(cls, value):
        # Une ligne vide entre deux étapes ne doit pas faire refuser la recette.
        if isinstance(value, list):
            return [v for v in value if not (isinstance(v, str) and not v.strip())]
        return value

    @field_validator("categorie")
    @classmethod
    def _category(cls, value):
        # Indulgent : une catégorie hors liste est devinée d'après le titre
        # plutôt que de coûter un tour au modèle.
        value = (value or "").strip().lower()
        return value if value in CATEGORIES else None


class AddShoppingArgs(_Args):
    elements: list[ShoppingEntry] | None = Field(None, max_length=30)
    recette_id: str | None = None
    portions: int | None = Field(None, ge=1, le=100)

    @field_validator("recette_id")
    @classmethod
    def _id(cls, value):
        return None if value is None else str(_recipe_uuid(value))


# ---------------------------------------------------------------------------
# Lecture des recettes
# ---------------------------------------------------------------------------

def _owned_done(user_id: uuid.UUID):
    """Le filtre de TOUS les outils sur les recettes : les siennes, terminées."""
    return and_(Recipe.owner_id == user_id, Recipe.status == ExtractionStatus.done)


async def owned_recipe(ctx: ToolContext, recipe_id: str) -> Recipe:
    """Recette du compte connecté, sinon ToolError (même message qu'absente)."""
    recipe = await ctx.db.get(Recipe, uuid.UUID(recipe_id))
    if not recipe or recipe.owner_id != ctx.user_id or recipe.status != ExtractionStatus.done:
        raise ToolError("Recette introuvable dans la bibliothèque de l'utilisateur.")
    return recipe


def total_minutes(recipe: Recipe) -> int | None:
    total = (recipe.prep_time or 0) + (recipe.cook_time or 0)
    return total or None


def card(recipe: Recipe) -> dict:
    """Carte « recette trouvée » pour l'interface."""
    return {
        "id": str(recipe.id), "title": recipe.title,
        "thumbnail_url": recipe.thumbnail_url, "minutes": total_minutes(recipe),
    }


def summary(recipe: Recipe) -> dict:
    """Résumé court pour le modèle : de quoi choisir, pas de quoi cuisiner."""
    out = {"id": str(recipe.id), "titre": recipe.title}
    if recipe.category:
        out["categorie"] = recipe.category
    if total_minutes(recipe):
        out["minutes"] = total_minutes(recipe)
    if recipe.servings:
        out["portions"] = recipe.servings
    if recipe.is_favorite:
        out["favori"] = True
    if recipe.rating:
        out["note"] = recipe.rating
    return out


def ingredient_line(ing) -> str:
    if not isinstance(ing, dict):
        return str(ing)
    parts = [str(ing.get(k) or "").strip() for k in ("quantity", "unit", "name")]
    line = " ".join(p for p in parts if p)
    if ing.get("notes"):
        line += f" ({ing['notes']})"
    if ing.get("section"):
        line = f"[{ing['section']}] {line}"
    return line


def step_line(step) -> str:
    if isinstance(step, dict):
        text = str(step.get("text") or "").strip()
        if step.get("section"):
            text = f"[{step['section']}] {text}"
    else:
        text = str(step).strip()
    return text if len(text) <= MAX_STEP_CHARS else text[:MAX_STEP_CHARS] + "…"


def compact_recipe(recipe: Recipe) -> dict:
    """Version compacte d'une recette : ingrédients, étapes, portions, temps."""
    out = summary(recipe)
    out.pop("minutes", None)
    if recipe.prep_time:
        out["preparation_min"] = recipe.prep_time
    if recipe.cook_time:
        out["cuisson_min"] = recipe.cook_time
    out["ingredients"] = [ingredient_line(i) for i in as_list(recipe.ingredients)]
    out["etapes"] = [step_line(s) for s in as_list(recipe.steps)]
    if recipe.notes:
        out["notes_perso"] = recipe.notes[:300]
    return out


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _contains(column, text: str):
    return column.ilike(f"%{_escape_like(text)}%", escape="\\")


async def search_recipes(ctx: ToolContext, args: SearchArgs) -> ToolOutcome:
    """Plein texte Postgres (français) sur titre, description, ingrédients et
    tags, avec repli ILIKE mot à mot quand il ne trouve rien (fautes,
    mots partiels) ou hors Postgres."""
    ingredients_text = cast(Recipe.ingredients, Text)
    base = select(Recipe).where(_owned_done(ctx.user_id))
    if args.categorie:
        base = base.where(Recipe.category == args.categorie)
    if args.max_minutes:
        total = func.coalesce(Recipe.prep_time, 0) + func.coalesce(Recipe.cook_time, 0)
        base = base.where(total <= args.max_minutes)
    if args.favoris:
        base = base.where(Recipe.is_favorite.is_(True))
    for ing in args.ingredients or []:
        base = base.where(_contains(ingredients_text, ing))

    rows: list[Recipe] = []
    texte = (args.texte or "").strip()
    if texte and ctx.db.get_bind().dialect.name == "postgresql":
        french = literal_column("'french'::regconfig")
        document = func.to_tsvector(french, func.concat_ws(
            " ", Recipe.title, Recipe.description, ingredients_text, cast(Recipe.tags, Text),
        ))
        query = func.plainto_tsquery(french, texte)
        rows = (await ctx.db.execute(
            base.where(document.op("@@")(query))
            .order_by(func.ts_rank(document, query).desc(), Recipe.created_at.desc())
            .limit(MAX_SEARCH_RESULTS + 1)
        )).scalars().all()
    if texte and not rows:
        words = [w for w in texte.replace(",", " ").split() if len(w) >= 3][:6] or [texte]
        rows = (await ctx.db.execute(
            base.where(or_(*(
                or_(_contains(Recipe.title, w), _contains(Recipe.description, w),
                    _contains(ingredients_text, w))
                for w in words
            ))).order_by(Recipe.created_at.desc()).limit(MAX_SEARCH_RESULTS + 1)
        )).scalars().all()
    if not texte:
        rows = (await ctx.db.execute(
            base.order_by(Recipe.created_at.desc()).limit(MAX_SEARCH_RESULTS + 1)
        )).scalars().all()

    more = len(rows) > MAX_SEARCH_RESULTS
    rows = rows[:MAX_SEARCH_RESULTS]
    result = {"recettes": [summary(r) for r in rows]}
    if more:
        result["remarque"] = f"Plus de {MAX_SEARCH_RESULTS} résultats : préciser la recherche."
    if not rows:
        result["remarque"] = "Aucune recette ne correspond dans la bibliothèque."
    return ToolOutcome(result, recipes=[card(r) for r in rows])


async def cook_with(ctx: ToolContext, args: PantryArgs) -> ToolOutcome:
    """« Qu'est-ce que je cuisine avec… » : même classement que la page Frigo."""
    rows = (await ctx.db.execute(select(Recipe).where(_owned_done(ctx.user_id)))).scalars().all()
    by_id = {str(r.id): r for r in rows}
    ranked = grocery.rank_by_pantry(
        [{"id": str(r.id), "ingredients": r.ingredients or []} for r in rows], args.ingredients,
    )
    if args.manque_max is not None:
        ranked = [r for r in ranked if len(r["missing"]) <= args.manque_max]
    ranked = ranked[:MAX_PANTRY_RESULTS]
    found = []
    for match in ranked:
        recipe = by_id[match["recipe"]["id"]]
        found.append({
            **summary(recipe),
            "avec": match["matched"][:6],
            "manque": match["missing"][:6] + (["…"] if len(match["missing"]) > 6 else []),
        })
    result = {"recettes": found}
    if not found:
        result["remarque"] = "Aucune recette de la bibliothèque n'utilise ces ingrédients."
    return ToolOutcome(result, recipes=[card(by_id[r["recipe"]["id"]]) for r in ranked])


def _ingredient_sets(recipe: Recipe) -> list[frozenset[str]]:
    """Ingrédients principaux (hors sel, poivre, huile, eau) en ensembles de mots."""
    sets = []
    for ing in as_list(recipe.ingredients):
        name = ing.get("name") if isinstance(ing, dict) else str(ing)
        tokens = frozenset(grocery.ingredient_tokens(name or ""))
        if tokens and not grocery.is_staple(name or ""):
            sets.append(tokens)
    return sets


def _shared_ingredients(a: list[frozenset[str]], b: list[frozenset[str]]) -> list[str]:
    """Ingrédients de a présents dans b (« poulet » ≈ « blancs de poulet »)."""
    return [" ".join(sorted(x)) for x in a if any(x <= y or y <= x for y in b)]


async def similar_recipes(ctx: ToolContext, args: RecipeArgs) -> ToolOutcome:
    """Recettes de la bibliothèque proches d'une recette : mêmes ingrédients
    principaux, même catégorie, tags communs."""
    source = await owned_recipe(ctx, args.recette_id)
    rows = (await ctx.db.execute(
        select(Recipe).where(_owned_done(ctx.user_id), Recipe.id != source.id)
    )).scalars().all()
    mine = _ingredient_sets(source)
    tags = {str(t).lower() for t in as_list(source.tags)}
    scored = []
    for recipe in rows:
        shared = _shared_ingredients(mine, _ingredient_sets(recipe))
        same_category = bool(source.category) and recipe.category == source.category
        common_tags = tags & {str(t).lower() for t in as_list(recipe.tags)}
        score = 2 * len(shared) + 3 * same_category + len(common_tags)
        if shared or (same_category and common_tags):
            scored.append((score, recipe, shared))
    scored.sort(key=lambda item: (-item[0], item[1].title))
    best = scored[:MAX_SIMILAR_RESULTS]
    result = {
        "recette": source.title,
        "similaires": [{**summary(r), "en_commun": shared[:5]} for _, r, shared in best],
    }
    if not best:
        result["remarque"] = (
            "Aucune recette proche dans sa bibliothèque. Propose des idées de plats en disant "
            "qu'elles n'y sont pas, et offre de les créer avec creer_recette."
        )
    return ToolOutcome(result, recipes=[card(r) for _, r, _ in best])


async def substitute(ctx: ToolContext, args: SubstituteArgs) -> ToolOutcome:
    """Remplacements éprouvés d'un ingrédient (table substitutions.py), avec
    la quantité utilisée dans la recette quand elle est donnée."""
    result: dict = {"ingredient": args.ingredient}
    recipes = []
    if args.recette_id:
        recipe = await owned_recipe(ctx, args.recette_id)
        recipes.append(recipe)
        wanted = frozenset(grocery.ingredient_tokens(args.ingredient))
        lines = [
            ingredient_line(i) for i in as_list(recipe.ingredients)
            if isinstance(i, dict) and wanted
            and (wanted <= (t := frozenset(grocery.ingredient_tokens(i.get("name") or ""))) or t and t <= wanted)
        ]
        result["dans_la_recette"] = lines or "absent de la recette"
        result["recette"] = recipe.title
    found = substitutions.lookup(args.ingredient)
    if found:
        result["reconnu"], result["remplacements"] = found
    else:
        result["remplacements"] = []
        result["remarque"] = "Pas dans la table : propose d'après tes connaissances, en le précisant."
    return ToolOutcome(result, recipes=[card(r) for r in recipes])


def _new_ingredient(entry: NewIngredient) -> dict:
    ingredient = {
        "quantity": entry.quantite,
        "unit": recipe_parsing.canonical_unit(entry.unite),
        "name": entry.nom,
        "notes": entry.precision,
    }
    if not ingredient["quantity"] and not ingredient["unit"]:
        # « 200 g de farine » tout dans le nom : découpé comme à l'extraction.
        parsed = recipe_parsing.parse_ingredient_line(entry.nom)
        if parsed["quantity"] or parsed["unit"]:
            ingredient = {**parsed, "notes": entry.precision or parsed["notes"]}
    section = (entry.section or "").strip().rstrip(" :")
    if section:
        ingredient["section"] = section[: recipe_parsing.MAX_SECTION_LENGTH]
    return ingredient


async def create_recipe(ctx: ToolContext, args: CreateArgs) -> ToolOutcome:
    """Enregistre dans la bibliothèque une recette rédigée par l'assistant."""
    title = " ".join(args.titre.split())
    ingredients = [_new_ingredient(i) for i in args.ingredients]
    steps = [s for s in (recipe_parsing.clean_step(t) for t in args.etapes) if s]
    if not steps:
        raise ToolError("Étapes vides : rédige les étapes de la recette.")

    # Même appel rejoué (le modèle répète parfois un outil) : pas de doublon.
    names = sorted(i["name"].lower() for i in ingredients)
    for existing in (await ctx.db.execute(
        select(Recipe).where(_owned_done(ctx.user_id), func.lower(Recipe.title) == title.lower())
    )).scalars():
        if sorted(str(i.get("name", "")).lower() for i in as_list(existing.ingredients) if isinstance(i, dict)) == names:
            return ToolOutcome(
                {"id": str(existing.id), "titre": existing.title, "lien": f"/recettes/{existing.id}",
                 "remarque": "Déjà enregistrée : ne la crée pas une deuxième fois."},
                recipes=[card(existing)],
            )

    description = " ".join((args.description or "").split())
    recipe = Recipe(
        owner_id=ctx.user_id,
        status=ExtractionStatus.done,
        source_type=SourceType.manual,
        title=title,
        description=f"{GENERATED_NOTICE} {description}".strip(),
        language="fr",
        category=recipe_parsing.normalize_category(args.categorie, title),
        servings=args.portions,
        prep_time=args.preparation_min or None,
        cook_time=args.cuisson_min or None,
        ingredients=ingredients,
        steps=recipe_parsing.steps_from_pairs((None, s) for s in steps),
        tags=recipe_parsing.normalize_tags(["assistant"] + list(args.tags or [])),
    )
    ctx.db.add(recipe)
    await ctx.db.commit()
    try:
        await achievement_service.on_recipe_added(ctx.db, SourceType.manual.value)
    except Exception:
        await ctx.db.rollback()
        logger.warning("Succès non mis à jour après une recette de l'assistant", exc_info=True)
    await sharing.auto_share(ctx.db, recipe)

    return ToolOutcome(
        {"id": str(recipe.id), "titre": title, "lien": f"/recettes/{recipe.id}",
         "remarque": "Enregistrée. Donne le lien et un résumé de 2 lignes, sans recopier la recette."},
        recipes=[card(recipe)],
        action={"kind": "recette", "label": f"Recette ajoutée : {title}", "recipe_id": str(recipe.id)},
    )


async def read_recipe(ctx: ToolContext, args: RecipeArgs) -> ToolOutcome:
    recipe = await owned_recipe(ctx, args.recette_id)
    return ToolOutcome(compact_recipe(recipe), recipes=[card(recipe)])


def scale_ingredient(ing, factor: float) -> str:
    if not isinstance(ing, dict):
        return str(ing)
    amount = grocery.parse_quantity(ing.get("quantity"))
    if amount is None:
        return ingredient_line(ing)
    quantity, unit = grocery.format_quantity(amount * factor, ing.get("unit") or None)
    return ingredient_line({**ing, "quantity": quantity, "unit": unit})


async def scale_recipe(ctx: ToolContext, args: ScaleArgs) -> ToolOutcome:
    recipe = await owned_recipe(ctx, args.recette_id)
    if not recipe.servings:
        raise ToolError("Le nombre de portions d'origine de cette recette n'est pas renseigné.")
    factor = args.portions / recipe.servings
    return ToolOutcome({
        "id": str(recipe.id), "titre": recipe.title,
        "portions_origine": recipe.servings, "portions": args.portions,
        "facteur": round(factor, 3),
        "ingredients": [scale_ingredient(i, factor) for i in as_list(recipe.ingredients)],
        "remarque": "Temps de cuisson inchangés ; ajuster le moule si besoin.",
    }, recipes=[card(recipe)])


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

async def show_planning(ctx: ToolContext, args: PlanningArgs) -> ToolOutcome:
    day = args.semaine or ctx.today
    start = day - timedelta(days=day.weekday())
    end = start + timedelta(days=6)
    rows = (await ctx.db.execute(
        select(MealPlan).where(
            MealPlan.owner_id == ctx.user_id, MealPlan.date >= start, MealPlan.date <= end,
        ).order_by(MealPlan.date)
    )).scalars().all()
    order = {m: i for i, m in enumerate(MEALS)}
    rows = sorted(rows, key=lambda r: (r.date, order.get(_meal_value(r.meal_type), 9)))
    return ToolOutcome({
        "du": start.isoformat(), "au": end.isoformat(),
        "repas": [{
            "date": r.date.isoformat(), "jour": JOURS[r.date.weekday()],
            "repas": _meal_value(r.meal_type), "recette": r.recipe_title or "?",
            "id": str(r.recipe_id),
        } for r in rows],
    })


def _meal_value(meal) -> str:
    return meal.value if isinstance(meal, MealType) else str(meal)


async def add_to_planning(ctx: ToolContext, args: AddPlanArgs) -> ToolOutcome:
    earliest, latest = ctx.today - timedelta(days=7), ctx.today + timedelta(days=366)
    # Tout est vérifié avant la moindre écriture : un lot à moitié ajouté
    # serait difficile à expliquer.
    recipes = {}
    for entry in args.elements:
        if not earliest <= entry.date <= latest:
            raise ToolError(
                f"Date {entry.date.isoformat()} hors limites "
                f"(du {earliest.isoformat()} au {latest.isoformat()})."
            )
        if entry.recette_id not in recipes:
            recipes[entry.recette_id] = await owned_recipe(ctx, entry.recette_id)

    added, already = [], []
    for entry in args.elements:
        recipe = recipes[entry.recette_id]
        meal = MealType(entry.repas)
        exists = (await ctx.db.execute(
            select(MealPlan.id).where(
                MealPlan.owner_id == ctx.user_id, MealPlan.date == entry.date,
                MealPlan.meal_type == meal, MealPlan.recipe_id == recipe.id,
            )
        )).first()
        line = f"{JOURS[entry.date.weekday()]} {entry.date.isoformat()} ({entry.repas}) : {recipe.title}"
        if exists or line in added:
            already.append(line)
            continue
        ctx.db.add(MealPlan(
            owner_id=ctx.user_id, date=entry.date, meal_type=meal, recipe_id=recipe.id,
            recipe_title=recipe.title, recipe_thumbnail=recipe.thumbnail_url,
        ))
        added.append(line)
    await ctx.db.commit()

    if added:
        # Même succès « Semaine complète » que depuis la page Planning.
        last = max(e.date for e in args.elements)
        week_start = last - timedelta(days=last.weekday())
        week_count = (await ctx.db.execute(
            select(func.count()).select_from(MealPlan).where(
                MealPlan.owner_id == ctx.user_id, MealPlan.date >= week_start,
                MealPlan.date <= week_start + timedelta(days=6),
            )
        )).scalar_one()
        try:
            await achievement_service.on_meal_plan_created(ctx.db, week_count)
        except Exception:
            await ctx.db.rollback()
            logger.warning("Succès du planning non mis à jour", exc_info=True)

    result = {"ajoutes": added}
    if already:
        result["deja_prevus"] = already
    action = None
    if added:
        if len(added) == 1:
            label = f"Ajouté au planning : {added[0]}"
        else:
            label = f"Ajouté au planning : {len(added)} repas"
        action = {"kind": "planning", "label": label}
    return ToolOutcome(result, recipes=[card(r) for r in recipes.values()], action=action)


# ---------------------------------------------------------------------------
# Liste de courses
# ---------------------------------------------------------------------------

def _shopping_line(row) -> str:
    quantity = " ".join(p for p in (row.quantity, row.unit) if p)
    return f"{row.name}{f' — {quantity}' if quantity else ''} ({row.aisle})"


async def show_shopping(ctx: ToolContext, args: NoArgs) -> ToolOutcome:
    rows = await shopping_list.list_items(ctx.db, ctx.user_id)
    todo = [r for r in rows if not r.checked]
    result = {
        "a_acheter": [_shopping_line(r) for r in todo[:MAX_SHOPPING_LINES]],
        "deja_coches": len(rows) - len(todo),
    }
    if len(todo) > MAX_SHOPPING_LINES:
        result["remarque"] = f"{len(todo) - MAX_SHOPPING_LINES} autres articles non affichés."
    return ToolOutcome(result)


async def add_to_shopping(ctx: ToolContext, args: AddShoppingArgs) -> ToolOutcome:
    if not args.elements and not args.recette_id:
        raise ToolError("Donner des elements à ajouter, ou une recette_id.")
    items: list[dict] = []
    recipes = []
    if args.recette_id:
        recipe = await owned_recipe(ctx, args.recette_id)
        recipes.append(recipe)
        ingredients = as_list(recipe.ingredients)
        if args.portions and recipe.servings:
            factor = args.portions / recipe.servings
            ingredients = [
                {**i, "quantity": grocery.format_quantity(q * factor, i.get("unit") or None)[0]}
                if isinstance(i, dict) and (q := grocery.parse_quantity(i.get("quantity"))) is not None
                else i
                for i in ingredients
            ]
        items += grocery.merge_ingredients([(recipe.title, ingredients)])
    for entry in args.elements or []:
        items.append({
            "name": entry.nom[:1].upper() + entry.nom[1:], "quantity": entry.quantite,
            "unit": entry.unite, "aisle": grocery.guess_aisle(entry.nom), "recipes": [],
        })
    if not items:
        raise ToolError("Rien à ajouter : la recette n'a pas d'ingrédients.")

    existing = [r for r in await shopping_list.list_items(ctx.db, ctx.user_id) if not r.checked]
    added, merged = await shopping_list.add_merged(ctx.db, ctx.user_id, items, existing)
    await ctx.db.commit()
    count = added + merged
    label = f"Ajouté à la liste de courses : {count} élément{'s' if count > 1 else ''}"
    return ToolOutcome(
        {"ajoutes": added, "quantites_augmentees": merged,
         "articles": [i["name"] for i in items][:30]},
        recipes=[card(r) for r in recipes],
        action={"kind": "courses", "label": label},
    )


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    args_model: type[_Args]
    run: Callable[[ToolContext, _Args], Awaitable[ToolOutcome]]
    status: str  # affiché pendant l'exécution
    writes: bool = False


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


_ID = {"type": "string", "description": "id renvoyé par un outil"}

# Schémas écrits à la main, plus courts que ceux générés par pydantic : ils
# occupent la fenêtre de contexte à chaque tour.
TOOLS: dict[str, Tool] = {t.name: t for t in (
    Tool(
        "chercher_recettes",
        "Cherche dans les recettes de l'utilisateur (titre, description, ingrédients). "
        "Sans texte : ses dernières recettes.",
        _obj({
            "texte": {"type": "string", "description": "mots-clés"},
            "ingredients": {"type": "array", "items": {"type": "string"},
                            "description": "ingrédients tous requis"},
            "categorie": {"type": "string", "enum": list(CATEGORIES)},
            "max_minutes": {"type": "integer", "description": "temps total maximum"},
            "favoris": {"type": "boolean"},
        }),
        SearchArgs, search_recipes, "Recherche dans tes recettes…",
    ),
    Tool(
        "cuisiner_avec",
        "Recettes de l'utilisateur réalisables avec ces ingrédients (frigo), "
        "classées par ingrédients manquants.",
        _obj({
            "ingredients": {"type": "array", "items": {"type": "string"}},
            "manque_max": {"type": "integer", "description": "ingrédients manquants maximum"},
        }, ["ingredients"]),
        PantryArgs, cook_with, "Je regarde ce que tu peux cuisiner…",
    ),
    Tool(
        "lire_recette",
        "Recette complète : ingrédients, étapes, portions, temps.",
        _obj({"recette_id": _ID}, ["recette_id"]),
        RecipeArgs, read_recipe, "Lecture de la recette…",
    ),
    Tool(
        "adapter_quantites",
        "Recalcule les quantités d'une recette pour un nombre de portions.",
        _obj({"recette_id": _ID, "portions": {"type": "integer"}}, ["recette_id", "portions"]),
        ScaleArgs, scale_recipe, "Calcul des quantités…",
    ),
    Tool(
        "recettes_similaires",
        "Recettes de sa bibliothèque proches d'une recette (ingrédients, catégorie, tags).",
        _obj({"recette_id": _ID}, ["recette_id"]),
        RecipeArgs, similar_recipes, "Je cherche des recettes proches…",
    ),
    Tool(
        "remplacer_ingredient",
        "Remplacements éprouvés d'un ingrédient, avec proportions. "
        "Avec recette_id : quantité utilisée dans cette recette.",
        _obj({"ingredient": {"type": "string"}, "recette_id": _ID}, ["ingredient"]),
        SubstituteArgs, substitute, "Je cherche par quoi le remplacer…",
    ),
    Tool(
        "creer_recette",
        "Enregistre dans sa bibliothèque une recette complète que tu as rédigée "
        "(demandée par l'utilisateur : générer, inventer, version adaptée).",
        _obj({
            "titre": {"type": "string"},
            "description": {"type": "string", "description": "1-2 phrases"},
            "portions": {"type": "integer"},
            "preparation_min": {"type": "integer"},
            "cuisson_min": {"type": "integer"},
            "categorie": {"type": "string", "enum": list(CATEGORIES)},
            "ingredients": {"type": "array", "items": _obj({
                "nom": {"type": "string"}, "quantite": {"type": "string"},
                "unite": {"type": "string"}, "precision": {"type": "string"},
                "section": {"type": "string", "description": "partie (Pâte, Sauce…), sinon vide"},
            }, ["nom"])},
            "etapes": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string"}},
        }, ["titre", "ingredients", "etapes"]),
        CreateArgs, create_recipe, "J'enregistre la recette…", writes=True,
    ),
    Tool(
        "planning",
        "Repas planifiés sur une semaine (lundi-dimanche).",
        _obj({"semaine": {"type": "string", "description": "un jour de la semaine, AAAA-MM-JJ ; "
                                                           "défaut : cette semaine"}}),
        PlanningArgs, show_planning, "Lecture du planning…",
    ),
    Tool(
        "ajouter_au_planning",
        "Ajoute des recettes de l'utilisateur à son planning.",
        _obj({"elements": {"type": "array", "items": _obj({
            "recette_id": _ID,
            "date": {"type": "string", "description": "AAAA-MM-JJ"},
            "repas": {"type": "string", "enum": list(MEALS)},
        }, ["recette_id", "date", "repas"])}}, ["elements"]),
        AddPlanArgs, add_to_planning, "Ajout au planning…", writes=True,
    ),
    Tool(
        "liste_de_courses",
        "Articles de la liste de courses encore à acheter.",
        _obj({}),
        NoArgs, show_shopping, "Lecture de la liste de courses…",
    ),
    Tool(
        "ajouter_aux_courses",
        "Ajoute des articles, ou les ingrédients d'une recette, à la liste de courses.",
        _obj({
            "elements": {"type": "array", "items": _obj({
                "nom": {"type": "string"}, "quantite": {"type": "string"},
                "unite": {"type": "string"},
            }, ["nom"])},
            "recette_id": _ID,
            "portions": {"type": "integer", "description": "avec recette_id"},
        }),
        AddShoppingArgs, add_to_shopping, "Ajout à la liste de courses…", writes=True,
    ),
)}


def ollama_tools() -> list[dict]:
    return [
        {"type": "function", "function": {
            "name": t.name, "description": t.description, "parameters": t.parameters,
        }}
        for t in TOOLS.values()
    ]


def claude_tools() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.parameters}
        for t in TOOLS.values()
    ]


def _validation_message(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:4]:
        where = ".".join(str(p) for p in err.get("loc", ())) or "arguments"
        message = err.get("msg", "invalide")
        if err.get("type") == "extra_forbidden":
            message = "champ inconnu"
        parts.append(f"{where} : {message}")
    return "Arguments invalides — " + " ; ".join(parts)


def encode_result(result: dict) -> str:
    """JSON compact, tronqué : un résultat ne doit jamais remplir le contexte."""
    text = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + "…(tronqué)"
    return text


async def run_tool(ctx: ToolContext, name: str, arguments) -> ToolOutcome:
    """Exécute un appel d'outil du modèle ; ne lève jamais (sauf annulation)."""
    tool = TOOLS.get(name)
    if tool is None:
        return ToolOutcome({"erreur": f"Outil inconnu : {name}. Outils : {', '.join(TOOLS)}."}, error=True)
    if isinstance(arguments, str):
        # Certains modèles envoient les arguments en texte JSON.
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except ValueError:
            return ToolOutcome({"erreur": "Arguments illisibles (JSON attendu)."}, error=True)
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return ToolOutcome({"erreur": "Arguments invalides — objet attendu."}, error=True)
    try:
        args = tool.args_model.model_validate(arguments)
    except ValidationError as exc:
        return ToolOutcome({"erreur": _validation_message(exc)}, error=True)
    try:
        return await tool.run(ctx, args)
    except ToolError as exc:
        await ctx.db.rollback()
        return ToolOutcome({"erreur": str(exc)}, error=True)
    except Exception:
        await ctx.db.rollback()
        logger.exception("Outil %s en échec", name)
        return ToolOutcome({"erreur": "L'outil a échoué (erreur interne)."}, error=True)
