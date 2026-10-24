"""Forme des requêtes envoyées à Ollama, partagée par toutes les tâches IA."""

import asyncio
import json

import httpx

from app.services import llm_service


def _patch_http(monkeypatch, module, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        module.httpx, "AsyncClient",
        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(handler), **kw),
    )


def _assert_common_options(body):
    # Jamais de réflexion, et toujours la MÊME fenêtre de contexte : une
    # autre valeur ferait recharger le modèle par Ollama.
    assert body["think"] is False
    assert body["stream"] is False
    assert body["options"]["num_ctx"] == llm_service.settings.ollama_num_ctx
    assert body["options"]["num_predict"] > 0


def test_recipe_request_uses_shared_options():
    body = llm_service.build_ollama_request("recette")
    _assert_common_options(body)
    assert body["model"] == llm_service.settings.ollama_model
    assert body["options"]["num_predict"] == llm_service.NUM_PREDICT_RECIPE


def test_dish_description_request_uses_shared_options(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "claude_api_key", "")
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "A bowl of soup."}})

    _patch_http(monkeypatch, llm_service, handler)
    text = asyncio.run(llm_service.describe_dish_for_image("Soupe", None, "soupe", [], []))
    assert text == "A bowl of soup."
    _assert_common_options(bodies[0])
    assert bodies[0]["options"]["num_predict"] > 120
    assert "format" not in bodies[0]


def test_unrelated_400_does_not_disable_the_schema(monkeypatch):
    monkeypatch.setattr(llm_service, "_schema_supported", True)
    monkeypatch.setattr(llm_service.settings, "claude_api_key", "")
    formats = []

    def handler(request):
        formats.append(json.loads(request.content)["format"])
        return httpx.Response(400, json={"error": "input length exceeds the context length"})

    _patch_http(monkeypatch, llm_service, handler)
    try:
        asyncio.run(llm_service._chat_ollama("recette"))
    except RuntimeError as e:
        assert "context length" in str(e)
    else:
        raise AssertionError("un 400 doit remonter")
    assert len(formats) == 1 and isinstance(formats[0], dict)
    assert llm_service._schema_supported is True


def test_schema_stays_enabled_when_the_json_fallback_fails_too(monkeypatch):
    monkeypatch.setattr(llm_service, "_schema_supported", True)

    def handler(request):
        return httpx.Response(400, json={"error": "invalid format: bad image format"})

    _patch_http(monkeypatch, llm_service, handler)
    try:
        asyncio.run(llm_service._chat_ollama("recette"))
    except RuntimeError:
        pass
    assert llm_service._schema_supported is True


def test_old_ollama_refusing_the_schema_switches_to_json(monkeypatch):
    monkeypatch.setattr(llm_service, "_schema_supported", True)
    content = json.dumps({"found": True, "title": "Pâtes", "ingredients": ["200 g de pâtes"], "steps": ["Cuire."]})

    def handler(request):
        if isinstance(json.loads(request.content)["format"], dict):
            return httpx.Response(400, json={
                "error": "json: cannot unmarshal object into Go struct field ChatRequest.format of type string",
            })
        return httpx.Response(200, json={"message": {"content": content}})

    _patch_http(monkeypatch, llm_service, handler)
    assert asyncio.run(llm_service._chat_ollama("recette"))["title"] == "Pâtes"
    assert llm_service._schema_supported is False


def test_nutrition_request_has_a_schema_and_shared_options(monkeypatch):
    from app.services import nutrition_service

    monkeypatch.setattr(nutrition_service.settings, "claude_api_key", "")
    monkeypatch.setattr(llm_service, "_schema_supported", True)
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": (
            'Voici : {"calories": "450 kcal", "proteins": 25.55, "carbs": 55, "fat": null, '
            '"fiber": -1, "sodium": 3}'
        )}})

    _patch_http(monkeypatch, llm_service, handler)
    data = asyncio.run(nutrition_service.analyze_nutrition("Pâtes", [{"name": "pâtes", "quantity": "200", "unit": "g"}], 2))
    assert data == {"calories": 450.0, "proteins": 25.6, "carbs": 55.0, "fat": None, "fiber": None}
    _assert_common_options(bodies[0])
    schema = bodies[0]["format"]
    assert set(schema["required"]) == set(nutrition_service.NUTRITION_FIELDS)
    assert all(prop["type"] == "number" for prop in schema["properties"].values())


def test_nutrition_parse_reads_fenced_json_and_rejects_garbage():
    from app.services import nutrition_service

    fenced = '```json\n{"calories": 300, "proteins": 10, "carbs": 40, "fat": 8, "fiber": 3}\n```'
    assert nutrition_service._parse(fenced)["calories"] == 300.0
    try:
        nutrition_service._parse("désolé")
    except ValueError as e:
        assert "illisible" in str(e)
    else:
        raise AssertionError("une réponse illisible doit lever")
