import json
import logging
import re

import httpx

from ..config import settings
from . import recipe_parsing

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un assistant culinaire expert chargé d'extraire UNE recette d'un texte : page web, transcription de vidéo, légende de publication ou texte collé.
Réponds UNIQUEMENT avec un objet JSON valide, sans markdown ni commentaire.

Format attendu :
{
  "found": true,
  "title": "Nom de la recette",
  "description": "Brève description (1-2 phrases)",
  "language": "fr",
  "category": "dessert",
  "servings": 4,
  "prep_time": 15,
  "cook_time": 30,
  "ingredients": [
    {"quantity": "200", "unit": "g", "name": "farine", "notes": ""},
    {"quantity": "2", "unit": "c. à s.", "name": "huile d'olive", "notes": ""},
    {"quantity": "1", "unit": "", "name": "oignon", "notes": "émincé"}
  ],
  "steps": ["Préchauffer le four à 180 °C.", "Mélanger la farine et le sucre."],
  "tags": ["facile", "végétarien"]
}

Règles :
- Tout rédiger en français (traduire si besoin). "language" = langue d'origine du texte ("fr", "en"…).
- Ingrédients : TOUS, y compris ceux cités seulement dans les étapes. Quantité, unité et nom séparés ; les précisions (« émincé », « à température ambiante ») vont dans notes.
- Étapes : dans l'ordre, une action principale par étape, complètes mais concises, sans numéro au début.
- prep_time et cook_time : entiers en minutes ; servings : entier (nombre de portions).
- Valeur inconnue ou absente : "" pour un texte, 0 pour un nombre. Ne jamais inventer.
- category : UNE valeur parmi petit-déjeuner, entrée, plat, dessert, snack, boisson, sauce, apéritif, soupe.
- tags : 2 à 5 mots-clés courts (régime, difficulté, technique, ingrédient principal).
- Ignorer publicités, commentaires, navigation et autres recettes suggérées.
- Si le texte ne contient aucune recette : {"found": false}.
"""

# Imposé à Ollama (sorties structurées) : le modèle ne peut plus produire
# des ingrédients en texte brut, « 15 minutes » au lieu de 15, une catégorie
# hors liste ou des champs inventés — autant de réponses qui faisaient
# échouer l'enregistrement. Types simples uniquement (pas d'unions avec null),
# pour rester compatible avec toutes les versions d'Ollama.
RECIPE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "language": {"type": "string"},
        "category": {"type": "string", "enum": list(recipe_parsing.CATEGORIES)},
        "servings": {"type": "integer"},
        "prep_time": {"type": "integer"},
        "cook_time": {"type": "integer"},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quantity": {"type": "string"},
                    "unit": {"type": "string"},
                    "name": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["quantity", "unit", "name", "notes"],
            },
        },
        "steps": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "found", "title", "description", "language", "category", "servings",
        "prep_time", "cook_time", "ingredients", "steps", "tags",
    ],
}

_MAX_INPUT_CHARS = 12000
# Aligné juste sous EXTRACTION_TIMEOUT_SECONDS (api/extract.py, 300s) pour
# que le budget global de 5 minutes s'applique réellement.
_OLLAMA_TIMEOUT_SECONDS = 280
# Passé à False si ce serveur Ollama refuse un schéma JSON comme `format`
# (versions antérieures à 0.5) : on retombe alors sur format="json".
_schema_supported = True


def build_ollama_request(text: str, model: str | None = None, *, use_schema: bool = True) -> dict:
    """Corps de requête /api/chat, partagé avec l'évaluation mensuelle des modèles."""
    return {
        "model": model or settings.ollama_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Voici le texte à analyser :\n\n{text[:_MAX_INPUT_CHARS]}"},
        ],
        "stream": False,
        "format": RECIPE_JSON_SCHEMA if use_schema else "json",
        "options": {
            # Déterministe : la même page donne la même recette.
            "temperature": 0,
            # Sans ça, Ollama travaille sur 2048-4096 tokens et TRONQUE en
            # silence une page longue (souvent la partie recette, en bas) :
            # d'où certains « Aucune recette trouvée ».
            "num_ctx": settings.ollama_num_ctx,
            # Garde-fou : en mode JSON certains modèles bouclent sur des
            # espaces jusqu'au délai maximal au lieu de s'arrêter.
            "num_predict": 3072,
        },
    }


def parse_llm_content(content: str) -> dict:
    """Réponse brute du modèle → recette normalisée, ou {"error": ...}."""
    try:
        data = _parse_json(content)
    except ValueError:
        logger.warning("Réponse du modèle illisible : %.300s", content)
        raise ValueError("Le modèle a renvoyé une réponse illisible, réessaie l'extraction.")
    if not isinstance(data, dict) or data.get("found") is False or "error" in data:
        return {"error": "Aucune recette trouvée"}
    data.pop("found", None)
    _normalize_recipe_shape(data)
    if not data["ingredients"] and not data["steps"]:
        return {"error": "Aucune recette trouvée"}
    return data


