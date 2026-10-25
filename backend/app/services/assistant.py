"""Assistant culinaire : conversation en streaming avec appels d'outils.

Le modèle (Ollama par défaut, Claude si CLAUDE_API_KEY est définie) répond
en français et agit sur les données du compte connecté par les outils de
services/assistant_tools.py. La boucle tourne côté serveur : le modèle
demande un outil, le serveur l'exécute et lui renvoie le résultat, jusqu'à
une réponse finale (MAX_TOOL_ROUNDS tours d'outils au plus).

La réponse est diffusée en événements (dictionnaires) que l'API écrit en
NDJSON, une ligne JSON par événement :

- {"type": "status", "text": …}   ce que fait l'assistant (outil, attente) ;
- {"type": "delta", "text": …}    morceau de réponse, au fil de l'eau ;
- {"type": "recipes", "recipes": [{id, title, thumbnail_url, minutes}]} ;
- {"type": "action", "kind": "courses"|"planning", "label": …} : écriture ;
- {"type": "error", "message": …} ;
- {"type": "done", "trimmed": n}  toujours en dernier ; n = messages anciens
  laissés de côté pour tenir dans la fenêtre du modèle.

La conversation est tenue par le client (rien en base) : chaque requête
renvoie l'historique, réduit ici pour tenir dans num_ctx.
"""

import asyncio
import json
import logging
import time
import uuid
from contextlib import aclosing
from datetime import date
from typing import AsyncIterator, Callable

import httpx

from ..config import settings
from . import assistant_tools as tools
from .llm_service import CLAUDE_MAX_TOKENS, ollama_chat_request

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
# Une question qui attend derrière une extraction (Ollama traite une
# requête à la fois) puis enchaîne plusieurs outils : 3 minutes au total.
TIMEOUT_SECONDS = 180
# Sans premier mot passé ce délai, on prévient que le modèle est occupé
# ou en cours de chargement.
SLOW_NOTICE_SECONDS = 8

# Tokens générés au plus par tour : une réponse de chat, pas une recette.
NUM_PREDICT_CHAT = 1024
TEMPERATURE = 0.3
# Estimation grossière (~4 caractères par token) : on garde une marge.
CHARS_PER_TOKEN = 4
SAFETY_TOKENS = 300
# Claude a une fenêtre bien plus grande ; la limite garde un coût raisonnable.
CLAUDE_PROMPT_BUDGET = 30000

MAX_USER_MESSAGE_CHARS = 4000
MAX_MESSAGE_CHARS = 16000
MAX_MESSAGES = 60
MAX_TOTAL_CHARS = 150_000
MAX_PAGE_CHARS = 200

TIMEOUT_MESSAGE = (
    f"L'assistant n'a pas répondu à temps ({TIMEOUT_SECONDS} s). Le modèle est peut-être "
    "occupé par une extraction de recette : réessaie dans un instant."
)
SLOW_MESSAGE = (
    "Le modèle est occupé ou se charge (une extraction est peut-être en cours) : "
    "ta question attend son tour…"
)


class RequestTooLarge(ValueError):
    """Message ou conversation trop longs : 413."""


class InvalidConversation(ValueError):
    """Conversation mal formée : 422."""


class ProviderError(RuntimeError):
    """Le modèle a refusé ou échoué ; le message est montré tel quel."""


class AssistantTimeout(Exception):
    pass


# ---------------------------------------------------------------------------
# Validation et budget de contexte
# ---------------------------------------------------------------------------

def validate_conversation(messages: list[dict]) -> list[dict]:
    """Vérifie la conversation envoyée par le client ; renvoie role/content.

    Le dernier message, celui de l'utilisateur, doit tenir dans la fenêtre
    du modèle avec le reste : au-delà de MAX_USER_MESSAGE_CHARS, 413 avec
    un message clair plutôt qu'une réponse tronquée.
    """
    if not messages:
        raise InvalidConversation("Conversation vide.")
    if len(messages) > MAX_MESSAGES * 4:
        raise RequestTooLarge("Conversation trop longue : commence une nouvelle conversation.")
    cleaned = []
    for message in messages:
        role, content = message.get("role"), message.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            raise InvalidConversation("Message invalide (role user/assistant, contenu texte).")
        if len(content) > MAX_MESSAGE_CHARS:
            raise RequestTooLarge(f"Un message dépasse {MAX_MESSAGE_CHARS} caractères.")
        cleaned.append({"role": role, "content": content})
    last = cleaned[-1]
    if last["role"] != "user" or not last["content"].strip():
        raise InvalidConversation("Le dernier message doit être une question de l'utilisateur.")
    if len(last["content"]) > MAX_USER_MESSAGE_CHARS:
        raise RequestTooLarge(
            f"Message trop long ({len(last['content'])} caractères, {MAX_USER_MESSAGE_CHARS} au plus) : "
            "raccourcis ta question."
        )
    if sum(len(m["content"]) for m in cleaned) > MAX_TOTAL_CHARS:
        raise RequestTooLarge("Conversation trop longue : commence une nouvelle conversation.")
    # Les plus anciens partent de toute façon (fenêtre du modèle).
    return cleaned[-MAX_MESSAGES:]


