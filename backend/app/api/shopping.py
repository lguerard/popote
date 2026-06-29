from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models.recipe import Recipe
from ..schemas.recipe import ShoppingListRequest, ShoppingItem
from ..services import achievement_service

router = APIRouter(tags=["shopping"])


@router.post("/shopping-list", response_model=list[ShoppingItem])
async def get_shopping_list(req: ShoppingListRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Recipe).where(Recipe.id.in_(req.recipe_ids))
    )
    recipes = result.scalars().all()

    # Merge ingredients: key = (name_lower, unit_lower)
    merged: dict[tuple, dict] = {}
    for recipe in recipes:
        for ing in (recipe.ingredients or []):
            name = ing.get("name", "").strip()
            unit = (ing.get("unit") or "").strip().lower()
            key = (name.lower(), unit)
            if key not in merged:
                merged[key] = {
                    "name": name,
                    "unit": ing.get("unit") or None,
                    "quantity": None,
                    "qty_num": 0.0,
                    "has_numeric": False,
                    "recipes": [],
                }
            merged[key]["recipes"].append(recipe.title)
            qty = _parse_qty(ing.get("quantity"))
            if qty is not None:
                merged[key]["qty_num"] += qty
                merged[key]["has_numeric"] = True

    items = []
    for item in merged.values():
        qty_str = None
        if item["has_numeric"]:
            n = item["qty_num"]
            qty_str = str(int(n)) if n == int(n) else f"{round(n, 1)}"
        items.append(ShoppingItem(
            name=item["name"],
            quantity=qty_str,
            unit=item["unit"],
            recipes=item["recipes"],
        ))

    await achievement_service.on_shopping_generated(db)
    return sorted(items, key=lambda x: x.name.lower())


def _parse_qty(s: str | None) -> float | None:
    if not s:
        return None
    import re
    frac = re.match(r"^(\d+)\s*/\s*(\d+)$", s.strip())
    if frac:
        return int(frac.group(1)) / int(frac.group(2))
    mixed = re.match(r"^(\d+)\s+(\d+)\s*/\s*(\d+)$", s.strip())
    if mixed:
        return int(mixed.group(1)) + int(mixed.group(2)) / int(mixed.group(3))
    try:
        return float(s.strip().replace(",", "."))
    except ValueError:
        return None
