from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from .config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


# create_all() ne cree que les tables ABSENTES : il n'ajoute jamais une
# colonne a une table qui existe deja. Une instance deployee avant les
# comptes utilisateurs garderait donc des tables sans owner_id, et chaque
# requete echouerait sur une colonne inconnue. Ces instructions sont
# idempotentes et rattrapent ce cas precis, sans imposer Alembic a un
# projet qui ne l'a jamais utilise.
_MIGRATIONS = (
    "ALTER TABLE recipes ADD COLUMN IF NOT EXISTS owner_id UUID"
    " REFERENCES users(id) ON DELETE CASCADE",
    "ALTER TABLE meal_plans ADD COLUMN IF NOT EXISTS owner_id UUID"
    " REFERENCES users(id) ON DELETE CASCADE",
    "CREATE INDEX IF NOT EXISTS ix_recipes_owner_id ON recipes (owner_id)",
    "CREATE INDEX IF NOT EXISTS ix_meal_plans_owner_id ON meal_plans (owner_id)",
    # Validation des inscriptions. Les comptes anterieurs sont approuves
    # d'office : ils existaient avant qu'il y ait quoi que ce soit a
    # valider, les refuser reviendrait a fermer la porte a l'occupant.
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(20)"
    " NOT NULL DEFAULT 'approved'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN"
    " NOT NULL DEFAULT false",
    "CREATE INDEX IF NOT EXISTS ix_users_status ON users (status)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS status_changed_at"
    " TIMESTAMPTZ NOT NULL DEFAULT now()",
    # Un serveur sans aucun administrateur ne peut plus valider personne :
    # le compte le plus ancien le devient. Sans effet des qu'il en existe un.
    "UPDATE users SET is_admin = true WHERE id = ("
    "  SELECT id FROM users ORDER BY created_at LIMIT 1"
    ") AND NOT EXISTS (SELECT 1 FROM users WHERE is_admin)",
)


async def init_db():
    async with engine.begin() as conn:
        from . import models  # noqa
        await conn.run_sync(Base.metadata.create_all)
        for statement in _MIGRATIONS:
            await conn.execute(text(statement))
