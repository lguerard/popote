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


async def scrape_url(url: str) -> ScrapeResult:
    """Récupère la recette d'une page web, du moyen le plus rapide au plus lourd.

    1. Simple requête HTTP (< 1 s) : la plupart des sites de recettes
       servent leurs données schema.org directement dans le HTML.
    2. Chromium (Playwright) seulement si ça ne suffit pas : page rendue en
       JavaScript, protection anti-robot, contenu sans recette apparente.
    """
    static_html = await _fetch_static(url)
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


async def _fetch_static(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=_STATIC_HEADERS) as client:
            resp = await client.get(url)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200 or "html" not in resp.headers.get("content-type", ""):
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

    return ScrapeResult(recipe_parsing.extract_page_text(soup), thumbnail)
