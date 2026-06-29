from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import init_db, AsyncSessionLocal
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


app = FastAPI(title="KitchenAI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recipes_router, prefix="/api")
app.include_router(extract_router, prefix="/api")
app.include_router(shopping_router, prefix="/api")
app.include_router(meal_plan_router, prefix="/api")
app.include_router(achievements_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
