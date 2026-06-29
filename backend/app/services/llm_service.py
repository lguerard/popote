import json
import re
import httpx
from ..config import settings

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
    if settings.use_claude:
        return await _extract_claude(text)
    return await _extract_ollama(text)


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
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            models = [m["name"] for m in resp.json().get("models", [])]
            if not any(settings.ollama_model in m for m in models):
                # Fire-and-forget pull (can take minutes)
                async with httpx.AsyncClient(timeout=600) as pull_client:
                    await pull_client.post(
                        f"{settings.ollama_base_url}/api/pull",
                        json={"name": settings.ollama_model, "stream": False},
                    )
        except Exception:
            pass
