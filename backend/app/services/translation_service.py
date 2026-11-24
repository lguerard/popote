"""Traduction du contenu des recettes pour l'affichage (comptes en anglais).

Sert aussi, dans l'autre sens, à l'extraction : une recette lue telle quelle
sur un site (données structurées) dans l'autre langue que celle du compte
est traduite avant d'être enregistrée (translate_recipe_content avec
source_lang/target_lang, voir extractor._in_account_language).

Les recettes sont enregistrées en français (l'extraction traduit tout, voir
SYSTEM_PROMPT dans llm_service.py). Un compte en anglais en voit une
traduction, faite à la première lecture puis gardée dans
``Recipe.translations`` : un cache, jamais une donnée de référence. Les
champs title/description/ingredients/steps/tags ne sont JAMAIS modifiés ici,
sinon le formulaire d'édition (qui les relit et les renvoie tels quels)
remplacerait l'original par sa traduction.

Fraîcheur : chaque traduction garde l'empreinte (source_hash) du contenu
qu'elle traduit. Une recette modifiée depuis (édition, réextraction) ne
correspond plus et sera retraduite à la prochaine lecture : rien à
invalider ailleurs. updated_at ne convient pas pour ça : un favori, une
note ou une vignette le changent aussi, et chacun relancerait un appel au
modèle pour un contenu identique.

Un seul processus uvicorn sert l'API (backend/entrypoint.sh) : le suivi des
traductions en cours tient dans un dictionnaire en mémoire, comme le verrou
de l'assistant.
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import update

from ..config import settings
from ..models.recipe import Recipe
from . import llm_service, recipe_parsing

logger = logging.getLogger(__name__)

# Seule autre langue de l'interface (users.language) : pas de système
# générique à N langues tant qu'il n'y en a pas d'autre.
SUPPORTED_LANGUAGES = {"en"}

# Langues entre lesquelles le contenu peut être traduit, dans un sens ou
# dans l'autre. L'affichage (SUPPORTED_LANGUAGES) ne traduit que vers
# l'anglais ; l'extraction traduit aussi vers le français une recette lue
# telle quelle sur un site anglophone (voir extractor._in_account_language).
TRANSLATION_LANGUAGES = ("fr", "en")

# Ce qui change d'un sens à l'autre : le nom des langues, les unités, les
# sections et les plats données en exemple. Le reste des consignes est commun.
_DIRECTIONS = {
    ("fr", "en"): {
        "source": "French",
        "target": "English",
        "units": (
            'with standard English cooking abbreviations: "c. à s." / "cuillère à soupe" → "tbsp", '
            '"c. à c." / "cuillère à café" → "tsp", "pincée" → "pinch", "gousse" → "clove", '
            '"sachet" → "packet", "verre" → "glass", "botte" → "bunch", "tranche" → "slice". '
            'Metric units stay metric ("g", "kg", "ml", "cl", "l") — never convert amounts.'
        ),
        "sections": '"Pâte" → "Dough", "Garniture" → "Filling", "Glaçage" → "Icing"',
        "dishes": '"Ratatouille", "Clafoutis"',
    },
    ("en", "fr"): {
        "source": "English",
        "target": "French",
        # Seul le MOT de l'unité est traduit, jamais la mesure : « cup »
        # devient « tasse » (comme le fait déjà recipe_parsing.canonical_unit
        # à la lecture d'un site), « oz » et « lb » restent tels quels.
        "units": (
            'with standard French cooking abbreviations: "tbsp" / "tablespoon" → "c. à s.", '
            '"tsp" / "teaspoon" → "c. à c.", "cup" → "tasse", "pinch" → "pincée", "clove" → "gousse", '
            '"packet" → "sachet", "can" → "boîte", "glass" → "verre", "bunch" → "botte", "slice" → "tranche". '
            'Every unit stays in its own measuring system ("g", "kg", "ml", "l", "oz", "lb", cups…): '
            "only the unit word is translated — never convert amounts and never switch to metric."
        ),
        "sections": '"Dough" → "Pâte", "Filling" → "Garniture", "Frosting" / "Icing" → "Glaçage"',
        "dishes": '"Brownies", "Cheesecake", "Coleslaw"',
    },
}

_PROMPT_TEMPLATE = """You are a professional culinary translator. Translate the recipe JSON below from {source} into natural, idiomatic {target} as used in {target}-language cookbooks.
Reply ONLY with a valid JSON object, no markdown, no comment, in exactly this format:
{{"title": "...", "description": "...", "ingredients": [{{"unit": "...", "name": "...", "notes": "...", "section": "..."}}], "steps": [{{"text": "...", "section": "..."}}], "tags": ["..."]}}

