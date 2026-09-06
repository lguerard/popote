import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from ..services.auth_service import MIN_PASSWORD_LENGTH


class SetupRequest(BaseModel):
    """Création du tout premier compte — n'est acceptée que tant qu'aucun
    compte n'existe."""

    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    is_admin: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LoginOut(BaseModel):
    """Le jeton sert à l'application Android (en-tête Bearer). Le navigateur
    reçoit en plus un cookie httpOnly et peut ignorer ce champ."""

    token: str
    user: UserOut


class AuthStatus(BaseModel):
    needs_setup: bool
    user: UserOut | None = None


class ResetLinkOut(BaseModel):
    email: str
    reset_url: str
    expires_at: datetime


class ResetTargetOut(BaseModel):
    valid: bool
    email: str | None = None
