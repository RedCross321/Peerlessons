import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def check_password_strength(password: str) -> None:
    errors = []

    if len(password) < 8:
        errors.append("минимум 8 символов")
    if not re.search(r"[A-Z]", password):
        errors.append("хотя бы одна заглавная буква")
    if not re.search(r"[a-z]", password):
        errors.append("хотя бы одна строчная буква")
    if not re.search(r"\d", password):
        errors.append("хотя бы одна цифра")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_+=-]', password):
        errors.append("хотя бы один спецсимвол")

    if errors:
        raise ValueError("Пароль слишком простой. Требования: " + "; ".join(errors))


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
    token_type: str = "bearer"
    user: UserRead


class RoomCreate(BaseModel):
    title: str = Field(default="Новая комната", min_length=3, max_length=255)


class RoomRead(BaseModel):
    id: UUID
    title: str
    host_id: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
