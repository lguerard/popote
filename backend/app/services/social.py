"""Légende d'un post Instagram ou TikTok, sans compte ni yt-dlp.

Instagram bloque de plus en plus souvent yt-dlp (« login required »,
« rate-limit reached ») et ne montre qu'un mur de connexion aux visiteurs
anonymes. Deux portes restent ouvertes, faites pour être intégrées ailleurs :

- Instagram : la page d'intégration ``/p/<code>/embed/captioned/`` (celle des
  posts insérés dans les blogs) contient la légende complète ;
- TikTok : l'API publique oEmbed renvoie la légende dans ``title``.

La légende est souvent la recette elle-même : c'est le repli le plus fiable
quand la vidéo ne peut pas être lue.
"""

import json
import logging
import re

import httpx
from bs4 import BeautifulSoup

from . import recipe_parsing

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_INSTAGRAM_POST = re.compile(
    r"instagram\.com/(?:[\w.]+/)?(?:p|reels?|tv)/([A-Za-z0-9_-]+)", re.IGNORECASE,
)
_TIKTOK = re.compile(r"(?:^|\.|//)tiktok\.com/", re.IGNORECASE)


def instagram_shortcode(url: str) -> str | None:
    match = _INSTAGRAM_POST.search(url or "")
    return match.group(1) if match else None


def is_tiktok(url: str) -> bool:
    return bool(_TIKTOK.search(url or ""))


def _json_caption(html: str) -> str:
    """Légende dans les données JSON de la page (quand le HTML ne l'a pas)."""
    for pattern in (
        r'"edge_media_to_caption"\s*:\s*\{\s*"edges"\s*:\s*\[\s*\{\s*"node"\s*:\s*\{\s*"text"\s*:\s*("(?:[^"\\]|\\.)*")',
        r'"caption"\s*:\s*\{[^{}]*?"text"\s*:\s*("(?:[^"\\]|\\.)*")',
    ):
        for raw in (html, html.replace('\\"', '"').replace("\\\\", "\\")):
            match = re.search(pattern, raw)
            if match:
                try:
                    return json.loads(match.group(1)).strip()
                except ValueError:
                    continue
    return ""


def parse_instagram_embed(html: str) -> tuple[str, str | None]:
    """(légende, vignette) d'une page /embed/captioned/ ; légende vide si absente."""
    soup = BeautifulSoup(html, "html.parser")
    image = soup.select_one("img.EmbeddedMediaImage") or soup.find("meta", property="og:image")
    thumbnail = (image.get("src") or image.get("content")) if image else None

    caption = ""
    block = soup.select_one(".Caption")
    if block:
        for noise in block.select(".CaptionUsername, .CaptionComments"):
            noise.decompose()
        for br in block.find_all("br"):
            br.replace_with("\n")
        caption = recipe_parsing.clean_text(block.get_text())
    if not caption:
        caption = _json_caption(html)
    return caption, thumbnail


async def instagram_caption(url: str) -> tuple[str, str | None]:
    code = instagram_shortcode(url)
    if not code:
        return "", None
    embed = f"https://www.instagram.com/p/{code}/embed/captioned/"
    async with httpx.AsyncClient(
        timeout=15, follow_redirects=True,
        headers={"User-Agent": _USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
    ) as client:
        resp = await client.get(embed)
    if resp.status_code != 200:
        return "", None
    return parse_instagram_embed(resp.text)


async def tiktok_caption(url: str) -> tuple[str, str | None]:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get("https://www.tiktok.com/oembed", params={"url": url})
    if resp.status_code != 200:
        return "", None
    data = resp.json()
    return recipe_parsing.clean_text(data.get("title")), data.get("thumbnail_url")


async def post_caption(url: str) -> tuple[str, str | None]:
    """(légende, vignette) d'un post Instagram/TikTok ; ("", None) sinon ou en cas d'échec."""
    try:
        if instagram_shortcode(url):
            return await instagram_caption(url)
        if is_tiktok(url):
            return await tiktok_caption(url)
    except Exception:
        logger.warning("Légende du post illisible : %s", url, exc_info=True)
    return "", None