Rules:
- Translate the title, the description, every ingredient's unit, name, notes and section, every step's text and section, and every tag.
- Units must be translated too, {units}
- Section titles are translated too ({sections}).
- Keep EXACTLY the same number of ingredients, steps and tags, in the same order: never add, drop, merge, split or reorder anything. One output item per input item.
- Preserve meaning, temperatures, durations, numbers and quantities exactly as written inside the text. Quantities themselves are given for context only and are not part of the output.
- An empty string stays an empty string. Text that is already in {target} stays as it is.
- Proper nouns of dishes with no usual {target} name may stay in {source} (e.g. {dishes})."""


def other_language(lang: str) -> str:
    """L'autre langue de TRANSLATION_LANGUAGES ("fr" ↔ "en")."""
    return "en" if lang == "fr" else "fr"


def translation_prompt(source_lang: str = "fr", target_lang: str = "en") -> str:
    """Consignes de traduction de source_lang vers target_lang ("fr" ↔ "en")."""
    try:
        return _PROMPT_TEMPLATE.format(**_DIRECTIONS[(source_lang, target_lang)])
    except KeyError:
        raise ValueError(f"Traduction non prise en charge : {source_lang} → {target_lang}") from None


# Sens historique (affichage pour un compte en anglais), inchangé.
TRANSLATION_PROMPT = translation_prompt("fr", "en")

# Imposé à Ollama (sorties structurées), comme RECIPE_JSON_SCHEMA pour
# l'extraction : types simples, tous les champs requis.
TRANSLATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "unit": {"type": "string"},
                    "name": {"type": "string"},
                    "notes": {"type": "string"},
                    "section": {"type": "string"},
                },
                "required": ["unit", "name", "notes", "section"],
            },
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "section": {"type": "string"}},
                "required": ["text", "section"],
            },
        },
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "description", "ingredients", "steps", "tags"],
}

_TRANSLATION_TIMEOUT_SECONDS = 150
# Une recette traduite est à peu près aussi longue que l'originale : même
# plafond que l'extraction.
_NUM_PREDICT = llm_service.NUM_PREDICT_RECIPE

# Champs de contenu traduits, et clés exposées à l'API (sans les métadonnées).
CONTENT_FIELDS = ("title", "description", "ingredients", "steps", "tags")
_INGREDIENT_TEXT = ("unit", "name", "notes", "section")

# Lecture d'une fiche : on attend la traduction jusqu'à ce délai, puis la
# page s'affiche en version originale et se met à jour toute seule une fois
# la traduction finie (translation_pending, interrogé par le client). Bien
# en dessous des délais de nginx/Cloudflare, qu'un appel synchrone plus
# long avait déjà fait sauter (voir la génération de vignette).
DISPLAY_WAIT_SECONDS = 10
# Traductions simultanées au plus (lectures et tâches de fond) : Ollama
# traite une requête à la fois, une liste de 50 recettes ne doit pas
# empiler 50 appels devant la prochaine extraction.
MAX_CONCURRENT = 2
# Traductions de fond lancées au plus par chargement de la liste.
BACKGROUND_PER_REQUEST = 2
# Après un échec (modèle injoignable…), pas de nouvel essai avant ce délai :
# sinon chaque chargement de la fiche relancerait un appel voué à l'échec.
RETRY_AFTER_SECONDS = 600

_in_flight: dict[tuple[uuid.UUID, str], asyncio.Task] = {}
_failed_until: dict[tuple[uuid.UUID, str], float] = {}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _significant(value):
    """Sans les clés vides : enregistrer le formulaire sans rien changer
    réécrit les ingrédients avec des "notes": null en plus (RecipeUpdate),
    ce qui ne doit pas passer pour un nouveau contenu à retraduire."""
    if isinstance(value, dict):
        return {k: _significant(v) for k, v in value.items() if v not in (None, "", [], {})}
    if isinstance(value, list):
        return [_significant(v) for v in value]
    return None if value == "" else value


