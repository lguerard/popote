import json
import re
import httpx
from ..config import settings

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


async def analyze_nutrition(title: str, ingredients: list[dict], servings: int | None) -> dict:
    ing_text = "\n".join(
        f"- {i.get('quantity', '')} {i.get('unit', '')} {i['name']}".strip()
        for i in ingredients
    )
    user_msg = f"Recette: {title}\nPortions: {servings or '?'}\n\nIngrédients:\n{ing_text}"

    if settings.use_claude:
        return await _claude_nutrition(user_msg)
    return await _ollama_nutrition(user_msg)


async def _ollama_nutrition(prompt: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": NUTRITION_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
            },
        )
        resp.raise_for_status()
        text = resp.json()["message"]["content"]
        return _parse(text)


async def _claude_nutrition(prompt: str) -> dict:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=NUTRITION_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse(msg.content[0].text)


def _parse(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)
