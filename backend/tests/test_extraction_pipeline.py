import asyncio
import json

import httpx
import pytest

from app.services import llm_service, video_service, web_scraper
from app.services.llm_service import build_ollama_request, parse_llm_content


# ---------------------------------------------------------------------------
# Réponses du LLM
# ---------------------------------------------------------------------------

def test_parse_llm_content_not_found():
    assert parse_llm_content('{"found": false}') == {"error": "Aucune recette trouvée"}
    assert parse_llm_content('{"error": "Aucune recette trouvée"}') == {"error": "Aucune recette trouvée"}
    empty = {"found": True, "title": "x", "ingredients": [], "steps": []}
    assert parse_llm_content(json.dumps(empty)) == {"error": "Aucune recette trouvée"}


def test_parse_llm_content_normalizes_everything():
    raw = {
        "found": True,
        "title": " Mousse au chocolat ",
        "description": "",
        "language": "FR",
        "category": "Dessert gourmand",
        "servings": "4 personnes",
        "prep_time": "15 minutes",
        "cook_time": 0,
        "ingredients": [
            {"quantity": "", "unit": "", "name": "200 g de chocolat noir", "notes": ""},
            {"quantity": "4", "unit": "", "name": "œufs", "notes": "à température ambiante"},
            "1 pincée de sel",
            {"quantity": "4", "unit": "", "name": "œufs", "notes": ""},
            {"quantity": "", "unit": "", "name": "", "notes": ""},
        ],
        "steps": ["1. Faire fondre le chocolat.", {"order": 7, "text": "Étape 2 : Monter les blancs."}, ""],
        "tags": ["Facile", "facile", "Sans cuisson"],
        "invented_field": ["x"],
    }
    data = parse_llm_content("Voici la recette :\n" + json.dumps(raw, ensure_ascii=False))
    assert data["title"] == "Mousse au chocolat"
    assert data["description"] is None
    assert data["language"] == "fr"
    assert data["category"] == "dessert"
    assert (data["servings"], data["prep_time"], data["cook_time"]) == (4, 15, None)
    assert data["ingredients"] == [
        {"quantity": "200", "unit": "g", "name": "chocolat noir", "notes": None},
        {"quantity": "4", "unit": None, "name": "œufs", "notes": "à température ambiante"},
        {"quantity": "1", "unit": "pincée", "name": "sel", "notes": None},
    ]
    assert data["steps"] == [
        {"order": 1, "text": "Faire fondre le chocolat."},
        {"order": 2, "text": "Monter les blancs."},
    ]
    assert data["tags"] == ["facile", "sans cuisson"]


def test_parse_llm_content_unreadable_raises_clear_error():
    with pytest.raises(ValueError, match="illisible"):
        parse_llm_content("désolé, je ne peux pas")


def test_build_ollama_request():
    payload = build_ollama_request("texte" * 5000, "qwen2.5:7b")
    assert payload["model"] == "qwen2.5:7b"
    assert payload["format"]["properties"]["category"]["enum"][0] == "petit-déjeuner"
    assert payload["options"]["temperature"] == 0
    assert payload["options"]["num_ctx"] >= 8192
    assert len(payload["messages"][1]["content"]) < 12100
    assert build_ollama_request("x", use_schema=False)["format"] == "json"


def _patch_ollama(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        llm_service.httpx, "AsyncClient",
        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(handler), **kw),
    )


def test_extract_ollama_falls_back_when_schema_is_refused(monkeypatch):
    monkeypatch.setattr(llm_service, "_schema_supported", True)
    formats = []
    content = json.dumps({"found": True, "title": "Pâtes", "ingredients": ["200 g de pâtes"], "steps": ["Cuire."]})

    def handler(request):
        fmt = json.loads(request.content)["format"]
        formats.append(fmt)
        if isinstance(fmt, dict):
            return httpx.Response(400, json={"error": "invalid format"})
        return httpx.Response(200, json={"message": {"content": content}})

    _patch_ollama(monkeypatch, handler)
    data = asyncio.run(llm_service._extract_ollama("recette"))
    assert data["title"] == "Pâtes"
    assert isinstance(formats[0], dict) and formats[1] == "json"
    assert llm_service._schema_supported is False


