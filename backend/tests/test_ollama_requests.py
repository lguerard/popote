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
