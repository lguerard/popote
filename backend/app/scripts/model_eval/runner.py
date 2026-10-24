"""Passe chaque cas au modèle donné, avec les requêtes et analyseurs de la prod.

Chaque cas tourne UNE fois, à température 0 (sorties déterministes) : pas
de nouvel essai sur une réponse illisible comme en production, qui
masquerait justement ce qu'on veut mesurer. JSON illisible = 0 pour ce cas.
"""

import base64
import logging
import time

import httpx

from ...config import settings
from ...services import llm_service, nutrition_service
from . import scoring
from .cases import HERE

logger = logging.getLogger("model_eval")

CASE_TIMEOUT_SECONDS = 300
MAX_NOTES = 6


class CaseError(Exception):
    """Le modèle n'a pas répondu (Ollama injoignable, modèle absent, délai…)."""


def _image_b64(case: dict) -> str:
    raw = (HERE / case["image"]).read_bytes()
    raw, _ = llm_service.prepare_image(raw, case.get("mime") or "image/jpeg")
    return base64.standard_b64encode(raw).decode()


def build_request(task: str, case: dict, model: str, use_schema: bool = True) -> dict:
    """Corps /api/chat d'un cas, construit par les fonctions de la prod."""
    if task == "extraction":
        return llm_service.build_ollama_request(case["input"], model, use_schema=use_schema)
    if task == "photo_recipe":
        return llm_service.build_image_recipe_request(_image_b64(case), use_schema=use_schema, model=model)
    if task == "nutrition":
        prompt = nutrition_service.nutrition_prompt(case["title"], case["ingredients"], case["servings"])
        return nutrition_service.build_nutrition_request(prompt, use_schema, model=model)
    if task == "description":
        recipe = llm_service.image_description_input(
            case["title"], case.get("description"), case.get("category"),
            case.get("ingredients"), case.get("steps"),
        )
        return llm_service.build_description_request(recipe, model=model, temperature=0)
    raise ValueError(f"tâche inconnue : {task}")


def score_reply(task: str, case: dict, content: str) -> tuple[float, list[str]]:
    """Réponse brute → note, via les analyseurs de la prod."""
    if task in ("extraction", "photo_recipe"):
        try:
            data = llm_service.parse_llm_content(content)
        except llm_service.UnreadableResponse:
            return 0.0, ["JSON illisible"]
        return scoring.score_recipe(data, case["expected"])
    if task == "nutrition":
        try:
            values = nutrition_service.parse_nutrition(content)
        except ValueError:
            return 0.0, ["JSON illisible"]
        return scoring.score_nutrition(values, case["expected"])
    return scoring.score_description(llm_service.clean_image_description(content))


async def run_case(client: httpx.AsyncClient, task: str, case: dict, model: str) -> dict:
    started = time.monotonic()
    try:
        resp = await llm_service.post_ollama_chat(
            client, lambda use_schema: build_request(task, case, model, use_schema),
        )
        body = resp.json()
        content = (body.get("message") or {}).get("content") or ""
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        if isinstance(exc, httpx.HTTPStatusError):
            detail = f"HTTP {exc.response.status_code} : {llm_service._ollama_error(exc.response)}"
        else:
            detail = str(exc) or type(exc).__name__
        return {"id": case["id"], "score": 0.0, "failed": True, "notes": [f"erreur : {detail[:160]}"],
                "seconds": time.monotonic() - started, "eval_count": 0, "eval_ns": 0}
    score, notes = score_reply(task, case, content)
    return {
        "id": case["id"], "score": score, "notes": notes,
        "failed": notes[:1] == ["JSON illisible"],
        "seconds": time.monotonic() - started,
        "eval_count": int(body.get("eval_count") or 0),
        "eval_ns": int(body.get("eval_duration") or 0),
    }


def summarize(results: list[dict], source_note: str) -> dict:
    n = len(results)
    worst = sorted(results, key=lambda r: r["score"])[: MAX_NOTES - 1]
    notes = [source_note] + [
        f"{r['id']} : {r['score']:.0f}" + (f" — {'; '.join(r['notes'][:3])}" if r["notes"] else "")
        for r in worst if r["score"] < 100
    ]
    return {
        "score": round(sum(r["score"] for r in results) / n, 1) if n else 0.0,
        "n": n,
        "failed": sum(1 for r in results if r["failed"]),
        "avg_seconds": round(sum(r["seconds"] for r in results) / n, 2) if n else 0.0,
        "notes": notes,
    }


async def evaluate(model: str, cases: dict, sources: dict) -> dict:
    """{tâche: résumé} et vitesse de génération mesurée par Ollama."""
    tasks, tokens, ns = {}, 0, 0
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=CASE_TIMEOUT_SECONDS) as client:
        for task, task_cases in cases.items():
            if not task_cases:
                continue
            results = []
            for case in task_cases:
                logger.info("%s / %s / %s", model, task, case["id"])
                result = await run_case(client, task, case, model)
                results.append(result)
                tokens += result["eval_count"]
                ns += result["eval_ns"]
            tasks[task] = summarize(results, sources.get(task, ""))
    return {"tasks": tasks, "eval_tokens_per_s": round(tokens / (ns / 1e9), 1) if ns else None}