def test_extract_ollama_timeout_has_a_message(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("", request=request)

    _patch_ollama(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="n'a pas répondu"):
        asyncio.run(llm_service._extract_ollama("recette"))


# ---------------------------------------------------------------------------
# Pages web
# ---------------------------------------------------------------------------

def _html(jsonld=None, body="", og_image=None):
    head = f'<meta property="og:image" content="{og_image}">' if og_image else ""
    if jsonld:
        head += f'<script type="application/ld+json">{json.dumps(jsonld)}</script>'
    return f"<html><head>{head}</head><body>{body}</body></html>"


RECIPE = {
    "@type": "Recipe",
    "name": "Crêpes",
    "image": "https://example.com/crepes.jpg",
    "recipeIngredient": ["250 g de farine", "4 œufs", "50 cl de lait"],
    "recipeInstructions": ["Mélanger la farine et les œufs.", "Ajouter le lait et laisser reposer.",
                           "Cuire les crêpes dans la poêle."],
}


def test_analyze_html_french_jsonld_is_used_without_llm():
    result = web_scraper._analyze_html(_html(RECIPE))
    assert result.structured_recipe["title"] == "Crêpes"
    assert result.thumbnail == "https://example.com/crepes.jpg"
    assert "thumbnail_url" not in result.structured_recipe


def test_analyze_html_prefers_og_image():
    result = web_scraper._analyze_html(_html(RECIPE, og_image="https://example.com/og.jpg"))
    assert result.thumbnail == "https://example.com/og.jpg"


def test_analyze_html_english_jsonld_goes_to_llm_as_compact_text():
    english = dict(RECIPE, name="Pancakes", recipeIngredient=["1 cup of flour", "2 eggs", "1 cup of milk"],
                   recipeInstructions=["Mix the flour and the eggs.", "Add the milk to the batter.",
                                       "Cook them in the pan until golden."])
    result = web_scraper._analyze_html(_html(english, body="<p>" + "blabla " * 500 + "</p>"))
    assert result.structured_recipe is None
    assert result.text.startswith("Titre : Pancakes") and "blabla" not in result.text


def test_analyze_html_incomplete_jsonld_falls_back_to_page_text():
    partial = dict(RECIPE, recipeInstructions=[])
    result = web_scraper._analyze_html(_html(partial, body="<article>Mélanger 250 g de farine.</article>"))
    assert result.structured_recipe is None
    assert "Mélanger 250 g de farine" in result.text


def _run_scrape(monkeypatch, static_html, browser_html=None, browser_error=None):
    calls = []

    async def fake_static(url):
        return static_html

    async def fake_browser(url):
        calls.append(url)
        if browser_error:
            raise browser_error
        return browser_html

    monkeypatch.setattr(web_scraper, "_fetch_static", fake_static)
    monkeypatch.setattr(web_scraper, "_fetch_with_browser", fake_browser)
    return asyncio.run(web_scraper.scrape_url("https://example.com/r")), calls


def test_scrape_skips_browser_when_static_html_has_the_recipe(monkeypatch):
    result, calls = _run_scrape(monkeypatch, _html(RECIPE))
    assert result.structured_recipe and calls == []


def test_scrape_uses_browser_for_javascript_pages(monkeypatch):
    result, calls = _run_scrape(monkeypatch, _html(body="<div id='app'></div>"), _html(RECIPE))
    assert result.structured_recipe and len(calls) == 1


def test_scrape_keeps_static_html_if_browser_fails(monkeypatch):
    static = _html(body="<article>" + "Un long texte sans recette. " * 50 + "</article>")
    result, _ = _run_scrape(monkeypatch, static, browser_error=RuntimeError("boom"))
    assert "Un long texte" in result.text


def test_fetch_static_rejects_bot_walls(monkeypatch):
    real_client = httpx.AsyncClient
    pages = iter([
        httpx.Response(200, headers={"content-type": "text/html"}, text="<title>Just a moment...</title>"),
        httpx.Response(403, headers={"content-type": "text/html"}, text="nope"),
        httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="<p>ok</p>"),
    ])
    monkeypatch.setattr(
        web_scraper.httpx, "AsyncClient",
        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(lambda r: next(pages)), **kw),
    )
    results = [asyncio.run(web_scraper._fetch_static("https://example.com")) for _ in range(3)]
    assert results == [None, None, "<p>ok</p>"]


# ---------------------------------------------------------------------------
# Vidéos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("info, expected", [
    ({"subtitles": {"en": [], "fr": []}}, ("fr", False)),
    ({"subtitles": {"live_chat": [], "de": []}}, ("de", False)),
    ({"automatic_captions": {"fr": [], "en": [], "it-orig": []}}, ("it-orig", True)),
    ({"language": "es", "automatic_captions": {"fr": [], "es": []}}, ("es", True)),
    ({}, None),
])
def test_pick_subtitle_track(info, expected):
    assert video_service._pick_subtitle_track(info) == expected


CAPTION = """Cookies 🍪
- 125g de margarine
- 100g de sucre
- 200g de farine
Préchauffez le four, mélangez tout, formez des boules et enfournez 10 min."""


