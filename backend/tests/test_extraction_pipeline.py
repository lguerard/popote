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

def _run_extract(
    monkeypatch, source, scrape_result=None, llm_result=None, rebuilt=None, caption=("", None),
    linked=None, searched=None,
):
    from app.services import extractor

    llm_calls = []

    async def fake_caption(url):
        return caption

    async def fake_linked(text, exclude=None):
        llm_calls.append(("lien", text))
        return linked

    async def fake_search(dish):
        llm_calls.append(("recherche", dish))
        return searched

    monkeypatch.setattr(extractor.social, "post_caption", fake_caption)
    monkeypatch.setattr(extractor.recipe_finder, "linked_recipe", fake_linked)
    monkeypatch.setattr(extractor.recipe_finder, "search_recipe", fake_search)

    async def fake_scrape(url):
        if isinstance(scrape_result, Exception):
            raise scrape_result
        return scrape_result

    async def fake_llm(text):
        llm_calls.append(text)
        return dict(llm_result or {})

    async def fake_reconstruct(text):
        llm_calls.append(("reconstruction", text))
        return dict(rebuilt or {"error": "Aucune recette trouvée"})

    monkeypatch.setattr(extractor, "scrape_url", fake_scrape)
    monkeypatch.setattr(extractor, "extract_recipe_with_llm", fake_llm)
    monkeypatch.setattr(extractor, "reconstruct_recipe_with_llm", fake_reconstruct)
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
    with pytest.raises(ValueError, match="Aucune recette ni aucun plat"):
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


def test_video_survives_a_failed_transcription(monkeypatch):
    monkeypatch.setattr(video_service, "_fetch_info", lambda url: {"description": "Recette en description ?"})
    monkeypatch.setattr(video_service, "_fetch_subtitles", lambda url, i: "")

    def boom(url):
        raise ValueError("max() arg is an empty sequence")

    monkeypatch.setattr(video_service, "_download_audio_and_transcribe", boom)
    monkeypatch.setattr(video_service, "_ocr_video_text", lambda url: "200 g de farine\n2 œufs")
    text, _ = asyncio.run(video_service.video_to_text("https://instagram.com/reel/x"))
    assert "Recette en description ?" in text and "200 g de farine" in text


def test_whisper_without_any_speech_returns_empty(monkeypatch):
    class SilentModel:
        def transcribe(self, *args, **kwargs):
            raise ValueError("max() arg is an empty sequence")

    monkeypatch.setattr(video_service, "_load_whisper", lambda: (SilentModel(), False))
    assert video_service._transcribe("audio.m4a") == ""

    class BrokenModel:
        def transcribe(self, *args, **kwargs):
            raise ValueError("autre chose")

    monkeypatch.setattr(video_service, "_load_whisper", lambda: (BrokenModel(), False))
    with pytest.raises(ValueError):
        video_service._transcribe("audio.m4a")


# ---------------------------------------------------------------------------
# « Peu importe l'entrée » : replis quand la voie normale échoue
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("typed, expected", [
    ("marmiton.org/recettes/recette_x.aspx", "https://marmiton.org/recettes/recette_x.aspx"),
    ("www.cuisineaz.com", "https://www.cuisineaz.com"),
    ("Regarde www.instagram.com/reel/abc/ !", "https://www.instagram.com/reel/abc/"),
    ("youtu.be/abc?si=1", "https://youtu.be/abc?si=1"),
    ("lasagnes", "lasagnes"),
    ("tarte.tatin", "tarte.tatin"),
    ("1.5", "1.5"),
])
def test_resolve_input_accepts_links_without_https(typed, expected):
    assert resolve_input(typed) == expected


def test_dish_name_alone_gets_a_reconstructed_recipe(monkeypatch):
    rebuilt = {"title": "Lasagnes", "ingredients": [{"name": "pâtes"}], "steps": [{"order": 1, "text": "Cuire."}]}
    data, calls = _run_extract(
        monkeypatch, "lasagnes", llm_result={"error": "Aucune recette trouvée"}, rebuilt=rebuilt,
    )
    assert calls == ["lasagnes", ("reconstruction", "lasagnes"), ("recherche", "Lasagnes")]
    assert data["title"] == "Lasagnes" and data["source_type"].value == "text"


