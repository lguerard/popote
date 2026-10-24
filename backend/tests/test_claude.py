"""Appels Claude : un seul réglage de modèle, pas de paramètres d'échantillonnage."""

import asyncio
import json
import sys
import types

from app.services import llm_service, nutrition_service


class _Block:
    def __init__(self, type, text=""):
        self.type, self.text = type, text


def _fake_anthropic(monkeypatch, answer):
    calls = []

    class _Messages:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return types.SimpleNamespace(content=[_Block("thinking"), _Block("text", answer)])

    class AsyncAnthropic:
        def __init__(self, api_key):
            assert api_key == "sk-test"
            self.messages = _Messages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(AsyncAnthropic=AsyncAnthropic))
    monkeypatch.setattr(llm_service.settings, "claude_api_key", "sk-test")
    return calls


def _no_sampling(params):
    assert not {"temperature", "top_p", "top_k"} & set(params)


def test_defaults():
    assert llm_service.settings.claude_model == "claude-sonnet-5-5"
    assert llm_service.settings.claude_fast_model == "claude-haiku-5-5"


def test_recipe_extraction_uses_claude_model_and_skips_thinking_blocks(monkeypatch):
    recipe = {"found": True, "title": "Soupe", "ingredients": ["1 l d'eau"], "steps": ["Chauffer."]}
    calls = _fake_anthropic(monkeypatch, json.dumps(recipe))
    monkeypatch.setattr(llm_service.settings, "claude_model", "claude-test")
    data = asyncio.run(llm_service.extract_recipe_with_llm("soupe"))
    assert data["title"] == "Soupe"
    assert calls[0]["model"] == "claude-test" and calls[0]["system"] == llm_service.SYSTEM_PROMPT
    _no_sampling(calls[0])


def test_photo_goes_to_claude_with_an_image_block(monkeypatch):
    recipe = {"found": True, "title": "Tarte", "ingredients": ["3 pommes"], "steps": ["Cuire."]}
    calls = _fake_anthropic(monkeypatch, json.dumps(recipe))
    data = asyncio.run(llm_service.extract_recipe_from_image(b"img", "image/png"))
    assert data["title"] == "Tarte"
    blocks = calls[0]["messages"][0]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["media_type"] == "image/png"
    assert calls[0]["model"] == llm_service.settings.claude_model
    _no_sampling(calls[0])


def test_short_tasks_use_the_fast_model(monkeypatch):
    calls = _fake_anthropic(monkeypatch, '{"calories": 300, "proteins": 10, "carbs": 40, "fat": 8, "fiber": 3}')
    data = asyncio.run(nutrition_service.analyze_nutrition("Pâtes", [{"name": "pâtes"}], 2))
    assert data["calories"] == 300.0
    calls_desc = _fake_anthropic(monkeypatch, "A plate of pasta.")
    assert asyncio.run(llm_service.describe_dish_for_image("Pâtes", None, "plat", [], [])) == "A plate of pasta."
    for call in calls + calls_desc:
        assert call["model"] == llm_service.settings.claude_fast_model
        _no_sampling(call)
