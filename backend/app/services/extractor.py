import logging
import re
import time
from typing import Awaitable, Callable

from .video_service import video_to_text
from .web_scraper import scrape_url
from .llm_service import extract_recipe_with_llm, reconstruct_recipe_with_llm
from .extraction_steps import error_text
from . import recipe_finder, recipe_parsing, social
from ..models.recipe import SourceType

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], Awaitable[None]]


async def _noop_progress(_message: str) -> None:
    pass

VIDEO_DOMAINS = re.compile(
    r"(youtube\.com|youtu\.be|tiktok\.com|instagram\.com|twitter\.com|x\.com|"
    r"dailymotion\.com|vimeo\.com|twitch\.tv|facebook\.com|reddit\.com|clips\.twitch)",
    re.IGNORECASE,
)

URL_PATTERN = re.compile(r"^https?://\S+$", re.IGNORECASE)
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
# « marmiton.org/recettes/… », « www.x.fr » : une adresse tapée ou copiée
# sans https:// partait au LLM comme du texte (aucune recette trouvée).
_TLDS = r"(?:com|fr|org|net|be|ch|ca|it|es|de|uk|eu|io|co|tv|me|lu|nl|pt|us|info|blog|app|gl|ly)"
_BARE_URL = re.compile(
    rf"^(?:www\.)?(?:[a-z0-9-]+\.)+{_TLDS}(?::\d+)?(?:[/?#]\S*)?$", re.IGNORECASE,
)
_BARE_URL_IN_TEXT = re.compile(
    rf"(?<![@\w.])(?:www\.)?(?:[a-z0-9-]+\.)+{_TLDS}/[^\s<>\"']*", re.IGNORECASE,
)
# Au-delà, le texte partagé est probablement la recette elle-même (copiée
# depuis une page) et l'URL qu'il contient n'est qu'une mention de source.
_SHARED_TEXT_MAX_CHARS = 400


def resolve_input(input_text: str) -> str:
    """L'URL à extraire quand l'entrée est un texte de partage qui en contient une.

    Le bouton « Partager » d'Instagram, TikTok ou d'un navigateur envoie
    souvent « Regarde cette recette ! https://… » plutôt que l'URL seule :
    traité comme du texte, le LLM ne trouvait évidemment aucune recette.
    Un texte long qui contient déjà ingrédients et étapes reste du texte.
    """
    text = input_text.strip()
    if URL_PATTERN.match(text):
        return text
    if len(text) > _SHARED_TEXT_MAX_CHARS:
        return text
    if _BARE_URL.match(text):
        return "https://" + text
    match = _URL_IN_TEXT.search(text) or _BARE_URL_IN_TEXT.search(text)
    if not match or recipe_parsing.has_full_recipe(text):
        return text
    url = match.group(0).rstrip(".,;:!?)]}»")
    return url if URL_PATTERN.match(url) else "https://" + url


def detect_source_type(input_text: str) -> SourceType:
    input_text = input_text.strip()
    if not URL_PATTERN.match(input_text):
        return SourceType.text
    if VIDEO_DOMAINS.search(input_text):
        return SourceType.video
    return SourceType.web


