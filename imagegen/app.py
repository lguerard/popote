"""Micro-service de génération d'image, isolé du backend.

Torch + diffusers sont de grosses dépendances avec leur propre runtime CUDA
embarqué : les garder dans un conteneur à part évite tout conflit avec les
roues nvidia-cublas/nvidia-cudnn épinglées pour ctranslate2 (Whisper) côté
backend. Le modèle n'est chargé qu'à la demande puis libéré immédiatement
après chaque génération (voir _generate_sync) : sur un GPU de 10 Go déjà en
grande partie occupé par le modèle Ollama gardé en mémoire 24h, le garder
résident en permanence dépasserait le budget VRAM disponible.
"""

import asyncio
import io
import logging
import os

import torch
from diffusers import AutoPipelineForText2Image
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("imagegen")

MODEL_ID = os.environ.get("IMAGE_GEN_MODEL", "stabilityai/sd-turbo")
REQUESTED_DEVICE = os.environ.get("IMAGE_GEN_DEVICE", "cuda")

app = FastAPI(title="Popote Image Generator")


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str | None = None
    width: int = 512
    height: int = 512


def _load_pipeline(device: str):
    dtype = torch.float16 if device == "cuda" else torch.float32
    kwargs = {"torch_dtype": dtype}
    if device == "cuda":
        kwargs["variant"] = "fp16"
    pipe = AutoPipelineForText2Image.from_pretrained(MODEL_ID, **kwargs)
    return pipe.to(device)


def _generate_sync(req: GenerateRequest) -> bytes:
    device = REQUESTED_DEVICE if (REQUESTED_DEVICE != "cuda" or torch.cuda.is_available()) else "cpu"
    if device != REQUESTED_DEVICE:
        logger.warning("CUDA demandé mais indisponible — bascule sur CPU (très lent).")

    try:
        pipe = _load_pipeline(device)
    except Exception:
        if device != "cuda":
            raise
        # VRAM déjà prise par Ollama, driver absent du conteneur, etc. :
        # repli CPU plutôt que de faire échouer toute la génération.
        logger.exception("Échec du chargement du modèle sur GPU — repli sur CPU.")
        device = "cpu"
        pipe = _load_pipeline(device)

    try:
        # sd-turbo est distillé pour 1-4 pas SANS guidance (guidance_scale=0) :
        # une config classique (20-50 pas, guidance>1) le fait sortir de sa
        # plage d'entraînement et dégrade fortement le résultat.
        steps = 2 if device == "cuda" else 4
        image = pipe(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt,
            num_inference_steps=steps,
            guidance_scale=0.0,
            width=req.width,
            height=req.height,
        ).images[0]
    finally:
        del pipe
        if device == "cuda":
            torch.cuda.empty_cache()

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@app.post("/generate")
async def generate(req: GenerateRequest):
    try:
        image_bytes = await asyncio.to_thread(_generate_sync, req)
    except Exception as e:
        logger.exception("Échec de la génération d'image")
        raise HTTPException(500, f"Échec de la génération d'image : {e}")
    return Response(content=image_bytes, media_type="image/png")


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_ID, "cuda_available": torch.cuda.is_available()}