def estimate_tokens(value) -> int:
    """~4 caractères par token, sur le JSON envoyé au modèle."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return len(text) // CHARS_PER_TOKEN + 1


def prompt_budget() -> int:
    """Tokens disponibles pour le prompt (outils compris)."""
    if settings.use_claude:
        return CLAUDE_PROMPT_BUDGET
    return settings.ollama_num_ctx - NUM_PREDICT_CHAT - SAFETY_TOKENS


def fit_history(system: str, history: list[dict], tool_defs: list, budget: int) -> tuple[list[dict], int]:
    """Retire les plus anciens échanges jusqu'à tenir dans le budget.

    Le prompt système (avec la recette ouverte) et le dernier message sont
    toujours gardés ; l'historique conservé commence par une question de
    l'utilisateur. Renvoie (historique, nombre de messages retirés).
    """
    fixed = estimate_tokens(system) + estimate_tokens(tool_defs) + 8
    kept: list[dict] = []
    used = fixed
    for message in reversed(history):
        cost = estimate_tokens(message["content"]) + 4
        if kept and used + cost > budget:
            break
        kept.append(message)
        used += cost
    kept.reverse()
    while len(kept) > 1 and kept[0]["role"] != "user":
        kept.pop(0)
    return kept, len(history) - len(kept)


def shrink_tool_results(messages: list[dict], start: int, budget: int, tool_defs: list) -> bool:
    """Pendant la boucle d'outils : vide les plus vieux résultats de ce tour
    si le prompt déborde. Renvoie False si ça ne suffit pas."""
    def total() -> int:
        return estimate_tokens(messages) + estimate_tokens(tool_defs)

    index = start
    while total() > budget and index < len(messages):
        message = messages[index]
        if message.get("role") == "tool" and not message.get("_shrunk"):
            message["content"] = '{"remarque":"résultat retiré pour tenir dans le contexte"}'
            message["_shrunk"] = True
        elif message.get("role") == "user" and isinstance(message.get("content"), list):
            for block in message["content"]:
                if block.get("type") == "tool_result" and not block.get("_shrunk"):
                    block["content"] = '{"remarque":"résultat retiré pour tenir dans le contexte"}'
        index += 1
    return total() <= budget


def _strip_private(messages: list[dict]) -> list[dict]:
    """Retire les marqueurs internes (_shrunk) avant l'envoi."""
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if not k.startswith("_")}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    return clean(messages)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

PAGES = {
    "/": "la liste de ses recettes", "/planning": "son planning de repas",
    "/courses": "sa liste de courses", "/frigo": "« Qu'est-ce que je cuisine ? »",
    "/carnets": "ses carnets", "/ajouter": "l'ajout d'une recette",
}


def build_system_prompt(today: date, recipe: dict | None = None, page: str | None = None) -> str:
    lines = [
        "Tu es l'assistant culinaire de Popote, l'appli de recettes de l'utilisateur.",
        f"Nous sommes le {tools.date_fr(today)} ({today.isoformat()}).",
        "Réponds en français, brièvement, en Markdown simple (listes, gras).",
        "Pour ses recettes, son planning et sa liste de courses, utilise les outils : "
        "n'invente jamais une recette de sa bibliothèque ni une action non faite.",
        "Cite une recette de sa bibliothèque par un lien [Titre](/recettes/ID), ID renvoyé par un outil.",
        "Tu peux ajouter au planning et à la liste de courses quand il le demande ; "
        "tu ne peux rien supprimer ni modifier une recette.",
        "Pour les questions générales de cuisine, réponds directement.",
    ]
    if page and not recipe:
        where = PAGES.get(page.rstrip("/") or "/")
        if where:
            lines.append(f"Il regarde {where}.")
    if recipe:
        lines.append(
            "Recette ouverte à l'écran (« cette recette ») : "
            + tools.encode_result(recipe)
        )
    return "\n".join(lines)


