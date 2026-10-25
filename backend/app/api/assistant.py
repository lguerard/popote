"""Assistant culinaire : POST /api/assistant/chat, réponse diffusée en NDJSON.

Une ligne JSON par événement (voir services/assistant.py) : facile à lire
avec fetch() et un ReadableStream, y compris dans une WebView Android, là
où EventSource (SSE) ne sait ni faire de POST ni envoyer l'en-tête
Authorization.
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from ..database import AsyncSessionLocal
from ..deps import current_user
from ..models.user import User
from ..services import assistant

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatContext(BaseModel):
    # Recette ouverte à l'écran (« Demander à l'assistant ») : lue côté
    # serveur, seulement si elle appartient au compte.
    recipe_id: uuid.UUID | None = None
    page: str | None = Field(None, max_length=200)


class ChatIn(BaseModel):
    messages: list[ChatMessage]
    context: ChatContext | None = None


BUSY_MESSAGE = (
    "Une réponse est déjà en cours pour ton compte : attends-la ou arrête-la avant "
    "de poser une autre question."
)


@router.post("/chat")
async def chat(data: ChatIn, user: User = Depends(current_user)):
    try:
        messages = assistant.validate_conversation([m.model_dump() for m in data.messages])
    except assistant.RequestTooLarge as exc:
        raise HTTPException(413, str(exc))
    except assistant.InvalidConversation as exc:
        raise HTTPException(422, str(exc))

    token = assistant.locks.acquire(user.id)
    if token is None:
        raise HTTPException(409, BUSY_MESSAGE)

    def release() -> None:
        assistant.locks.release(user.id, token)

    context = data.context or ChatContext()

    async def lines():
        # Session propre au flux : celle de la dépendance get_db est
        # refermée avant que la réponse ne commence.
        try:
            async for event in assistant.run_chat(
                user.id, messages, session_factory=AsyncSessionLocal,
                recipe_id=context.recipe_id, page=context.page,
            ):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            # Arrêt par l'utilisateur (requête annulée) compris.
            release()

    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            # nginx (frontend/nginx.conf) transmettrait sinon la réponse
            # par blocs : plus de rendu mot à mot.
            "X-Accel-Buffering": "no",
        },
        # Filet de sécurité si le flux n'a jamais démarré (client parti).
        background=BackgroundTask(release),
    )