async def extract_recipe_with_llm(text: str) -> dict:
    if settings.use_claude:
        return await _extract_claude(text)
    return await _extract_ollama(text)


def _none_if_blank(value):
    if value is None:
        return None
    text = recipe_parsing.clean_text(value)
    return text or None


def _normalize_ingredient(item) -> dict | None:
    if isinstance(item, dict):
        ingredient = {
            "quantity": _none_if_blank(item.get("quantity")),
            "unit": recipe_parsing.canonical_unit(_none_if_blank(item.get("unit"))),
            "name": _none_if_blank(item.get("name")),
            "notes": _none_if_blank(item.get("notes")),
        }
        if ingredient["name"] and not ingredient["quantity"] and not ingredient["unit"]:
            # Ligne entière recopiée dans le nom (« 200 g de farine ») :
            # on la découpe nous-mêmes plutôt que de la laisser telle quelle.
            parsed = recipe_parsing.parse_ingredient_line(ingredient["name"])
            if parsed["quantity"] or parsed["unit"]:
                parsed["notes"] = ingredient["notes"] or parsed["notes"]
                ingredient = parsed
    else:
        ingredient = recipe_parsing.parse_ingredient_line(str(item))
    return ingredient if ingredient.get("name") else None


def _normalize_recipe_shape(data: dict) -> None:
    """Remet toute réponse de modèle dans la forme exacte attendue par l'API.

    Même avec un schéma imposé (et a fortiori sans, pour Claude ou un vieil
    Ollama), rien ne garantit la forme : une seule recette mal formée
    enregistrée casse ensuite la liste entière, donc on normalise tout.
    """
    ingredients, seen = [], set()
    for item in data.get("ingredients") or []:
        ingredient = _normalize_ingredient(item)
        key = ingredient and (ingredient["name"].lower(), ingredient["quantity"], ingredient["unit"])
        if ingredient and key not in seen:
            seen.add(key)
            ingredients.append(ingredient)
    data["ingredients"] = ingredients

    steps = []
    for item in data.get("steps") or []:
        text = item.get("text") if isinstance(item, dict) else item
        step = recipe_parsing.clean_step(text or "")
        if step:
            steps.append(step)
    data["steps"] = [{"order": i, "text": step} for i, step in enumerate(steps, 1)]

    # 0 = « inconnu » dans le schéma ; « 15 minutes » en texte libre sans schéma.
    for key in ("prep_time", "cook_time"):
        data[key] = recipe_parsing.parse_duration_minutes(data.get(key))
    data["servings"] = recipe_parsing.parse_int(data.get("servings"))

    data["title"] = _none_if_blank(data.get("title")) or "Recette sans titre"
    data["description"] = _none_if_blank(data.get("description"))
    language = _none_if_blank(data.get("language"))
    data["language"] = language.lower()[:5] if language else None
    data["category"] = recipe_parsing.normalize_category(data.get("category"), data["title"])
    tags = data.get("tags")
    data["tags"] = recipe_parsing.normalize_tags(tags if isinstance(tags, list) else [])


async def _extract_ollama(text: str) -> dict:
    global _schema_supported
    try:
        async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT_SECONDS) as client:
            url = f"{settings.ollama_base_url}/api/chat"
            resp = await client.post(url, json=build_ollama_request(text, use_schema=_schema_supported))
            if resp.status_code == 400 and _schema_supported:
                logger.warning(
                    "Ollama refuse le schéma JSON (%s) — repli sur format=json. "
                    "Mettre à jour l'image ollama pour les sorties structurées.", resp.text[:200],
                )
                _schema_supported = False
                resp = await client.post(url, json=build_ollama_request(text, use_schema=False))
            resp.raise_for_status()
            return parse_llm_content(resp.json()["message"]["content"])
    except httpx.TimeoutException:
        # httpx.TimeoutException se transforme souvent en message vide
        # (str(e) == ""), ce qui laissait error_msg vide en base — "Extraction
        # échouée" sans la moindre raison affichée.
        raise RuntimeError(
            f"Le modèle Ollama {settings.ollama_model} n'a pas répondu en "
            f"{_OLLAMA_TIMEOUT_SECONDS}s. Il est peut-être surchargé "
            "(GPU partagé avec la génération d'image, machine occupée…)."
        )


async def _extract_claude(text: str) -> dict:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Voici le texte à analyser :\n\n{text[:30000]}"}],
    )
    return parse_llm_content(message.content[0].text)


def _parse_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    if not text.startswith("{"):
        # Phrase d'introduction avant le JSON : on garde le premier objet.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
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
