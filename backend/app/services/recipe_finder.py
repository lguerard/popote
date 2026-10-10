"""Trouver la VRAIE recette au lieu de la deviner.

Deux astuces, toutes deux appuyées sur les données structurées
(schema.org/Recipe) que publient presque tous les sites de recettes : une
recette lue ainsi est exacte (quantités, étapes, temps) et ne passe pas par
le LLM.

1. Suivre le lien de la recette : une vidéo YouTube, Instagram ou TikTok
   renvoie très souvent vers la recette complète sur le blog de l'auteur
   (« la recette détaillée : https://… ») — inutile de reconstituer les
   quantités depuis la vidéo, elles sont publiées.
2. Chercher le plat sur le web : quand le contenu ne donne qu'un nom de plat
   (« lasagnes », reel en musique « Pasta alla vodka 🍝 »), une recette
   publiée et éprouvée vaut mieux qu'une recette inventée par l'IA.
"""

import asyncio
import logging
import re
import unicodedata
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import settings
from . import web_scraper

logger = logging.getLogger(__name__)

_URL = re.compile(r"""(?:https?://|\bwww\.)[^\s<>"'()\[\]{}]+""", re.IGNORECASE)
# Liens qui ne mènent jamais à une recette : réseaux sociaux, boutiques,
# dons, musique, pages de liens.
_NOT_RECIPE_HOST = re.compile(
    r"(^|\.)(instagram|tiktok|youtube|youtu|facebook|fb|twitter|x|threads|pinterest|snapchat|twitch|"
    r"discord|reddit|amazon|amzn|patreon|tipeee|paypal|spotify|deezer|apple|google|goo|linktr|beacons|"
    r"duckduckgo|bing|whatsapp|telegram|t)\.[a-z.]+$",
    re.IGNORECASE,
)
_RECIPE_HINT = re.compile(r"recette|recipe|ingr[ée]dient|full|compl[eè]te|blog|d[ée]tail", re.IGNORECASE)
_MAX_LINKS = 4


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def candidate_links(text: str, exclude: str | None = None) -> list[str]:
    """Liens du texte susceptibles de mener à une recette, les plus prometteurs d'abord."""
    found: list[tuple[int, int, str]] = []
    seen = {exclude} if exclude else set()
    for line_no, line in enumerate((text or "").splitlines()):
        for match in _URL.finditer(line):
            url = match.group(0).rstrip(".,;:!?»")
            if url.lower().startswith("www."):
                url = "https://" + url
            host = _host(url)
            if not host or "." not in host or _NOT_RECIPE_HOST.search(host) or url in seen:
                continue
            seen.add(url)
            # Lien annoncé comme la recette (« recette complète : … ») en premier.
            found.append((0 if _RECIPE_HINT.search(line) else 1, line_no, url))
    return [url for _, _, url in sorted(found)][:_MAX_LINKS]


async def structured_recipe_at(url: str) -> tuple[dict, str | None] | None:
    """(recette, image) publiée en données structurées à cette adresse, sinon None."""
    try:
        html = await web_scraper._fetch_static(url)
        if not isinstance(html, str):
            return None
        page = web_scraper._analyze_html(html)
    except Exception:
        logger.info("Recette non lue à %s", url, exc_info=True)
        return None
    return (page.structured_recipe, page.thumbnail) if page.structured_recipe else None


async def _first_recipe(urls: list[str]) -> tuple[dict, str, str | None] | None:
    """Première adresse (dans l'ordre donné) qui publie une recette ; requêtes en parallèle."""
    results = await asyncio.gather(*(structured_recipe_at(u) for u in urls))
    for url, result in zip(urls, results):
        if result:
            recipe, image = result
            return recipe, url, image
    return None


async def linked_recipe(text: str, exclude: str | None = None) -> tuple[dict, str, str | None] | None:
    """(recette, lien, image) de la recette vers laquelle pointe le texte, s'il y en a une."""
    links = candidate_links(text, exclude)
    return await _first_recipe(links) if links else None


# ── Recherche web ────────────────────────────────────────────────────────────

_SEARCH_URL = "https://html.duckduckgo.com/html/"
_SEARCH_HEADERS = {
    "User-Agent": web_scraper._USER_AGENT,
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
_STOPWORDS = {"de", "du", "des", "la", "le", "les", "aux", "au", "a", "et", "en", "the", "with", "recette", "maison"}


def _words(text: str) -> set[str]:
    folded = "".join(
        c for c in unicodedata.normalize("NFKD", (text or "").lower()) if not unicodedata.combining(c)
    )
    return {w.rstrip("sx") for w in re.findall(r"[a-z]{3,}", folded) if w not in _STOPWORDS}


def same_dish(dish: str, title: str) -> bool:
    """La recette trouvée parle bien du plat cherché (un mot significatif en commun)."""
    return bool(_words(dish) & _words(title))


def parse_search_results(html: str) -> list[str]:
    """Liens des résultats d'une page DuckDuckGo HTML, publicités exclues."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for anchor in soup.select("a.result__a"):
        if anchor.find_parent(class_="result--ad"):
            continue
        href = anchor.get("href") or ""
        if "duckduckgo.com/l/" in href or href.startswith("/l/"):
            target = parse_qs(urlparse(href).query).get("uddg", [""])[0]
            href = unquote(target) if target else ""
        if href.startswith("http") and "duckduckgo.com/y.js" not in href and href not in links:
            links.append(href)
    return links


async def search_recipe(dish: str) -> tuple[dict, str, str | None] | None:
    """(recette, lien, image) d'une recette publiée du plat, trouvée sur le web."""
    if not settings.recipe_web_search or not dish.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=_SEARCH_HEADERS) as client:
            resp = await client.get(_SEARCH_URL, params={"q": f"{dish} recette", "kl": "fr-fr"})
        if resp.status_code != 200:
            logger.info("Recherche web indisponible (%s) pour « %s »", resp.status_code, dish)
            return None
        urls = [u for u in parse_search_results(resp.text) if not _NOT_RECIPE_HOST.search(_host(u))]
    except Exception:
        logger.info("Recherche web impossible pour « %s »", dish, exc_info=True)
        return None
    found = await _first_recipe(urls[:5])
    if found and same_dish(dish, found[0].get("title") or ""):
        return found
    return None
