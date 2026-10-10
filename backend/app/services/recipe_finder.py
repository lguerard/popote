"""Lien vers la recette complète, cité par l'auteur dans sa description.

Une vidéo YouTube, Instagram ou TikTok renvoie très souvent vers la recette
détaillée sur le blog de son auteur (« la recette complète : https://… »).
C'est la même recette, mais publiée en données structurées (schema.org/
Recipe) : quantités, étapes et temps exacts, sans passer par le LLM.

Seuls les liens présents dans le contenu fourni sont suivis : Popote ne va
jamais chercher une recette ailleurs.
"""

import asyncio
import logging
import re
from urllib.parse import urlparse

from . import web_scraper

logger = logging.getLogger(__name__)

_URL = re.compile(r"""(?:https?://|\bwww\.)[^\s<>"'()\[\]{}]+""", re.IGNORECASE)
# Liens qui ne mènent jamais à une recette : réseaux sociaux, boutiques,
# dons, musique, pages de liens.
_NOT_RECIPE_HOST = re.compile(
    r"(^|\.)(instagram|tiktok|youtube|youtu|facebook|fb|twitter|x|threads|pinterest|snapchat|twitch|"
    r"discord|reddit|amazon|amzn|patreon|tipeee|paypal|spotify|deezer|apple|google|goo|linktr|beacons|"
    r"whatsapp|telegram|t)\.[a-z.]+$",
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
