"""Monthly check: is a new Ollama model both better and GPU-affordable?

Runs INSIDE the backend container (`docker compose exec backend python -m
app.scripts.model_watch.run_eval`) — that's what gives it network access to
the `ollama` service (not published on the host) and lets it import the
project's actual extraction code, so the eval uses exactly the same prompt
and JSON normalization as production, not a re-implementation that could
drift out of sync.

Prints one JSON object to stdout and nothing else (logging goes to
stderr): the host-side driver script parses that stdout for the verdict.
Never touches `.env` or restarts anything itself — it only measures and
reports; `scripts/model_watch/check_model.sh` decides what to do with the
result.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # /app, so `app.*` imports work

from app.config import settings  # noqa: E402
from app.services.llm_service import SYSTEM_PROMPT, _parse_json, _normalize_recipe_shape  # noqa: E402
from app.scripts.model_watch.candidates import build_candidate_list, get_gpu_vram_gb  # noqa: E402
from app.scripts.model_watch.scoring import score_extraction  # noqa: E402

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("model_watch")

EVAL_CASES = json.loads((Path(__file__).parent / "eval_cases.json").read_text())

VRAM_HEADROOM_GB = float(os.environ.get("MODEL_WATCH_VRAM_HEADROOM_GB", "1.0"))
MAX_CANDIDATES = int(os.environ.get("MODEL_WATCH_MAX_CANDIDATES", "3"))
MIN_IMPROVEMENT = float(os.environ.get("MODEL_WATCH_MIN_IMPROVEMENT", "5.0"))
PULL_TIMEOUT = 3600
CHAT_TIMEOUT = 180


async def pull_model(client: httpx.AsyncClient, model: str) -> None:
    resp = await client.post(
        f"{settings.ollama_base_url}/api/pull",
        json={"name": model, "stream": False},
        timeout=PULL_TIMEOUT,
    )
    resp.raise_for_status()


async def delete_model(client: httpx.AsyncClient, model: str) -> None:
    try:
        await client.request(
            "DELETE", f"{settings.ollama_base_url}/api/delete",
            json={"model": model, "name": model}, timeout=30,
        )
    except Exception:
        logger.warning("Échec de la suppression de %s (non bloquant)", model, exc_info=True)


async def extract_with_model(client: httpx.AsyncClient, model: str, text: str) -> dict:
    resp = await client.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Voici le texte à analyser:\n\n{text[:12000]}"},
            ],
            "stream": False,
            "format": "json",
        },
        timeout=CHAT_TIMEOUT,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    data = _parse_json(content)
    if "error" not in data:
        _normalize_recipe_shape(data)
    return data


async def evaluate_model(client: httpx.AsyncClient, model: str) -> dict:
    case_results = []
    total_score = 0.0
    total_latency = 0.0
    for case in EVAL_CASES:
        start = time.monotonic()
        try:
            data = await extract_with_model(client, model, case["input"])
            score, notes = score_extraction(data, case["expected"])
        except Exception as e:
            score, notes = 0.0, [f"Erreur : {e}"]
        latency = time.monotonic() - start
        total_score += score
        total_latency += latency
        case_results.append({"case": case["id"], "score": score, "notes": notes, "latency_s": round(latency, 1)})
    n = len(EVAL_CASES)
    return {
        "model": model,
        "avg_score": round(total_score / n, 1),
        "avg_latency_s": round(total_latency / n, 1),
        "cases": case_results,
    }


async def main() -> dict:
    warnings: list[str] = []

    vram_total = get_gpu_vram_gb()
    if vram_total is None:
        return {"ok": False, "error": "Impossible de mesurer la VRAM du GPU (nvidia-smi indisponible)."}
    vram_budget = vram_total - VRAM_HEADROOM_GB
    logger.info("VRAM totale : %.1f Go — budget modèle : %.1f Go", vram_total, vram_budget)

    baseline_model = settings.ollama_model
    candidates = build_candidate_list(vram_budget, MAX_CANDIDATES)
    # Le modèle actuel n'a pas à se re-proposer lui-même comme "candidat".
    candidates = [c for c in candidates if c["model"] != baseline_model]

    async with httpx.AsyncClient() as client:
        logger.info("Évaluation du modèle actuel : %s", baseline_model)
        try:
            await pull_model(client, baseline_model)
            baseline_result = await evaluate_model(client, baseline_model)
        except Exception as e:
            return {"ok": False, "error": f"Échec de l'évaluation du modèle actuel {baseline_model} : {e}"}

        candidate_results = []
        for c in candidates:
            model = c["model"]
            logger.info("Évaluation du candidat : %s (~%.1f Go sur disque)", model, c["disk_size_gb"])
            try:
                await pull_model(client, model)
                result = await evaluate_model(client, model)
                result["disk_size_gb"] = c["disk_size_gb"]
                candidate_results.append(result)
            except Exception as e:
                warnings.append(f"{model} : échec de l'évaluation ({e})")
                logger.exception("Échec de l'évaluation de %s", model)

        winner = None
        best_score = baseline_result["avg_score"]
        for r in candidate_results:
            if r["avg_score"] >= best_score + MIN_IMPROVEMENT and r["avg_score"] > best_score:
                best_score = r["avg_score"]
                winner = r["model"]

        # Nettoyage : on ne garde que le modele actuel et, s'il y en a un,
        # le gagnant. Les autres candidats testes sont supprimes pour ne
        # pas accumuler des dizaines de Go de modeles non retenus.
        for r in candidate_results:
            if r["model"] != winner:
                await delete_model(client, r["model"])

    return {
        "ok": True,
        "vram_total_gb": round(vram_total, 1),
        "vram_budget_gb": round(vram_budget, 1),
        "baseline": baseline_result,
        "candidates": candidate_results,
        "winner": winner,
        "warnings": warnings,
    }


if __name__ == "__main__":
    result = asyncio.run(main())
    print(json.dumps(result, ensure_ascii=False))
