"""Liste de courses persistée : lecture et ajout, partagés par l'API et l'assistant.

Sans FastAPI : l'assistant (services/assistant_tools.py) ajoute des
articles exactement comme le bouton « Ajouter à la liste » de l'appli,
avec la même fusion des quantités.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.shopping import ShoppingItem
from . import grocery


def aisle_rank(aisle: str) -> int:
    try:
        return grocery.AISLES.index(aisle)
    except ValueError:
        return len(grocery.AISLES)


async def list_items(db: AsyncSession, owner_id: uuid.UUID) -> list[ShoppingItem]:
    rows = (await db.execute(
        select(ShoppingItem).where(ShoppingItem.owner_id == owner_id)
        .order_by(ShoppingItem.position, ShoppingItem.created_at)
    )).scalars().all()
    return sorted(rows, key=lambda r: (aisle_rank(r.aisle), r.name.lower()))


async def last_position(db: AsyncSession, owner_id: uuid.UUID) -> int:
    return (await db.execute(
        select(func.coalesce(func.max(ShoppingItem.position), 0))
        .where(ShoppingItem.owner_id == owner_id)
    )).scalar_one()


def find_mergeable(existing: list[ShoppingItem], item: dict) -> ShoppingItem | None:
    """Article déjà sur la liste auquel ajouter la quantité, s'il y en a un."""
    key = grocery.ingredient_key(item["name"])
    for row in existing:
        if (
            grocery.ingredient_key(row.name) == key
            and (row.unit or None) == (item["unit"] or None)
            and grocery.parse_quantity(row.quantity) is not None
            and grocery.parse_quantity(item["quantity"]) is not None
        ):
            return row
    return None


async def add_merged(
    db: AsyncSession, owner_id: uuid.UUID, items: list[dict], existing: list[ShoppingItem],
) -> tuple[int, int]:
    """Ajoute `items` (name, quantity, unit, aisle, recipes) à la liste.

    Un article déjà présent (même ingrédient, même unité, quantités
    lisibles) voit sa quantité augmenter au lieu d'apparaître deux fois.
    Ne valide pas la session. Retourne (ajoutés, fusionnés).
    """
    added = merged = 0
    position = await last_position(db, owner_id)
    for item in items:
        target = find_mergeable(existing, item)
        if target:
            total = grocery.parse_quantity(target.quantity) + grocery.parse_quantity(item["quantity"])
            target.quantity, target.unit = grocery.format_quantity(total, target.unit)
            target.recipes = list(dict.fromkeys([*(target.recipes or []), *item["recipes"]]))
            merged += 1
            continue
        position += 1
        row = ShoppingItem(owner_id=owner_id, position=position, **item)
        db.add(row)
        existing.append(row)
        added += 1
    return added, merged
