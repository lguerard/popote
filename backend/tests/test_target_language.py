"""Langue de rédaction des recettes créées (users.language du compte).

L'IA rédige une nouvelle recette dans la langue du compte ; le champ
"language" reste la langue d'origine de la source. Aucun appel réel au
modèle : on vérifie les consignes envoyées.
"""

import asyncio
import json
import sys
import types
import uuid

import httpx
import pytest

from app.services import llm_service

FR_RULE = 'Tout rédiger en français (traduire si besoin). "language" = langue d\'origine du texte ("fr", "en"…).'
EN_RULE = "Tout rédiger en ANGLAIS (traduire si besoin, même si le texte est en français)"


# ---------------------------------------------------------------------------
# Consignes
# ---------------------------------------------------------------------------

def test_french_prompts_are_the_default_and_unchanged():
    assert llm_service.system_prompt() == llm_service.SYSTEM_PROMPT
    assert llm_service.system_prompt("fr") == llm_service.SYSTEM_PROMPT
    assert llm_service.reconstruct_prompt() == llm_service.RECONSTRUCT_PROMPT
    assert llm_service.image_recipe_prompt() == llm_service.IMAGE_RECIPE_PROMPT
    assert FR_RULE in llm_service.SYSTEM_PROMPT and EN_RULE not in llm_service.SYSTEM_PROMPT
    assert '"name": "farine"' in llm_service.SYSTEM_PROMPT
    assert "Tout rédiger en français. \"language\" = langue d'origine du texte." in llm_service.RECONSTRUCT_PROMPT
    assert FR_RULE in llm_service.IMAGE_RECIPE_PROMPT
    assert "- Recopie ce qui est écrit sur la photo" in llm_service.IMAGE_RECIPE_PROMPT


@pytest.mark.parametrize("build", [
    llm_service.system_prompt, llm_service.reconstruct_prompt, llm_service.image_recipe_prompt,
])
def test_english_prompts_ask_for_english_and_keep_the_source_language(build):
    prompt = build("en")
    assert "Tout rédiger en ANGLAIS" in prompt
    assert "rédiger en français" not in prompt
    # "language" garde son sens : la langue d'origine, pas celle de la rédaction.
    assert "\"language\" = langue d'origine du texte" in prompt and "pas celle de la rédaction" in prompt
    # Exemple en anglais, catégorie toujours prise dans la liste française.
    assert '"name": "flour"' in prompt and '"name": "farine"' not in prompt
    assert "petit-déjeuner, entrée, plat, dessert" in prompt
    # Le reste des consignes ne change pas (toujours en français).
    assert "Réponds UNIQUEMENT avec un objet JSON valide" in prompt
    assert prompt.count("Format attendu") == 1 and prompt.count("Règles :") == 1


def test_english_derived_prompts_keep_their_own_parts():
    reconstruct = llm_service.reconstruct_prompt("en")
    assert reconstruct.startswith("Tu es un chef cuisinier expert")
    assert "Identifie ce plat" in reconstruct and "Ignorer publicités" not in reconstruct
    image = llm_service.image_recipe_prompt("en")
    assert image.startswith("Tu es un assistant culinaire expert chargé d'extraire UNE recette d'une photo")
    assert "Ignorer publicités" in image  # règles de l'extraction de texte reprises
    assert image.endswith('sans recette écrite : {"found": false}.\n')
    assert "Recopie (en le traduisant en anglais)" in image


@pytest.mark.parametrize("value, expected", [
    ("en", "en"), ("EN", "en"), ("en-US", "en"), ("fr", "fr"), (None, "fr"), ("", "fr"), ("de", "fr"),
])
def test_unknown_languages_fall_back_to_french(value, expected):
    assert llm_service.target_language(value) == expected
    assert llm_service.system_prompt(value) == llm_service.system_prompt(expected)


def test_image_request_carries_the_target_language():
    assert llm_service.build_image_recipe_request("aGk=")["messages"][0]["content"] == llm_service.IMAGE_RECIPE_PROMPT
    body = llm_service.build_image_recipe_request("aGk=", target_lang="en")
    assert body["messages"][0]["content"] == llm_service.image_recipe_prompt("en")


# ---------------------------------------------------------------------------
# Appels au modèle (Ollama et Claude simulés)
# ---------------------------------------------------------------------------

RECIPE = {"found": True, "title": "Soup", "description": "Simple.", "language": "fr",
          "ingredients": [{"name": "water"}], "steps": ["Heat."], "tags": ["easy"]}


def _patch_ollama(monkeypatch):
    systems = []
    real_client = httpx.AsyncClient

    def handler(request):
        systems.append(json.loads(request.content)["messages"][0]["content"])
        return httpx.Response(200, json={"message": {"content": json.dumps(RECIPE)}})

    monkeypatch.setattr(llm_service.settings, "claude_api_key", "", raising=False)
    monkeypatch.setattr(
        llm_service.httpx, "AsyncClient",
        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(handler), **kw),
    )
    return systems


