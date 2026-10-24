"""CLI : note un modèle Ollama sur les tâches IA de Popote, sortie JSON.

    python -m app.scripts.model_eval --model gemma4:12b [--max-cases 12] [--cases-only]

Imprime UN objet JSON sur la sortie standard (les journaux vont sur la
sortie d'erreur) :

    {"app": "popote", "model": "...", "tasks": {"extraction": {"score": 0-100,
     "n": 12, "failed": 0, "avg_seconds": 8.4, "notes": [...]}, ...},
     "eval_tokens_per_s": 41.2, "cases_hash": "..."}

--cases-only n'appelle pas Ollama : il dit combien de cas chaque tâche
passerait, et d'où ils viennent.
"""

import argparse
import asyncio
import json
import logging
import sys

from . import cases as case_mod
from . import runner

logger = logging.getLogger("model_eval")


async def harvest(max_cases: int) -> tuple[dict, dict, list[str]]:
    warnings = []
    try:
        from ...database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            recipes = await case_mod.load_recipes(session)
    except Exception as exc:  # base injoignable : on évalue quand même sur les cas fournis
        logger.warning("Lecture des recettes impossible : %s", exc)
        warnings.append(f"base indisponible ({type(exc).__name__}) : cas fournis seulement")
        recipes = []
    cases, sources = case_mod.build_cases(recipes, max_cases)
    return cases, sources, warnings


async def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(prog="python -m app.scripts.model_eval", description=__doc__.split("\n")[0])
    parser.add_argument("--model", required=True, help="modèle Ollama à évaluer (ex. gemma4:12b)")
    parser.add_argument("--max-cases", type=int, default=case_mod.DEFAULT_MAX_CASES,
                        help=f"cas au plus par tâche (défaut {case_mod.DEFAULT_MAX_CASES})")
    parser.add_argument("--cases-only", action="store_true",
                        help="compte les cas sans appeler Ollama")
    args = parser.parse_args(argv)

    cases, sources, warnings = await harvest(args.max_cases)
    out = {"app": "popote", "model": args.model, "cases_hash": case_mod.cases_hash(cases)}
    if warnings:
        out["warnings"] = warnings
    if args.cases_only:
        out["cases_only"] = True
        out["tasks"] = {t: {"n": len(cs), "source": sources[t]} for t, cs in cases.items()}
        return out
    result = await runner.evaluate(args.model, cases, sources)
    out.update(result)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(asyncio.run(main()), ensure_ascii=False))