def test_unreadable_video_falls_back_to_the_page(monkeypatch):
    from app.services import extractor

    async def no_video(url, progress):
        raise RuntimeError("ERROR: [Instagram] abc: There is no video in this post")

    monkeypatch.setattr(extractor, "video_to_text", no_video)
    page = web_scraper.ScrapeResult("Tarte : 200 g de farine…", "https://img/x.jpg")
    data, calls = _run_extract(monkeypatch, "https://www.instagram.com/p/abc/", page, {"title": "Tarte"})
    assert calls == ["Tarte : 200 g de farine…"]
    assert data["source_type"].value == "video" and data["thumbnail_url"] == "https://img/x.jpg"


def test_unreachable_page_gives_a_readable_error(monkeypatch):
    from app.services import extractor

    async def no_video(url, progress):
        raise RuntimeError("ERROR: Sign in to confirm you're not a bot")

    monkeypatch.setattr(extractor, "video_to_text", no_video)
    with pytest.raises(ValueError, match="Impossible de lire ce lien .*not a bot"):
        _run_extract(monkeypatch, "https://youtu.be/x", RuntimeError("Page.goto: net::ERR\nCall log: …"))
    with pytest.raises(ValueError, match=r"Impossible de lire ce lien \(Page.goto: net::ERR\)"):
        _run_extract(monkeypatch, "https://exemple.fr/x", RuntimeError("Page.goto: net::ERR\nCall log: …"))


def test_page_metadata_is_kept_behind_a_login_wall():
    html = (
        '<html><head><meta property="og:title" content="Chef sur Instagram">'
        '<meta property="og:description" content="Tiramisu : 250 g de mascarpone, 3 œufs…"></head>'
        "<body><main>Connectez-vous pour voir cette publication.</main></body></html>"
    )
    text = web_scraper._analyze_html(html).text
    assert text.startswith("Chef sur Instagram\nTiramisu : 250 g de mascarpone")
    assert "Connectez-vous" in text


def test_image_link_is_read_by_ocr(monkeypatch):
    from app.services import ocr_service

    async def fake_static(url):
        return web_scraper.Document(b"\x89PNG...", "image/png")

    async def fake_ocr(data, mime):
        assert mime == "image/png"
        return "Crêpes\n250 g de farine"

    monkeypatch.setattr(web_scraper, "_fetch_static", fake_static)
    monkeypatch.setattr(ocr_service, "extract_text_from_image", fake_ocr)
    result = asyncio.run(web_scraper.scrape_url("https://exemple.fr/recette.png"))
    assert result.text == "Crêpes\n250 g de farine" and result.thumbnail == "https://exemple.fr/recette.png"


def test_fetch_static_returns_files_as_documents(monkeypatch):
    real_client = httpx.AsyncClient
    response = httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4")
    monkeypatch.setattr(
        web_scraper.httpx, "AsyncClient",
        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(lambda r: response), **kw),
    )
    doc = asyncio.run(web_scraper._fetch_static("https://exemple.fr/fiche.pdf"))
    assert isinstance(doc, web_scraper.Document) and doc.content_type == "application/pdf"


def test_pdf_to_text():
    pypdf = pytest.importorskip("pypdf")
    import io

    writer = pypdf.PdfWriter()
    writer.add_blank_page(100, 100)
    buffer = io.BytesIO()
    writer.write(buffer)
    assert web_scraper.pdf_to_text(buffer.getvalue()) == ""


def test_unreadable_llm_answer_is_retried_once(monkeypatch):
    answers = iter(["pas du json", json.dumps({"found": True, "title": "Soupe", "ingredients": [{"name": "eau"}], "steps": ["Chauffer."]})])
    temperatures = []

    def handler(request):
        temperatures.append(json.loads(request.content)["options"]["temperature"])
        return httpx.Response(200, json={"message": {"content": next(answers)}})

    _patch_ollama(monkeypatch, handler)
    monkeypatch.setattr(llm_service.settings, "claude_api_key", "", raising=False)
    data = asyncio.run(llm_service.extract_recipe_with_llm("soupe"))
    assert data["title"] == "Soupe" and temperatures == [0, 0.4]


