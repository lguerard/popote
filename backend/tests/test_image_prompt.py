import asyncio
import json

import httpx

from app.services import image_service, llm_service


def test_prompt_puts_visual_description_before_style():
    prompt = image_service.build_prompt(
        "A glass cup of dark chocolate mousse dusted with cocoa powder.",
        "Mousse au chocolat", "dessert", [],
    )
    assert prompt.startswith("A glass cup of dark chocolate mousse dusted with cocoa powder. ")
    assert "food photography" in prompt


def test_fallback_prompt_is_short_and_in_english_structure():
    prompt = image_service.build_prompt(
        None, "Poulet basquaise", "plat",
        [{"name": n} for n in ["poulet", "poivrons", "tomates", "oignons", "ail", "piment"]],
    )
    assert prompt.startswith("Poulet basquaise, a main course with poulet, poivrons, tomates, oignons, served")
    assert "piment" not in prompt


def test_clean_image_description():
    raw = 'Here is the prompt: "A rustic bowl of creamy pumpkin soup, swirled with cream."\n'
    assert llm_service.clean_image_description(raw) == (
        "A rustic bowl of creamy pumpkin soup, swirled with cream."
    )
    long = " ".join(["word"] * 80)
    assert len(llm_service.clean_image_description(long).split()) == 45


def test_image_description_input_uses_last_steps_for_plating():
    text = llm_service.image_description_input(
        "Tiramisu", None, "dessert",
        [{"name": "mascarpone"}, {"name": "café"}],
        [{"order": 1, "text": "Battre les œufs."}, {"order": 2, "text": "Tremper les biscuits."},
         {"order": 3, "text": "Monter en couches."}, {"order": 4, "text": "Saupoudrer de cacao et servir en verrines."}],
    )
    assert "Ingrédients : mascarpone, café" in text
    assert "servir en verrines" in text
    assert "Battre les œufs" not in text


def test_generation_frees_the_gpu_then_sends_the_llm_prompt(monkeypatch):
    calls = []

    async def fake_describe(*args):
        calls.append("describe")
        return "A bowl of ratatouille topped with basil"

    async def fake_unload():
        calls.append("unload")

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append("imagegen")
        body = json.loads(request.content)
        assert body["prompt"].startswith("A bowl of ratatouille topped with basil. ")
        assert body["negative_prompt"]
        return httpx.Response(200, content=b"PNG")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(llm_service, "describe_dish_for_image", fake_describe)
    monkeypatch.setattr(llm_service, "unload_ollama_model", fake_unload)
    monkeypatch.setattr(
        image_service.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    image = asyncio.run(image_service.generate_recipe_image("Ratatouille", None, "plat", [], []))
    assert image == b"PNG"
    assert calls == ["describe", "unload", "imagegen"]


def test_generation_falls_back_when_the_llm_is_down(monkeypatch):
    async def failing_describe(*args):
        raise httpx.ConnectError("ollama down")

    async def fake_unload():
        pass

    prompts = []

    def handler(request):
        prompts.append(json.loads(request.content)["prompt"])
        return httpx.Response(200, content=b"PNG")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(llm_service, "describe_dish_for_image", failing_describe)
    monkeypatch.setattr(llm_service, "unload_ollama_model", fake_unload)
    monkeypatch.setattr(
        image_service.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    asyncio.run(image_service.generate_recipe_image("Crêpes", None, "dessert", [{"name": "farine"}]))
    assert prompts[0].startswith("Crêpes, a dessert with farine, served on a plate")
