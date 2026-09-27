import asyncio
import logging
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from . import recipe_parsing

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_STATIC_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
# Instagram, Facebook, Threads ne montrent qu'un mur de connexion à un
# navigateur anonyme, mais servent la légende (og:description) aux robots
# d'aperçu de liens : c'est elle qui contient la recette d'un post photo.
_LINK_PREVIEW_HOSTS = re.compile(r"(^|\.)(instagram\.com|facebook\.com|fb\.watch|threads\.net)$", re.I)
_LINK_PREVIEW_HEADERS = {
    **_STATIC_HEADERS,
    "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
}
# Pages de contrôle anti-robot renvoyées avec un code 200 : le vrai contenu
# n'arrive qu'après exécution de JavaScript, il faut alors le navigateur.
_BOT_WALL = re.compile(
    r"cf-browser-verification|challenge-platform|Just a moment\.\.\.|"
    r"Enable JavaScript and cookies to continue|Please enable JavaScript",
    re.I,
)

# Ressources qui ralentissent le chargement sans jamais contenir la recette :
# images, polices, medias et la plupart des scripts tiers (pubs, trackers,
# bannieres de consentement) qui bloquent souvent le DOMContentLoaded sur les
# sites de recettes charges en publicite.
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}
_BLOCKED_HOST_PATTERN = re.compile(
    r"(doubleclick\.net|googlesyndication\.com|google-analytics\.com|"
    r"googletagmanager\.com|googletagservices\.com|adservice\.google\.|"
    r"facebook\.net|facebook\.com/tr|connect\.facebook|hotjar\.com|"
    r"criteo\.com|taboola\.com|outbrain\.com|didomi\.io|tarteaucitron\.io|"
    r"consensu\.org|amazon-adsystem\.com|adnxs\.com|pubmatic\.com|"
    r"rubiconproject\.com|scorecardresearch\.com|quantserve\.com)",
    re.IGNORECASE,
)

_playwright = None
_browser = None
_browser_lock = asyncio.Lock()


async def _get_browser():
    """Lance Chromium une seule fois et reutilise l'instance entre les extractions.

    Relancer un navigateur complet a chaque recette coute 1 a 2 secondes de
    pur overhead ; le reutiliser garde ce cout une seule fois par vie du
    processus (avec relance automatique s'il a plante).
    """
    global _playwright, _browser
    async with _browser_lock:
        if _browser is None or not _browser.is_connected():
            if _playwright is None:
                _playwright = await async_playwright().start()
            _browser = await _playwright.chromium.launch(headless=True)
        return _browser


async def close_browser():
    """A appeler a l'arret de l'application pour liberer Chromium proprement."""
    global _playwright, _browser
    async with _browser_lock:
        if _browser is not None:
            await _browser.close()
            _browser = None
        if _playwright is not None:
            await _playwright.stop()
            _playwright = None


async def _block_heavy_requests(route):
    request = route.request
    if request.resource_type in _BLOCKED_RESOURCE_TYPES or _BLOCKED_HOST_PATTERN.search(request.url):
        await route.abort()
    else:
        await route.continue_()


@dataclass
class ScrapeResult:
    text: str
    thumbnail: str | None
    # Recette complète lue dans les données structurées du site, prête à
    # enregistrer sans passer par le LLM (None si absente ou à traduire).
    structured_recipe: dict | None = None


@dataclass
class Document:
    """Lien vers un fichier (photo d'une recette, PDF) plutôt qu'une page."""
    content: bytes
    content_type: str


# Au-delà, ce n'est plus une fiche recette (et ça ne tient pas en mémoire).
_MAX_DOCUMENT_BYTES = 25 * 1024 * 1024


async def _read_document(url: str, doc: Document) -> ScrapeResult:
    if doc.content_type.startswith("image/"):
        from .ocr_service import extract_text_from_image
        text = await extract_text_from_image(doc.content, doc.content_type.split(";")[0])
        return ScrapeResult(text or "", url)
    text = await asyncio.to_thread(pdf_to_text, doc.content)
    return ScrapeResult(text, None)


def pdf_to_text(data: bytes, max_pages: int = 20) -> str:
    """Texte d'un PDF (fiche recette, livre numérisé avec couche texte)."""
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages[:max_pages]]
    return "\n".join(pages).strip()