def test_reconstructed_recipe_is_flagged(monkeypatch):
    content = json.dumps({"found": True, "title": "Lasagnes", "description": "Un classique.",
                          "ingredients": [{"name": "pâtes"}], "steps": ["Cuire."], "tags": ["italien"]})
    prompts = []

    def handler(request):
        prompts.append(json.loads(request.content)["messages"][0]["content"])
        return httpx.Response(200, json={"message": {"content": content}})

    _patch_ollama(monkeypatch, handler)
    monkeypatch.setattr(llm_service.settings, "claude_api_key", "", raising=False)
    data = asyncio.run(llm_service.reconstruct_recipe_with_llm("lasagnes"))
    assert prompts == [llm_service.RECONSTRUCT_PROMPT]
    assert data["description"].startswith(llm_service.RECONSTRUCTED_NOTICE)
    assert data["tags"][0] == "à vérifier"


# ---------------------------------------------------------------------------
# Légende des posts Instagram / TikTok, sans compte
# ---------------------------------------------------------------------------

from app.services import social  # noqa: E402


@pytest.mark.parametrize("url, code", [
    ("https://www.instagram.com/reel/DeT4q4AtgNE/", "DeT4q4AtgNE"),
    ("https://instagram.com/p/AbC_-1/?igsh=xyz", "AbC_-1"),
    ("https://www.instagram.com/chef.martin/reel/Xyz123/", "Xyz123"),
    ("https://www.instagram.com/reels/Q1w2/", "Q1w2"),
    ("https://www.instagram.com/chef.martin/", None),
    ("https://www.tiktok.com/@a/video/1", None),
])
def test_instagram_shortcode(url, code):
    assert social.instagram_shortcode(url) == code


EMBED_HTML = """<html><body><div class="Embed">
<img class="EmbeddedMediaImage" src="https://cdn.ig/x.jpg">
<div class="Caption"><a class="CaptionUsername" href="#">chef.martin</a><br><br>
Tiramisu express 😍<br>Ingrédients :<br>- 250 g de mascarpone<br>- 3 œufs<br>
Battre les jaunes avec le sucre.
<div class="CaptionComments"><a>Voir les 120 commentaires</a></div></div>
</div></body></html>"""


def test_parse_instagram_embed():
    caption, thumbnail = social.parse_instagram_embed(EMBED_HTML)
    assert caption.startswith("Tiramisu express")
    assert "250 g de mascarpone" in caption and "\n- 3 œufs" in caption
    assert "chef.martin" not in caption and "commentaires" not in caption
    assert thumbnail == "https://cdn.ig/x.jpg"


def test_parse_instagram_embed_from_json_data():
    html = (
        '<html><body><script>window.__additionalDataLoaded("extra", {"shortcode_media":'
        '{"edge_media_to_caption":{"edges":[{"node":{"text":"Cr\\u00eapes\\n250 g de farine"}}]}}});'
        "</script></body></html>"
    )
    caption, _ = social.parse_instagram_embed(html)
    assert caption == "Crêpes\n250 g de farine"


def test_parse_instagram_embed_without_caption():
    assert social.parse_instagram_embed("<html><body>Connectez-vous</body></html>") == ("", None)


def test_blocked_instagram_video_uses_the_caption(monkeypatch):
    from app.services import extractor

    async def login_required(url, progress):
        raise RuntimeError("ERROR: [Instagram] DeT4q4AtgNE: Requested content is not available, login required")

    monkeypatch.setattr(extractor, "video_to_text", login_required)
    data, calls = _run_extract(
        monkeypatch, "https://www.instagram.com/reel/DeT4q4AtgNE/",
        scrape_result=RuntimeError("ne doit pas être appelé"),
        llm_result={"title": "Tiramisu"}, caption=("Tiramisu : 250 g de mascarpone…", "https://cdn.ig/x.jpg"),
    )
    assert calls == ["Légende de la publication :\nTiramisu : 250 g de mascarpone…"]
    assert data["thumbnail_url"] == "https://cdn.ig/x.jpg" and data["source_type"].value == "video"


