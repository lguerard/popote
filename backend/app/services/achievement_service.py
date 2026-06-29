from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.achievement import Achievement
from app.models.recipe import Recipe

ACHIEVEMENTS = [
    # Collection
    {"id": "first_recipe",      "name": "Premier Pas",        "icon": "🌟", "description": "Ajoutez votre première recette",          "goal": 1,   "category": "collection"},
    {"id": "collection_10",     "name": "Collectionneur",     "icon": "📚", "description": "10 recettes dans votre collection",        "goal": 10,  "category": "collection"},
    {"id": "collection_50",     "name": "Bibliothèque",       "icon": "🏛️", "description": "50 recettes dans votre collection",       "goal": 50,  "category": "collection"},
    {"id": "collection_100",    "name": "Grand Chef",         "icon": "👨‍🍳", "description": "100 recettes dans votre collection",     "goal": 100, "category": "collection"},
    # Cuisine mode
    {"id": "first_cooking",     "name": "En Cuisine !",       "icon": "🍳", "description": "Utilisez Mode Cuisine pour la 1ère fois", "goal": 1,   "category": "cuisine"},
    {"id": "cooking_10",        "name": "Chef Confirmé",      "icon": "⭐", "description": "Mode Cuisine utilisé 10 fois",             "goal": 10,  "category": "cuisine"},
    {"id": "cooking_50",        "name": "Chef Étoilé",        "icon": "🌟", "description": "Mode Cuisine utilisé 50 fois",             "goal": 50,  "category": "cuisine"},
    # Organisation
    {"id": "first_shopping",    "name": "Organisé",           "icon": "🛒", "description": "Générez votre première liste de courses",  "goal": 1,   "category": "organisation"},
    {"id": "first_meal_plan",   "name": "Planificateur",      "icon": "📅", "description": "Planifiez votre première semaine",         "goal": 1,   "category": "organisation"},
    {"id": "full_week",         "name": "Semaine Complète",   "icon": "🏆", "description": "Remplissez tous les repas d'une semaine",  "goal": 28,  "category": "organisation"},
    # Découverte
    {"id": "gourmet",           "name": "Gourmet",            "icon": "🍽️", "description": "Recettes dans 5 catégories différentes",  "goal": 5,   "category": "decouverte"},
    {"id": "world_tour",        "name": "Tour du Monde",      "icon": "🌍", "description": "Recettes en 3 langues différentes",        "goal": 3,   "category": "decouverte"},
    {"id": "video_hunter",      "name": "Chasseur de Vidéos", "icon": "🎬", "description": "Extrayez 10 recettes depuis des vidéos",   "goal": 10,  "category": "decouverte"},
    # Perfectionniste
    {"id": "first_favorite",    "name": "Coup de Cœur",       "icon": "❤️", "description": "Mettez une recette en favori",            "goal": 1,   "category": "perfectionniste"},
    {"id": "nutritionniste",    "name": "Nutritionniste",     "icon": "🥗", "description": "Analysez la nutrition de 5 recettes",      "goal": 5,   "category": "perfectionniste"},
    {"id": "photographe",       "name": "Photographe",        "icon": "📷", "description": "Ajoutez une recette par photo/OCR",        "goal": 1,   "category": "perfectionniste"},
    {"id": "noteur",            "name": "Carnet de Notes",    "icon": "📝", "description": "Écrivez des notes sur 3 recettes",         "goal": 3,   "category": "perfectionniste"},
]

ACHIEVEMENT_MAP = {a["id"]: a for a in ACHIEVEMENTS}


async def init_achievements(db: AsyncSession):
    """Seed achievement rows on first boot."""
    for ach in ACHIEVEMENTS:
        existing = await db.get(Achievement, ach["id"])
        if existing is None:
            db.add(Achievement(
                id=ach["id"], name=ach["name"], description=ach["description"],
                icon=ach["icon"], goal=ach["goal"], category=ach["category"],
                progress=0, unlocked_at=None,
            ))
    await db.commit()


async def _unlock(db: AsyncSession, ach_id: str, progress: int):
    row = await db.get(Achievement, ach_id)
    if row is None:
        return
    row.progress = min(progress, row.goal)
    if row.progress >= row.goal and row.unlocked_at is None:
        row.unlocked_at = datetime.now(timezone.utc)
    await db.commit()


async def check_collection(db: AsyncSession):
    count = (await db.execute(select(func.count()).select_from(Recipe))).scalar_one()
    for ach_id, goal in [("first_recipe", 1), ("collection_10", 10), ("collection_50", 50), ("collection_100", 100)]:
        await _unlock(db, ach_id, count)


async def check_video_hunter(db: AsyncSession):
    count = (await db.execute(
        select(func.count()).select_from(Recipe).where(Recipe.source_type == "video")
    )).scalar_one()
    await _unlock(db, "video_hunter", count)


async def check_gourmet(db: AsyncSession):
    result = await db.execute(
        select(func.count(func.distinct(Recipe.category))).select_from(Recipe).where(Recipe.category.isnot(None))
    )
    count = result.scalar_one()
    await _unlock(db, "gourmet", count)


async def check_world_tour(db: AsyncSession):
    result = await db.execute(
        select(func.count(func.distinct(Recipe.language))).select_from(Recipe).where(Recipe.language.isnot(None))
    )
    count = result.scalar_one()
    await _unlock(db, "world_tour", count)


async def increment(db: AsyncSession, ach_id: str, amount: int = 1):
    row = await db.get(Achievement, ach_id)
    if row is None or row.unlocked_at is not None:
        return
    await _unlock(db, ach_id, row.progress + amount)


async def on_recipe_added(db: AsyncSession, source_type: str):
    await check_collection(db)
    await check_gourmet(db)
    await check_world_tour(db)
    if source_type == "video":
        await check_video_hunter(db)
    if source_type == "image":
        await increment(db, "photographe")


async def on_favorite_toggled(db: AsyncSession):
    await increment(db, "first_favorite")


async def on_nutrition_analyzed(db: AsyncSession):
    await increment(db, "nutritionniste")


async def on_notes_saved(db: AsyncSession):
    await increment(db, "noteur")


async def on_cooking_mode_used(db: AsyncSession):
    await increment(db, "first_cooking")
    await increment(db, "cooking_10")
    await increment(db, "cooking_50")


async def on_shopping_generated(db: AsyncSession):
    await increment(db, "first_shopping")


async def on_meal_plan_created(db: AsyncSession, week_meal_count: int = 0):
    await increment(db, "first_meal_plan")
    row = await db.get(Achievement, "full_week")
    if row:
        await _unlock(db, "full_week", week_meal_count)
