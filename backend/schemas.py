import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from config import settings
from password_strength import PasswordPolicy
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

PASSWORD_POLICY = PasswordPolicy.from_names(
    length=8,
    strength=settings.password_strength_threshold,
)


def check_password_strength(password: str) -> None:
    """
    Оценивает сложность пароля по энтропии (password-strength).
    Коэффициент strength нормирован в диапазоне 0..1; порог задаётся
    в настройках и по умолчанию равен 0.4.
    """
    if not password:
        raise ValueError("Пароль не может быть пустым")

    if PASSWORD_POLICY.test(password):
        raise ValueError(
            "Пароль слишком слабый. Используйте более длинный пароль "
            "или добавьте разнообразия."
        )


def validate_username_value(value: str) -> str:
    value = value.strip()
    if not re.match(r"^[a-zA-Z0-9_]+$", value):
        raise ValueError(
            "Имя пользователя может содержать только буквы, цифры и знак подчеркивания"
        )
    return value


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)
    captcha_token: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        return validate_username_value(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        check_password_strength(value)
        return value


class UserRead(BaseModel):
    id: int
    username: str | None = None
    email: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class AccountRead(BaseModel):
    id: int
    username: str | None = None
    email: str
    is_active: bool
    totp_enabled: bool = False
    pending_email: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    captcha_token: str | None = None


class TotpRequired(BaseModel):
    totp_required: Literal[True] = True
    challenge: str


class TotpLoginRequest(BaseModel):
    challenge: str
    code: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead


LoginResponse = Token | TotpRequired


class ChangeUsernameRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return validate_username_value(value)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        check_password_strength(value)
        return value


class ChangeEmailRequest(BaseModel):
    password: str
    new_email: EmailStr


class ConfirmEmailChangeRequest(BaseModel):
    code: str | None = None
    token: str | None = None


class PendingEmailChangeResponse(BaseModel):
    status: Literal["pending"] = "pending"
    email: EmailStr
    expires_in: int
    resend_after: int


ChangeEmailResponse = UserRead | PendingEmailChangeResponse


class TotpSetupRequest(BaseModel):
    password: str


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    qr_data_uri: str


class TotpEnableRequest(BaseModel):
    code: str


class TotpEnableResponse(BaseModel):
    recovery_codes: list[str]


class TotpDisableRequest(BaseModel):
    password: str
    code: str


class TotpStatus(BaseModel):
    totp_enabled: bool


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PendingRegistration(BaseModel):
    status: Literal["pending"] = "pending"
    email: EmailStr
    expires_in: int
    resend_after: int


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str | None = None
    token: str | None = None


class ResendVerificationRequest(BaseModel):
    email: EmailStr
    captcha_token: str | None = None


class VerificationSent(BaseModel):
    status: Literal["sent"] = "sent"
    resend_after: int
    expires_in: int


RegisterResponse = Token | PendingRegistration


class RoomCreate(BaseModel):
    title: str = Field(default="Новая комната", min_length=3, max_length=255)


class RoomRead(BaseModel):
    id: UUID
    title: str
    host_id: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
