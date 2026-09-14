"""Discover Ollama models worth trying, and filter them to what fits the GPU.

There's no API that says "here are the best new LLMs" — this combines two
sources instead:

  - a small curated list of model families worth re-checking every month
    (kept even if the discovery below breaks, so the watch never goes
    completely blind to new tags/versions published under a known family);
  - a best-effort scrape of ollama.com's library sorted by newest, which is
    how genuinely new model families get noticed at all. Ollama doesn't
    publish a stable API for this, so this is fragile by nature: any
    failure here is caught and logged, never fatal to the run.

VRAM fitting uses the REAL manifest size from Ollama's registry (the same
one `ollama pull` reads), not a guess from the parameter count in the
model's name — quantization changes the on-disk size a lot for the same
parameter count.
"""

import logging
import re
import subprocess

import httpx

logger = logging.getLogger("model_watch")

REGISTRY_BASE = "https://registry.ollama.ai"
LIBRARY_URL = "https://ollama.com/library"

# Familles verifiees meme si la decouverte par scraping echoue. Ce sont
# des modeles generalistes/instruct couramment cites comme bons pour du
# suivi d'instructions strict (extraction JSON), la tache de cette app.
CURATED_FAMILIES = [
    "qwen2.5", "qwen3", "llama3.1", "llama3.2", "llama3.3",
    "mistral", "mistral-nemo", "gemma2", "gemma3", "phi3.5", "phi4",
    "deepseek-r1", "command-r",
]

# Tags a essayer par famille, du plus petit au plus gros : on s'arrete au
# premier qui existe pour chaque taille listee ici plutot que de tout
# essayer (Ollama liste souvent des dizaines de variantes de quantization).
CANDIDATE_SIZE_TAGS = ["7b", "8b", "9b", "13b", "14b", "27b", "32b"]


def get_gpu_vram_gb() -> float | None:
    """VRAM totale du GPU 0 en Go, mesurée en direct via nvidia-smi.

    Retourne None si nvidia-smi est absent/échoue (pas de GPU visible dans
    ce conteneur, pilote absent...) : l'appelant doit alors refuser de
    lancer l'évaluation plutôt que de deviner une valeur.
    """
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        mib = float(out.stdout.strip().splitlines()[0])
        return mib / 1024
    except Exception:
        logger.exception("nvidia-smi indisponible : impossible de mesurer la VRAM")
        return None


def discover_candidate_names(max_new: int = 15) -> list[str]:
    """Familles à considérer ce mois-ci : la liste curée + les nouveautés du site."""
    names = list(CURATED_FAMILIES)
    try:
        resp = httpx.get(f"{LIBRARY_URL}?sort=newest", timeout=15, follow_redirects=True)
        resp.raise_for_status()
        found = re.findall(r'/library/([a-zA-Z0-9][a-zA-Z0-9._-]*)"', resp.text)
        seen = list(dict.fromkeys(found))[:max_new]
        for name in seen:
            if name not in names:
                names.append(name)
        if not seen:
            logger.warning(
                "Scraping de %s n'a trouvé aucun modèle — la page a peut-être changé "
                "de structure ; on continue avec la seule liste curée.", LIBRARY_URL,
            )
    except Exception:
        logger.exception(
            "Échec de la découverte de nouveaux modèles sur %s — on continue avec "
            "la seule liste curée.", LIBRARY_URL,
        )
    return names


def _manifest_size_bytes(name: str, tag: str) -> int | None:
    try:
        resp = httpx.get(f"{REGISTRY_BASE}/v2/library/{name}/manifests/{tag}", timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        manifest = resp.json()
        layers = manifest.get("layers", [])
        return sum(int(layer.get("size", 0)) for layer in layers)
    except Exception:
        logger.warning("Impossible de lire le manifest de %s:%s", name, tag, exc_info=True)
        return None


def find_best_fitting_tag(name: str, vram_budget_gb: float) -> tuple[str, float] | None:
    """Le plus gros tag connu de `name` qui tient dans le budget, ou None."""
    best: tuple[str, float] | None = None
    for size_tag in CANDIDATE_SIZE_TAGS:
        for tag in (size_tag, f"{size_tag}-instruct", f"{size_tag}-instruct-q4_K_M"):
            size_bytes = _manifest_size_bytes(name, tag)
            if size_bytes is None:
                continue
            size_gb = size_bytes / (1024 ** 3)
            # La VRAM utile en usage reel depasse un peu la taille sur
            # disque (cache KV, buffers d'activation) : marge de 15 % + 0.5 Go.
            estimated_vram_gb = size_gb * 1.15 + 0.5
            if estimated_vram_gb <= vram_budget_gb:
                if best is None or size_gb > best[1]:
                    best = (f"{name}:{tag}", size_gb)
            break  # un tag de cette taille existe, pas besoin des variantes
    return best


def build_candidate_list(vram_budget_gb: float, max_candidates: int) -> list[dict]:
    """[{model: "qwen2.5:14b", disk_size_gb: 9.0}, ...], le plus gros d'abord."""
    candidates: list[dict] = []
    for name in discover_candidate_names():
        result = find_best_fitting_tag(name, vram_budget_gb)
        if result:
            model, size_gb = result
            candidates.append({"model": model, "disk_size_gb": round(size_gb, 2)})
    candidates.sort(key=lambda c: c["disk_size_gb"], reverse=True)
    return candidates[:max_candidates]