async def recipe_context(ctx: tools.ToolContext, recipe_id) -> dict | None:
    """Recette ouverte, si elle appartient bien au compte (sinon ignorée)."""
    if not recipe_id:
        return None
    try:
        recipe = await tools.owned_recipe(ctx, str(uuid.UUID(str(recipe_id))))
    except (ValueError, tools.ToolError):
        return None
    return tools.compact_recipe(recipe)


# ---------------------------------------------------------------------------
# Verrou : une question à la fois par compte
# ---------------------------------------------------------------------------

class UserLocks:
    """Au plus une réponse en cours par compte (le GPU est partagé).

    Un seul processus uvicorn sert l'API (backend/entrypoint.sh) : un
    dictionnaire en mémoire suffit. Un verrou plus vieux que le délai
    maximal est considéré comme abandonné (client parti avant le début du
    flux, sans que le nettoyage ait pu tourner).
    """

    def __init__(self, stale_after: float = TIMEOUT_SECONDS + 30, clock: Callable[[], float] = time.monotonic):
        self._held: dict[uuid.UUID, tuple[str, float]] = {}
        self._stale_after = stale_after
        self._clock = clock

    def acquire(self, user_id) -> str | None:
        now = self._clock()
        held = self._held.get(user_id)
        if held and now - held[1] < self._stale_after:
            return None
        token = uuid.uuid4().hex
        self._held[user_id] = (token, now)
        return token

    def release(self, user_id, token: str) -> None:
        held = self._held.get(user_id)
        if held and held[0] == token:
            del self._held[user_id]

    def busy(self, user_id) -> bool:
        held = self._held.get(user_id)
        return bool(held) and self._clock() - held[1] < self._stale_after


locks = UserLocks()


# ---------------------------------------------------------------------------
# Échéance globale
# ---------------------------------------------------------------------------

# Marqueur interne : le modèle a commencé à répondre (pas transmis au client).
ALIVE = {"type": "_alive"}


