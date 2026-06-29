import re
from .video_service import download_and_transcribe
from .web_scraper import scrape_url
from .llm_service import extract_recipe_with_llm
from ..models.recipe import SourceType

VIDEO_DOMAINS = re.compile(
    r"(youtube\.com|youtu\.be|tiktok\.com|instagram\.com|twitter\.com|x\.com|"
    r"dailymotion\.com|vimeo\.com|twitch\.tv|facebook\.com|reddit\.com|clips\.twitch)",
    re.IGNORECASE,
)

URL_PATTERN = re.compile(r"^https?://\S+$", re.IGNORECASE)


def detect_source_type(input_text: str) -> SourceType:
    input_text = input_text.strip()
    if not URL_PATTERN.match(input_text):
        return SourceType.text
    if VIDEO_DOMAINS.search(input_text):
        return SourceType.video
    return SourceType.web


async def extract(input_text: str, db=None) -> dict:
    """
    Returns dict with recipe fields + source_type + thumbnail_url.
    Raises on unrecoverable error. Pass db session for duplicate detection.
    """
    source_type = detect_source_type(input_text.strip())
    thumbnail_url = None

    if source_type == SourceType.video:
        raw_text, thumbnail_url = await download_and_transcribe(input_text.strip())
    elif source_type == SourceType.web:
        raw_text, thumbnail_url = await scrape_url(input_text.strip())
    else:
        raw_text = input_text

    recipe_data = await extract_recipe_with_llm(raw_text)

    if "error" in recipe_data:
        raise ValueError(recipe_data["error"])

    recipe_data["source_url"] = input_text.strip() if source_type != SourceType.text else None
    recipe_data["source_type"] = source_type
    recipe_data["thumbnail_url"] = recipe_data.get("thumbnail_url") or thumbnail_url

    # Duplicate detection
    if db and recipe_data.get("title"):
        similar = await _find_similar(recipe_data["title"], db)
        if similar:
            recipe_data["similar_recipe_id"] = similar

    return recipe_data


async def _find_similar(title: str, db) -> str | None:
    from sqlalchemy import select
    from ..models.recipe import Recipe
    words = [w for w in title.lower().split() if len(w) > 3]
    if not words:
        return None
    from sqlalchemy import or_
    conditions = [Recipe.title.ilike(f"%{w}%") for w in words[:3]]
    q = select(Recipe.id, Recipe.title).where(or_(*conditions)).limit(5)
    result = await db.execute(q)
    rows = result.all()
    for row_id, row_title in rows:
        overlap = sum(1 for w in words if w in row_title.lower())
        if overlap >= max(2, len(words) // 2):
            return str(row_id)
    return None
