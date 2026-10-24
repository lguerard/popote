"""Photos lues par le modèle de vision configuré, avec Tesseract en secours."""

import asyncio
import json

import httpx
import pytest

from app.services import llm_service, ocr_service

RECIPE = {"found": True, "title": "Crêpes", "ingredients": ["250 g de farine", "4 œufs"], "steps": ["Mélanger."]}


def _patch_http(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        llm_service.httpx, "AsyncClient",
        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(handler), **kw),
    )


def _local(monkeypatch, vision_model=""):
    monkeypatch.setattr(llm_service.settings, "claude_api_key", "")
    monkeypatch.setattr(llm_service.settings, "ollama_model", "gemma4:12b")
    monkeypatch.setattr(llm_service.settings, "ollama_vision_model", vision_model)
    monkeypatch.setattr(llm_service, "_schema_supported", True)
    monkeypatch.setattr(llm_service, "_OFFLOAD_CHECK_DELAY_SECONDS", 3600)


def test_photo_is_read_into_a_recipe_in_one_call(monkeypatch):
    _local(monkeypatch)
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": json.dumps(RECIPE)}})

    _patch_http(monkeypatch, handler)
    data = asyncio.run(llm_service.extract_recipe_from_image(b"\xff\xd8photo", "image/jpeg"))
    assert data["title"] == "Crêpes"
    assert len(bodies) == 1
    body = bodies[0]
    assert body["model"] == "gemma4:12b"  # OLLAMA_VISION_MODEL vide : OLLAMA_MODEL
    assert body["format"] == llm_service.RECIPE_JSON_SCHEMA
    assert body["think"] is False
    assert body["options"]["num_ctx"] == llm_service.settings.ollama_num_ctx
    assert body["messages"][-1]["images"] and body["messages"][-1]["role"] == "user"
    assert "photo" in body["messages"][0]["content"]


def test_vision_model_setting_is_used(monkeypatch):
    _local(monkeypatch, vision_model="qwen2.5vl:7b")
    body = llm_service.build_image_recipe_request("aGk=")
    assert body["model"] == "qwen2.5vl:7b"
    assert llm_service._ollama_models() == ["gemma4:12b", "qwen2.5vl:7b"]


def test_unload_frees_every_model(monkeypatch):
    _local(monkeypatch, vision_model="qwen2.5vl:7b")
    unloaded = []

    def handler(request):
        body = json.loads(request.content)
        assert body["keep_alive"] == 0
        unloaded.append(body["model"])
        return httpx.Response(200, json={})

    _patch_http(monkeypatch, handler)
    asyncio.run(llm_service.unload_ollama_model())
    assert unloaded == ["gemma4:12b", "qwen2.5vl:7b"]

    monkeypatch.setattr(llm_service.settings, "ollama_vision_model", "")
    unloaded.clear()
    asyncio.run(llm_service.unload_ollama_model())
    assert unloaded == ["gemma4:12b"]


def test_ocr_uses_the_vision_model_through_chat(monkeypatch):
    _local(monkeypatch)
    bodies = []

    def handler(request):
        assert request.url.path == "/api/chat"
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "Crêpes\n250 g de farine"}})

    _patch_http(monkeypatch, handler)
    monkeypatch.setattr(ocr_service, "_tesseract_ocr", lambda data: "tesseract")
    text = asyncio.run(ocr_service.extract_text_from_image(b"img", "image/png"))
    assert text == "Crêpes\n250 g de farine"
    assert bodies[0]["model"] == "gemma4:12b" and bodies[0]["messages"][-1]["images"]
    assert "format" not in bodies[0] and bodies[0]["think"] is False


def test_ocr_falls_back_to_tesseract_when_vision_fails_or_is_empty(monkeypatch):
    _local(monkeypatch)
    monkeypatch.setattr(ocr_service, "_tesseract_ocr", lambda data: "texte tesseract")

    _patch_http(monkeypatch, lambda request: httpx.Response(400, json={"error": "model does not support images"}))
    assert asyncio.run(ocr_service.extract_text_from_image(b"img")) == "texte tesseract"

    _patch_http(monkeypatch, lambda request: httpx.Response(200, json={"message": {"content": "  "}}))
    assert asyncio.run(ocr_service.extract_text_from_image(b"img")) == "texte tesseract"