async def timed(source, deadline: float, slow_after: float | None = None, slow_event: dict | None = None):
    """Relaie les événements de `source` (générateur asynchrone) jusqu'à l'échéance.

    `source` tourne dans une tâche à part : l'attente de la réponse HTTP
    (Ollama ne répond qu'une fois la requête sortie de sa file) compte dans
    l'échéance au même titre que la lecture. Si rien n'arrive (ALIVE ou
    autre) avant `slow_after` secondes, `slow_event` est produit une fois.
    Lève AssistantTimeout à l'échéance ; annuler la tâche referme la
    connexion, ce qui arrête aussi la génération côté Ollama.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    end = object()

    async def pump():
        try:
            async with aclosing(source) as items:
                async for item in items:
                    await queue.put((None, item))
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # transmise au consommateur
            await queue.put((end, exc))
            return
        await queue.put((end, None))

    task = asyncio.create_task(pump())
    started = False
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise AssistantTimeout()
            wait = remaining
            if not started and slow_after is not None:
                wait = min(wait, slow_after)
            try:
                tag, item = await asyncio.wait_for(queue.get(), wait)
            except asyncio.TimeoutError:
                if not started and slow_after is not None:
                    slow_after = None
                    if slow_event:
                        yield slow_event
                continue
            if tag is end:
                if item is not None:
                    raise item
                return
            started = True
            if item is not ALIVE:
                yield item
    finally:
        task.cancel()
        try:
            await task
        except BaseException:
            pass


# ---------------------------------------------------------------------------
# Exécution des outils (commun aux deux fournisseurs)
# ---------------------------------------------------------------------------

def tool_status(name: str) -> dict:
    tool = tools.TOOLS.get(name)
    return {"type": "status", "text": tool.status if tool else "…"}


def outcome_events(outcome: tools.ToolOutcome) -> list[dict]:
    events = []
    if outcome.recipes:
        events.append({"type": "recipes", "recipes": outcome.recipes})
    if outcome.action:
        events.append({"type": "action", **outcome.action})
    return events


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def _ollama_error(body: bytes) -> str:
    try:
        data = json.loads(body)
        return str(data.get("error") or data)[:300]
    except ValueError:
        return body.decode(errors="replace")[:300]


def ollama_request(messages: list[dict], with_tools: bool) -> dict:
    """Corps /api/chat : options communes (même num_ctx, think false), en flux."""
    body = ollama_chat_request(
        _strip_private(messages), num_predict=NUM_PREDICT_CHAT, temperature=TEMPERATURE,
    )
    body["stream"] = True
    if with_tools:
        body["tools"] = tools.ollama_tools()
    return body


async def _ollama_round(client: httpx.AsyncClient, body: dict, calls: list):
    """Un appel /api/chat en flux : produit le texte, remplit `calls`."""
    url = f"{settings.ollama_base_url}/api/chat"
    try:
        async with client.stream("POST", url, json=body) as resp:
            if resp.status_code >= 400:
                detail = _ollama_error(await resp.aread())
                raise ProviderError(f"Le modèle local a refusé la requête : {detail}")
            yield ALIVE
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except ValueError:
                    continue
                if chunk.get("error"):
                    raise ProviderError(f"Erreur du modèle local : {str(chunk['error'])[:300]}")
                message = chunk.get("message") or {}
                if message.get("content"):
                    yield {"type": "delta", "text": message["content"]}
                if message.get("tool_calls"):
                    calls.extend(message["tool_calls"])
                if chunk.get("done"):
                    return
    except httpx.TimeoutException:
        raise AssistantTimeout()
    except httpx.TransportError as exc:
        raise ProviderError(f"Le modèle local est injoignable ({type(exc).__name__}).")


async def run_ollama(
    ctx: tools.ToolContext, system: str, history: list[dict], deadline: float,
) -> AsyncIterator[dict]:
    messages = [{"role": "system", "content": system}, *history]
    turn_start = len(messages)
    budget = prompt_budget()
    # Délai de lecture large : l'échéance globale (timed) s'en charge.
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=10)) as client:
        for round_index in range(MAX_TOOL_ROUNDS + 1):
            with_tools = round_index < MAX_TOOL_ROUNDS
            tool_defs = tools.ollama_tools() if with_tools else []
            if not shrink_tool_results(messages, turn_start, budget, tool_defs):
                # Plus de place pour un tour d'outils : réponse avec ce qu'on a.
                with_tools = False
            content, calls = "", []
            round_events = _ollama_round(client, ollama_request(messages, with_tools), calls)
            slow = SLOW_NOTICE_SECONDS if round_index == 0 else None
            async with aclosing(timed(round_events, deadline, slow, {"type": "status", "text": SLOW_MESSAGE})) as events:
                async for event in events:
                    if event["type"] == "delta":
                        content += event["text"]
                    yield event
            if not calls or not with_tools:
                return
            messages.append({"role": "assistant", "content": content, "tool_calls": calls})
            for call in calls:
                function = call.get("function") or {}
                name = str(function.get("name") or "")
                yield tool_status(name)
                outcome = await tools.run_tool(ctx, name, function.get("arguments"))
                for event in outcome_events(outcome):
                    yield event
                messages.append({
                    "role": "tool", "tool_name": name, "content": tools.encode_result(outcome.result),
                })
            if content and not content.endswith("\n"):
                # Texte avant les outils (« Je regarde… ») : la suite repart
                # sur un nouveau paragraphe.
                yield {"type": "delta", "text": "\n\n"}


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------

def _claude_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    if status == 429:
        return "Claude est saturé (trop de requêtes) : réessaie dans une minute."
    if status in (401, 403):
        return "Clé Claude refusée : vérifie CLAUDE_API_KEY."
    if status:
        return f"Claude a renvoyé une erreur {status}."
    return "Claude est injoignable pour le moment."


async def _claude_round(client, params: dict, state: dict):
    """Un appel Claude en flux : produit le texte, reconstitue les blocs dans `state`.

    Les blocs sont rebâtis ici à partir des événements bruts (texte, appels
    d'outils, et blocs de réflexion avec leur signature, à renvoyer tels
    quels au tour suivant) : l'assembleur du SDK épinglé (0.37) ne connaît
    pas les blocs de réflexion des modèles récents et perdrait la signature.
    """
    blocks, inputs = state["blocks"], state["inputs"]
    try:
        stream = await client.messages.create(**params, stream=True)
    except Exception as exc:
        logger.warning("Appel Claude refusé : %s", exc)
        raise ProviderError(_claude_error(exc))
    yield ALIVE
    try:
        async for event in stream:
            etype = getattr(event, "type", None)
            if etype == "content_block_start":
                block = event.content_block
                blocks[event.index] = (
                    block.model_dump(exclude_none=True) if hasattr(block, "model_dump") else dict(block)
                )
            elif etype == "content_block_delta":
                delta, block = event.delta, blocks.get(event.index)
                if block is None:
                    continue
                dtype = getattr(delta, "type", None)
                if dtype == "text_delta":
                    block["text"] = block.get("text", "") + delta.text
                    yield {"type": "delta", "text": delta.text}
                elif dtype == "input_json_delta":
                    inputs[event.index] = inputs.get(event.index, "") + delta.partial_json
                elif dtype == "thinking_delta":
                    block["thinking"] = block.get("thinking", "") + getattr(delta, "thinking", "")
                elif dtype == "signature_delta":
                    block["signature"] = getattr(delta, "signature", "")
            elif etype == "message_delta":
                state["stop_reason"] = getattr(event.delta, "stop_reason", None)
    except Exception as exc:
        logger.warning("Flux Claude interrompu : %s", exc)
        raise ProviderError(_claude_error(exc))
    finally:
        close = getattr(stream, "close", None)
        if close:
            await close()


def _tool_input(block: dict, raw: str):
    """Arguments d'un appel d'outil Claude, ou None s'ils sont illisibles."""
    try:
        arguments = json.loads(raw) if raw.strip() else (block.get("input") or {})
    except ValueError:
        block["input"] = {}
        return None
    block["input"] = arguments
    return arguments


