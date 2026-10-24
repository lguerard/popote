import asyncio
import json
import logging
import re
from typing import Awaitable, Callable

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
    {"quantity": "200", "unit": "g", "name": "farine", "notes": "", "section": ""},
    {"quantity": "2", "unit": "c. à s.", "name": "huile d'olive", "notes": "", "section": ""},
    {"quantity": "1", "unit": "", "name": "oignon", "notes": "émincé", "section": ""}
  ],
  "steps": ["Préchauffer le four à 180 °C.", "Mélanger la farine et le sucre."],
  "tags": ["facile", "végétarien"]
}

Règles :
- Tout rédiger en français (traduire si besoin). "language" = langue d'origine du texte ("fr", "en"…).
- Ingrédients : TOUS, y compris ceux cités seulement dans les étapes. Quantité, unité et nom séparés ; les précisions (« émincé », « à température ambiante ») vont dans notes.
- section : partie de la recette à laquelle appartient l'ingrédient quand le texte la sépare en parties (« Pâte », « Garniture », « Sauce », « Glaçage ») ; "" sinon. Un ingrédient utilisé dans deux parties apparaît deux fois.
- Étapes : dans l'ordre, une action principale par étape, complètes mais concises, sans numéro au début.
- prep_time et cook_time : entiers en minutes ; servings : entier (nombre de portions).
- Valeur inconnue ou absente : "" pour un texte, 0 pour un nombre. Ne jamais inventer.
- category : UNE valeur parmi petit-déjeuner, entrée, plat, dessert, snack, boisson, sauce, apéritif, soupe.
- tags : 2 à 5 mots-clés courts (régime, difficulté, technique, ingrédient principal).
- Ignorer publicités, commentaires, navigation et autres recettes suggérées.
- Des ingrédients sans étapes (étapes seulement montrées dans la vidéo) SONT une recette : "found": true, "steps": [].
- {"found": false} uniquement si le texte ne donne ni ingrédients ni étapes.
"""

# Dernier recours quand le contenu ne contient pas de recette détaillée :
# nom de plat seul (« lasagnes »), reel en musique avec juste « Pasta alla
# vodka 🍝 » en légende, photo d'un plat… Plutôt qu'un échec, l'IA propose
# une recette classique du plat, signalée comme reconstituée.
RECONSTRUCT_PROMPT = (
    "Tu es un chef cuisinier expert chargé de proposer UNE recette à partir d'un texte "
    "qui évoque un plat sans en donner la recette détaillée.\n"
    "Réponds UNIQUEMENT avec un objet JSON valide, sans markdown ni commentaire.\n\n"
    + SYSTEM_PROMPT[SYSTEM_PROMPT.index("Format attendu"):SYSTEM_PROMPT.index("Règles :")]
) + """Règles :
- Le texte ne contient PAS de recette détaillée, mais il peut nommer ou décrire un plat (titre, légende, hashtags, ingrédients épars, simple nom de plat tapé par l'utilisateur).
- Identifie ce plat et rédige une recette classique, réaliste et complète pour le réaliser : ingrédients avec quantités, étapes dans l'ordre.
- Reprends tout ce que le texte donne (ingrédients cités, portions, temps, technique) et complète le reste de façon plausible.
- Tout rédiger en français. "language" = langue d'origine du texte.
- prep_time et cook_time : entiers en minutes ; servings : entier.
- category : UNE valeur parmi petit-déjeuner, entrée, plat, dessert, snack, boisson, sauce, apéritif, soupe.
- tags : 2 à 5 mots-clés courts.
- Si le texte ne permet d'identifier AUCUN plat, boisson ou préparation culinaire : {"found": false}.
"""

# Photo d'une recette (page de livre, fiche manuscrite, capture d'écran) :
# lue directement par le modèle de vision, sans passer par un texte OCR
# intermédiaire qui perdait la mise en page (colonnes, quantités en marge).
IMAGE_RECIPE_PROMPT = (
    "Tu es un assistant culinaire expert chargé d'extraire UNE recette d'une photo : "
    "page de livre ou de magazine, fiche manuscrite, capture d'écran, emballage.\n"
    + SYSTEM_PROMPT[SYSTEM_PROMPT.index("Réponds UNIQUEMENT"):]
    + "- Recopie ce qui est écrit sur la photo, sans rien inventer ; une écriture illisible est ignorée.\n"
    "- Photo d'un plat, d'un menu ou d'un produit sans recette écrite : {\"found\": false}.\n"
)

RECONSTRUCTED_NOTICE = "Recette reconstituée par l'IA : quantités et étapes à vérifier."


class UnreadableResponse(ValueError):
    """Réponse du modèle qui n'est pas du JSON exploitable."""


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
                    "section": {"type": "string"},
                },
                "required": ["quantity", "unit", "name", "notes", "section"],
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