def _run_video(monkeypatch, info, subtitles=""):
    calls = []
    monkeypatch.setattr(video_service, "_fetch_info", lambda url: info)
    monkeypatch.setattr(video_service, "_fetch_subtitles", lambda url, i: calls.append("subs") or subtitles)
    monkeypatch.setattr(
        video_service, "_download_audio_and_transcribe", lambda url: calls.append("whisper") or "transcription",
    )
    text, thumbnail = asyncio.run(video_service.video_to_text("https://instagram.com/reel/x"))
    return text, thumbnail, calls


def test_video_with_full_recipe_in_caption_skips_download(monkeypatch):
    text, thumbnail, calls = _run_video(monkeypatch, {"title": "Cookies", "description": CAPTION, "thumbnail": "t.jpg"})
    assert calls == [] and "125g de margarine" in text and thumbnail == "t.jpg"


def test_video_prefers_subtitles_over_whisper(monkeypatch):
    text, _, calls = _run_video(monkeypatch, {"description": "Abonnez-vous !"}, subtitles="on mélange la farine")
    assert calls == ["subs"] and "on mélange la farine" in text and "Abonnez-vous" in text


def test_video_falls_back_to_whisper(monkeypatch):
    text, _, calls = _run_video(monkeypatch, {"description": ""})
    assert calls == ["subs", "whisper"] and "transcription" in text


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _run_extract(monkeypatch, source, scrape_result=None, llm_result=None):
    from app.services import extractor

    llm_calls = []

    async def fake_scrape(url):
        return scrape_result

    async def fake_llm(text):
        llm_calls.append(text)
        return dict(llm_result or {})

    monkeypatch.setattr(extractor, "scrape_url", fake_scrape)
    monkeypatch.setattr(extractor, "extract_recipe_with_llm", fake_llm)
    return asyncio.run(extractor.extract(source)), llm_calls


def test_extract_web_structured_recipe_skips_llm(monkeypatch):
    page = web_scraper._analyze_html(_html(RECIPE))
    data, llm_calls = _run_extract(monkeypatch, "https://example.com/crepes", scrape_result=page)
    assert llm_calls == []
    assert data["title"] == "Crêpes" and data["source_type"].value == "web"
    assert data["thumbnail_url"] == "https://example.com/crepes.jpg"


def test_extract_web_page_without_structured_data_uses_llm(monkeypatch):
    page = web_scraper.ScrapeResult("Mélanger 200 g de farine…", None)
    data, llm_calls = _run_extract(monkeypatch, "https://example.com/blog", page, {"title": "Blog"})
    assert llm_calls == ["Mélanger 200 g de farine…"] and data["source_url"] == "https://example.com/blog"


def test_extract_text_and_errors(monkeypatch):
    data, llm_calls = _run_extract(monkeypatch, "200 g de farine, 2 œufs…", llm_result={"title": "T"})
    assert llm_calls and data["source_url"] is None
    with pytest.raises(ValueError, match="Aucune recette"):
        _run_extract(monkeypatch, "bonjour", llm_result={"error": "Aucune recette trouvée"})
    with pytest.raises(ValueError, match="Aucun contenu"):
        _run_extract(monkeypatch, "https://example.com/vide", web_scraper.ScrapeResult("  ", None))


# ---------------------------------------------------------------------------
# Texte de partage contenant une URL, texte incrusté des vidéos
# ---------------------------------------------------------------------------

from app.services.extractor import resolve_input  # noqa: E402
from app.services.video_service import merge_ocr_lines  # noqa: E402


@pytest.mark.parametrize("shared, expected", [
    ("https://www.instagram.com/reel/abc/", "https://www.instagram.com/reel/abc/"),
    ("Regarde cette recette ! https://www.instagram.com/reel/abc/?igsh=xyz",
     "https://www.instagram.com/reel/abc/?igsh=xyz"),
    ("Cookies vegan (https://www.planetevegan.com/recettes/cookies-vegan/).",
     "https://www.planetevegan.com/recettes/cookies-vegan/"),
    ("Pas de lien ici", "Pas de lien ici"),
])
def test_resolve_input_extracts_url_from_share_text(shared, expected):
    assert resolve_input(shared) == expected


def test_resolve_input_keeps_a_pasted_recipe_that_cites_its_source():
    recipe = (
        "Ingrédients : 200 g de farine, 100 g de sucre, 2 œufs, 50 g de beurre.\n"
        "Préchauffer le four. Mélanger la farine et le sucre, ajouter les œufs, "
        "verser dans le moule et cuire 20 minutes.\nSource : https://exemple.fr/gateau"
    )
    assert resolve_input(recipe) == recipe.strip()


def test_merge_ocr_lines_dedupes_frames_and_drops_noise():
    frames = [
        "200 g de farine\n|| ~~",
        "200 g de farine\n2 oeufs",
        "2 œufs\nMélanger",
        "Mélanger le tout",
        "",
    ]
    assert merge_ocr_lines(frames).splitlines() == [
        "200 g de farine", "2 oeufs", "Mélanger le tout",
    ]