def content_hash(recipe) -> str:
    """Empreinte du contenu traduisible (titre, description, ingrédients, étapes, tags)."""
    payload = json.dumps(
        _significant([getattr(recipe, field) for field in CONTENT_FIELDS]),
        ensure_ascii=False, sort_keys=True, default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def cached_translation(recipe, lang: str | None) -> dict | None:
    """Traduction en cache encore valable pour le contenu actuel, sinon None."""
    if lang not in SUPPORTED_LANGUAGES:
        return None
    entry = (recipe.translations or {}).get(lang)
    if not isinstance(entry, dict) or entry.get("source_hash") != content_hash(recipe):
        return None
    return {field: entry.get(field) for field in CONTENT_FIELDS}


def _content_text(title, ingredients, steps) -> str:
    """Titre, noms des ingrédients et texte des étapes : ce sur quoi la
    langue du contenu est jugée (ni unités, ni quantités, ni tags)."""
    words = [str(title or "")]
    words += [str(i.get("name") or "") for i in recipe_parsing.as_list(ingredients) if isinstance(i, dict)]
    words += [
        str(s.get("text") if isinstance(s, dict) else s) for s in recipe_parsing.as_list(steps)
    ]
    return " ".join(words)


def content_language(title, ingredients, steps) -> str | None:
    """Langue dans laquelle le contenu est ÉCRIT : "fr", "en", ou None si le
    texte ne permet pas de trancher (trop court, mélangé)."""
    text = _content_text(title, ingredients, steps)
    if recipe_parsing.looks_french(text):
        return "fr"
    if recipe_parsing.looks_english(text):
        return "en"
    return None


def already_in(recipe, lang: str) -> bool:
    """Le contenu semble déjà dans la langue voulue (heuristique sur le texte).

    Recipe.language ne convient pas : c'est la langue de la SOURCE, et une
    vidéo anglaise est enregistrée traduite en français avec language="en".
    Seul le texte enregistré dit ce qu'il faut traduire (recette saisie à
    la main en anglais, par exemple).
    """
    if lang != "en":
        return False
    return recipe_parsing.looks_english(_content_text(recipe.title, recipe.ingredients, recipe.steps))


def scraped_source_language(recipe: dict, target_lang: str) -> str | None:
    """Langue à traduire vers target_lang pour une recette lue telle quelle
    sur un site (dict pas encore enregistré), ou None si rien à traduire.

    Comme already_in, on juge le texte lui-même, pas le champ "language".
    Il faut un texte NETTEMENT dans l'autre langue : un contenu ambigu
    (titre seul, liste très courte) reste tel quel plutôt que de coûter un
    appel au modèle pour rien.
    """
    if target_lang not in TRANSLATION_LANGUAGES:
        return None
    written_in = content_language(recipe.get("title"), recipe.get("ingredients"), recipe.get("steps"))
    if written_in is None or written_in == target_lang:
        return None
    return written_in


def needs_translation(recipe, lang: str | None) -> bool:
    return (
        lang in SUPPORTED_LANGUAGES
        and cached_translation(recipe, lang) is None
        and not already_in(recipe, lang)
    )


# ---------------------------------------------------------------------------
# Appel au modèle
# ---------------------------------------------------------------------------

def _text(value) -> str:
    return "" if value is None else str(value)


def translation_input(title, description, ingredients, steps, tags) -> str:
    """Ce que le modèle reçoit : le contenu en JSON, chaînes vides pour l'absent."""
    return json.dumps({
        "title": _text(title),
        "description": _text(description),
        "ingredients": [
            {"quantity": _text(i.get("quantity")), **{k: _text(i.get(k)) for k in _INGREDIENT_TEXT}}
            if isinstance(i, dict) else {"quantity": "", "unit": "", "name": _text(i), "notes": "", "section": ""}
            for i in recipe_parsing.as_list(ingredients)
        ],
        "steps": [
            {"text": _text(s.get("text")), "section": _text(s.get("section"))}
            if isinstance(s, dict) else {"text": _text(s), "section": ""}
            for s in recipe_parsing.as_list(steps)
        ],
        "tags": [_text(t) for t in recipe_parsing.as_list(tags)],
    }, ensure_ascii=False)


def _pick(original, translated) -> object:
    """Texte traduit si l'original en avait un, sinon l'original tel quel
    (None reste None : la forme des objets ne change pas)."""
    if original is None or not str(original).strip():
        return original
    translated = recipe_parsing.clean_text(translated) if translated is not None else ""
    return translated or original


def merge_translation(title, description, ingredients, steps, tags, data: dict) -> dict:
    """Réponse du modèle → contenu de même forme que l'original.

    Les quantités et l'ordre viennent toujours de l'original ; seules les
    chaînes de texte sont remplacées. Un nombre d'ingrédients ou d'étapes
    différent rend la traduction inutilisable (on ne saurait plus quelle
    ligne correspond à quelle quantité) : UnreadableResponse, réessayée.
    """
    if not isinstance(data, dict):
        raise llm_service.UnreadableResponse("Traduction illisible.")
    ingredients = recipe_parsing.as_list(ingredients)
    steps = recipe_parsing.as_list(steps)
    tags = recipe_parsing.as_list(tags)
    out_ingredients = recipe_parsing.as_list(data.get("ingredients"))
    out_steps = recipe_parsing.as_list(data.get("steps"))
    if len(out_ingredients) != len(ingredients) or len(out_steps) != len(steps):
        raise llm_service.UnreadableResponse(
            f"Traduction incomplète ({len(out_ingredients)}/{len(ingredients)} ingrédients, "
            f"{len(out_steps)}/{len(steps)} étapes)."
        )

    merged_ingredients = []
    for original, translated in zip(ingredients, out_ingredients):
        translated = translated if isinstance(translated, dict) else {"name": translated}
        if isinstance(original, dict):
            item = dict(original)
            for key in _INGREDIENT_TEXT:
                if key in item:
                    item[key] = _pick(item[key], translated.get(key))
            merged_ingredients.append(item)
        else:
            merged_ingredients.append(_pick(original, translated.get("name")))

    merged_steps = []
    for original, translated in zip(steps, out_steps):
        translated = translated if isinstance(translated, dict) else {"text": translated}
        if isinstance(original, dict):
            item = dict(original)
            item["text"] = _pick(item.get("text"), translated.get("text"))
            if "section" in item:
                item["section"] = _pick(item["section"], translated.get("section"))
            merged_steps.append(item)
        else:
            merged_steps.append(_pick(original, translated.get("text")))

    out_tags = recipe_parsing.as_list(data.get("tags"))
    # Tags : de simples étiquettes, une réponse au mauvais compte garde les
    # originaux plutôt que de faire échouer toute la traduction.
    merged_tags = (
        [_pick(o, t) for o, t in zip(tags, out_tags)] if len(out_tags) == len(tags) else list(tags)
    )

    return {
        "title": _pick(title, data.get("title")),
        "description": _pick(description, data.get("description")),
        "ingredients": merged_ingredients,
        "steps": merged_steps,
        "tags": merged_tags,
    }


def build_translation_request(
    content: str, *, use_schema: bool = True, temperature: float = 0, system: str = TRANSLATION_PROMPT,
) -> dict:
    return llm_service.ollama_chat_request(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        temperature=temperature, num_predict=_NUM_PREDICT,
        format=TRANSLATION_JSON_SCHEMA if use_schema else "json",
    )


async def translate_recipe_content(
    title, description, ingredients, steps, tags=None, target_lang: str = "en",
    source_lang: str | None = None,
) -> dict:
    """Traduit le contenu d'une recette ; renvoie {title, description,
    ingredients, steps, tags}, de même forme que l'entrée.

    source_lang : langue du contenu, par défaut l'autre langue que
    target_lang (français → anglais pour l'affichage, anglais → français
    pour une recette lue sur un site anglophone par un compte français).
    """
    if target_lang not in TRANSLATION_LANGUAGES:
        raise ValueError(f"Langue non prise en charge : {target_lang}")
    system = translation_prompt(source_lang or other_language(target_lang), target_lang)
    content = translation_input(title, description, ingredients, steps, tags)

    async def ask(temperature: float) -> dict:
        if settings.use_claude:
            raw = await llm_service.ask_claude(
                content, system=system, fast=True,
                max_tokens=llm_service.CLAUDE_MAX_TOKENS,
            )
        else:
            async with httpx.AsyncClient(timeout=_TRANSLATION_TIMEOUT_SECONDS) as client:
                resp = await llm_service.post_ollama_chat(
                    client, lambda use_schema: build_translation_request(
                        content, use_schema=use_schema, temperature=temperature, system=system,
                    ),
                )
                raw = resp.json()["message"]["content"]
        try:
            data = llm_service._parse_json(raw)
        except ValueError:
            logger.warning("Traduction illisible : %.300s", raw)
            raise llm_service.UnreadableResponse("Traduction illisible.")
        return merge_translation(title, description, ingredients, steps, tags, data)

    return await llm_service._retry_unreadable(ask)


# ---------------------------------------------------------------------------
# Traduction + mise en cache, une seule fois par recette
# ---------------------------------------------------------------------------

def _session_factory():
    from ..database import AsyncSessionLocal

    return AsyncSessionLocal


async def _translate_and_store(recipe_id: uuid.UUID, lang: str, session_factory=None) -> dict | None:
    """Traduit la recette et l'enregistre dans son cache ; renvoie la traduction.

    Session propre : la tâche peut survivre à la requête qui l'a lancée.
    """
    async with (session_factory or _session_factory())() as db:
        recipe = await db.get(Recipe, recipe_id)
        if recipe is None:
            return None
        fresh = cached_translation(recipe, lang)
        if fresh is not None:
            return fresh
        source = {field: getattr(recipe, field) for field in CONTENT_FIELDS}
        source_hash = content_hash(recipe)
        source_updated_at = recipe.updated_at
        started = time.monotonic()
        translation = await translate_recipe_content(**source, target_lang=lang)
        logger.info(
            "Recette %s traduite (%s) en %.1fs", recipe_id, lang, time.monotonic() - started,
        )
        entry = {
            **translation,
            "source_hash": source_hash,
            "source_updated_at": (source_updated_at or datetime.now(timezone.utc)).isoformat(),
        }
        await db.refresh(recipe, ["translations"])
        translations = {**(recipe.translations or {}), lang: entry}
        # UPDATE direct, updated_at réécrit à sa propre valeur : sans ça,
        # onupdate le bumperait, et une simple mise en cache passerait pour
        # une modification de la recette (tri, synchronisation…).
        await db.execute(
            update(Recipe).where(Recipe.id == recipe_id)
            .values(translations=translations, updated_at=Recipe.updated_at)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        return translation


def _finished(key, task: asyncio.Task) -> None:
    _in_flight.pop(key, None)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _failed_until[key] = time.monotonic() + RETRY_AFTER_SECONDS
        logger.warning("Traduction de la recette %s (%s) échouée : %s", key[0], key[1], exc)
    else:
        _failed_until.pop(key, None)


def translation_task(recipe_id: uuid.UUID, lang: str, *, session_factory=None) -> asyncio.Task | None:
    """Tâche de traduction de la recette : celle déjà en cours s'il y en a
    une (une fiche ouverte deux fois, la liste et l'assistant ne lancent
    qu'un appel), sinon une nouvelle. None si un échec récent impose
    d'attendre avant de réessayer."""
    key = (recipe_id, lang)
    task = _in_flight.get(key)
    if task is not None:
        return task
    if _failed_until.get(key, 0) > time.monotonic():
        return None
    task = asyncio.create_task(_translate_and_store(recipe_id, lang, session_factory))
    _in_flight[key] = task
    task.add_done_callback(lambda t: _finished(key, t))
    return task


async def translation_for_display(
    recipe, lang: str | None, *, wait: float = DISPLAY_WAIT_SECONDS, session_factory=None,
) -> tuple[dict | None, bool]:
    """(traduction, en_cours) pour afficher UNE recette.

    Traduit si besoin, en attendant au plus `wait` secondes ; au-delà, la
    traduction continue en arrière-plan et en_cours vaut True. Un échec du
    modèle n'empêche jamais l'affichage : version originale.
    """
    if lang not in SUPPORTED_LANGUAGES:
        return None, False
    cached = cached_translation(recipe, lang)
    if cached is not None or already_in(recipe, lang):
        return cached, False
    task = translation_task(recipe.id, lang, session_factory=session_factory)
    if task is None:
        return None, False
    try:
        # shield : le délai dépassé n'annule pas la traduction, qui finit
        # en arrière-plan et sera servie par la prochaine lecture.
        return await asyncio.wait_for(asyncio.shield(task), timeout=wait), False
    except asyncio.TimeoutError:
        return None, True
    except Exception:
        # Déjà journalisé par _finished.
        return None, False


def is_pending(recipe_id: uuid.UUID, lang: str | None) -> bool:
    return (recipe_id, lang) in _in_flight


def schedule_background(recipes, lang: str | None, *, session_factory=None) -> int:
    """Lance la traduction de quelques recettes de la liste, sans l'attendre.

    Au plus BACKGROUND_PER_REQUEST par appel et MAX_CONCURRENT en tout :
    la bibliothèque finit traduite au fil des visites, sans file de tâches
    et sans saturer le modèle. Renvoie le nombre de traductions lancées.
    """
    if lang not in SUPPORTED_LANGUAGES:
        return 0
    started = 0
    for recipe in recipes:
        if started >= BACKGROUND_PER_REQUEST or len(_in_flight) >= MAX_CONCURRENT:
            break
        key = (recipe.id, lang)
        if key in _in_flight or _failed_until.get(key, 0) > time.monotonic():
            continue
        if needs_translation(recipe, lang):
            if translation_task(recipe.id, lang, session_factory=session_factory) is not None:
                started += 1
    return started