def test_ollama_extraction_sends_the_account_language(monkeypatch):
    systems = _patch_ollama(monkeypatch)
    asyncio.run(llm_service.extract_recipe_with_llm("soupe"))
    data = asyncio.run(llm_service.extract_recipe_with_llm("soupe", "en"))
    assert systems == [llm_service.SYSTEM_PROMPT, llm_service.system_prompt("en")]
    assert data["language"] == "fr"  # la langue de la source, telle que renvoyée


def test_ollama_photo_sends_the_account_language(monkeypatch):
    systems = _patch_ollama(monkeypatch)
    asyncio.run(llm_service.extract_recipe_from_image(b"img", "image/png", "en"))
    assert systems == [llm_service.image_recipe_prompt("en")]


def test_reconstructed_recipe_notice_follows_the_language(monkeypatch):
    systems = _patch_ollama(monkeypatch)
    data = asyncio.run(llm_service.reconstruct_recipe_with_llm("lasagna", "en"))
    assert systems == [llm_service.reconstruct_prompt("en")]
    assert data["description"].startswith(llm_service.RECONSTRUCTED_NOTICES["en"])
    assert data["tags"][0] == "to check"


def _fake_anthropic(monkeypatch):
    calls = []

    class _Messages:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=json.dumps(RECIPE))])

    class AsyncAnthropic:
        def __init__(self, api_key):
            self.messages = _Messages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(AsyncAnthropic=AsyncAnthropic))
    monkeypatch.setattr(llm_service.settings, "claude_api_key", "sk-test")
    return calls


def test_claude_extraction_and_photo_send_the_account_language(monkeypatch):
    calls = _fake_anthropic(monkeypatch)
    asyncio.run(llm_service.extract_recipe_with_llm("soup", "en"))
    asyncio.run(llm_service.extract_recipe_from_image(b"img", "image/png", "en"))
    asyncio.run(llm_service.extract_recipe_with_llm("soupe"))
    assert [c["system"] for c in calls] == [
        llm_service.system_prompt("en"), llm_service.image_recipe_prompt("en"), llm_service.SYSTEM_PROMPT,
    ]


# ---------------------------------------------------------------------------
# extractor.extract()
# ---------------------------------------------------------------------------

def _patch_extractor(monkeypatch, llm_result, rebuilt=None):
    from app.services import extractor

    langs = []

    async def fake_llm(text, target_lang="fr"):
        langs.append(("llm", target_lang))
        return dict(llm_result)

    async def fake_reconstruct(text, target_lang="fr"):
        langs.append(("reconstruction", target_lang))
        return dict(rebuilt or {"error": "Aucune recette trouvée"})

    monkeypatch.setattr(extractor, "extract_recipe_with_llm", fake_llm)
    monkeypatch.setattr(extractor, "reconstruct_recipe_with_llm", fake_reconstruct)
    return extractor, langs


def test_extract_passes_the_language_to_the_llm(monkeypatch):
    extractor, langs = _patch_extractor(monkeypatch, {"title": "T", "ingredients": [], "steps": []})
    asyncio.run(extractor.extract("200 g de farine, 2 œufs…"))
    asyncio.run(extractor.extract("200 g de farine, 2 œufs…", target_lang="en"))
    assert langs == [("llm", "fr"), ("llm", "en")]


def test_extract_passes_the_language_to_the_reconstruction(monkeypatch):
    rebuilt = {"title": "Lasagna", "ingredients": [{"name": "pasta"}], "steps": [{"order": 1, "text": "Cook."}]}
    extractor, langs = _patch_extractor(monkeypatch, {"error": "Aucune recette trouvée"}, rebuilt)
    asyncio.run(extractor.extract("lasagna", target_lang="en"))
    assert langs == [("llm", "en"), ("reconstruction", "en")]


# ---------------------------------------------------------------------------
# api/extract.py : la langue du compte jusqu'à extract()
# ---------------------------------------------------------------------------

class _FakeRecipe:
    def __init__(self, **kwargs):
        self.id = uuid.uuid4()
        self.owner_id = None
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeDb:
    def __init__(self, recipe=None):
        self.recipe = recipe

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.recipe = obj

    def add_all(self, objs):
        pass

    async def get(self, model, recipe_id):
        return self.recipe

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, obj):
        pass


