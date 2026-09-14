import json
import logging
import re
import httpx
from ..config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un assistant culinaire expert.
À partir d'un texte (transcription vidéo, page web ou texte brut), extrais les informations d'une recette de cuisine.
Réponds UNIQUEMENT avec un JSON valide, sans markdown, sans explication.

Structure JSON attendue:
{
  "title": "Nom de la recette",
  "description": "Brève description (1-2 phrases)",
  "language": "fr",
  "category": "plat",
  "servings": 4,
  "prep_time": 15,
  "cook_time": 30,
  "ingredients": [
    {"quantity": "200", "unit": "g", "name": "farine", "notes": null}
  ],
  "steps": [
    {"order": 1, "text": "Préchauffer le four à 180°C."}
  ],
  "tags": ["facile", "végétarien"]
}

Règles:
- Traduis tout en français
- prep_time et cook_time en minutes (null si inconnu)
- servings: nombre de portions (null si inconnu)
- quantity: string (peut être une fraction comme "1/2")
- category: UNE SEULE valeur parmi: petit-déjeuner, entrée, plat, dessert, snack, boisson, sauce, apéritif, soupe
- tags: 2-5 mots-clés descriptifs (difficulté, régime alimentaire, technique, ingrédient principal…)
- Si le texte ne contient pas de recette, retourne {"error": "Aucune recette trouvée"}
"""


async def extract_recipe_with_llm(text: str) -> dict:
    data = await _extract_claude(text) if settings.use_claude else await _extract_ollama(text)
    if "error" not in data:
        _normalize_recipe_shape(data)
    return data


def _normalize_recipe_shape(data: dict) -> None:
    """Coerce ingredients/steps into the objects the API expects.

    Models — especially smaller local ones — don't always follow the
    structured schema in the prompt and sometimes return a flat list of
    strings instead. Saved as-is, a single malformed recipe like that
    breaks the response validation for the whole recipe list, not just
    itself, so normalize defensively rather than trust the shape.
    """
    ingredients = data.get("ingredients")
    if isinstance(ingredients, list):
        data["ingredients"] = [
            item if isinstance(item, dict)
            else {"quantity": None, "unit": None, "name": str(item), "notes": None}
            for item in ingredients
        ]

    steps = data.get("steps")
    if isinstance(steps, list):
        normalized_steps = []
        for i, item in enumerate(steps, 1):
            if isinstance(item, dict):
                item.setdefault("order", i)
                normalized_steps.append(item)
            else:
                normalized_steps.append({"order": i, "text": str(item)})
        data["steps"] = normalized_steps

    # Meme chose pour des champs numeriques renvoyes en texte libre
    # ("15 minutes" au lieu de 15) : la colonne Postgres est un entier,
    # une string y passe telle quelle jusqu'au crash au commit.
    for key in ("prep_time", "cook_time", "servings"):
        if key in data and not isinstance(data[key], (int, type(None))):
            data[key] = _coerce_int(data[key])

    tags = data.get("tags")
    if isinstance(tags, list):
        data["tags"] = [str(t) for t in tags if t is not None]


def _coerce_int(value) -> int | None:
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


async def _extract_ollama(text: str) -> dict:
    prompt = f"Voici le texte à analyser:\n\n{text[:12000]}"
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
            },
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        return _parse_json(content)


async def _extract_claude(text: str) -> dict:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Voici le texte à analyser:\n\n{text[:30000]}"}],
    )
    return _parse_json(message.content[0].text)


def _parse_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown code blocks if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


async def ensure_model_available():
    """Pull Ollama model if not present."""
    if settings.use_claude:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            models = [m["name"] for m in resp.json().get("models", [])]
        if not any(settings.ollama_model in m for m in models):
            logger.info("Téléchargement du modèle Ollama %s…", settings.ollama_model)
            # ~5 Go : laisser largement le temps du téléchargement
            async with httpx.AsyncClient(timeout=3600) as pull_client:
                resp = await pull_client.post(
                    f"{settings.ollama_base_url}/api/pull",
                    json={"name": settings.ollama_model, "stream": False},
                )
                resp.raise_for_status()
            logger.info("Modèle %s prêt", settings.ollama_model)
    except Exception:
        logger.exception(
            "Impossible de vérifier/télécharger le modèle Ollama %s — "
            "les extractions échoueront tant qu'il n'est pas disponible",
            settings.ollama_model,
        )