# Tokens générés au plus, par tâche. Garde-fou : en mode JSON certains
# modèles bouclent sur des espaces jusqu'au délai maximal au lieu de
# s'arrêter.
NUM_PREDICT_RECIPE = 3072
# Une phrase de 35 mots : 120 tokens coupaient parfois la phrase en plein
# milieu (mots longs, tokenizer différent selon le modèle).
NUM_PREDICT_DESCRIPTION = 200
NUM_PREDICT_NUTRITION = 256
# Transcription du texte d'une image : une page de recette entière.
NUM_PREDICT_TRANSCRIPTION = 2048
# Lecture d'une photo : chargement de l'image + génération de la recette.
# Assez court pour laisser au repli (OCR Tesseract puis LLM texte) le temps
# de finir dans le budget de 5 minutes de l'extraction.
_VISION_TIMEOUT_SECONDS = 150
# Côté le plus long d'une photo envoyée au modèle. Les modèles de vision
# réduisent eux-mêmes l'image (~900 px pour Gemma) ; envoyer 12 Mpx ne fait
# qu'allonger l'envoi, et Claude refuse les images de plus de 5 Mo.
_MAX_IMAGE_SIDE = 2000


def ollama_options(num_predict: int, temperature: float = 0) -> dict:
    """Options communes à TOUS les appels Ollama de l'appli.

    num_ctx est toujours le même (settings.ollama_num_ctx) : Ollama recharge
    entièrement le modèle dès qu'une requête demande une autre fenêtre de
    contexte que celle avec laquelle il est chargé — plusieurs secondes
    perdues, et un pic de VRAM, à chaque alternance extraction/description.
    La même valeur doit être utilisée par les autres clients de ce serveur
    Ollama (Paperless…), voir OLLAMA_CONTEXT_LENGTH dans docker-compose.yml.
    """
    return {
        "temperature": temperature,
        # Sans ça, Ollama travaille sur 2048-4096 tokens et TRONQUE en
        # silence une page longue (souvent la partie recette, en bas) :
        # d'où certains « Aucune recette trouvée ».
        "num_ctx": settings.ollama_num_ctx,
        "num_predict": num_predict,
    }


def ollama_chat_request(
    messages: list[dict], *, num_predict: int, model: str | None = None,
    temperature: float = 0, format: dict | str | None = None,
) -> dict:
    """Corps de requête /api/chat commun (extraction, photo, nutrition, description).

    "think": False : les modèles à raisonnement (Gemma 4, Qwen 3…) écrivent
    sinon des centaines de tokens de réflexion avant de répondre, ce qui
    multiplie la durée d'une extraction sans gain mesurable pour recopier
    une recette dans un schéma.
    """
    body = {
        "model": model or settings.ollama_model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": ollama_options(num_predict, temperature),
    }
    if format is not None:
        body["format"] = format
    return body


def build_ollama_request(
    text: str, model: str | None = None, *, use_schema: bool = True,
    system: str = SYSTEM_PROMPT, temperature: float = 0,
) -> dict:
    """Corps de requête /api/chat, partagé avec l'évaluation des modèles (app/scripts/model_eval)."""
    # Déterministe : la même page donne la même recette (un peu de hasard
    # seulement pour réessayer après une réponse illisible).
    return ollama_chat_request(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Voici le texte à analyser :\n\n{text[:_MAX_INPUT_CHARS]}"},
        ],
        model=model, temperature=temperature, num_predict=NUM_PREDICT_RECIPE,
        format=RECIPE_JSON_SCHEMA if use_schema else "json",
    )


