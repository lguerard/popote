import base64
import re
import httpx
from ..config import settings


async def extract_text_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Extract text from an image. Uses Claude Vision if key available, else pytesseract."""
    if settings.use_claude:
        return await _claude_ocr(image_bytes, mime_type)
    return await _ollama_ocr(image_bytes, mime_type)


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
                {
                    "type": "text",
                    "text": "Extrais tout le texte visible dans cette image. Si c'est une recette de cuisine, transcris-la intégralement avec les ingrédients et les étapes.",
                },
            ],
        }],
    )
    return msg.content[0].text


async def _ollama_ocr(image_bytes: bytes, mime_type: str) -> str:
    """Use Ollama llava model for vision OCR."""
    b64 = base64.standard_b64encode(image_bytes).decode()
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": "llava",
                    "prompt": "Extrais tout le texte de cette image. Si c'est une recette, transcris les ingrédients et les étapes.",
                    "images": [b64],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception:
            # Fallback: pytesseract
            return _tesseract_ocr(image_bytes)


def _tesseract_ocr(image_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(img, lang="fra+eng")
    except Exception as e:
        raise RuntimeError(f"OCR non disponible: {e}. Configurez CLAUDE_API_KEY pour l'OCR par IA.")