def test_claude_ocr_failure_falls_back_to_tesseract(monkeypatch):
    monkeypatch.setattr(ocr_service.settings, "claude_api_key", "sk-test")

    async def broken(data, mime):
        raise RuntimeError("API indisponible")

    monkeypatch.setattr(ocr_service, "_claude_ocr", broken)
    monkeypatch.setattr(ocr_service, "_tesseract_ocr", lambda data: "texte tesseract")
    assert asyncio.run(ocr_service.extract_text_from_image(b"img")) == "texte tesseract"


class _FakeRecipe:
    def __init__(self):
        for field in ("owner_id", "source_type", "title", "ingredients", "steps", "thumbnail_url", "error_msg"):
            setattr(self, field, None)


class _FakeSession:
    def __init__(self, recipe):
        self.recipe = recipe

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, recipe_id):
        return self.recipe

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _run_photo_import(monkeypatch, *, vision, ocr_text="", text_llm=None, dish=None):
    pytest.importorskip("fastapi")  # absent de la CI : routes non testées là-bas
    from app import database
    from app.api import extract as extract_api
    from app.services import extractor

    calls = []
    recipe = _FakeRecipe()
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _FakeSession(recipe), raising=False)

    async def fake_vision(data, mime):
        calls.append("vision")
        if isinstance(vision, Exception):
            raise vision
        return vision

    async def fake_ocr(data, mime):
        calls.append("ocr")
        return ocr_text

    async def fake_text_llm(text):
        calls.append("text-llm")
        return text_llm

    async def fake_dish(text, progress):
        calls.append("dish")
        return dish, None

    async def nothing(*args, **kwargs):
        pass

    monkeypatch.setattr(llm_service, "extract_recipe_from_image", fake_vision)
    monkeypatch.setattr(llm_service, "extract_recipe_with_llm", fake_text_llm)
    monkeypatch.setattr(ocr_service, "extract_text_from_image", fake_ocr)
    monkeypatch.setattr(extractor, "recipe_for_dish", fake_dish)
    monkeypatch.setattr(extract_api, "_record_achievement", nothing)
    monkeypatch.setattr(extract_api.sharing, "auto_share", nothing)
    asyncio.run(extract_api._run_image_extraction("id", b"img", "image/jpeg"))
    return recipe, calls


def test_photo_import_needs_a_single_vision_call(monkeypatch):
    recipe, calls = _run_photo_import(monkeypatch, vision={"title": "Crêpes", "ingredients": [], "steps": []})
    assert calls == ["vision"] and recipe.title == "Crêpes"


def test_photo_import_falls_back_to_ocr_and_text_llm(monkeypatch):
    recipe, calls = _run_photo_import(
        monkeypatch, vision=RuntimeError("pas de vision"), ocr_text="Crêpes 250 g de farine",
        text_llm={"title": "Crêpes OCR"},
    )
    assert calls == ["vision", "ocr", "text-llm"] and recipe.title == "Crêpes OCR"


def test_photo_of_a_dish_goes_to_recipe_for_dish(monkeypatch):
    recipe, calls = _run_photo_import(
        monkeypatch, vision={"error": "Aucune recette trouvée"}, ocr_text="Une assiette de lasagnes.",
        dish={"title": "Lasagnes"},
    )
    assert calls == ["vision", "ocr", "dish"] and recipe.title == "Lasagnes"


def test_large_photos_are_downscaled_before_upload():
    pytest.importorskip("PIL")
    import io

    from PIL import Image

    big = io.BytesIO()
    Image.new("RGB", (4000, 3000), "red").save(big, format="PNG")
    data, mime = llm_service.prepare_image(big.getvalue(), "image/png")
    assert mime == "image/jpeg" and max(Image.open(io.BytesIO(data)).size) == llm_service._MAX_IMAGE_SIDE
    assert llm_service.prepare_image(b"pas une image", "image/jpeg") == (b"pas une image", "image/jpeg")
