import asyncio
import base64
import logging

import httpx

from ..config import settings
from .llm_service import NUM_PREDICT_TRANSCRIPTION, build_vision_request, prepare_image

logger = logging.getLogger(__name__)

OCR_PROMPT = (
    "Recopie fidèlement tout le texte visible sur cette image, ligne par ligne. "
    "Si c'est une recette de cuisine, transcris-la intégralement : titre, ingrédients "
    "avec leurs quantités, étapes. S'il n'y a aucun texte, nomme le plat ou l'aliment "
    "montré et décris-le en une phrase. Réponds uniquement avec ce texte, sans commentaire."
)

_OLLAMA_OCR_TIMEOUT_SECONDS = 120


async def extract_text_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Texte d'une image : modèle de vision (Claude ou Ollama), Tesseract en secours.

    Le repli sert quand le modèle ne répond pas, n'accepte pas les images
    (OLLAMA_MODEL texte seul) ou ne renvoie rien : une photo de recette
    reste lisible, moins bien, plutôt que de faire échouer l'import.
    """
    try:
        prepared, prepared_mime = prepare_image(image_bytes, mime_type)
        if settings.use_claude:
            text = await _claude_ocr(prepared, prepared_mime)
        else:
            text = await _ollama_ocr(prepared)
    except Exception:
        logger.warning("Lecture de l'image par l'IA impossible — repli sur Tesseract", exc_info=True)
        text = ""
    if text.strip():
        return text
    return await asyncio.to_thread(_tesseract_ocr, image_bytes)


async def _claude_ocr(image_bytes: bytes, mime_type: str) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.claude_api_key)
    b64 = base64.standard_b64encode(image_bytes).decode()
    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": mime_type, "data": b64},
                },
                {"type": "text", "text": OCR_PROMPT},
            ],
        }],
    )
    return msg.content[0].text


async def _ollama_ocr(image_bytes: bytes) -> str:
    """Transcription par le modèle de vision configuré (OLLAMA_VISION_MODEL)."""
    b64 = base64.standard_b64encode(image_bytes).decode()
    async with httpx.AsyncClient(timeout=_OLLAMA_OCR_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json=build_vision_request(b64, OCR_PROMPT, num_predict=NUM_PREDICT_TRANSCRIPTION),
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


def _tesseract_ocr(image_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(img, lang="fra+eng")
    except Exception as e:
        raise RuntimeError(f"OCR non disponible: {e}. Configurez CLAUDE_API_KEY pour l'OCR par IA.")
