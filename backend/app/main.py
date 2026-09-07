from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .database import init_db, AsyncSessionLocal
from .api.auth import router as auth_router
from .api.recipes import router as recipes_router
from .api.extract import router as extract_router
from .api.shopping import router as shopping_router
from .api.meal_plan import router as meal_plan_router
from .api.achievements import router as achievements_router
from .services.llm_service import ensure_model_available
from .services.achievement_service import init_achievements


# Valeurs historiques du depot et de docker-compose : elles ne doivent
# jamais servir en production.
_CLES_FAIBLES = {"changeme", "changeme-in-production", "secret", "popote"}


def _verifier_secret_key() -> None:
    """Refuse de demarrer avec une cle de signature devinable.

    Le jeton de session est signe avec SECRET_KEY. Une cle laissee a sa
    valeur par defaut, ou trop courte, laisse n'importe qui fabriquer un
    jeton valide et lire les donnees de tous les comptes. Un demarrage
    qui echoue en expliquant quoi faire vaut mieux qu'une instance
    ouverte que personne ne remarque.
    """
    cle = settings.secret_key.strip()
    if cle.lower() in _CLES_FAIBLES or len(cle) < 32:
        raise RuntimeError(
            "SECRET_KEY absente, trop courte (32 caracteres minimum) ou laissee a "
            "sa valeur par defaut : les jetons de session seraient falsifiables. "
            "Genere-en une et mets-la dans popote/.env :\n"
            "    python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _verifier_secret_key()
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

app.include_router(auth_router, prefix="/api")
app.include_router(recipes_router, prefix="/api")
app.include_router(extract_router, prefix="/api")
app.include_router(shopping_router, prefix="/api")
app.include_router(meal_plan_router, prefix="/api")
app.include_router(achievements_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
