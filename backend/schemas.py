import re
from datetime import datetime
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


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError(
                "Имя пользователя может содержать только буквы, цифры и знак подчеркивания"
            )
        return v

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


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RoomCreate(BaseModel):
    title: str = Field(default="Новая комната", min_length=3, max_length=255)


class RoomRead(BaseModel):
    id: UUID
    title: str
    host_id: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