def prepare_image(image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
    """Photo réduite (JPEG) si elle est inutilement grande, sinon telle quelle."""
    try:
        import io

        from PIL import Image, ImageOps

        image = Image.open(io.BytesIO(image_bytes))
        if max(image.size) <= _MAX_IMAGE_SIDE and len(image_bytes) <= 4 * 1024 * 1024:
            return image_bytes, mime_type
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((_MAX_IMAGE_SIDE, _MAX_IMAGE_SIDE))
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=90)
        return out.getvalue(), "image/jpeg"
    except Exception:
        # Pillow absent ou format qu'il ne lit pas : le modèle s'en charge.
        return image_bytes, mime_type


def build_vision_request(
    image_b64: str, prompt: str, *, system: str | None = None, num_predict: int,
    format: dict | str | None = None, temperature: float = 0, model: str | None = None,
) -> dict:
    """Corps /api/chat avec une image, pour le modèle de vision configuré.

    ``model`` remplace le modèle configuré : l'évaluation des modèles
    (app/scripts/model_eval) envoie ainsi exactement la requête de la prod.
    """
    messages = [{"role": "system", "content": system}] if system else []
    messages.append({"role": "user", "content": prompt, "images": [image_b64]})
    return ollama_chat_request(
        messages, model=model or settings.vision_model, num_predict=num_predict,
        temperature=temperature, format=format,
    )


def build_image_recipe_request(
    image_b64: str, *, use_schema: bool = True, temperature: float = 0, model: str | None = None,
) -> dict:
    return build_vision_request(
        image_b64, "Voici la photo à analyser.", system=IMAGE_RECIPE_PROMPT,
        num_predict=NUM_PREDICT_RECIPE, temperature=temperature,
        format=RECIPE_JSON_SCHEMA if use_schema else "json", model=model,
    )


def parse_llm_content(content: str) -> dict:
    """Réponse brute du modèle → recette normalisée, ou {"error": ...}."""
    try:
        data = _parse_json(content)
    except ValueError:
        logger.warning("Réponse du modèle illisible : %.300s", content)
        raise UnreadableResponse("Le modèle a renvoyé une réponse illisible, réessaie l'extraction.")
    if not isinstance(data, dict) or "error" in data:
        return {"error": "Aucune recette trouvée"}
    said_none = data.pop("found", None) is False
    _normalize_recipe_shape(data)
    if not data["ingredients"] and not data["steps"]:
        return {"error": "Aucune recette trouvée"}
    if said_none and len(data["ingredients"]) < 2:
        return {"error": "Aucune recette trouvée"}
    # Les petits modèles répondent souvent « pas de recette » tout en ayant
    # rempli les ingrédients (légende avec ingrédients, étapes seulement
    # montrées dans la vidéo) : ce qui a été extrait fait foi.
    return data


async def extract_recipe_with_llm(text: str) -> dict:
    return await _ask_model(text, SYSTEM_PROMPT)


async def reconstruct_recipe_with_llm(text: str) -> dict:
    """Recette classique du plat évoqué par un contenu sans recette détaillée."""
    data = await _ask_model(text, RECONSTRUCT_PROMPT)
    if "error" not in data:
        description = data.get("description")
        data["description"] = f"{RECONSTRUCTED_NOTICE} {description}" if description else RECONSTRUCTED_NOTICE
        data["tags"] = recipe_parsing.normalize_tags(["à vérifier"] + data.get("tags", []))
    return data


