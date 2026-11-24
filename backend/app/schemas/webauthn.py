import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PasskeyOptionsOut(BaseModel):
    """Debut de ceremonie : options a passer telles quelles au navigateur.

    `challenge_id` revient avec l'appel "finish" et designe sans ambiguite
    le defi qu'il termine.
    """

    options: dict[str, Any]
    challenge_id: uuid.UUID


class StartAuthenticationIn(BaseModel):
    email: str | None = None

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str | None) -> str | None:
        # Meme normalisation que Credentials, sans rejeter une adresse mal
        # formee : une erreur ici dirait ce que le serveur accepte.
        value = (value or "").strip().lower()
        return value or None


class FinishRegistrationIn(BaseModel):
    challenge_id: uuid.UUID
    # Reponse de navigator.credentials.create(), au format JSON de
    # @simplewebauthn/browser, transmise sans retouche a py_webauthn.
    credential: dict[str, Any]
    label: str | None = Field(default=None, max_length=100)

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None


class FinishAuthenticationIn(BaseModel):
    challenge_id: uuid.UUID
    credential: dict[str, Any]


class PasskeyOut(BaseModel):
    id: uuid.UUID
    device_label: str | None
    created_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}
