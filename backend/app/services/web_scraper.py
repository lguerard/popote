import asyncio
import json
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

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


async def scrape_url(url: str) -> tuple[str, str | None]:
    """Returns (page_text, thumbnail_url)."""
    browser = await _get_browser()
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    try:
        page = await context.new_page()
        await page.route("**/*", _block_heavy_requests)
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        html = await page.content()
    finally:
        await context.close()

    soup = BeautifulSoup(html, "html.parser")

    # Extract thumbnail from og:image
    thumbnail = None
    og_image = soup.find("meta", property="og:image")
    if og_image:
        thumbnail = og_image.get("content")

    # La plupart des sites de recettes exposent deja la recette structuree
    # (schema.org/Recipe) : un texte court et sans bruit, bien plus rapide a
    # traiter par le LLM qu'une page complete pleine de pubs/commentaires.
    recipe_text = _extract_recipe_jsonld(soup)
    if recipe_text:
        return recipe_text[:15000], thumbnail

    # Remove noise
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
        tag.decompose()

    # Prefer article/main content
    content_el = soup.find("article") or soup.find("main") or soup.body
    text = content_el.get_text(separator="\n", strip=True) if content_el else ""

    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text[:15000], thumbnail


def _extract_recipe_jsonld(soup: BeautifulSoup) -> str | None:
    """Cherche un bloc JSON-LD schema.org/Recipe et le met en texte compact."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        for node in _iter_jsonld_nodes(data):
            if _is_recipe_node(node):
                text = _recipe_node_to_text(node)
                if text:
                    return text
    return None


def _iter_jsonld_nodes(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_nodes(item)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _iter_jsonld_nodes(data["@graph"])


def _is_recipe_node(node: dict) -> bool:
    node_type = node.get("@type")
    if isinstance(node_type, list):
        return any(isinstance(t, str) and t.lower() == "recipe" for t in node_type)
    return isinstance(node_type, str) and node_type.lower() == "recipe"


def _parse_iso_duration(value) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.match(r"^P(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?$", value.strip())
    if not match:
        return value
    hours, minutes = match.groups()
    total = int(hours or 0) * 60 + int(minutes or 0)
    return f"{total} minutes" if total else value


def _flatten_instructions(instructions) -> list[str]:
    steps: list[str] = []
    if isinstance(instructions, str):
        return [line.strip() for line in instructions.split("\n") if line.strip()]
    if isinstance(instructions, list):
        for item in instructions:
            if isinstance(item, str):
                steps.append(item.strip())
            elif isinstance(item, dict):
                if "itemListElement" in item:
                    steps.extend(_flatten_instructions(item["itemListElement"]))
                elif item.get("text"):
                    steps.append(str(item["text"]).strip())
                elif item.get("name"):
                    steps.append(str(item["name"]).strip())
    return [s for s in steps if s]


def _recipe_node_to_text(node: dict) -> str:
    lines = []
    name = node.get("name")
    if name:
        lines.append(f"Titre: {name}")
    description = node.get("description")
    if description:
        lines.append(f"Description: {description}")
    yield_ = node.get("recipeYield")
    if yield_:
        lines.append(f"Portions: {yield_ if isinstance(yield_, str) else yield_}")
    prep_time = _parse_iso_duration(node.get("prepTime"))
    if prep_time:
        lines.append(f"Temps de preparation: {prep_time}")
    cook_time = _parse_iso_duration(node.get("cookTime"))
    if cook_time:
        lines.append(f"Temps de cuisson: {cook_time}")
    category = node.get("recipeCategory")
    if category:
        lines.append(f"Categorie: {category}")
    keywords = node.get("keywords")
    if keywords:
        lines.append(f"Mots-cles: {keywords}")

    ingredients = node.get("recipeIngredient") or node.get("ingredients")
    if ingredients:
        lines.append("Ingredients:")
        for ing in ingredients:
            lines.append(f"- {ing}")

    steps = _flatten_instructions(node.get("recipeInstructions"))
    if steps:
        lines.append("Instructions:")
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")

    # Sans ingredients ni etapes, ce n'est pas exploitable : mieux vaut
    # retomber sur le texte complet de la page.
    if not ingredients or not steps:
        return ""

    return "\n".join(lines)