async def extract_recipe_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Photo d'une recette → recette normalisée en UN appel au modèle de vision.

    Renvoie {"error": ...} si la photo ne montre pas de recette écrite (plat,
    menu…) ; lève si le modèle ne répond pas ou n'accepte pas les images :
    l'appelant se rabat alors sur l'OCR.
    """
    import base64

    image_bytes, mime_type = prepare_image(image_bytes, mime_type)

    async def ask(temperature: float) -> dict:
        if settings.use_claude:
            return await _extract_claude_image(image_bytes, mime_type)
        return await _extract_ollama_image(base64.standard_b64encode(image_bytes).decode(), temperature)

    return await _retry_unreadable(ask)


async def _ask_model(text: str, system: str) -> dict:
    async def ask(temperature: float) -> dict:
        if settings.use_claude:
            return await _extract_claude(text, system)
        return await _extract_ollama(text, system, temperature)

    return await _retry_unreadable(ask)


async def _retry_unreadable(ask: Callable[[float], Awaitable[dict]]) -> dict:
    """Une réponse illisible (JSON tronqué, texte libre) est réessayée une
    fois avec un peu de hasard : à température 0, le même appel redonnerait
    exactement la même réponse."""
    for attempt, temperature in enumerate((0, 0.4)):
        try:
            return await ask(temperature)
        except UnreadableResponse:
            if attempt:
                raise
            logger.info("Réponse illisible, nouvel essai")


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
    section = _none_if_blank(item.get("section")) if isinstance(item, dict) else None
    if section:
        ingredient["section"] = section.rstrip(" :")[: recipe_parsing.MAX_SECTION_LENGTH]
    return ingredient if ingredient.get("name") else None


def _normalize_recipe_shape(data: dict) -> None:
    """Remet toute réponse de modèle dans la forme exacte attendue par l'API.

    Même avec un schéma imposé (et a fortiori sans, pour Claude ou un vieil
    Ollama), rien ne garantit la forme : une seule recette mal formée
    enregistrée casse ensuite la liste entière, donc on normalise tout.
    """
    ingredients, seen = [], set()
    for item in recipe_parsing.as_list(data.get("ingredients")):
        ingredient = _normalize_ingredient(item)
        key = ingredient and (
            ingredient["name"].lower(), ingredient["quantity"], ingredient["unit"], ingredient.get("section"),
        )
        if ingredient and key not in seen:
            seen.add(key)
            ingredients.append(ingredient)
    data["ingredients"] = ingredients

    steps = []
    for item in recipe_parsing.as_list(data.get("steps")):
        text = item.get("text") if isinstance(item, dict) else item
        step = recipe_parsing.clean_step(text or "")
        section = _none_if_blank(item.get("section")) if isinstance(item, dict) else None
        if step:
            steps.append((section and section[: recipe_parsing.MAX_SECTION_LENGTH], step))
    data["steps"] = recipe_parsing.steps_from_pairs(steps)

    # 0 = « inconnu » dans le schéma ; « 15 minutes » en texte libre sans schéma.
    for key in ("prep_time", "cook_time"):
        data[key] = recipe_parsing.parse_duration_minutes(data.get(key))
    data["servings"] = recipe_parsing.parse_int(data.get("servings"))

    # Bornes des colonnes en base : un titre trop long ferait échouer l'enregistrement.
    data["title"] = (_none_if_blank(data.get("title")) or "Recette sans titre")[:500]
    data["description"] = _none_if_blank(data.get("description"))
    language = _none_if_blank(data.get("language"))
    data["language"] = language.lower()[:5] if language else None
    data["category"] = recipe_parsing.normalize_category(data.get("category"), data["title"])
    data["tags"] = recipe_parsing.normalize_tags(data.get("tags"))


# Part du modèle Ollama tournant sur CPU faute de VRAM (None : inconnu).
# Mesurée pendant les extractions, reprise dans le message d'échec.
cpu_offload_ratio: float | None = None
# Suggéré quand le modèle configuré déborde du GPU : texte seul, ~5 Go.
_LIGHT_FALLBACK_MODEL = "qwen2.5:7b"
_OFFLOAD_CHECK_DELAY_SECONDS = 15


def offload_ratio(ps: dict, model: str) -> float | None:
    """Part du modèle hors GPU d'après /api/ps (0 = tout sur GPU)."""
    for entry in ps.get("models") or []:
        name = entry.get("name") or entry.get("model") or ""
        if name == model or name.split(":latest")[0] == model:
            size, vram = entry.get("size") or 0, entry.get("size_vram") or 0
            return max(0.0, 1 - vram / size) if size else None
    return None


def offload_hint() -> str:
    """Explication à ajouter à un échec par délai dépassé, si elle est connue."""
    if not cpu_offload_ratio or cpu_offload_ratio < 0.02:
        return ""
    return (
        f"Le modèle {settings.ollama_model} ne tient pas sur le GPU "
        f"({cpu_offload_ratio:.0%} tourne sur le processeur) : libérer le GPU "
        f"(autres services), prendre un modèle plus léger (OLLAMA_MODEL={_LIGHT_FALLBACK_MODEL}) "
        "ou baisser OLLAMA_NUM_CTX."
    )


