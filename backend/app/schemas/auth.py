import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Volontairement permissif : le but est d'attraper la faute de frappe
# evidente, pas de valider la RFC 5322. Une adresse acceptee ici et
# refusee par un serveur mail ne genera personne, l'e-mail ne sert qu'a
# se connecter.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("Adresse e-mail invalide")
        return value


class RegisterIn(Credentials):
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le nom ne peut pas etre vide")
        return value


class LoginIn(Credentials):
    pass


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
