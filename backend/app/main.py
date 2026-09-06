from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import init_db, AsyncSessionLocal
from .deps import current_user
from .api.auth import router as auth_router
from .api.recipes import router as recipes_router
from .api.extract import router as extract_router
from .api.shopping import router as shopping_router
from .api.meal_plan import router as meal_plan_router
from .api.achievements import router as achievements_router
from .services.llm_service import ensure_model_available
from .services.achievement_service import init_achievements


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as db:
        await init_achievements(db)
    await ensure_model_available()
    yield


app = FastAPI(title="Popote", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# /api/auth porte sa propre protection : connexion, création du premier compte
# et réinitialisation doivent rester joignables sans être connecté.
app.include_router(auth_router, prefix="/api")

# Tout le reste exige une session. Le recettier est commun au foyer (les
# recettes n'appartiennent à personne en particulier) : l'authentification
# ferme la porte, elle ne cloisonne pas les données.
protected = [Depends(current_user)]
app.include_router(recipes_router, prefix="/api", dependencies=protected)
app.include_router(extract_router, prefix="/api", dependencies=protected)
app.include_router(shopping_router, prefix="/api", dependencies=protected)
app.include_router(meal_plan_router, prefix="/api", dependencies=protected)
app.include_router(achievements_router, prefix="/api", dependencies=protected)


@app.get("/api/health")
async def health():
    """Volontairement public : sert au healthcheck et au bouton « Tester la
    connexion » de l'application Android, avant toute connexion."""
    return {"status": "ok"}
