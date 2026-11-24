"""Recette lue telle quelle sur un site (données structurées) dans l'autre
langue que celle du compte : traduite avant d'être enregistrée.

Aucun appel réel : le site est simulé, le modèle aussi (Ollama via
httpx.MockTransport). La traduction passe par le vrai
translation_service.translate_recipe_content : consignes, fusion,
quantités et ordre gardés.
"""

import asyncio
import json

import pytest

from app.services import recipe_parsing, translation_service as ts, web_scraper
from test_assistant import fake_ollama
from test_extraction_pipeline import _html, _run_extract

# Tel que le lit recipe_parsing.jsonld_to_recipe : unités déjà ramenées à
# leur forme canonique (« cups » → « tasse »), le reste en anglais.
ENGLISH_NODE = {
    "@type": "Recipe",
    "name": "Banana bread",
    "description": "The easiest banana bread.",
    "image": "https://blog.example.com/banana.jpg",
    "recipeIngredient": ["2 cups of flour", "3 ripe bananas", "1 tablespoon of baking soda"],
    "recipeInstructions": [
        "Preheat the oven to 350°F and grease the pan.",
        "Mash the bananas with a fork and add the flour.",
        "Pour the batter into the pan and bake for 60 minutes until golden.",
    ],
}
ENGLISH_RECIPE = recipe_parsing.jsonld_to_recipe(ENGLISH_NODE)
ENGLISH_RECIPE.pop("thumbnail_url")  # retirée par web_scraper._analyze_html

FRENCH_REPLY = {
    "title": "Pain à la banane",
    "description": "Le pain à la banane le plus simple.",
    "ingredients": [
        {"unit": "tasse", "name": "farine", "notes": "", "section": ""},
        {"unit": "", "name": "bananes mûres", "notes": "", "section": ""},
        {"unit": "c. à s.", "name": "bicarbonate de soude", "notes": "", "section": ""},
    ],
    "steps": [
        {"text": "Préchauffer le four à 350°F et graisser le moule.", "section": ""},
        {"text": "Écraser les bananes à la fourchette et ajouter la farine.", "section": ""},
        {"text": "Verser la pâte dans le moule et cuire 60 minutes jusqu'à ce qu'il soit doré.", "section": ""},
    ],
    "tags": [],
}

FRENCH_NODE = {
    "@type": "Recipe",
    "name": "Crêpes",
    "description": "Les crêpes de la Chandeleur.",
    "image": "https://exemple.fr/crepes.jpg",
    "keywords": "facile, chandeleur",
    "recipeIngredient": ["250 g de farine", "4 œufs", "50 cl de lait"],
    "recipeInstructions": ["Mélanger la farine et les œufs.", "Ajouter le lait et laisser reposer.",
                           "Cuire les crêpes dans la poêle."],
}


def ollama_json(payload) -> bytes:
    return json.dumps({"message": {"role": "assistant", "content": json.dumps(payload)}, "done": True}).encode()


def english_reply(recipe: dict) -> dict:
    """Réponse simulée du modèle pour une recette française → anglais."""
    return {
        "title": "Pancakes",
        "description": "Pancakes for Candlemas.",
        "ingredients": [{"unit": i.get("unit") or "", "name": f"en:{i['name']}", "notes": "", "section": ""}
                        for i in recipe["ingredients"]],
        "steps": [{"text": f"en:{s['text']}", "section": ""} for s in recipe["steps"]],
        "tags": [f"en:{t}" for t in recipe["tags"]],
    }


def _video(monkeypatch, caption: str):
    from app.services import extractor

    async def video(url, progress):
        return caption, "https://thumb/video.jpg"

    monkeypatch.setattr(extractor, "video_to_text", video)


# ---------------------------------------------------------------------------
# Consignes dans les deux sens
# ---------------------------------------------------------------------------

def test_french_to_english_prompt_is_the_historical_one():
    assert ts.translation_prompt() == ts.TRANSLATION_PROMPT == ts.translation_prompt("fr", "en")
    assert "from French into natural, idiomatic English" in ts.TRANSLATION_PROMPT
    assert '"c. à s." / "cuillère à soupe" → "tbsp"' in ts.TRANSLATION_PROMPT
    # L'affichage ne traduit toujours que vers l'anglais.
    assert ts.SUPPORTED_LANGUAGES == {"en"}


def test_english_to_french_prompt_reverses_units_without_converting():
    prompt = ts.translation_prompt("en", "fr")
    assert "from English into natural, idiomatic French as used in French-language cookbooks" in prompt
    assert '"tbsp" / "tablespoon" → "c. à s."' in prompt and '"cup" → "tasse"' in prompt
    assert "never convert amounts and never switch to metric" in prompt
    assert "Text that is already in French stays as it is." in prompt
    assert '"Dough" → "Pâte"' in prompt and "may stay in English" in prompt
    # Même forme de réponse et mêmes règles de structure que l'autre sens.
    assert '{"title": "...", "description": "...", "ingredients": [{"unit": "..."' in prompt
    assert "Keep EXACTLY the same number of ingredients, steps and tags" in prompt
    with pytest.raises(ValueError):
        ts.translation_prompt("fr", "fr")
    with pytest.raises(ValueError):
        ts.translation_prompt("de", "fr")