def test_video_without_recipe_gets_the_full_caption(monkeypatch):
    from app.services import extractor

    async def music_only(url, progress):
        return "Titre de la vidéo : Video by chef", "https://thumb"

    monkeypatch.setattr(extractor, "video_to_text", music_only)
    data, calls = _run_extract(
        monkeypatch, "https://www.instagram.com/reel/Abc/", llm_result={"title": "T"},
        caption=("Gâteau : 200 g de farine, 3 œufs…", None),
    )
    assert calls == ["Titre de la vidéo : Video by chef\n\nLégende de la publication :\nGâteau : 200 g de farine, 3 œufs…"]
    assert data["thumbnail_url"] == "https://thumb"


def test_tiktok_caption_from_oembed(monkeypatch):
    real_client = httpx.AsyncClient

    def handler(request):
        assert request.url.host == "www.tiktok.com" and request.url.path == "/oembed"
        return httpx.Response(200, json={"title": "Pâtes <b>crémeuses</b> #recette", "thumbnail_url": "https://t/x.jpg"})

    monkeypatch.setattr(
        social.httpx, "AsyncClient",
        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(handler), **kw),
    )
    assert asyncio.run(social.post_caption("https://www.tiktok.com/@chef/video/123")) == (
        "Pâtes crémeuses #recette", "https://t/x.jpg",
    )


def test_post_caption_never_raises(monkeypatch):
    real_client = httpx.AsyncClient

    def boom(request):
        raise httpx.ConnectError("réseau coupé")

    monkeypatch.setattr(
        social.httpx, "AsyncClient",
        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(boom), **kw),
    )
    assert asyncio.run(social.post_caption("https://www.instagram.com/p/Abc/")) == ("", None)
    assert asyncio.run(social.post_caption("https://exemple.fr/x")) == ("", None)


def test_ydl_options_use_a_copy_of_the_cookies(tmp_path, monkeypatch):
    cookies = tmp_path / "cookies.txt"
    monkeypatch.setattr(video_service.settings, "ytdlp_cookies_file", str(cookies))
    assert "cookiefile" not in video_service._ydl_base()  # absent : ignoré
    cookies.write_text("# Netscape HTTP Cookie File\n")
    opts = video_service._ydl_base()
    assert opts["cookiefile"] != str(cookies)
    assert open(opts["cookiefile"]).read() == "# Netscape HTTP Cookie File\n"
    assert opts["retries"] >= 1


# ---------------------------------------------------------------------------
# Trouver la vraie recette : lien de la description, recherche web
# ---------------------------------------------------------------------------

from app.services import recipe_finder  # noqa: E402

PUBLISHED = {
    "title": "Tiramisu", "description": "Le classique.", "ingredients": [{"name": "mascarpone"}],
    "steps": [{"order": 1, "text": "Monter."}], "language": "fr",
}


def test_candidate_links_prefer_the_announced_recipe():
    text = (
        "Mon matériel : https://amzn.to/xyz\n"
        "Suivez-moi https://www.instagram.com/chef\n"
        "Mon livre https://editions.fr/livre\n"
        "👉 Recette complète : https://www.chef-martin.fr/tiramisu/.\n"
        "Aussi sur www.chef-martin.fr/blog\n"
        "Doublon https://www.chef-martin.fr/tiramisu/"
    )
    assert recipe_finder.candidate_links(text) == [
        "https://www.chef-martin.fr/tiramisu/",
        "https://www.chef-martin.fr/blog",
        "https://editions.fr/livre",
    ]
    assert recipe_finder.candidate_links("https://youtu.be/x et https://t.co/a") == []
    assert recipe_finder.candidate_links("https://site.fr/r", exclude="https://site.fr/r") == []


def test_video_with_recipe_link_uses_the_published_recipe(monkeypatch):
    from app.services import extractor

    async def video(url, progress):
        return "Titre : Tiramisu\nLa recette : https://www.chef-martin.fr/tiramisu", "https://thumb/video.jpg"

    monkeypatch.setattr(extractor, "video_to_text", video)
    data, calls = _run_extract(
        monkeypatch, "https://youtu.be/abc", linked=(dict(PUBLISHED), "https://www.chef-martin.fr/tiramisu", "https://img"),
    )
    assert [c for c in calls if not isinstance(c, tuple)] == []  # aucun appel au LLM
    assert data["title"] == "Tiramisu" and data["source_url"] == "https://youtu.be/abc"
    assert data["description"] == "Recette complète publiée sur chef-martin.fr. Le classique."
    assert data["thumbnail_url"] == "https://thumb/video.jpg"


