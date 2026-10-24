import httpx

from ..config import settings
from .llm_service import (
    NUM_PREDICT_NUTRITION, _parse_json, ask_claude, ollama_chat_request, post_ollama_chat,
)

NUTRITION_PROMPT = """Tu es un nutritionniste expert.
À partir d'une liste d'ingrédients et du nombre de portions, estime les valeurs nutritionnelles PAR PORTION.
Réponds UNIQUEMENT avec un JSON valide.

Format attendu:
{
  "calories": 450,
  "proteins": 25.5,
  "carbs": 55.0,
  "fat": 12.3,
  "fiber": 6.2
}

Toutes les valeurs sont en grammes sauf calories (kcal).
Si tu ne peux pas estimer une valeur, mets null.
"""

NUTRITION_FIELDS = ("calories", "proteins", "carbs", "fat", "fiber")

# Imposé à Ollama comme pour les recettes : plus de « 450 kcal » en texte
# ni de champ en trop. Nombres simples (pas d'union avec null, voir
# RECIPE_JSON_SCHEMA) : le modèle donne alors toujours une estimation.
NUTRITION_JSON_SCHEMA = {
    "type": "object",
    "properties": {field: {"type": "number"} for field in NUTRITION_FIELDS},
    "required": list(NUTRITION_FIELDS),
}

_OLLAMA_TIMEOUT_SECONDS = 60


def nutrition_prompt(title: str, ingredients: list[dict], servings: int | None) -> str:
    """Message envoyé au modèle, partagé avec l'évaluation des modèles."""
    ing_text = "\n".join(
        f"- {i.get('quantity', '')} {i.get('unit', '')} {i['name']}".strip()
        for i in ingredients
    )
    return f"Recette: {title}\nPortions: {servings or '?'}\n\nIngrédients:\n{ing_text}"


async def analyze_nutrition(title: str, ingredients: list[dict], servings: int | None) -> dict:
    user_msg = nutrition_prompt(title, ingredients, servings)

    if settings.use_claude:
        return await _claude_nutrition(user_msg)
    return await _ollama_nutrition(user_msg)


def build_nutrition_request(prompt: str, use_schema: bool = True, model: str | None = None) -> dict:
    return ollama_chat_request(
        [
            {"role": "system", "content": NUTRITION_PROMPT},
            {"role": "user", "content": prompt},
        ],
        model=model,
        num_predict=NUM_PREDICT_NUTRITION,
        format=NUTRITION_JSON_SCHEMA if use_schema else "json",
    )


def parse_nutrition(text: str) -> dict:
    """Réponse brute du modèle → valeurs nutritionnelles (lève si illisible)."""
    return _parse(text)


async def _ollama_nutrition(prompt: str) -> dict:
    async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT_SECONDS) as client:
        resp = await post_ollama_chat(client, lambda use_schema: build_nutrition_request(prompt, use_schema))
        return _parse(resp.json()["message"]["content"])


async def _claude_nutrition(prompt: str) -> dict:
    return _parse(await ask_claude(prompt, system=NUTRITION_PROMPT, fast=True))


def _number(value) -> float | None:
    """Nombre positif arrondi, ou None (« 450 kcal », null, texte, négatif…)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.replace(",", ".").strip().split(" ")[0]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number < 0:  # NaN ou négatif
        return None
    return round(number, 1)


def _parse(text: str) -> dict:
    """Réponse du modèle → exactement les champs de NutritionOut.

    Même lecture tolérante que pour les recettes (bloc ```json```, phrase
    avant le JSON), puis seuls les champs attendus sont gardés, en nombres.
    """
    try:
        data = _parse_json(text)
    except ValueError:
        raise ValueError("Le modèle a renvoyé une estimation illisible, réessaie.")
    if not isinstance(data, dict):
        raise ValueError("Le modèle a renvoyé une estimation illisible, réessaie.")
    return {field: _number(data.get(field)) for field in NUTRITION_FIELDS}