async def _check_offload(model: str | None = None) -> None:
    """Mesure, une fois le modèle chargé, s'il déborde du GPU sur le CPU.

    Un modèle trop gros pour la VRAM est chargé en partie sur le CPU sans
    la moindre erreur : l'analyse passe de quelques secondes à plusieurs
    minutes, et rien ne l'explique dans les logs.
    """
    global cpu_offload_ratio
    await asyncio.sleep(_OFFLOAD_CHECK_DELAY_SECONDS)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            ps = (await client.get(f"{settings.ollama_base_url}/api/ps")).json()
    except Exception:
        return
    model = model or settings.ollama_model
    ratio = offload_ratio(ps, model)
    if ratio is None:
        return
    cpu_offload_ratio = ratio
    if ratio >= 0.02:
        logger.warning(
            "Le modèle %s déborde du GPU : %.0f%% tourne sur le processeur, "
            "l'analyse sera très lente. Libérer le GPU (autres services), prendre "
            "un modèle plus léger (OLLAMA_MODEL=%s) ou baisser OLLAMA_NUM_CTX "
            "(actuellement %d).",
            model, ratio * 100, _LIGHT_FALLBACK_MODEL, settings.ollama_num_ctx,
        )


async def _extract_ollama(text: str, system: str = SYSTEM_PROMPT, temperature: float = 0) -> dict:
    checker = asyncio.create_task(_check_offload())
    try:
        return await _chat_ollama(text, system, temperature)
    finally:
        checker.cancel()


def _ollama_error(resp: httpx.Response) -> str:
    """Message d'erreur renvoyé par Ollama ({"error": "..."}), sinon le corps brut."""
    try:
        body = resp.json()
    except ValueError:
        return resp.text
    return str(body.get("error") or body) if isinstance(body, dict) else str(body)


def _is_format_error(resp: httpx.Response) -> bool:
    """Ce 400 vient-il du `format` (schéma JSON refusé) et non d'autre chose ?

    Un vieil Ollama répond par exemple « json: cannot unmarshal object into
    Go struct field ChatRequest.format of type string » ou « invalid
    format ». Un 400 sans rapport (contexte trop long, image illisible,
    option inconnue…) ne doit PAS désactiver le schéma pour toute la vie du
    processus : les extractions suivantes perdraient les sorties
    structurées sans raison.
    """
    message = _ollama_error(resp).lower()
    return "format" in message or "schema" in message


async def post_ollama_chat(
    client: httpx.AsyncClient, make_body: Callable[[bool], dict],
) -> httpx.Response:
    """POST /api/chat, avec repli sur format="json" si le schéma est refusé.

    make_body(use_schema) construit la requête. Le repli n'est retenu pour
    les appels suivants que s'il a réussi : sinon le 400 venait d'ailleurs.
    """
    global _schema_supported
    url = f"{settings.ollama_base_url}/api/chat"
    resp = await client.post(url, json=make_body(_schema_supported))
    if resp.status_code == 400 and _schema_supported and _is_format_error(resp):
        logger.warning(
            "Ollama refuse le schéma JSON (%s) — repli sur format=json. "
            "Mettre à jour l'image ollama pour les sorties structurées.", _ollama_error(resp)[:200],
        )
        resp = await client.post(url, json=make_body(False))
        if resp.is_success:
            _schema_supported = False
    if resp.status_code == 400:
        raise RuntimeError(f"Ollama a refusé la requête : {_ollama_error(resp)[:300]}")
    resp.raise_for_status()
    return resp


async def _chat_ollama(text: str, system: str = SYSTEM_PROMPT, temperature: float = 0) -> dict:
    try:
        async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT_SECONDS) as client:
            resp = await post_ollama_chat(client, lambda use_schema: build_ollama_request(
                text, use_schema=use_schema, system=system, temperature=temperature,
            ))
            return parse_llm_content(resp.json()["message"]["content"])
    except httpx.TimeoutException:
        # httpx.TimeoutException se transforme souvent en message vide
        # (str(e) == ""), ce qui laissait error_msg vide en base — "Extraction
        # échouée" sans la moindre raison affichée.
        raise RuntimeError(
            f"Le modèle Ollama {settings.ollama_model} n'a pas répondu en "
            f"{_OLLAMA_TIMEOUT_SECONDS}s. "
            + (offload_hint() or "Il est peut-être surchargé (machine occupée…).")
        )