async def scrape_url(url: str) -> ScrapeResult:
    """Récupère la recette d'une page web, du moyen le plus rapide au plus lourd.

    1. Simple requête HTTP (< 1 s) : la plupart des sites de recettes
       servent leurs données schema.org directement dans le HTML.
    2. Chromium (Playwright) seulement si ça ne suffit pas : page rendue en
       JavaScript, protection anti-robot, contenu sans recette apparente.
    """
    static_html = await _fetch_static(url)
    if isinstance(static_html, Document):
        logger.info("scrape %s : fichier %s", url, static_html.content_type)
        return await _read_document(url, static_html)
    static = _analyze_html(static_html) if static_html else None
    if static and (static.structured_recipe or recipe_parsing.looks_like_recipe(static.text)):
        logger.info("scrape %s : HTML statique suffisant", url)
        return static

    try:
        browser_html = await _fetch_with_browser(url)
    except Exception:
        if static:
            logger.warning("scrape %s : échec du navigateur, repli sur le HTML statique", url, exc_info=True)
            return static
        raise
    rendered = _analyze_html(browser_html)
    logger.info("scrape %s : rendu navigateur utilisé", url)
    if static and not rendered.structured_recipe and not recipe_parsing.looks_like_recipe(rendered.text):
        # Ni l'un ni l'autre n'a d'indices de recette : garder le plus fourni.
        return rendered if len(rendered.text) >= len(static.text) else static
    return rendered


async def _fetch_static(url: str) -> str | Document | None:
    host = httpx.URL(url).host if url.startswith("http") else ""
    headers = _LINK_PREVIEW_HEADERS if _LINK_PREVIEW_HOSTS.search(host) else _STATIC_HEADERS
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
    except httpx.HTTPError:
        return None
    content_type = resp.headers.get("content-type", "").lower()
    if resp.status_code == 200 and (content_type.startswith("image/") or "pdf" in content_type):
        if len(resp.content) > _MAX_DOCUMENT_BYTES:
            raise ValueError("Fichier trop volumineux pour en extraire une recette.")
        return Document(resp.content, content_type)
    if resp.status_code != 200 or "html" not in content_type:
        return None
    if _BOT_WALL.search(resp.text[:20000]):
        return None
    return resp.text


async def _fetch_with_browser(url: str) -> str:
    browser = await _get_browser()
    context = await browser.new_context(user_agent=_USER_AGENT, locale="fr-FR")
    try:
        page = await context.new_page()
        await page.route("**/*", _block_heavy_requests)
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        return await page.content()
    finally:
        await context.close()


def _analyze_html(html: str) -> ScrapeResult:
    soup = BeautifulSoup(html, "html.parser")
    og_image = soup.find("meta", property="og:image")
    thumbnail = og_image.get("content") if og_image else None

    node = recipe_parsing.find_jsonld_recipe(soup)
    if node:
        recipe = recipe_parsing.jsonld_to_recipe(node)
        image = recipe.pop("thumbnail_url", None) if recipe else None
        thumbnail = thumbnail or image
        if recipe and recipe["language"] == "fr":
            return ScrapeResult(recipe_parsing.jsonld_to_text(node), thumbnail, recipe)
        # Recette complète mais pas en français : le LLM la traduira à partir
        # d'un texte compact plutôt que de toute la page. Données incomplètes
        # (pas d'étapes…) : le texte de la page, plus complet, est préférable.
        compact = recipe_parsing.jsonld_to_text(node)
        if compact and recipe:
            return ScrapeResult(compact, thumbnail)

    summary = _page_summary(soup)
    text = recipe_parsing.extract_page_text(soup)
    if summary and summary[:200] not in text:
        # Instagram, Pinterest, Facebook… : sans connexion, la page n'affiche
        # qu'un mur de connexion, mais la légende est dans ses métadonnées.
        text = f"{summary}\n\n{text}"
    return ScrapeResult(text, thumbnail)


def _page_summary(soup) -> str:
    """Titre et description annoncés par la page (balises og: / meta)."""
    def meta(*names):
        for name in names:
            tag = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
            content = recipe_parsing.clean_text(tag.get("content")) if tag else ""
            if content:
                return content
        return ""

    title = meta("og:title", "twitter:title")
    description = meta("og:description", "description", "twitter:description")
    return "\n".join(part for part in (title, description) if part)