def test_translate_recipe_content_sends_the_right_direction(monkeypatch):
    bodies = fake_ollama(monkeypatch, [ollama_json(FRENCH_REPLY)])
    out = asyncio.run(ts.translate_recipe_content(
        ENGLISH_RECIPE["title"], ENGLISH_RECIPE["description"], ENGLISH_RECIPE["ingredients"],
        ENGLISH_RECIPE["steps"], ENGLISH_RECIPE["tags"], target_lang="fr",
    ))
    assert bodies[0]["messages"][0]["content"] == ts.translation_prompt("en", "fr")
    assert bodies[0]["format"] == ts.TRANSLATION_JSON_SCHEMA
    assert out["title"] == "Pain à la banane"
    with pytest.raises(ValueError):
        asyncio.run(ts.translate_recipe_content("T", None, [], [], [], target_lang="de"))


# ---------------------------------------------------------------------------
# Langue d'une recette lue sur un site (dict, pas encore une Recipe)
# ---------------------------------------------------------------------------

def test_scraped_source_language_judges_the_text_not_the_field():
    french = recipe_parsing.jsonld_to_recipe(FRENCH_NODE)
    assert ts.scraped_source_language(ENGLISH_RECIPE, "fr") == "en"
    assert ts.scraped_source_language(ENGLISH_RECIPE, "en") is None
    assert ts.scraped_source_language(french, "fr") is None
    assert ts.scraped_source_language(french, "en") == "fr"
    # Le champ "language" n'est pas consulté : seul le texte compte.
    assert ts.scraped_source_language({**ENGLISH_RECIPE, "language": "fr"}, "fr") == "en"
    # Texte trop court pour trancher : laissé tel quel, aucun appel au modèle.
    assert ts.scraped_source_language({"title": "Tiramisu", "ingredients": [{"name": "mascarpone"}],
                                       "steps": [{"text": "Monter."}]}, "en") is None
    assert ts.scraped_source_language(ENGLISH_RECIPE, "de") is None


# ---------------------------------------------------------------------------
# Lien direct vers un site
# ---------------------------------------------------------------------------

def test_english_structured_page_is_translated_for_a_french_account(monkeypatch):
    bodies = fake_ollama(monkeypatch, [ollama_json(FRENCH_REPLY)])
    page = web_scraper.ScrapeResult("Titre : Banana bread", "https://blog.example.com/og.jpg", dict(ENGLISH_RECIPE))
    data, llm_calls = _run_extract(monkeypatch, "https://blog.example.com/banana-bread", scrape_result=page,
                                   target_lang="fr")
    assert llm_calls == []  # pas d'extraction par l'IA, seulement la traduction
    assert len(bodies) == 1
    assert bodies[0]["messages"][0]["content"] == ts.translation_prompt("en", "fr")
    assert data["title"] == "Pain à la banane"
    assert data["description"] == "Le pain à la banane le plus simple."
    assert [i["name"] for i in data["ingredients"]] == ["farine", "bananes mûres", "bicarbonate de soude"]
    # Quantités, unités et ordre : ceux du site.
    assert [(i["quantity"], i["unit"]) for i in data["ingredients"]] == [(i["quantity"], i["unit"]) for i in ENGLISH_RECIPE["ingredients"]]
    assert [s["order"] for s in data["steps"]] == [1, 2, 3]
    assert data["steps"][0]["text"].startswith("Préchauffer le four à 350°F")
    assert ts.scraped_source_language(data, "fr") is None  # désormais en français
    # Métadonnées intactes : langue d'origine, durées, lien, vignette.
    assert data["language"] == "en" and data["source_url"] == "https://blog.example.com/banana-bread"
    assert data["thumbnail_url"] == "https://blog.example.com/og.jpg"


def test_french_structured_page_for_a_french_account_makes_no_call(monkeypatch):
    bodies = fake_ollama(monkeypatch, [ollama_json({})])
    page = web_scraper._analyze_html(_html(FRENCH_NODE), "https://exemple.fr/crepes")
    assert page.structured_recipe is not None
    expected = dict(page.structured_recipe)
    data, llm_calls = _run_extract(monkeypatch, "https://exemple.fr/crepes", scrape_result=page, target_lang="fr")
    assert llm_calls == [] and bodies == []
    assert data["title"] == "Crêpes" and data["ingredients"] == expected["ingredients"]
    assert data["steps"] == expected["steps"] and data["description"] == expected["description"]


