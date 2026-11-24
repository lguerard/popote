"""Liste des recettes : recherche libre (titre, description, tags) et filtre
de tag exact.

Postgres seulement (POPOTE_TEST_DATABASE_URL) : la recherche dans les tags
déplie le tableau JSONB, ce que SQLite ne sait pas faire.
"""

import uuid

import pytest

from app.models.recipe import ExtractionStatus, Recipe
from app.models.user import User
from test_assistant import PG_URL, run

pytestmark = pytest.mark.skipif(not PG_URL, reason="POPOTE_TEST_DATABASE_URL non défini")

# app.api.recipes importe fastapi, absent de l'environnement de test léger
# (voir ci.yml) : import différé, comme app.api.assistant dans test_assistant.py,
# pour que la collection du module ne casse jamais la suite légère.
def _list_recipes():
    pytest.importorskip("fastapi")
    from app.api.recipes import list_recipes
    return list_recipes


def _fold_text_fn():
    pytest.importorskip("fastapi")
    from app.api.recipes import _fold_text
    return _fold_text


async def _seed(db) -> dict[str, uuid.UUID]:
    ids = {}
    async with db.sessions() as session:
        for key, title, description, tags, owner in (
            ("gratin", "Gratin dauphinois", None, ["végétarien", "four"], db.alice),
            ("salade", "Salade express", "Prête en cinq minutes", ["rapide"], db.alice),
            ("chili", "Chili sin carne", "Un plat végétarien qui tient au corps", [], db.alice),
            ("oeufs", "Œufs cocotte", None, ["Brunch"], db.alice),
            # Même tag, autre compte : jamais renvoyée à Alice.
            ("bob", "Gratin de Bob", None, ["végétarien"], db.bob),
        ):
            recipe = Recipe(owner_id=owner, title=title, description=description, tags=tags,
                            ingredients=[], steps=[], status=ExtractionStatus.done)
            session.add(recipe)
            await session.flush()
            ids[key] = recipe.id
        await session.commit()
    return ids


async def _titles(db, **params) -> list[str]:
    defaults = dict(
        search=None, tag=None, category=None, source_type=None, max_time=None,
        favorites_only=False, never_cooked=False, cook_again=False, shared=False,
        sort="title", page=1, limit=100,
    )
    async with db.sessions() as session:
        user = await session.get(User, db.alice)
        out = await _list_recipes()(**{**defaults, **params}, db=session, user=user)
    return [r.title for r in out]


def test_search_matches_tags_partially_ignoring_case_and_accents():
    async def scenario(db):
        await _seed(db)
        # « veget » : tag « végétarien » du gratin, description du chili.
        assert await _titles(db, search="veget") == ["Chili sin carne", "Gratin dauphinois"]
        assert await _titles(db, search="VÉGÉT") == ["Chili sin carne", "Gratin dauphinois"]
        assert await _titles(db, search="rapi") == ["Salade express"]
        assert await _titles(db, search="brunch") == ["Œufs cocotte"]
    run(scenario)


def test_search_still_matches_title_and_description():
    async def scenario(db):
        await _seed(db)
        assert await _titles(db, search="dauphin") == ["Gratin dauphinois"]
        assert await _titles(db, search="cinq minutes") == ["Salade express"]
        assert await _titles(db, search="oeufs") == ["Œufs cocotte"]
        assert await _titles(db, search="gratin") == ["Gratin dauphinois"]  # pas celui de Bob
    run(scenario)


def test_tag_filter_stays_exact():
    async def scenario(db):
        await _seed(db)
        assert await _titles(db, tag="végétarien") == ["Gratin dauphinois"]
        # Ni partiel, ni sans accents, ni dans la description.
        assert await _titles(db, tag="veget") == []
        assert await _titles(db, tag="vegetarien") == []
        assert await _titles(db, tag="végétarien", search="dauphin") == ["Gratin dauphinois"]
        assert await _titles(db, tag="végétarien", search="chili") == []
    run(scenario)


def test_no_match_is_an_empty_list():
    async def scenario(db):
        await _seed(db)
        assert await _titles(db, search="zzz-introuvable") == []
        assert await _titles(db, tag="inexistant") == []
    run(scenario)


def test_fold_text():
    assert _fold_text_fn()("Végétarien Œuf ÇA") == "Vegetarien OEuf CA"
