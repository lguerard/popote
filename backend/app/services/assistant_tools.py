"""Outils de l'assistant : ce que le modèle peut lire et modifier.

Chaque outil ne voit que les données du compte connecté (owner_id), comme
les routes de l'API. Le partage entre comptes COPIE les recettes chez le
destinataire (services/sharing.py) : filtrer sur le propriétaire couvre
donc aussi les recettes reçues, sans jamais exposer celles d'autrui.

Aucun outil ne supprime ni ne modifie une recette : les seules écritures
sont des AJOUTS au planning et à la liste de courses, signalés à
l'interface par une « action ».

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
from ..models.recipe import ExtractionStatus, Recipe
from . import achievement_service, grocery, shopping_list
from .recipe_parsing import CATEGORIES, as_list

logger = logging.getLogger(__name__)

# Garde-fous de taille : la fenêtre du modèle local est de 8192 tokens.
MAX_SEARCH_RESULTS = 8
MAX_PANTRY_RESULTS = 6
MAX_SHOPPING_LINES = 60
MAX_TOOL_RESULT_CHARS = 2500
MAX_STEP_CHARS = 400

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
