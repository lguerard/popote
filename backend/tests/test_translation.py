"""Traduction du contenu des recettes (comptes en anglais) et langue de l'assistant.

Même base de test que test_assistant.py (SQLite en mémoire, ou Postgres
avec POPOTE_TEST_DATABASE_URL), Ollama simulé.
"""

import asyncio
import json

import httpx
import pytest

from app.models.recipe import Recipe
from app.services import assistant, translation_service as ts
from test_assistant import TODAY, chat, fake_ollama, run


INGREDIENTS = [
    {"quantity": "200", "unit": "g", "name": "farine", "notes": None, "section": "Pâte"},
    {"quantity": "2", "unit": "c. à s.", "name": "huile d'olive", "notes": "vierge", "section": "Pâte"},
    {"quantity": "1", "unit": None, "name": "oignon", "notes": "émincé"},
]
STEPS = [{"order": 1, "text": "Mélanger la farine et l'huile.", "section": "Pâte"}, {"order": 2, "text": "Cuire 20 min."}]
TAGS = ["facile", "végétarien"]

ENGLISH = {
    "title": "Onion tart",
    "description": "",
    "ingredients": [
        {"unit": "g", "name": "flour", "notes": "", "section": "Dough"},
        {"unit": "tbsp", "name": "olive oil", "notes": "extra virgin", "section": "Dough"},
        {"unit": "", "name": "onion", "notes": "sliced", "section": ""},
    ],
    "steps": [{"text": "Mix the flour and oil.", "section": "Dough"}, {"text": "Bake for 20 min.", "section": ""}],
    "tags": ["easy", "vegetarian"],
}


@pytest.fixture(autouse=True)
def _clean_state():
    ts._in_flight.clear()
    ts._failed_until.clear()
    yield
    ts._in_flight.clear()
    ts._failed_until.clear()


def ollama_json(payload) -> bytes:
    return json.dumps({"message": {"role": "assistant", "content": json.dumps(payload)}, "done": True}).encode()


async def add_tart(db, **overrides) -> Recipe:
    async with db.sessions() as session:
        fields = dict(
            owner_id=db.alice, title="Tarte à l'oignon", description=None,
            ingredients=INGREDIENTS, steps=STEPS, tags=TAGS, language="en",
        )
        recipe = Recipe(**{**fields, **overrides})
        session.add(recipe)
        await session.commit()
        return recipe


async def load(db, recipe_id) -> Recipe:
    async with db.sessions() as session:
        return await session.get(Recipe, recipe_id)


# ---------------------------------------------------------------------------
# Fusion de la réponse du modèle
# ---------------------------------------------------------------------------

def test_merge_keeps_quantities_shape_and_order():
    out = ts.merge_translation("Tarte à l'oignon", None, INGREDIENTS, STEPS, TAGS, ENGLISH)
    assert out["title"] == "Onion tart"
    assert out["description"] is None  # absent reste absent
    assert [i["quantity"] for i in out["ingredients"]] == ["200", "2", "1"]
    assert out["ingredients"][1] == {
        "quantity": "2", "unit": "tbsp", "name": "olive oil", "notes": "extra virgin", "section": "Dough",
    }
    # Pas de clé ajoutée (section absente de l'original), None reste None.
    assert out["ingredients"][2] == {"quantity": "1", "unit": None, "name": "onion", "notes": "sliced"}
    assert out["steps"] == [
        {"order": 1, "text": "Mix the flour and oil.", "section": "Dough"},
        {"order": 2, "text": "Bake for 20 min."},
    ]
    assert out["tags"] == ["easy", "vegetarian"]
    # L'original n'est jamais modifié en place.
    assert INGREDIENTS[0]["name"] == "farine" and STEPS[0]["text"].startswith("Mélanger")


def test_merge_rejects_missing_lines_but_tolerates_tags():
    with pytest.raises(ts.llm_service.UnreadableResponse):
        ts.merge_translation("T", None, INGREDIENTS, STEPS, TAGS, {**ENGLISH, "ingredients": ENGLISH["ingredients"][:2]})
    out = ts.merge_translation("T", None, INGREDIENTS, STEPS, TAGS, {**ENGLISH, "tags": ["easy"]})
    assert out["tags"] == TAGS