async def run_claude(
    ctx: tools.ToolContext, system: str, history: list[dict], deadline: float,
) -> AsyncIterator[dict]:
    """Même boucle avec l'API Claude (CLAUDE_MODEL), en flux."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
    messages: list[dict] = [dict(m) for m in history]
    turn_start = len(messages)
    claude_tools = tools.claude_tools()
    for round_index in range(MAX_TOOL_ROUNDS + 1):
        last_round = round_index == MAX_TOOL_ROUNDS
        shrink_tool_results(messages, turn_start, prompt_budget(), claude_tools)
        params = {
            "model": settings.claude_model, "max_tokens": CLAUDE_MAX_TOKENS,
            "system": system, "messages": _strip_private(messages),
            # L'historique contient des appels d'outils : les outils restent
            # déclarés, « none » interdit seulement d'en appeler.
            "tools": claude_tools,
        }
        if last_round:
            params["tool_choice"] = {"type": "none"}
        state = {"blocks": {}, "inputs": {}, "stop_reason": None}
        slow = SLOW_NOTICE_SECONDS if round_index == 0 else None
        async with aclosing(timed(_claude_round(client, params, state), deadline, slow,
                                  {"type": "status", "text": "Claude réfléchit…"})) as events:
            async for event in events:
                yield event
        blocks, stop_reason = state["blocks"], state["stop_reason"]
        if stop_reason == "refusal":
            raise ProviderError("Claude a refusé de répondre à cette demande.")
        if stop_reason != "tool_use" or last_round:
            return
        results = []
        for index, block in sorted(blocks.items()):
            if block.get("type") != "tool_use":
                continue
            arguments = _tool_input(block, state["inputs"].get(index, ""))
            name = block.get("name", "")
            yield tool_status(name)
            if arguments is None:
                outcome = tools.ToolOutcome({"erreur": "Arguments illisibles (JSON invalide)."}, error=True)
            else:
                outcome = await tools.run_tool(ctx, name, arguments)
            for event in outcome_events(outcome):
                yield event
            result = {
                "type": "tool_result", "tool_use_id": block.get("id"),
                "content": tools.encode_result(outcome.result),
            }
            if outcome.error:
                result["is_error"] = True
            results.append(result)
        # Un bloc de texte vide est refusé par l'API au tour suivant.
        content = [
            blocks[i] for i in sorted(blocks)
            if not (blocks[i].get("type") == "text" and not blocks[i].get("text"))
        ]
        # Tous les résultats dans UN message, comme l'API l'attend.
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": results})
        if any(b.get("type") == "text" and b.get("text") for b in content):
            yield {"type": "delta", "text": "\n\n"}


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

async def run_chat(
    user_id: uuid.UUID, messages: list[dict], *, session_factory,
    recipe_id=None, page: str | None = None, today: date | None = None,
) -> AsyncIterator[dict]:
    """Répond au dernier message ; produit les événements décrits en tête."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + TIMEOUT_SECONDS
    today = today or date.today()
    trimmed = 0
    try:
        async with session_factory() as db:
            ctx = tools.ToolContext(db=db, user_id=user_id, today=today)
            recipe = await recipe_context(ctx, recipe_id)
            system = build_system_prompt(today, recipe, (page or "")[:MAX_PAGE_CHARS] or None)
            tool_defs = tools.claude_tools() if settings.use_claude else tools.ollama_tools()
            history, trimmed = fit_history(system, messages, tool_defs, prompt_budget())
            runner = run_claude if settings.use_claude else run_ollama
            async for event in runner(ctx, system, history, deadline):
                yield event
    except AssistantTimeout:
        yield {"type": "error", "message": TIMEOUT_MESSAGE}
    except ProviderError as exc:
        yield {"type": "error", "message": str(exc)}
    except Exception:
        logger.exception("Assistant en échec")
        yield {"type": "error", "message": "L'assistant a rencontré une erreur inattendue."}
    yield {"type": "done", "trimmed": trimmed}