async def _extract_ollama_image(image_b64: str, temperature: float = 0) -> dict:
    checker = asyncio.create_task(_check_offload(settings.vision_model))
    try:
        async with httpx.AsyncClient(timeout=_VISION_TIMEOUT_SECONDS) as client:
            resp = await post_ollama_chat(client, lambda use_schema: build_image_recipe_request(
                image_b64, use_schema=use_schema, temperature=temperature,
            ))
            return parse_llm_content(resp.json()["message"]["content"])
    except httpx.TimeoutException:
        raise RuntimeError(
            f"Le modèle de vision {settings.vision_model} n'a pas lu la photo en "
            f"{_VISION_TIMEOUT_SECONDS}s."
        )
    finally:
        checker.cancel()


# Plafonds généreux : la réflexion adaptative des modèles Claude récents
# compte dans max_tokens, une limite serrée tronquait la réponse.
CLAUDE_MAX_TOKENS = 8192
CLAUDE_FAST_MAX_TOKENS = 2048


def claude_image_block(image_bytes: bytes, mime_type: str) -> dict:
    import base64

    return {"type": "image", "source": {
        "type": "base64", "media_type": mime_type,
        "data": base64.standard_b64encode(image_bytes).decode(),
    }}


def claude_request(
    content: str | list, *, system: str | None = None, fast: bool = False,
) -> dict:
    """Paramètres de messages.create, communs à tous les appels Claude.

    Un seul réglage de modèle (CLAUDE_MODEL, ou CLAUDE_FAST_MODEL pour les
    tâches courtes). Ni temperature, ni top_p, ni top_k : l'API les refuse
    désormais.
    """
    params = {
        "model": settings.claude_fast_model if fast else settings.claude_model,
        "max_tokens": CLAUDE_FAST_MAX_TOKENS if fast else CLAUDE_MAX_TOKENS,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        params["system"] = system
    return params


def claude_text(message) -> str:
    """Texte de la réponse : seulement les blocs « text ».

    Avec la réflexion adaptative, le premier bloc peut être un bloc
    « thinking » vide : content[0].text n'est alors pas la réponse.
    """
    return "".join(
        getattr(block, "text", "") or "" for block in message.content
        if getattr(block, "type", None) == "text"
    )


async def ask_claude(content: str | list, *, system: str | None = None, fast: bool = False) -> str:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
    message = await client.messages.create(**claude_request(content, system=system, fast=fast))
    return claude_text(message)


async def _extract_claude_image(image_bytes: bytes, mime_type: str) -> dict:
    return parse_llm_content(await ask_claude(
        [claude_image_block(image_bytes, mime_type), {"type": "text", "text": "Voici la photo à analyser."}],
        system=IMAGE_RECIPE_PROMPT,
    ))


async def _extract_claude(text: str, system: str = SYSTEM_PROMPT) -> dict:
    return parse_llm_content(await ask_claude(
        f"Voici le texte à analyser :\n\n{text[:30000]}", system=system,
    ))


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


def _full_model_name(name: str) -> str:
    """« gemma4 » et « gemma4:latest » désignent le même modèle pour Ollama."""
    name = name.strip()
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


def model_is_installed(model: str, installed: list[str]) -> bool:
    """Correspondance exacte (au :latest implicite près).

    Une simple sous-chaîne prenait « gemma4:12b-it-qat » ou
    « qwen2.5:7b-instruct » pour le modèle demandé : il n'était alors
    jamais téléchargé, et chaque extraction échouait sur « model not found ».
    """
    wanted = _full_model_name(model)
    return any(_full_model_name(name) == wanted for name in installed)


def _ollama_models() -> list[str]:
    """Modèles Ollama utilisés par l'appli : un seul, sauf OLLAMA_VISION_MODEL distinct."""
    return list(dict.fromkeys([settings.ollama_model, settings.vision_model]))


async def ensure_model_available():
    """Pull Ollama model if not present."""
    if settings.use_claude:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            models = [m.get("model") or m.get("name") or "" for m in resp.json().get("models", [])]
        for model in _ollama_models():
            if model_is_installed(model, models):
                continue
            logger.info("Téléchargement du modèle Ollama %s…", model)
            # ~8 Go : laisser largement le temps du téléchargement
            async with httpx.AsyncClient(timeout=3600) as pull_client:
                resp = await pull_client.post(
                    f"{settings.ollama_base_url}/api/pull",
                    json={"model": model, "stream": False},
                )
                resp.raise_for_status()
            logger.info("Modèle %s prêt", model)
    except Exception:
        logger.exception(
            "Impossible de vérifier/télécharger le modèle Ollama %s — "
            "les extractions échoueront tant qu'il n'est pas disponible",
            " / ".join(_ollama_models()),
        )


# ---------------------------------------------------------------------------
# Description visuelle du plat, pour la génération d'image
# ---------------------------------------------------------------------------

IMAGE_DESCRIPTION_PROMPT = """You write prompts for a text-to-image model that makes food photos.
From the recipe below (often written in French), describe in English what the FINISHED dish looks like when it is served: the food itself, its colors and textures, what it is served in (plate, bowl, glass, jar, pan…), and one or two visible garnishes.
Rules: only mention what is visible in the finished dish (no raw ingredients that were cooked or blended away), no people, no text, no brands. One sentence, at most 35 words. Reply with the sentence only."""

_IMAGE_DESCRIPTION_TIMEOUT_SECONDS = 90


def image_description_input(
    title: str, description: str | None, category: str | None,
    ingredients: list | None, steps: list | None,
) -> str:
    """Ce que le LLM voit de la recette : les dernières étapes disent souvent
    comment le plat est dressé (verrines, parsemer de…)."""
    names = [
        str(i.get("name")).strip() for i in recipe_parsing.as_list(ingredients)
        if isinstance(i, dict) and i.get("name")
    ][:15]
    texts = [
        str(s.get("text") if isinstance(s, dict) else s).strip() for s in recipe_parsing.as_list(steps)
    ]
    parts = [f"Titre : {title}"]
    if category:
        parts.append(f"Catégorie : {category}")
    if description:
        parts.append(f"Description : {str(description)[:300]}")
    if names:
        parts.append("Ingrédients : " + ", ".join(names))
    if texts:
        parts.append("Dernières étapes : " + " ".join(texts[-3:])[:600])
    return "\n".join(parts)


def clean_image_description(text: str) -> str:
    """Une seule phrase anglaise, sans guillemets ni préambule, bornée en longueur."""
    text = " ".join((text or "").split())
    text = re.sub(r"^(?:here is|prompt|description)\b[^:]*:\s*", "", text, flags=re.I)
    text = text.strip(" \"'“”`*")
    words = text.split()
    if len(words) > 45:
        text = " ".join(words[:45])
    return text.rstrip(" ,;")


def build_description_request(
    recipe: str, *, model: str | None = None, temperature: float = 0.2,
) -> dict:
    """Corps /api/chat de la description du plat, partagé avec l'évaluation des modèles."""
    return ollama_chat_request(
        [
            {"role": "system", "content": IMAGE_DESCRIPTION_PROMPT},
            {"role": "user", "content": recipe},
        ],
        model=model, temperature=temperature, num_predict=NUM_PREDICT_DESCRIPTION,
    )


async def describe_dish_for_image(
    title: str, description: str | None, category: str | None,
    ingredients: list | None, steps: list | None,
) -> str:
    """Courte description anglaise de l'apparence du plat servi.

    Les modèles d'image comprennent mal le français et ne lisent que 77
    tokens : un titre français suivi d'une liste d'ingrédients bruts
    remplissait tout, et le plat généré ne ressemblait pas à la recette.
    """
    recipe = image_description_input(title, description, category, ingredients, steps)
    if settings.use_claude:
        return clean_image_description(await ask_claude(recipe, system=IMAGE_DESCRIPTION_PROMPT, fast=True))
    async with httpx.AsyncClient(timeout=_IMAGE_DESCRIPTION_TIMEOUT_SECONDS) as client:
        resp = await client.post(f"{settings.ollama_base_url}/api/chat", json=build_description_request(recipe))
        resp.raise_for_status()
        return clean_image_description(resp.json()["message"]["content"])


async def unload_ollama_model() -> None:
    """Libère la VRAM occupée par le modèle Ollama (rechargé à la demande).

    Le modèle occupe presque tout le GPU (OLLAMA_KEEP_ALIVE) : sans cela,
    Whisper et le générateur d'image retombaient sur le CPU, lents. La
    prochaine extraction le recharge en quelques secondes. Le modèle de
    vision est déchargé aussi s'il est distinct (OLLAMA_VISION_MODEL).
    """
    if settings.use_claude:
        return
    async with httpx.AsyncClient(timeout=30) as client:
        for model in _ollama_models():
            await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={"model": model, "keep_alive": 0},
            )