def test_request_uses_schema_and_shared_options():
    body = ts.build_translation_request("{}")
    assert body["format"] == ts.TRANSLATION_JSON_SCHEMA
    assert body["think"] is False and body["stream"] is False
    assert body["options"]["num_ctx"] == ts.settings.ollama_num_ctx


# ---------------------------------------------------------------------------
# Cache et fraîcheur
# ---------------------------------------------------------------------------

def test_translated_once_cached_then_refreshed_after_edit(monkeypatch):
    async def scenario(db):
        bodies = fake_ollama(monkeypatch, [ollama_json(ENGLISH)])
        tart = await add_tart(db)
        before = await load(db, tart.id)

        recipe = await load(db, tart.id)
        translation, pending = await ts.translation_for_display(recipe, "en", session_factory=db.sessions)
        assert not pending and translation["title"] == "Onion tart"
        assert len(bodies) == 1
        assert bodies[0]["format"] == ts.TRANSLATION_JSON_SCHEMA
        sent = json.loads(bodies[0]["messages"][1]["content"])
        assert sent["ingredients"][1]["unit"] == "c. à s." and sent["tags"] == TAGS

        stored = await load(db, tart.id)
        # Original intact, updated_at inchangé : la mise en cache n'est pas une modification.
        assert stored.title == "Tarte à l'oignon" and stored.ingredients == INGREDIENTS
        assert stored.steps == STEPS and stored.tags == TAGS
        assert stored.updated_at == before.updated_at
        entry = stored.translations["en"]
        assert entry["source_hash"] == ts.content_hash(stored) and entry["source_updated_at"]

        # Deuxième lecture : servie par le cache, aucun appel au modèle.
        translation, _ = await ts.translation_for_display(stored, "en", session_factory=db.sessions)
        assert translation["ingredients"][0]["name"] == "flour" and len(bodies) == 1

        # Un favori ne change pas le contenu : la traduction reste valable.
        async with db.sessions() as session:
            r = await session.get(Recipe, tart.id)
            r.is_favorite = True
            await session.commit()
        assert ts.cached_translation(await load(db, tart.id), "en") is not None

        # Contenu modifié : cache périmé, nouvelle traduction.
        async with db.sessions() as session:
            r = await session.get(Recipe, tart.id)
            r.title = "Tarte aux oignons"
            await session.commit()
        edited = await load(db, tart.id)
        assert ts.cached_translation(edited, "en") is None
        await ts.translation_for_display(edited, "en", session_factory=db.sessions)
        assert len(bodies) == 2

    run(scenario)


def test_french_account_and_english_content_are_never_translated(monkeypatch):
    async def scenario(db):
        bodies = fake_ollama(monkeypatch, [ollama_json(ENGLISH)])
        tart = await add_tart(db)
        english = await add_tart(
            db, title="Onion tart",
        )
        async with db.sessions() as session:
            r = await session.get(Recipe, english.id)
            r.ingredients = [{"quantity": "1", "unit": "cup", "name": "flour"}]
            r.steps = [{"order": 1, "text": "Add the flour to the bowl and mix with the oil, then bake in the oven for 20 minutes."}]
            await session.commit()
        assert await ts.translation_for_display(await load(db, tart.id), "fr") == (None, False)
        assert await ts.translation_for_display(await load(db, english.id), "en",
                                                session_factory=db.sessions) == (None, False)
        assert bodies == []

    run(scenario)


def test_slow_translation_is_pending_then_served(monkeypatch):
    async def scenario(db):
        fake_ollama(monkeypatch, [ollama_json(ENGLISH)], delay=0.3)
        tart = await add_tart(db)
        recipe = await load(db, tart.id)
        translation, pending = await ts.translation_for_display(
            recipe, "en", wait=0.01, session_factory=db.sessions,
        )
        assert translation is None and pending and ts.is_pending(tart.id, "en")
        await ts._in_flight[(tart.id, "en")]
        assert ts.cached_translation(await load(db, tart.id), "en")["title"] == "Onion tart"

    run(scenario)


def test_failure_shows_original_and_backs_off(monkeypatch):
    async def scenario(db):
        bodies = fake_ollama(monkeypatch, [httpx.Response(500, json={"error": "boom"})])
        tart = await add_tart(db)
        recipe = await load(db, tart.id)
        assert await ts.translation_for_display(recipe, "en", session_factory=db.sessions) == (None, False)
        calls = len(bodies)
        # Pas de nouvel essai tout de suite.
        assert await ts.translation_for_display(recipe, "en", session_factory=db.sessions) == (None, False)
        assert len(bodies) == calls
        assert (await load(db, tart.id)).translations is None

    run(scenario)