def test_french_structured_page_is_translated_for_an_english_account(monkeypatch):
    """Le cas réellement atteint aujourd'hui : seules les données
    structurées françaises sont reprises telles quelles (web_scraper)."""
    page = web_scraper._analyze_html(_html(FRENCH_NODE), "https://exemple.fr/crepes")
    bodies = fake_ollama(monkeypatch, [ollama_json(english_reply(page.structured_recipe))])
    data, llm_calls = _run_extract(monkeypatch, "https://exemple.fr/crepes", scrape_result=page, target_lang="en")
    assert llm_calls == [] and len(bodies) == 1
    assert bodies[0]["messages"][0]["content"] == ts.TRANSLATION_PROMPT  # français → anglais
    assert data["title"] == "Pancakes"
    assert all(i["name"].startswith("en:") for i in data["ingredients"])
    assert all(s["text"].startswith("en:") for s in data["steps"])
    assert data["tags"] and all(t.startswith("en:") for t in data["tags"])
    assert data["language"] == "fr"


def test_failed_translation_keeps_the_published_recipe(monkeypatch):
    import httpx

    fake_ollama(monkeypatch, [httpx.Response(500, json={"error": "boom"})])
    page = web_scraper.ScrapeResult("Titre : Banana bread", None, dict(ENGLISH_RECIPE))
    data, _ = _run_extract(monkeypatch, "https://blog.example.com/banana-bread", scrape_result=page,
                           target_lang="fr")
    assert data["title"] == "Banana bread" and data["ingredients"] == ENGLISH_RECIPE["ingredients"]


def test_translation_reports_progress(monkeypatch):
    from app.services import extractor

    fake_ollama(monkeypatch, [ollama_json(FRENCH_REPLY)])
    messages = []

    async def progress(message):
        messages.append(message)

    asyncio.run(extractor._in_account_language(dict(ENGLISH_RECIPE), "fr", progress))
    assert messages == ["Traduction de la recette par l'IA…"]
    messages.clear()
    french = recipe_parsing.jsonld_to_recipe(FRENCH_NODE)
    assert asyncio.run(extractor._in_account_language(french, "fr", progress)) is french
    assert messages == []


# ---------------------------------------------------------------------------
# Vidéo dont la description renvoie à la recette sur un blog
# ---------------------------------------------------------------------------

def test_video_linking_an_english_blog_gets_a_french_recipe(monkeypatch):
    bodies = fake_ollama(monkeypatch, [ollama_json(FRENCH_REPLY)])
    _video(monkeypatch, "Titre : Mon banana bread\nLa recette complète : https://blog.example.com/banana-bread")
    data, calls = _run_extract(
        monkeypatch, "https://youtu.be/abc", target_lang="fr",
        linked=(dict(ENGLISH_RECIPE), "https://www.blog.example.com/banana-bread", "https://img"),
    )
    assert [c for c in calls if not isinstance(c, tuple)] == []  # pas d'extraction par l'IA
    assert len(bodies) == 1 and bodies[0]["messages"][0]["content"] == ts.translation_prompt("en", "fr")
    assert data["title"] == "Pain à la banane"
    assert [i["name"] for i in data["ingredients"]] == ["farine", "bananes mûres", "bicarbonate de soude"]
    assert [i["quantity"] for i in data["ingredients"]] == [i["quantity"] for i in ENGLISH_RECIPE["ingredients"]]
    # La note est ajoutée après la traduction, dans la langue du compte.
    assert data["description"] == "Recette complète publiée sur blog.example.com. Le pain à la banane le plus simple."
    assert data["source_url"] == "https://youtu.be/abc" and data["thumbnail_url"] == "https://thumb/video.jpg"


def test_video_linking_a_french_blog_makes_no_call(monkeypatch):
    bodies = fake_ollama(monkeypatch, [ollama_json({})])
    _video(monkeypatch, "Titre : Crêpes\nLa recette : https://www.exemple.fr/crepes")
    french = recipe_parsing.jsonld_to_recipe(FRENCH_NODE)
    data, calls = _run_extract(
        monkeypatch, "https://youtu.be/abc", target_lang="fr",
        linked=(dict(french), "https://www.exemple.fr/crepes", "https://img"),
    )
    assert [c for c in calls if not isinstance(c, tuple)] == [] and bodies == []
    assert data["title"] == "Crêpes" and data["ingredients"] == french["ingredients"]
    assert data["description"] == "Recette complète publiée sur exemple.fr. Les crêpes de la Chandeleur."


def test_video_linking_a_french_blog_for_an_english_account(monkeypatch):
    french = recipe_parsing.jsonld_to_recipe(FRENCH_NODE)
    bodies = fake_ollama(monkeypatch, [ollama_json(english_reply(french))])
    _video(monkeypatch, "Title: Crêpes\nRecipe: https://www.exemple.fr/crepes")
    data, _ = _run_extract(
        monkeypatch, "https://youtu.be/abc", target_lang="en",
        linked=(dict(french), "https://www.exemple.fr/crepes", "https://img"),
    )
    assert len(bodies) == 1 and bodies[0]["messages"][0]["content"] == ts.TRANSLATION_PROMPT
    assert data["description"] == "Full recipe published on exemple.fr. Pancakes for Candlemas."
    assert all(i["name"].startswith("en:") for i in data["ingredients"])