async def extract(
    input_text: str, db=None, on_progress: ProgressCallback | None = None, owner_id=None,
) -> dict:
    """
    Returns dict with recipe fields + source_type + thumbnail_url.
    Raises on unrecoverable error. Pass db session (and owner_id) for
    duplicate detection. on_progress, if given, is awaited with a short
    human-readable message before each slow step.
    """
    progress = on_progress or _noop_progress
    source = resolve_input(input_text)
    source_type = detect_source_type(source)
    thumbnail_url = None
    recipe_data = None
    raw_text = source
    started = time.monotonic()

    page = None
    if source_type == SourceType.video:
        await progress("Lecture des informations de la vidéo…")
        try:
            raw_text, thumbnail_url = await video_to_text(source, progress)
        except Exception as exc:
            # Instagram qui exige une connexion, post photo, tweet ou post
            # Reddit sans vidéo, vérification anti-robot de YouTube… : la
            # légende du post (lue sans compte) ou la page elle-même
            # contiennent souvent la recette.
            logger.warning("Vidéo illisible (%s), repli sur la légende/la page : %s", error_text(exc), source)
            await progress("Vidéo illisible, lecture de la légende du post…")
            caption, caption_thumb = await social.post_caption(source)
            if caption:
                raw_text, thumbnail_url = f"Légende de la publication :\n{caption}", caption_thumb
            else:
                await progress("Vidéo illisible, lecture de la page…")
                page = await _scrape(source, video_error=exc)
        else:
            if not recipe_parsing.has_full_recipe(raw_text):
                # yt-dlp a lu la vidéo mais sans la légende complète (Instagram
                # la tronque ou la cache sans connexion) : on la complète.
                caption, caption_thumb = await social.post_caption(source)
                if caption and caption[:80] not in raw_text:
                    raw_text = f"{raw_text}\n\nLégende de la publication :\n{caption}".strip()
                    thumbnail_url = thumbnail_url or caption_thumb
    elif source_type == SourceType.web:
        await progress("Chargement de la page web…")
        page = await _scrape(source)
    if page is not None:
        thumbnail_url = page.thumbnail or thumbnail_url
        raw_text = page.text
        if page.structured_recipe:
            # Recette publiée en données structurées par le site : lue telle
            # quelle, sans LLM — quelques secondes au lieu d'une ou deux
            # minutes, et rien d'inventé ni de mal recopié.
            await progress("Lecture de la recette publiée par le site…")
            recipe_data = page.structured_recipe
    if recipe_data is None and source_type != SourceType.web and recipe_finder.candidate_links(raw_text, source):
        # La description renvoie souvent à la recette complète sur le blog
        # de l'auteur : quantités exactes publiées, plutôt que devinées.
        await progress("Lecture de la recette complète liée dans la description…")
        linked = await recipe_finder.linked_recipe(raw_text, exclude=source)
        if linked:
            recipe_data, link, image = linked
            _add_note(recipe_data, f"Recette complète publiée sur {_domain(link)}.")
            thumbnail_url = thumbnail_url or image
    fetched = time.monotonic()

    used_llm = recipe_data is None
    if used_llm:
        if not raw_text.strip():
            raise ValueError("Aucun contenu exploitable n'a pu être récupéré depuis cette source.")
        await progress("Analyse de la recette par l'IA…")
        recipe_data = await extract_recipe_with_llm(raw_text)
        if "error" in recipe_data:
            if source_type != SourceType.text:
                # Un lien donne SA recette, jamais une autre : rien n'est
                # inventé ni cherché ailleurs quand il n'en contient pas.
                raise ValueError(
                    "Ce lien ne contient pas de recette détaillée (ni dans la vidéo, ni dans sa "
                    "légende ou sa page). Si elle est ailleurs (commentaire, lien en bio…), "
                    "copiez-la et collez-la dans Popote."
                )
            # Texte sans recette (nom de plat tapé seul…) : l'IA en propose une.
            recipe_data, _ = await recipe_for_dish(raw_text, progress)
            if "error" in recipe_data:
                raise ValueError(
                    "Aucune recette ni aucun plat reconnaissable dans ce contenu."
                )
    logger.info(
        "extraction %s (%s) : récupération %.1fs, analyse %.1fs%s",
        source[:80], source_type.value, fetched - started, time.monotonic() - fetched,
        "" if used_llm else " (sans LLM)",
    )

    recipe_data["source_url"] = source if source_type != SourceType.text else None
    recipe_data["source_type"] = source_type
    recipe_data["thumbnail_url"] = recipe_data.get("thumbnail_url") or thumbnail_url

    if db and recipe_data.get("title"):
        await progress("Vérification des doublons…")
        similar = await _find_similar(recipe_data["title"], db, owner_id)
        if similar:
            recipe_data["similar_recipe_id"] = similar

    return recipe_data


def _domain(url: str) -> str:
    host = recipe_finder._host(url)
    return host[4:] if host.startswith("www.") else host


def _add_note(recipe: dict, note: str) -> None:
    description = recipe.get("description")
    recipe["description"] = f"{note} {description}" if description else note


async def recipe_for_dish(text: str, progress: ProgressCallback | None = None) -> tuple[dict, str | None]:
    """(recette, image) pour une entrée SANS lien qui évoque un plat sans en
    donner la recette (nom de plat tapé, photo d'un plat) : l'IA en propose
    une, marquée « à vérifier ». Jamais utilisé pour un lien.
    {"error": …} si aucun plat n'est reconnaissable.
    """
    progress = progress or _noop_progress
    await progress("Pas de recette détaillée : l'IA en propose une…")
    return await reconstruct_recipe_with_llm(text), None


async def _scrape(url: str, video_error: Exception | None = None):
    """La page, ou une erreur compréhensible (pas la trace de Chromium)."""
    try:
        return await scrape_url(url)
    except Exception as exc:
        logger.warning("Page inaccessible : %s", url, exc_info=True)
        reason = error_text(video_error or exc).splitlines()[0][:200]
        raise ValueError(f"Impossible de lire ce lien ({reason}).") from exc


async def _find_similar(title: str, db, owner_id=None) -> str | None:
    from sqlalchemy import or_, select
    from ..models.recipe import ExtractionStatus, Recipe
    words = [w for w in title.lower().split() if len(w) > 3]
    if not words:
        return None
    conditions = [Recipe.title.ilike(f"%{w}%") for w in words[:3]]
    q = (
        select(Recipe.id, Recipe.title)
        .where(or_(*conditions))
        .where(Recipe.status == ExtractionStatus.done)
        # Seulement parmi SES recettes : le lien « recette similaire » vers
        # celle d'un autre compte donnait une 404 (et révélait son existence).
        .where(Recipe.owner_id == owner_id)
        .limit(5)
    )
    rows = (await db.execute(q)).all()
    for row_id, row_title in rows:
        overlap = sum(1 for w in words if w in row_title.lower())
        if overlap >= max(2, len(words) // 2):
            return str(row_id)
    return None