def test_background_translations_are_bounded(monkeypatch):
    async def scenario(db):
        fake_ollama(monkeypatch, [ollama_json(ENGLISH)], delay=0.05)
        tarts = [await load(db, (await add_tart(db)).id) for _ in range(5)]
        assert ts.schedule_background(tarts, "fr", session_factory=db.sessions) == 0
        assert ts.schedule_background(tarts, "en", session_factory=db.sessions) == ts.BACKGROUND_PER_REQUEST
        # Déjà au maximum : rien de plus.
        assert ts.schedule_background(tarts, "en", session_factory=db.sessions) == 0
        assert len(ts._in_flight) <= ts.MAX_CONCURRENT
        await asyncio.gather(*list(ts._in_flight.values()))
        done = [ts.cached_translation(await load(db, t.id), "en") is not None for t in tarts]
        assert sum(done) == ts.BACKGROUND_PER_REQUEST

    run(scenario)


# ---------------------------------------------------------------------------
# Assistant
# ---------------------------------------------------------------------------

def test_system_prompt_reply_language():
    fr = assistant.build_system_prompt(TODAY)
    en = assistant.build_system_prompt(TODAY, language="en")
    assert "Réponds en français, brièvement, en Markdown simple (listes, gras)." in fr
    assert "Reply in English" in en and "Réponds en français" not in en
    # Le reste des consignes ne change pas.
    assert fr.replace(assistant.REPLY_LANGUAGE["fr"], "") == en.replace(assistant.REPLY_LANGUAGE["en"], "")


def test_assistant_english_account_gets_translated_open_recipe(monkeypatch):
    async def scenario(db):
        bodies = fake_ollama(monkeypatch, [
            ollama_json(ENGLISH),
            json.dumps({"message": {"role": "assistant", "content": "Sure."}, "done": True}).encode(),
        ])
        monkeypatch.setattr(ts, "_session_factory", lambda: db.sessions)
        tart = await add_tart(db)
        events = await chat(db, "Can I skip the onion?", recipe_id=tart.id, language="en")
        assert not any(e["type"] == "error" for e in events)
        system = bodies[-1]["messages"][0]["content"]
        assert "Reply in English" in system
        assert "Onion tart" in system and "2 tbsp olive oil" in system
        assert "farine" not in system

        # Compte en français : recette d'origine, aucun appel de traduction.
        bodies.clear()
        await chat(db, "Puis-je enlever l'oignon ?", recipe_id=tart.id)
        assert len(bodies) == 1
        system = bodies[0]["messages"][0]["content"]
        assert "Réponds en français" in system and "farine" in system

    run(scenario)


def test_hash_ignores_empty_keys_added_by_a_no_op_save():
    from types import SimpleNamespace
    from app.schemas.recipe import RecipeUpdate

    sparse = [{"quantity": "200", "unit": "g", "name": "farine"}, {"name": "sel", "section": "Pâte"}]
    stored = SimpleNamespace(title="T", description=None, ingredients=sparse, steps=STEPS, tags=TAGS)
    saved = RecipeUpdate(ingredients=sparse, steps=STEPS)
    resaved = SimpleNamespace(title="T", description="", ingredients=saved.ingredients, steps=saved.steps, tags=TAGS)
    assert saved.ingredients != sparse  # notes: None… ajoutées
    assert ts.content_hash(stored) == ts.content_hash(resaved)
    edited = SimpleNamespace(**{**vars(resaved), "title": "T2"})
    assert ts.content_hash(edited) != ts.content_hash(stored)


def test_every_assistant_status_has_an_english_text():
    from app.services import assistant_tools as tools

    for tool in tools.TOOLS.values():
        assert assistant.localize_event({"type": "status", "text": tool.status}, "en")["text"] != tool.status
    event = {"type": "action", "kind": "planning", "label": "Ajouté au planning : 2 repas"}
    assert assistant.localize_event(event, "en")["label"] == "Added to the meal plan: 2 meals"
    assert assistant.localize_event(event, "fr") is event