def test_dish_name_gets_a_real_recipe_from_the_web(monkeypatch):
    rebuilt = {"title": "Lasagnes", "ingredients": [{"name": "pâtes"}], "steps": [{"order": 1, "text": "Cuire."}]}
    found = {**PUBLISHED, "title": "Lasagnes à la bolognaise", "description": None}
    data, calls = _run_extract(
        monkeypatch, "lasagnes", llm_result={"error": "Aucune recette trouvée"}, rebuilt=rebuilt,
        searched=(found, "https://www.marmiton.org/lasagnes", "https://img/lasagnes.jpg"),
    )
    assert calls[-1] == ("recherche", "Lasagnes")
    assert data["title"] == "Lasagnes à la bolognaise"
    assert data["description"].startswith("Recette trouvée sur marmiton.org")
    assert data["thumbnail_url"] == "https://img/lasagnes.jpg"


DDG_HTML = """<html><body>
<div class="result results_links result--ad"><a class="result__a" href="https://duckduckgo.com/y.js?ad=1">Pub</a></div>
<div class="result"><a rel="nofollow" class="result__a"
  href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.marmiton.org%2Frecettes%2Ftiramisu.aspx&amp;rut=abc">Tiramisu</a></div>
<div class="result"><a class="result__a" href="https://www.750g.com/tiramisu-r1.htm">Tiramisu facile</a></div>
<div class="result"><a class="result__a" href="https://www.youtube.com/watch?v=1">Vidéo</a></div>
</body></html>"""


def test_parse_search_results():
    assert recipe_finder.parse_search_results(DDG_HTML) == [
        "https://www.marmiton.org/recettes/tiramisu.aspx",
        "https://www.750g.com/tiramisu-r1.htm",
        "https://www.youtube.com/watch?v=1",
    ]


@pytest.mark.parametrize("dish, title, same", [
    ("Pasta alla vodka", "Pâtes à la vodka", True),
    ("Lasagnes", "Lasagnes à la bolognaise", True),
    ("Tiramisu", "Gâteau au chocolat", False),
])
def test_same_dish(dish, title, same):
    assert recipe_finder.same_dish(dish, title) is same


def _patch_search(monkeypatch, pages):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        recipe_finder.httpx, "AsyncClient",
        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(lambda r: httpx.Response(200, text=DDG_HTML)), **kw),
    )

    async def fake_page(url):
        return pages.get(url)

    monkeypatch.setattr(recipe_finder, "structured_recipe_at", fake_page)


def test_search_recipe_takes_the_first_published_recipe(monkeypatch):
    _patch_search(monkeypatch, {
        "https://www.750g.com/tiramisu-r1.htm": ({**PUBLISHED, "title": "Tiramisu facile"}, "https://img/750g.jpg"),
    })
    recipe, link, image = asyncio.run(recipe_finder.search_recipe("Tiramisu"))
    assert recipe["title"] == "Tiramisu facile" and link == "https://www.750g.com/tiramisu-r1.htm"


def test_search_recipe_rejects_an_unrelated_page(monkeypatch):
    _patch_search(monkeypatch, {
        "https://www.marmiton.org/recettes/tiramisu.aspx": ({**PUBLISHED, "title": "Gâteau au chocolat"}, None),
    })
    assert asyncio.run(recipe_finder.search_recipe("Tiramisu")) is None


def test_search_recipe_can_be_disabled(monkeypatch):
    monkeypatch.setattr(recipe_finder.settings, "recipe_web_search", False)
    assert asyncio.run(recipe_finder.search_recipe("Tiramisu")) is None


def test_structured_recipe_at_reads_json_ld(monkeypatch):
    async def fake_static(url):
        return _html(RECIPE)

    monkeypatch.setattr(web_scraper, "_fetch_static", fake_static)
    recipe, image = asyncio.run(recipe_finder.structured_recipe_at("https://exemple.fr/crepes"))
    assert recipe["title"] == "Crêpes" and recipe["ingredients"]