def test_submit_endpoints_pass_the_account_language(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import BackgroundTasks

    from app.api import extract as extract_api
    from app.schemas.recipe import ExtractionRequest

    user = types.SimpleNamespace(id=uuid.uuid4(), language="en")
    tasks = BackgroundTasks()
    asyncio.run(extract_api.submit_extraction(ExtractionRequest(input="lasagna"), tasks, db=_FakeDb(), user=user))
    assert tasks.tasks[0].func is extract_api._run_extraction and tasks.tasks[0].args[-1] == "en"

    class _Upload:
        content_type = "image/jpeg"

        async def read(self):
            return b"img"

    tasks = BackgroundTasks()
    asyncio.run(extract_api.submit_image_extraction(tasks, file=_Upload(), db=_FakeDb(), user=user))
    assert tasks.tasks[0].func is extract_api._run_image_extraction and tasks.tasks[0].args[-1] == "en"


def test_run_extraction_and_batch_pass_the_language_to_extract(monkeypatch):
    pytest.importorskip("fastapi")
    from app import database
    from app.api import extract as extract_api

    seen = []

    async def fake_extract(input_text, **kwargs):
        seen.append(kwargs.get("target_lang"))
        return {"title": "Lasagna"}

    async def nothing(*args, **kwargs):
        pass

    recipe = _FakeRecipe(title=None, status=None, error_msg=None, progress_message=None, source_type=None)
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _FakeDb(recipe), raising=False)
    monkeypatch.setattr(extract_api, "extract", fake_extract)
    monkeypatch.setattr(extract_api, "_record_achievement", nothing)
    monkeypatch.setattr(extract_api.sharing, "auto_share", nothing)
    from app.services import image_service
    monkeypatch.setattr(image_service, "apply_source_image", nothing)

    asyncio.run(extract_api._run_extraction(recipe.id, "lasagna", "en"))
    asyncio.run(extract_api._run_batch([(recipe.id, "https://a.example/1")], "en"))
    asyncio.run(extract_api._run_extraction(recipe.id, "lasagne"))
    assert seen == ["en", "en", "fr"]


def test_photo_import_passes_the_language_everywhere(monkeypatch):
    pytest.importorskip("fastapi")
    from tests.test_vision import _run_photo_import

    langs = []
    _run_photo_import(
        monkeypatch, vision=RuntimeError("pas de vision"), ocr_text="Lasagna " * 50,
        text_llm={"error": "Aucune recette trouvée"}, dish={"title": "Lasagna"},
        target_lang="en", langs=langs,
    )
    assert langs == [("vision", "en"), ("text-llm", "en"), ("dish", "en")]


# ---------------------------------------------------------------------------
# Filet de sécurité : le modèle n'a pas écrit dans la langue demandée
# (ex. transcription Whisper mal détectée mêlée à la légende correcte).
# ---------------------------------------------------------------------------

def _patch_translate(monkeypatch, translated):
    from app.services import translation_service

    calls = []

    async def fake_translate(**kwargs):
        calls.append(kwargs)
        return translated

    monkeypatch.setattr(translation_service, "translate_recipe_content", fake_translate)
    return calls


def test_extract_corrects_llm_output_in_the_wrong_language(monkeypatch):
    """Le modèle demandait du français, mais a écrit en anglais (entrée
    mélangée, petit modèle qui n'a pas suivi la consigne…) : le filet de
    sécurité détecte le décalage et traduit avant d'enregistrer."""
    extractor, _ = _patch_extractor(monkeypatch, {
        "title": "Hot chocolate with dark chocolate", "description": "A rich hot chocolate for two.",
        "ingredients": [{"quantity": "65", "unit": "g", "name": "dark chocolate", "notes": "", "section": ""}],
        "steps": [{
            "text": "Add the chocolate into the warm milk, then stir until melted, for about 5 minutes.",
            "section": "",
        }],
        "tags": ["easy"],
    })
    calls = _patch_translate(monkeypatch, {
        "title": "Chocolat chaud", "description": "Un chocolat chaud riche.",
        "ingredients": [{"quantity": "65", "unit": "g", "name": "chocolat noir", "notes": "", "section": ""}],
        "steps": [{"text": "Faites fondre le chocolat dans le lait chaud.", "section": ""}],
        "tags": ["facile"],
    })
    data = asyncio.run(extractor.extract("transcription anglaise confuse…", target_lang="fr"))
    assert len(calls) == 1
    assert calls[0]["source_lang"] == "en" and calls[0]["target_lang"] == "fr"
    assert data["title"] == "Chocolat chaud"
    assert data["ingredients"][0]["name"] == "chocolat noir"


def test_extract_does_not_retranslate_output_already_in_the_right_language(monkeypatch):
    extractor, _ = _patch_extractor(monkeypatch, {
        "title": "Chocolat chaud", "description": "Un chocolat chaud riche.",
        "ingredients": [{"quantity": "65", "unit": "g", "name": "chocolat noir", "notes": "", "section": ""}],
        "steps": [{"text": "Faites fondre le chocolat dans le lait chaud.", "section": ""}],
        "tags": ["facile"],
    })
    calls = _patch_translate(monkeypatch, {"title": "ne devrait jamais être appelé"})
    data = asyncio.run(extractor.extract("légende en français…", target_lang="fr"))
    assert calls == []
    assert data["title"] == "Chocolat chaud"
